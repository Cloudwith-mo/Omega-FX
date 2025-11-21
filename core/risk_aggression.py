"""Risk aggression filtering with tier-based risk scaling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config.settings import (
    ENABLE_RISK_AGGRESSION_FILTER,
    RISK_AGGRESSION_A_EXPECTANCY,
    RISK_AGGRESSION_B_EXPECTANCY,
    RISK_AGGRESSION_MAP_PATH,
    RISK_AGGRESSION_MIN_TRADES,
    RISK_PROFILE_PRESET,
)
from core.risk import RiskMode

EDGE_MAP_PATH = Path("results/trade_edge_map.csv")
OVERRIDE_PATH = Path(RISK_AGGRESSION_MAP_PATH)

Combo = tuple[str | None, str | None, str | None, str | None]

RISK_PROFILE_PRESETS = {
    "FULL": {"A": 1.5, "B": 0.75, "UNKNOWN": 0.5, "C": 0.0},
    "A_ONLY": {"A": 1.5, "B": 0.0, "UNKNOWN": 0.25, "C": 0.0},
    "A_PLUS_UNKNOWN": {"A": 1.5, "B": 0.25, "UNKNOWN": 0.25, "C": 0.0},
}

TIER_SCALE_DEFAULTS = RISK_PROFILE_PRESETS["FULL"].copy()

CUSTOM_TIER_SCALES: dict[str, float] | None = None
_combo_cache: dict | None = None


def set_custom_tier_scales(scales: dict[str, float] | None) -> None:
    global CUSTOM_TIER_SCALES, _combo_cache
    CUSTOM_TIER_SCALES = scales.copy() if scales else None
    _combo_cache = None


def _current_preset_name() -> str:
    env_preset = os.environ.get("OMEGA_RISK_PRESET")
    default = (RISK_PROFILE_PRESET or "FULL").upper()
    preset = (env_preset or default).upper()
    if preset not in RISK_PROFILE_PRESETS:
        return "FULL"
    return preset


def _resolve_scales() -> dict[str, float]:
    base = RISK_PROFILE_PRESETS[_current_preset_name()].copy()
    env_a = os.environ.get("OMEGA_TIER_SCALE_A")
    env_b = os.environ.get("OMEGA_TIER_SCALE_B")
    env_unknown = os.environ.get("OMEGA_TIER_SCALE_UNKNOWN")
    if env_a:
        base["A"] = float(env_a)
    if env_b:
        base["B"] = float(env_b)
    if env_unknown:
        base["UNKNOWN"] = float(env_unknown)
    if CUSTOM_TIER_SCALES:
        base.update(CUSTOM_TIER_SCALES)
    return base


@dataclass(frozen=True)
class ComboTier:
    tier: str
    risk_scale: float


@dataclass
class RiskAggressionResult:
    allowed: bool
    risk_scale: float
    tier: str
    reason: str | None = None


def _normalize_value(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _combo_from_row(row: pd.Series) -> Combo:
    return (
        _normalize_value(row.get("session_tag")),
        _normalize_value(row.get("trend_regime")),
        _normalize_value(row.get("volatility_regime")),
        _normalize_value(row.get("pattern_tag")),
    )


def _load_edge_map() -> dict[Combo, ComboTier]:
    tier_scales = _resolve_scales()
    combo_map: dict[Combo, ComboTier] = {}
    if not EDGE_MAP_PATH.exists():
        return combo_map
    try:
        df = pd.read_csv(EDGE_MAP_PATH)
    except Exception:
        return combo_map

    for _, row in df.iterrows():
        trades = row.get("n_trades")
        expectancy = row.get("expectancy")
        if pd.isna(trades) or pd.isna(expectancy):
            continue
        trades = float(trades)
        expectancy = float(expectancy)
        if trades < RISK_AGGRESSION_MIN_TRADES:
            continue

        tier: str | None = None
        if expectancy >= RISK_AGGRESSION_A_EXPECTANCY:
            tier = "A"
        elif expectancy >= RISK_AGGRESSION_B_EXPECTANCY:
            tier = "B"
        elif expectancy < 0:
            tier = "C"

        if not tier:
            continue

        combo = _combo_from_row(row)
        combo_map[combo] = ComboTier(tier=tier, risk_scale=tier_scales[tier])
    return combo_map


def _load_override_map() -> dict[Combo, ComboTier]:
    combo_map: dict[Combo, ComboTier] = {}
    if not OVERRIDE_PATH.exists():
        return combo_map
    try:
        df = pd.read_csv(OVERRIDE_PATH)
    except Exception:
        return combo_map

    for _, row in df.iterrows():
        tier_value = _normalize_value(row.get("tier"))
        if not tier_value:
            continue
        tier_value = tier_value.upper()
        tier_scales = _resolve_scales()
        if tier_value not in tier_scales:
            continue
        combo = _combo_from_row(row)
        if combo == (None, None, None, None):
            continue
        scale_value = row.get("risk_scale")
        if pd.isna(scale_value):
            scale = tier_scales[tier_value]
        else:
            try:
                scale = float(scale_value)
            except (TypeError, ValueError):
                scale = tier_scales[tier_value]
        combo_map[combo] = ComboTier(tier=tier_value, risk_scale=scale)
    return combo_map


def _build_combo_map() -> dict[Combo, ComboTier]:
    combo_map = _load_edge_map()
    overrides = _load_override_map()
    combo_map.update(overrides)
    return combo_map


def _get_combo_tiers() -> dict[Combo, ComboTier]:
    global _combo_cache
    if _combo_cache is None:
        _combo_cache = _build_combo_map()
    return _combo_cache


def _resolve_combo(tags: Combo) -> ComboTier:
    combo_map = _get_combo_tiers()
    tier_info = combo_map.get(tags)
    if tier_info:
        return tier_info
    return ComboTier(tier="UNKNOWN", risk_scale=TIER_SCALE_DEFAULTS["UNKNOWN"])


def should_allow_risk_aggression(
    tags: Combo,
    current_mode: RiskMode,
) -> RiskAggressionResult:
    if not ENABLE_RISK_AGGRESSION_FILTER:
        return RiskAggressionResult(True, 1.0, tier="UNFILTERED")

    tier_info = _resolve_combo(tags)
    if tier_info.tier == "C" or tier_info.risk_scale <= 0:
        return RiskAggressionResult(False, 0.0, tier="C", reason="risk_aggression")
    return RiskAggressionResult(True, tier_info.risk_scale, tier=tier_info.tier)
