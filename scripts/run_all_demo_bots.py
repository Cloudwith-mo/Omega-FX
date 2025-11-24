#!/usr/bin/env python3
"""Run all demo bots concurrently with isolated logs/summaries."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
RUNNER = REPO_ROOT / "scripts" / "run_demo_autopilot.py"
LOG_DIR = REPO_ROOT / "logs" / "autopilot"

BOTS = [
    {"name": "demo_trend_only", "strategy_id": "demo_trend_only"},
    {"name": "demo_mr_only", "strategy_id": "demo_mr_only"},
    {"name": "demo_session_only", "strategy_id": "demo_session_only"},
    {"name": "demo_trend_mr_london", "strategy_id": "demo_trend_mr_london"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all demo bots concurrently.")
    parser.add_argument("--hours", type=float, default=24.0, help="Session length")
    parser.add_argument("--sleep-seconds", type=float, default=60.0, help="Pause between iterations")
    parser.add_argument("--per-trade-risk-fraction", type=float, default=0.0005)
    parser.add_argument("--daily-loss-fraction", type=float, default=0.03)
    return parser.parse_args()


def build_cmd(bot: dict, args: argparse.Namespace) -> list[str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{bot['name']}.csv"
    summary_path = LOG_DIR / f"{bot['name']}_summary.json"
    cmd = [
        PYTHON,
        str(RUNNER),
        "--strategy-id",
        bot["strategy_id"],
        "--log_path",
        str(log_path),
        "--summary_path",
        str(summary_path),
        "--hours",
        str(args.hours),
        "--sleep-seconds",
        str(args.sleep_seconds),
        "--per_trade_risk_fraction",
        str(args.per_trade_risk_fraction),
        "--daily_loss_fraction",
        str(args.daily_loss_fraction),
    ]
    return cmd


def main() -> int:
    args = parse_args()
    procs: list[subprocess.Popen] = []
    try:
        for bot in BOTS:
            cmd = build_cmd(bot, args)
            print(f"Starting {bot['name']}: {' '.join(cmd)}")
            proc = subprocess.Popen(cmd)
            procs.append(proc)
        for proc in procs:
            proc.wait()
        return 0
    except KeyboardInterrupt:
        print("\nStopping bots...")
        for proc in procs:
            proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
