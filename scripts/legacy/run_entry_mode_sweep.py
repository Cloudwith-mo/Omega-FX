#!/usr/bin/env python3
"""Compare entry modes under the FULL risk preset."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ENTRY_MODES = ["H1_ONLY", "M15_WITH_H1_CTX"]
RESULTS_DIR = Path("results")
SUMMARY_PATH = RESULTS_DIR / "challenge_summary.json"
OUTPUT_CSV = RESULTS_DIR / "entry_mode_sweep.csv"


def run_challenge(entry_mode: str) -> dict:
    env = os.environ.copy()
    env["OMEGA_ENTRY_MODE"] = entry_mode
    env.setdefault("OMEGA_RISK_PRESET", "FULL")
    cmd = [
        sys.executable,
        "scripts/run_challenge_sim.py",
        "--portfolio",
        "--step",
        "2000",
        "--entry_mode",
        entry_mode,
    ]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(SUMMARY_PATH)
    with SUMMARY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def extract(entry_mode: str, summary: dict) -> dict:
    mean_trades_per_symbol = summary.get("mean_trades_per_symbol", {})
    return {
        "entry_mode": entry_mode,
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
    for mode in ENTRY_MODES:
        print(f"\n=== Running entry mode: {mode} ===")
        summary = run_challenge(mode)
        rows.append(extract(mode, summary))

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved entry sweep to {OUTPUT_CSV}")
    print(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
