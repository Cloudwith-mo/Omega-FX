#!/usr/bin/env python3
"""Run the minimal FTMO evaluation preset (M15_WITH_H1_CTX, FULL risk, 2 positions)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.deploy_ftmo_eval import FTMO_EVAL_PRESET  # noqa: E402

RESULTS_DIR = Path("results")
SUMMARY_PATH = RESULTS_DIR / "challenge_summary.json"
RUNS_PATH = RESULTS_DIR / "challenge_runs.csv"
OUTPUT_SUMMARY = RESULTS_DIR / "minimal_ftmo_eval_summary.json"
OUTPUT_RUNS = RESULTS_DIR / "minimal_ftmo_eval_runs.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute the minimal FTMO eval preset.")
    parser.add_argument("--step", type=int, default=10000, help="Seed spacing for challenge simulations.")
    parser.add_argument(
        "--max_trading_days",
        type=int,
        default=None,
        help="Optional time-box (defaults to config ChallengeConfig).",
    )
    return parser.parse_args()


def run_minimal(step: int, max_days: int | None) -> dict:
    env = os.environ.copy()
    env["OMEGA_ENTRY_MODE"] = FTMO_EVAL_PRESET.entry_mode
    env["OMEGA_FIRM_PROFILE"] = FTMO_EVAL_PRESET.firm_profile
    env["OMEGA_MAX_CONCURRENT_POSITIONS"] = str(FTMO_EVAL_PRESET.max_concurrent_positions)
    env["OMEGA_TIER_SCALE_A"] = str(FTMO_EVAL_PRESET.tier_scales.get("A", 1.5))
    env["OMEGA_TIER_SCALE_B"] = str(FTMO_EVAL_PRESET.tier_scales.get("B", 0.75))
    env["OMEGA_TIER_SCALE_UNKNOWN"] = str(FTMO_EVAL_PRESET.tier_scales.get("UNKNOWN", 0.5))
    env.setdefault("OMEGA_RISK_PRESET", "FULL")
    cmd = [
        sys.executable,
        "scripts/run_challenge_sim.py",
        "--portfolio",
        "--entry_mode",
        FTMO_EVAL_PRESET.entry_mode,
        "--firm_profile",
        FTMO_EVAL_PRESET.firm_profile,
        "--trading_firm",
        FTMO_EVAL_PRESET.trading_firm,
        "--account_phase",
        FTMO_EVAL_PRESET.account_phase,
        "--step",
        str(step),
    ]
    if max_days is not None:
        cmd += ["--max_trading_days", str(max_days)]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(SUMMARY_PATH)
    with SUMMARY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def summarize(summary: dict) -> dict:
    stats = summary.get("return_stats", {})
    return {
        "pass_rate": summary.get("pass_rate"),
        "mean_return": stats.get("mean_return"),
        "median_return": stats.get("median_return"),
        "max_daily_loss": summary.get("max_daily_loss_fraction"),
        "max_trailing_dd": summary.get("max_trailing_dd_fraction"),
        "mean_trades_per_run": summary.get("mean_trades_per_run"),
        "mean_trades_per_symbol": summary.get("mean_trades_per_symbol"),
        "runs": summary.get("num_runs"),
        "step": summary.get("step"),
    }


def main() -> int:
    args = parse_args()
    raw_summary = run_minimal(args.step, args.max_trading_days)
    filtered = summarize(raw_summary)
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SUMMARY.write_text(json.dumps(filtered, indent=2))
    if RUNS_PATH.exists():
        shutil.copyfile(RUNS_PATH, OUTPUT_RUNS)
    print("Minimal FTMO eval summary:")
    print(json.dumps(filtered, indent=2))
    print(f"Saved summary to {OUTPUT_SUMMARY}")
    print(f"Saved runs to {OUTPUT_RUNS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
