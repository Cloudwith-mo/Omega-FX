#!/usr/bin/env python3
"""Continuous MT5 demo execution loop with tiny risk."""

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

from scripts import run_exec_mt5_demo_from_signals as exec_loop  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MT5 demo execution loop continuously.")
    parser.add_argument("--hours", type=float, default=4.0, help="Total session duration.")
    parser.add_argument("--sleep-seconds", type=float, default=60.0, help="Pause between iterations.")
    parser.add_argument("--account_profile", type=str, default="METAQUOTES_DEMO")
    parser.add_argument("--starting_equity", type=float, default=100_000.0)
    parser.add_argument("--max_positions", type=int, default=6)
    parser.add_argument("--per_trade_risk_fraction", type=float, default=0.0005)
    parser.add_argument("--daily_loss_fraction", type=float, default=0.01)
    parser.add_argument("--risk_fraction", type=float, default=0.1, help="Extra multiplier on firm risk fraction.")
    parser.add_argument("--limit_trades", type=int, default=25, help="Trades to process per iteration.")
    parser.add_argument("--summary_path", type=Path, default=Path("results/mt5_demo_exec_live_summary.json"))
    parser.add_argument("--log_path", type=Path, default=Path("results/mt5_demo_exec_log.csv"))
    parser.add_argument("--login", type=int, default=None)
    parser.add_argument("--server", type=str, default=None)
    parser.add_argument("--password", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    deadline = time.monotonic() + max(args.hours, 0.0) * 3600
    iteration = 0
    while True:
        now = time.monotonic()
        if iteration > 0 and now >= deadline:
            break
        iteration += 1
        exec_args = Namespace(
            starting_equity=args.starting_equity,
            dry_run=False,
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
        )
        try:
            summary = exec_loop.run_exec_once(exec_args)
            pnl = summary.get("final_equity", 0.0) - summary.get("initial_equity", 0.0)
            print(
                f"[Autopilot] iteration {iteration} "
                f"trades={summary.get('number_of_trades', 0)} "
                f"pnl={pnl:.2f} "
                f"filters="
                f"{json.dumps({k: summary.get(k, 0) for k in ['filtered_max_positions', 'filtered_daily_loss', 'filtered_invalid_stops']})}"
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
