"""Loader for bot profile YAML definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class StrategyProfile:
    id: str
    risk_scale: float = 1.0
    enabled: bool = True


@dataclass(frozen=True)
class BotProfile:
    bot_id: str
    env: str
    mt5_account: str
    firm_profile: str
    strategies: List[StrategyProfile]
    symbols: List[str]
    risk_tier: str
    metadata: Dict[str, Any]

    @property
    def strategy_risk_map(self) -> Dict[str, float]:
        return {strategy.id: strategy.risk_scale for strategy in self.strategies if strategy.enabled}


def list_bot_profiles(base_dir: Path | str = Path("bots")) -> list[str]:
    return sorted(path.stem for path in Path(base_dir).glob("*.yaml"))


def load_bot_profile(name: str, base_dir: Path | str = Path("bots")) -> BotProfile:
    path = Path(base_dir) / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Bot profile '{name}' not found at {path}")
    data = yaml.safe_load(path.read_text()) or {}

    env = str(data.get("env") or "demo")
    bot_id = str(data.get("bot_id") or name).strip()
    mt5_account = str(data.get("mt5_account") or "").strip()
    if not mt5_account:
        raise ValueError(f"Bot profile '{name}' is missing an mt5_account alias.")
    firm_profile = str(data.get("firm_profile") or "FTMO_CHALLENGE").strip()
    risk_tier = str(data.get("risk_tier") or "default").strip()

    symbols_raw = data.get("symbols") or []
    if not isinstance(symbols_raw, list) or not symbols_raw:
        raise ValueError(f"Bot profile '{name}' symbols must be a non-empty list.")
    symbols = [str(sym).upper() for sym in symbols_raw]

    strategies_raw = data.get("strategies") or []
    if not isinstance(strategies_raw, list):
        raise ValueError(f"Bot profile '{name}' strategies must be a list.")
    strategies = [_strategy_from_dict(item, name) for item in strategies_raw]

    metadata = {
        k: v
        for k, v in data.items()
        if k
        not in {
            "env",
            "mt5_account",
            "firm_profile",
            "strategies",
            "symbols",
            "bot_id",
            "risk_tier",
        }
    }
    return BotProfile(
        bot_id=bot_id or name,
        env=env,
        mt5_account=mt5_account,
        firm_profile=firm_profile,
        strategies=strategies,
        symbols=symbols,
        risk_tier=risk_tier,
        metadata=metadata,
    )


def _strategy_from_dict(payload: dict, bot_name: str) -> StrategyProfile:
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid strategy entry in bot '{bot_name}': {payload}")
    strategy_id = str(payload.get("id") or payload.get("name") or "").strip()
    if not strategy_id:
        raise ValueError(f"Bot '{bot_name}' has a strategy without an id.")
    risk_scale_raw = payload.get("risk_scale", 1.0)
    try:
        risk_scale = float(risk_scale_raw)
    except (TypeError, ValueError):
        raise ValueError(f"Bot '{bot_name}' strategy '{strategy_id}' has invalid risk_scale {risk_scale_raw}")
    enabled = bool(payload.get("enabled", True))
    return StrategyProfile(id=strategy_id, risk_scale=risk_scale, enabled=enabled)
