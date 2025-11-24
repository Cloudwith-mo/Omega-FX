#!/usr/bin/env python3
"""Run all demo bots concurrently with isolated logs/summaries.

Bots configured here:
- demo_trend_only
- demo_mr_only
- demo_session_only
- demo_trend_mr_london

Each bot calls run_demo_autopilot.py with its own log/summary paths.
Stop with Ctrl+C; the script will terminate child processes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
RUNNER = REPO_ROOT / "scripts" / "run_demo_autopilot.py"

# Base options applied to all bots
BASE_ARGS = [
    "--hours",
    "24",
    "--sleep-seconds",
    "60",
    "--per_trade_risk_fraction",
    "0.0005",
    "--daily_loss_fraction",
    "0.03",
]

BOTS = [
    {
        "name": "demo_trend_only",
        "strategy_id": "demo_trend_only",
    },
    {
        "name": "demo_mr_only",
        "strategy_id": "demo_mr_only",
    },
    {
        "name": "demo_session_only",
        "strategy_id": "demo_session_only",
    },
    {
        "name": "demo_trend_mr_london",
        "strategy_id": "demo_trend_mr_london",
    },
]


def build_cmd(bot: dict) -> list[str]:
    log_path = REPO_ROOT / f"results/mt5_demo_exec_log_{bot['name']}.csv"
    summary_path = REPO_ROOT / f"results/mt5_demo_exec_summary_{bot['name']}.json"
    cmd = [
        PYTHON,
        str(RUNNER),
        "--strategy-id",
        bot["strategy_id"],
        "--log_path",
        str(log_path),
        "--summary_path",
        str(summary_path),
    ]
    cmd.extend(BASE_ARGS)
    return cmd


def main() -> int:
    procs: list[subprocess.Popen] = []
    try:
        for bot in BOTS:
            cmd = build_cmd(bot)
            print(f"Starting {bot['name']}: {' '.join(cmd)}")
            proc = subprocess.Popen(cmd)
            procs.append(proc)
        # Wait for all
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
