#!/usr/bin/env python3
"""Sweep challenge horizons for the M15 baseline."""

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
FIRM_PROFILES = ["TIGHT_PROP", "LOOSE_PROP"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run challenge sims across multiple horizons.")
    parser.add_argument(
        "--entry_mode",
        choices=["H1_ONLY", "M15_WITH_H1_CTX", "HYBRID"],
        default="H1_ONLY",
        help="Entry mode passed to run_challenge_sim.py",
    )
    parser.add_argument(
        "--risk_preset",
        type=str,
        default="FULL",
        help="Risk preset (OMEGA_RISK_PRESET env override).",
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[10, 15, 20],
        help="Trading-day horizons to evaluate.",
    )
    parser.add_argument(
        "--firm_profiles",
        type=str,
        nargs="+",
        default=FIRM_PROFILES,
        help="Firm profiles to test (default: %(default)s).",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=2000,
        help="Seed spacing for run_challenge_sim.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "timeboxed_pass_stats.csv",
        help="CSV destination for sweep metrics.",
    )
    return parser.parse_args()


def run_for_horizon(horizon: int, entry_mode: str, firm_profile: str, risk_preset: str, step: int) -> dict:
    env = os.environ.copy()
    env["OMEGA_RISK_PRESET"] = risk_preset
    env["OMEGA_ENTRY_MODE"] = entry_mode
    env["OMEGA_FIRM_PROFILE"] = firm_profile
    cmd = [
        sys.executable,
        "scripts/run_challenge_sim.py",
        "--portfolio",
        "--step",
        str(step),
        "--entry_mode",
        entry_mode,
        "--firm_profile",
        firm_profile,
        "--max_trading_days",
        str(horizon),
    ]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(SUMMARY_PATH)
    with SUMMARY_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    data["horizon"] = horizon
    data["firm_profile"] = firm_profile
    data["entry_mode"] = entry_mode
    return data


def extract_row(summary: dict) -> dict:
    stats = summary.get("return_stats", {})
    mean_trades_per_symbol = summary.get("mean_trades_per_symbol", {})
    return {
        "entry_mode": summary.get("entry_mode"),
        "firm_profile": summary.get("firm_profile"),
        "horizon": summary["horizon"],
        "pass_rate": summary.get("pass_rate", 0.0),
        "mean_return": stats.get("mean_return", 0.0),
        "median_return": stats.get("median_return", 0.0),
        "p10_return": stats.get("p10_return", 0.0),
        "p90_return": stats.get("p90_return", 0.0),
        "max_daily_loss": summary.get("max_daily_loss_fraction", 0.0),
        "max_trailing_dd": summary.get("max_trailing_dd_fraction", 0.0),
        "mean_trades_per_run": summary.get("mean_trades_per_run", 0.0),
        "mean_trades_per_symbol": json.dumps(mean_trades_per_symbol),
    }


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for firm in args.firm_profiles:
        for horizon in args.horizons:
            print(f"\n=== Timeboxed sweep: horizon={horizon} days, firm={firm} ===")
            summary = run_for_horizon(horizon, args.entry_mode, firm, args.risk_preset.upper(), args.step)
            rows.append(extract_row(summary))
    df = pd.DataFrame(rows).sort_values(["firm_profile", "horizon"])
    df.to_csv(args.output, index=False)
    print(f"\nSaved horizon sweep to {args.output}")
    print(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
