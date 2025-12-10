#!/usr/bin/env python3
"""Wrapper to emit execution reports on arbitrary hour windows."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_daily_exec_report import (
    generate_exec_report,
    read_latest_risk_env,
    read_latest_risk_tier,
    read_latest_session_id,
)  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quarter-day style execution report generator."
    )
    parser.add_argument(
        "--log_path", type=Path, default=Path("results/mt5_demo_exec_log.csv")
    )
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--tag", type=str, default="demo")
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=Path("results/mt5_demo_exec_live_summary.json"),
        help="Summary JSON used to infer current risk tier.",
    )
    parser.add_argument("--risk-tier", type=str, default=None)
    parser.add_argument("--session-id", type=str, default=None)
    parser.add_argument(
        "--use-latest-session",
        action="store_true",
        help="Ignore the hour window and focus on the latest recorded session.",
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Include historical (non-live) log rows when building the report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    window_end = datetime.now(timezone.utc)
    hours_label = (
        str(int(args.hours))
        if float(int(args.hours)) == float(args.hours)
        else str(args.hours).replace(".", "p")
    )
    output_name = (
        f"exec_report_{args.tag}_{hours_label}h_{window_end.strftime('%Y%m%d%H%M')}.md"
    )
    output_path = Path("results") / output_name
    tier = args.risk_tier or read_latest_risk_tier(args.summary_path)
    env_label = read_latest_risk_env(args.summary_path)
    session_filter = args.session_id
    session_only = False
    if args.use_latest_session:
        session_filter = session_filter or read_latest_session_id(args.summary_path)
        session_only = bool(session_filter)
    report_path = generate_exec_report(
        log_path=args.log_path,
        hours=args.hours,
        tag=args.tag,
        output_path=output_path,
        risk_tier=tier,
        session_id=session_filter,
        risk_env=env_label,
        session_only=session_only,
        include_historical=args.include_historical,
    )
    print(f"Wrote report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
