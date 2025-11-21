#!/usr/bin/env python3
"""Continuous MT5 demo execution loop with tiered risk."""

from __future__ import annotations

import argparse
import json
import sys
import time
from argparse import Namespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - CLI runner
    sys.path.insert(0, str(REPO_ROOT))

from core.constants import DEFAULT_STRATEGY_ID  # noqa: E402
from core.risk_profiles import load_risk_profile  # noqa: E402
from core.session import generate_session_id  # noqa: E402
from scripts import run_exec_mt5_demo_from_signals as exec_loop  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the MT5 demo execution loop continuously."
    )
    parser.add_argument(
        "--hours", type=float, default=4.0, help="Total session duration."
    )
    parser.add_argument(
        "--sleep-seconds", type=float, default=60.0, help="Pause between iterations."
    )
    parser.add_argument("--account_profile", type=str, default="METAQUOTES_DEMO")
    parser.add_argument("--starting_equity", type=float, default=100_000.0)
    parser.add_argument("--max_positions", type=int, default=6)
    parser.add_argument("--per_trade_risk_fraction", type=float, default=0.0005)
    parser.add_argument("--daily_loss_fraction", type=float, default=0.01)
    parser.add_argument(
        "--risk_fraction",
        type=float,
        default=0.1,
        help="Extra multiplier on firm risk fraction.",
    )
    parser.add_argument(
        "--limit_trades", type=int, default=25, help="Trades to process per iteration."
    )
    parser.add_argument(
        "--summary_path",
        type=Path,
        default=Path("results/mt5_demo_exec_live_summary.json"),
    )
    parser.add_argument(
        "--log_path", type=Path, default=Path("results/mt5_demo_exec_log.csv")
    )
    parser.add_argument("--login", type=int, default=None)
    parser.add_argument("--server", type=str, default=None)
    parser.add_argument("--password", type=str, default=None)
    parser.add_argument(
        "--risk_tier",
        type=str,
        default=None,
        help="Named risk tier (e.g. conservative).",
    )
    parser.add_argument(
        "--risk_env", type=str, default="demo", help="Risk profile environment key."
    )
    parser.add_argument(
        "--confirm_live",
        action="store_true",
        help="Required acknowledgement when --risk_env live is used.",
    )
    parser.add_argument(
        "--strategy-id",
        type=str,
        default=DEFAULT_STRATEGY_ID,
        help="Strategy identifier for this session.",
    )
    parser.add_argument(
        "--enable-mean-reversion",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Toggle the Omega MR strategy inside the demo loop.",
    )
    parser.add_argument(
        "--mr-risk-scale",
        type=float,
        default=0.5,
        help="Relative risk scale for MR trades.",
    )
    parser.add_argument(
        "--enable-session-momentum",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Toggle the London session strategy inside the demo loop.",
    )
    parser.add_argument(
        "--session-risk-scale",
        type=float,
        default=0.25,
        help="Relative risk scale for session trades.",
    )
    parser.add_argument(
        "--dry_run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Force dry-run mode.",
    )
    return parser.parse_args()


def _resolve_risk_tier(args: argparse.Namespace) -> str:
    if not args.risk_tier:
        return "custom"
    profile = load_risk_profile(args.risk_env, args.risk_tier)
    args.max_positions = profile.max_positions
    args.per_trade_risk_fraction = profile.per_trade_risk_fraction
    args.daily_loss_fraction = profile.daily_loss_fraction
    print(
        f"[Autopilot] Using risk tier '{profile.tier}' ({profile.env}) "
        f"per_trade={profile.per_trade_risk_fraction}, daily_loss={profile.daily_loss_fraction}, "
        f"max_positions={profile.max_positions}"
    )
    return profile.tier


