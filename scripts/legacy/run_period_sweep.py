#!/usr/bin/env python3
"""Sweep challenge results across multiple historical periods."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path("results")
SUMMARY_PATH = RESULTS_DIR / "challenge_summary.json"

DEFAULT_PERIODS = [
    ("2021-11-01", "2022-12-31"),
    ("2023-01-01", "2023-12-31"),
    ("2024-01-01", "2024-12-31"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run challenge sims across historical periods."
    )
    parser.add_argument(
        "--entry_mode",
        choices=["H1_ONLY", "M15_WITH_H1_CTX", "HYBRID"],
        default="M15_WITH_H1_CTX",
        help="Entry mode for all periods.",
    )
    parser.add_argument(
        "--firm_profile",
        type=str,
        default="TIGHT_PROP",
        help="Firm profile name.",
    )
    parser.add_argument(
        "--period",
        action="append",
        nargs=2,
        metavar=("START", "END"),
        help="Custom period (start_date end_date). Can be repeated.",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=2000,
        help="Seed step for challenge sim.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "period_sweep_m15.csv",
        help="CSV output path.",
    )
    return parser.parse_args()


def run_period(
    entry_mode: str, firm_profile: str, start: str, end: str, step: int
) -> dict:
    env = os.environ.copy()
    env["OMEGA_ENTRY_MODE"] = entry_mode
    env["OMEGA_FIRM_PROFILE"] = firm_profile
    cmd = [
        sys.executable,
        "scripts/run_challenge_sim.py",
        "--portfolio",
        "--entry_mode",
        entry_mode,
        "--firm_profile",
        firm_profile,
        "--start_date",
        start,
        "--end_date",
        end,
        "--step",
        str(step),
    ]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(SUMMARY_PATH)
    summary = json.loads(SUMMARY_PATH.read_text())
    summary["start_date"] = start
    summary["end_date"] = end
    summary["entry_mode"] = entry_mode
    summary["firm_profile"] = firm_profile
    return summary


def extract_row(summary: dict) -> dict:
    stats = summary.get("return_stats", {})
    mean_trades_per_symbol = summary.get("mean_trades_per_symbol", {})
    return {
        "entry_mode": summary.get("entry_mode"),
        "firm_profile": summary.get("firm_profile"),
        "start_date": summary.get("start_date"),
        "end_date": summary.get("end_date"),
        "pass_rate": summary.get("pass_rate", 0.0),
        "mean_return": stats.get("mean_return", 0.0),
        "median_return": stats.get("median_return", 0.0),
        "max_daily_loss": summary.get("max_daily_loss_fraction", 0.0),
        "max_trailing_dd": summary.get("max_trailing_dd_fraction", 0.0),
        "mean_trades_per_run": summary.get("mean_trades_per_run", 0.0),
        "mean_trades_per_symbol": json.dumps(mean_trades_per_symbol),
    }


def main() -> int:
    args = parse_args()
    periods = args.period or DEFAULT_PERIODS
    rows: list[dict] = []
    for start, end in periods:
        print(f"\n=== Period sweep: {start} to {end} ===")
        summary = run_period(args.entry_mode, args.firm_profile, start, end, args.step)
        rows.append(extract_row(summary))
    df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"\nSaved period sweep to {args.output}")
    print(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
