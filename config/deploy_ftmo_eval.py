"""Deployment presets for FTMO evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import ACCOUNT_PHASE_PROFILES


@dataclass(frozen=True)
class DeploymentPreset:
    trading_firm: str
    account_phase: str
    entry_mode: str
    firm_profile: str
    tier_scales: dict[str, float]
    max_concurrent_positions: int
    description: str = ""


_FTMO_PROFILE = ACCOUNT_PHASE_PROFILES["ftmo"]["EVAL"]
FTMO_EVAL_PRESET = DeploymentPreset(
    trading_firm="ftmo",
    account_phase="EVAL",
    entry_mode=_FTMO_PROFILE.entry_mode,
    firm_profile=_FTMO_PROFILE.firm_profile,
    tier_scales=_FTMO_PROFILE.tier_scales,
    max_concurrent_positions=_FTMO_PROFILE.max_concurrent_positions,
    description="Phase 4 FTMO evaluation preset (M15_WITH_H1_CTX, FULL risk, 2 concurrent positions).",
)