def main() -> int:
    args = parse_args()
    args.risk_env = (args.risk_env or "demo").lower()
    if args.risk_env == "live" and not args.confirm_live:
        print("Refusing to run in live environment without --confirm_live.")
        return 1
    selected_risk_tier = _resolve_risk_tier(args)
    session_id = generate_session_id(args.risk_env, selected_risk_tier)
    print(f"[Autopilot] Session ID {session_id}")
    deadline = time.monotonic() + max(args.hours, 0.0) * 3600
    iteration = 0
    session_start_equity: float | None = None
    session_start_balance: float | None = None
    while True:
        now = time.monotonic()
        if iteration > 0 and now >= deadline:
            break
        iteration += 1
        exec_args = Namespace(
            starting_equity=args.starting_equity,
            dry_run=args.dry_run,
            account_profile=args.account_profile,
            max_positions=args.max_positions,
            per_trade_risk_fraction=args.per_trade_risk_fraction,
            daily_loss_fraction=args.daily_loss_fraction,
            risk_fraction=args.risk_fraction,
            summary_path=args.summary_path,
            log_path=args.log_path,
            limit_trades=args.limit_trades,
            login=args.login,
            server=args.server,
            password=args.password,
            session_id=session_id,
            risk_env=args.risk_env,
            risk_tier=selected_risk_tier,
            strategy_id=args.strategy_id,
            enable_mean_reversion=args.enable_mean_reversion,
            mr_risk_scale=args.mr_risk_scale,
            enable_session_momentum=args.enable_session_momentum,
            session_risk_scale=args.session_risk_scale,
        )
        try:
            summary = exec_loop.run_exec_once(exec_args)
            if session_start_equity is None:
                session_start_equity = float(
                    summary.get("session_start_equity")
                    or summary.get("initial_equity")
                    or args.starting_equity
                    or 0.0
                )
            if session_start_balance is None:
                session_start_balance = float(
                    summary.get("starting_balance")
                    or summary.get("session_start_balance")
                    or session_start_equity
                )
            session_end_equity = float(
                summary.get("session_end_equity")
                or summary.get("final_equity")
                or session_start_equity
            )
            session_end_balance = float(
                summary.get("ending_balance")
                or summary.get("session_end_balance")
                or session_start_balance
            )
            summary["session_start_equity"] = session_start_equity
            summary["session_end_equity"] = session_end_equity
            summary["session_pnl"] = session_end_equity - session_start_equity
            summary["starting_balance"] = session_start_balance
            summary["ending_balance"] = session_end_balance
            summary["session_start_balance"] = session_start_balance
            summary["session_end_balance"] = session_end_balance
            summary["session_balance_pnl"] = session_end_balance - session_start_balance
            summary["risk_tier"] = selected_risk_tier
            summary["risk_env"] = args.risk_env
            summary["session_id"] = session_id
            summary["strategy_id"] = args.strategy_id
            args.summary_path.parent.mkdir(parents=True, exist_ok=True)
            args.summary_path.write_text(json.dumps(summary, indent=2))
            pnl = summary.get("final_equity", 0.0) - summary.get("initial_equity", 0.0)
            per_strategy = summary.get("per_strategy") or {}
            strategy_parts = [
                f"{sid}={int((entry or {}).get('trades', 0))}"
                for sid, entry in sorted(per_strategy.items())
            ]
            strategies_display = ", ".join(strategy_parts) if strategy_parts else "none"
            session_pnl_value = summary.get("session_pnl")
            session_text = (
                f" session_pnl={session_pnl_value:+.2f}"
                if session_pnl_value is not None
                else ""
            )
            print(
                f"[Autopilot] iteration {iteration} "
                f"trades={summary.get('number_of_trades', 0)} "
                f"pnl={pnl:.2f} "
                f"env={args.risk_env} tier={selected_risk_tier} strategy={args.strategy_id} "
                f"strategies={strategies_display}{session_text} "
                f"filters="
                f"{json.dumps({k: summary.get(k, 0) for k in ['filtered_max_positions', 'filtered_daily_loss', 'filtered_invalid_stops']})} "
                f"reasons={json.dumps(summary.get('signal_reason_counts', {}))}"
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"[Autopilot] iteration {iteration} failed: {exc}")
        if time.monotonic() >= deadline:
            break
        sleep_for = min(args.sleep_seconds, max(0.0, deadline - time.monotonic()))
        if sleep_for > 0:
            time.sleep(sleep_for)
    print("Autopilot session complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
