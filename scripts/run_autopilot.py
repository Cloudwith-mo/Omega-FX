#!/usr/bin/env python3
"""Run the Omega FX autopilot using a named bot profile."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adapters.mt5_backend import initialize_mt5_terminal, shutdown_mt5_terminal  # noqa: E402
from core.bot_profiles import BotProfile, list_bot_profiles, load_bot_profile  # noqa: E402
from core.execution_accounts import resolve_account_config  # noqa: E402
from core.risk import RiskMode  # noqa: E402
from scripts import run_live_signals_ftmo as live_signals  # noqa: E402


def parse_args() -> argparse.Namespace:
    bot_choices = list_bot_profiles()
    parser = argparse.ArgumentParser(description="Autopilot entry point backed by bot profiles.")
    parser.add_argument(
        "--bot",
        required=True,
        choices=bot_choices if bot_choices else None,
        help="Bot profile name (e.g. demo_trend_mr_london).",
    )
    parser.add_argument(
        "--account_profile",
        default=None,
        help="Override MT5 account alias (defaults to the bot's mt5_account).",
    )
    parser.add_argument("--symbols", nargs="+", default=None, help="Optional symbol override.")
    parser.add_argument("--account_equity", type=float, default=None, help="Override account equity assumption.")
    parser.add_argument("--firm_profile", type=str, default=None, help="Override firm profile label.")
    parser.add_argument("--output", type=Path, default=None, help="CSV destination for signals.")
    parser.add_argument(
        "--alert_mode",
        choices=["none", "telegram", "slack"],
        default=None,
        help="Optional alert mode override; defaults come from the bot profile.",
    )
    parser.add_argument("--m15-bars", dest="m15_bars", type=int, default=None, help="Bars to fetch for M15.")
    parser.add_argument("--h1-bars", dest="h1_bars", type=int, default=None, help="Bars to fetch for H1.")
    parser.add_argument("--login", type=int, default=None, help="Optional MT5 login override.")
    parser.add_argument("--server", type=str, default=None, help="Optional MT5 server override.")
    parser.add_argument("--password", type=str, default=None, help="Optional MT5 password override.")
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Optional runtime budget in hours; loops until elapsed if provided.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=900,
        help="Polling interval between cycles when --hours is set (defaults to 15 minutes).",
    )
    return parser.parse_args()


def resolve_runtime(profile: BotProfile, args: argparse.Namespace) -> dict:
    metadata = profile.metadata or {}

    def _coerce_number(raw, default):
        if raw is None:
            return default
        try:
            return type(default)(raw)
        except Exception:
            return default

    symbols = args.symbols or profile.symbols or metadata.get("symbols") or ["EURUSD", "GBPUSD", "USDJPY"]
    account_equity = _coerce_number(args.account_equity, metadata.get("account_equity", 100_000.0))
    firm_label = str(args.firm_profile or profile.firm_profile).upper()
    alert_mode = str(args.alert_mode or metadata.get("alert_mode") or "none").lower()
    m15_bars = _coerce_number(args.m15_bars, metadata.get("m15_bars", 500))
    h1_bars = _coerce_number(args.h1_bars, metadata.get("h1_bars", 500))
    output = args.output or Path(f"results/autopilot_{profile.bot_id}_signals.csv")
    return {
        "symbols": symbols,
        "account_equity": float(account_equity),
        "firm_label": firm_label,
        "alert_mode": alert_mode,
        "m15_bars": int(m15_bars),
        "h1_bars": int(h1_bars),
        "output_path": output,
        "strategies": profile.strategies,
        "risk_tier": profile.risk_tier,
        "risk_mode": _risk_mode_from_tier(profile.risk_tier),
    }


def describe(profile: BotProfile, runtime: dict, account_alias: str) -> None:
    print(
        f"[BOT] {profile.bot_id} env={profile.env} firm={profile.firm_profile} "
        f"tier={profile.risk_tier} account={account_alias}"
    )
    if profile.strategies:
        strategy_blurbs = ", ".join(
            f"{s.id} (x{s.risk_scale}{'' if s.enabled else ' disabled'})" for s in profile.strategies
        )
        print(f"[BOT] strategies: {strategy_blurbs}")
    print(
        f"[BOT] symbols={runtime['symbols']} equity={runtime['account_equity']:.2f} "
        f"alert_mode={runtime['alert_mode']}"
    )


def _risk_mode_from_tier(tier: str) -> RiskMode:
    tier_key = (tier or "").lower()
    if tier_key == "aggressive":
        return RiskMode.CONSERVATIVE
    if tier_key == "normal":
        return RiskMode.ULTRA_CONSERVATIVE
    return RiskMode.ULTRA_ULTRA_CONSERVATIVE


def main() -> int:
    args = parse_args()
    profile = load_bot_profile(args.bot)
    account_alias = args.account_profile or profile.mt5_account
    account = resolve_account_config(
        account_alias,
        login=args.login,
        password=args.password,
        server=args.server,
    )
    runtime = resolve_runtime(profile, args)
    describe(profile, runtime, account_alias)

    initialize_mt5_terminal(account)
    end_time = time.time() + args.hours * 3600 if args.hours else None
    try:
        while True:
            symbol_map = live_signals.build_symbol_data(runtime["symbols"], runtime["m15_bars"], runtime["h1_bars"])
            symbol_sets = live_signals._build_symbol_frame_sets(  # type: ignore[attr-defined]
                live_signals.FTMO_EVAL_PRESET.entry_mode,
                live_signals.DEFAULT_BREAKOUT_CONFIG,
                df=None,
                data_source=None,
                symbol_data_map=symbol_map,
                symbols_config=None,
            )
            signals = live_signals.evaluate_signals(
                symbol_sets,
                account_equity=runtime["account_equity"],
                firm_label=runtime["firm_label"],
                risk_mode=runtime["risk_mode"],
            )
            live_signals.append_signals(runtime["output_path"], signals)
            live_signals.emit_alerts(signals, runtime["alert_mode"])

            if end_time is None:
                break
            if time.time() >= end_time:
                break
            time.sleep(max(1, args.interval_seconds))
    finally:
        shutdown_mt5_terminal()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
