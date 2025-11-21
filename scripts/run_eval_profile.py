#!/usr/bin/env python3
"""Run the default evaluation profile for a specific firm."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import DEFAULT_EVAL_PROFILE_PER_FIRM, EVAL_PROFILES  # noqa: E402

RESULTS_DIR = Path("results")
SUMMARY_PATH = RESULTS_DIR / "challenge_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute the blessed FTMO-style eval profile."
    )
    parser.add_argument(
        "--firm",
        choices=sorted(DEFAULT_EVAL_PROFILE_PER_FIRM.keys()),
        default="ftmo",
        help="Target firm (ftmo, fundednext, aqua).",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=2000,
        help="Seed spacing for the underlying challenge simulation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path (defaults to results/eval_profile_<firm>.json).",
    )
    return parser.parse_args()


def load_profile(firm_key: str) -> tuple[str, dict]:
    profile_name = DEFAULT_EVAL_PROFILE_PER_FIRM[firm_key]
    profile = EVAL_PROFILES[profile_name]
    return profile_name, profile


def run_profile(firm_key: str, profile_name: str, profile: object, step: int) -> dict:
    env = os.environ.copy()
    env["OMEGA_FIRM_PROFILE"] = profile.firm_profile
    env["OMEGA_ENTRY_MODE"] = profile.entry_mode
    env["OMEGA_MAX_CONCURRENT_POSITIONS"] = str(profile.max_concurrent_positions)
    env["OMEGA_TIER_SCALE_A"] = str(profile.tier_scales.get("A", 1.5))
    env["OMEGA_TIER_SCALE_B"] = str(profile.tier_scales.get("B", 0.75))
    env["OMEGA_TIER_SCALE_UNKNOWN"] = str(profile.tier_scales.get("UNKNOWN", 0.5))
    env.setdefault("OMEGA_RISK_PRESET", "FULL")

    cmd = [
        sys.executable,
        "scripts/run_challenge_sim.py",
        "--portfolio",
        "--entry_mode",
        profile.entry_mode,
        "--firm_profile",
        profile.firm_profile,
        "--trading_firm",
        firm_key,
        "--account_phase",
        "EVAL",
        "--step",
        str(step),
    ]
    subprocess.run(cmd, check=True, env=env)
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(SUMMARY_PATH)
    summary = json.loads(SUMMARY_PATH.read_text())
    summary["profile_name"] = profile_name
    summary["firm"] = firm_key
    return summary


def summarize(summary: dict) -> dict:
    stats = summary.get("return_stats", {})
    return {
        "firm": summary.get("firm"),
        "profile_name": summary.get("profile_name"),
        "pass_rate": summary.get("pass_rate"),
        "mean_return": stats.get("mean_return"),
        "median_return": stats.get("median_return"),
        "max_daily_loss": summary.get("max_daily_loss_fraction"),
        "max_trailing_dd": summary.get("max_trailing_dd_fraction"),
        "mean_trades_per_run": summary.get("mean_trades_per_run"),
    }


def main() -> int:
    args = parse_args()
    profile_name, profile = load_profile(args.firm)
    raw_summary = run_profile(args.firm, profile_name, profile, args.step)
    filtered = summarize(raw_summary)
    output_path = args.output or RESULTS_DIR / f"eval_profile_{args.firm}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(filtered, indent=2))
    print("Evaluation profile summary:")
    print(json.dumps(filtered, indent=2))
    print(f"Saved summary to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
