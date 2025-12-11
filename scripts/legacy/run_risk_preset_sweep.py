#!/usr/bin/env python3
"""Run portfolio challenge sims across configured risk presets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

PRESETS = ["FULL", "A_ONLY", "A_PLUS_UNKNOWN"]
RESULTS_DIR = Path("results")
SUMMARY_PATH = RESULTS_DIR / "challenge_summary.json"
OUTPUT_CSV = RESULTS_DIR / "risk_profile_sweep.csv"


def run_challenge_sim(preset: str) -> dict:
    env = os.environ.copy()
    env["OMEGA_RISK_PRESET"] = preset
    env.setdefault("OMEGA_ENTRY_MODE", "H1_ONLY")
    cmd = [
        sys.executable,
        "scripts/run_challenge_sim.py",
        "--portfolio",
        "--step",
        "2000",
    ]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"Challenge summary not found at {SUMMARY_PATH}")
    with SUMMARY_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data


def extract_row(preset: str, summary: dict) -> dict:
    mean_trades_per_symbol = summary.get("mean_trades_per_symbol", {})
    return {
        "risk_preset": preset,
        "pass_rate": summary.get("pass_rate", 0.0),
        "mean_return": summary.get("return_stats", {}).get("mean_return", 0.0),
        "median_return": summary.get("return_stats", {}).get("median_return", 0.0),
        "p10_return": summary.get("return_stats", {}).get("p10_return", 0.0),
        "p90_return": summary.get("return_stats", {}).get("p90_return", 0.0),
        "max_daily_loss": summary.get("max_daily_loss_fraction", 0.0),
        "max_trailing_dd": summary.get("max_trailing_dd_fraction", 0.0),
        "mean_trades_per_run": summary.get("mean_trades_per_run", 0.0),
        "mean_trades_per_symbol": json.dumps(mean_trades_per_symbol),
    }


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for preset in PRESETS:
        print(f"\n=== Running risk preset: {preset} ===")
        summary = run_challenge_sim(preset)
        rows.append(extract_row(preset, summary))

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved sweep summary to {OUTPUT_CSV}")
    print(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
