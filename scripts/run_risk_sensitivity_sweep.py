#!/usr/bin/env python3
"""Evaluate sensitivity of risk knobs for the M15 baseline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from itertools import product
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path("results")
SUMMARY_PATH = RESULTS_DIR / "challenge_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Risk sensitivity sweep for Omega FX.")
    parser.add_argument(
        "--a_scales",
        type=float,
        nargs="+",
        default=[0.6, 0.7, 0.8, 0.9],
        help="A-tier risk scale multipliers.",
    )
    parser.add_argument(
        "--daily_caps",
        type=float,
        nargs="+",
        default=[0.018, 0.02, 0.022],
        help="Internal daily loss fractions to test.",
    )
    parser.add_argument(
        "--max_positions",
        type=int,
        nargs="+",
        default=[1, 2, 3],
        help="Concurrent position limits.",
    )
    parser.add_argument(
        "--entry_mode",
        choices=["H1_ONLY", "M15_WITH_H1_CTX", "HYBRID"],
        default="M15_WITH_H1_CTX",
        help="Entry mode to evaluate.",
    )
    parser.add_argument(
        "--firm_profile",
        type=str,
        default="TIGHT_PROP",
        help="Firm profile name.",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=2000,
        help="Seed spacing for challenge sim.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "risk_sensitivity_m15.csv",
        help="CSV output path.",
    )
    return parser.parse_args()


def run_combo(entry_mode: str, firm_profile: str, a_scale: float, daily_cap: float, max_pos: int, step: int) -> dict:
    env = os.environ.copy()
    env["OMEGA_TIER_SCALE_A"] = str(a_scale)
    env["OMEGA_INTERNAL_MAX_DAILY_LOSS"] = str(daily_cap)
    env["OMEGA_MAX_CONCURRENT_POSITIONS"] = str(max_pos)
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
        "--step",
        str(step),
    ]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(SUMMARY_PATH)
    summary = json.loads(SUMMARY_PATH.read_text())
    summary["a_scale"] = a_scale
    summary["daily_cap"] = daily_cap
    summary["max_positions"] = max_pos
    return summary


def extract_row(summary: dict) -> dict:
    stats = summary.get("return_stats", {})
    return {
        "a_scale": summary.get("a_scale"),
        "daily_cap": summary.get("daily_cap"),
        "max_positions": summary.get("max_positions"),
        "pass_rate": summary.get("pass_rate", 0.0),
        "mean_return": stats.get("mean_return", 0.0),
        "median_return": stats.get("median_return", 0.0),
        "max_daily_loss": summary.get("max_daily_loss_fraction", 0.0),
        "max_trailing_dd": summary.get("max_trailing_dd_fraction", 0.0),
        "mean_trades_per_run": summary.get("mean_trades_per_run", 0.0),
    }


def main() -> int:
    args = parse_args()
    rows: list[dict] = []
    for a_scale, daily_cap, max_pos in product(args.a_scales, args.daily_caps, args.max_positions):
        print(f"\n=== Sensitivity combo: A={a_scale}, daily={daily_cap}, max_pos={max_pos} ===")
        summary = run_combo(args.entry_mode, args.firm_profile, a_scale, daily_cap, max_pos, args.step)
        rows.append(extract_row(summary))
    df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"\nSaved risk sensitivity sweep to {args.output}")
    print(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
