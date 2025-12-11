#!/usr/bin/env python3
"""Print risk rails per bot (per-trade, daily, total loss, execution limits)."""

from __future__ import annotations

import yaml

from core.bot_profiles import list_bot_profiles, load_bot_profile
from core.execution_accounts import resolve_account_config
from core.risk import RISK_PROFILES, RiskMode
from config.settings import resolve_firm_profile

EXEC_LIMITS_PATH = "config/execution_limits.yaml"


def load_execution_limits() -> dict:
    try:
        with open(EXEC_LIMITS_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def resolve_limits(bot_id: str, limits_data: dict) -> tuple[int | None, int | None]:
    defaults = limits_data.get("defaults", {})
    bot_limits = limits_data.get("bots", {}).get(bot_id, {})
    max_trades = bot_limits.get("max_trades_per_day", defaults.get("max_trades_per_day"))
    min_hold = bot_limits.get("min_hold_seconds", defaults.get("min_hold_seconds"))
    return max_trades, min_hold


def tier_to_mode(tier: str) -> RiskMode:
    key = (tier or "").lower()
    if key == "aggressive":
        return RiskMode.CONSERVATIVE
    if key == "normal":
        return RiskMode.ULTRA_CONSERVATIVE
    return RiskMode.ULTRA_ULTRA_CONSERVATIVE


def main() -> int:
    limits = load_execution_limits()
    for bot_id in list_bot_profiles():
        profile = load_bot_profile(bot_id)
        account = resolve_account_config(profile.mt5_account)
        risk_mode = tier_to_mode(profile.risk_tier)
        rp = RISK_PROFILES[risk_mode]
        firm = resolve_firm_profile(profile.firm_profile)
        max_trades, min_hold = resolve_limits(bot_id, limits)
        print(
            f"{bot_id}: account={profile.mt5_account} firm={profile.firm_profile} tier={profile.risk_tier} "
            f"per_trade={rp.risk_per_trade_fraction*100:.2f}% "
            f"daily_limit={rp.daily_loss_limit_fraction*100:.2f}% "
            f"total_limit={firm.prop_max_total_loss_fraction*100:.2f}% "
            f"prop_daily_cap={firm.prop_max_daily_loss_fraction*100:.2f}%"
        )
        if max_trades is not None or min_hold is not None:
            print(f"  execution_limits: max_trades_per_day={max_trades} min_hold_seconds={min_hold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
