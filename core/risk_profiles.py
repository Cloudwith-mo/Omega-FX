from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RISK_PROFILE_PATH = Path("config/risk_profiles.yaml")


@dataclass(frozen=True)
class RiskProfile:
    env: str
    tier: str
    per_trade_risk_fraction: float
    daily_loss_fraction: float
    max_positions: int


def load_risk_profile(env: str, tier: str, *, path: Path | None = None) -> RiskProfile:
    """Load a risk profile from the YAML config."""
    config_path = path or DEFAULT_RISK_PROFILE_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Risk profile config not found at {config_path}")
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}

    env_key = (env or "").lower()
    tier_key = (tier or "").lower()
    normalized_envs = {str(k).lower(): v or {} for k, v in raw.items()}
    env_profiles = normalized_envs.get(env_key)
    if not env_profiles:
        raise KeyError(f"Unknown risk profile environment '{env}'")

    limits: dict[str, float | int] = {}
    for limit_key in ("max_per_trade_risk_fraction", "max_daily_loss_fraction", "max_positions"):
        value = env_profiles.get(limit_key)
        if isinstance(value, (int, float)):
            limits[limit_key] = value

    tier_cfg: dict[str, Any] | None = None
    for tier_name, tier_data in env_profiles.items():
        if isinstance(tier_data, dict) and "per_trade_risk_fraction" in tier_data:
            if str(tier_name).lower() == tier_key:
                tier_cfg = tier_data or {}
                break
    if tier_cfg is None:
        raise KeyError(f"Unknown risk tier '{tier}' for env '{env}'")

    per_trade = float(tier_cfg["per_trade_risk_fraction"])
    daily_loss = float(tier_cfg["daily_loss_fraction"])
    max_positions = int(tier_cfg["max_positions"])

    if "max_per_trade_risk_fraction" in limits:
        per_trade = min(per_trade, float(limits["max_per_trade_risk_fraction"]))
    if "max_daily_loss_fraction" in limits:
        daily_loss = min(daily_loss, float(limits["max_daily_loss_fraction"]))
    if "max_positions" in limits:
        max_positions = min(max_positions, int(limits["max_positions"]))

    return RiskProfile(
        env=env_key,
        tier=tier_key,
        per_trade_risk_fraction=per_trade,
        daily_loss_fraction=daily_loss,
        max_positions=max_positions,
    )
