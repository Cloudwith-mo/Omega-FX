#!/usr/bin/env python3
"""Bundle export helper for execution logs and behavior summary.

This script runs the standard export and analysis tools to produce
portable CSV + text reports under results/data_exports/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.monitoring_helpers import DEFAULT_LOG_PATH  # noqa: E402
from scripts.export_recent_logs import export_recent_logs  # noqa: E402
from scripts.analyze_recent_logs import (  # noqa: E402
    analyze_logs,
    generate_markdown_report,
)

DEFAULT_EXPORT_DIR = Path("results/data_exports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export and summarize recent execution logs in one step."
    )
    parser.add_argument("--hours", type=float, default=None, help="Look-back window in hours")
    parser.add_argument("--days", type=float, default=None, help="Look-back window in days")
    parser.add_argument("--env", type=str, default="demo", help="Environment label (demo/live)")
    parser.add_argument("--log-path", type=Path, default=None, help="Optional explicit log path override")
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Include historical/simulated rows in addition to live data",
    )
    return parser.parse_args()


def resolve_hours(args: argparse.Namespace) -> float:
    if args.hours is not None and args.days is not None:
        raise ValueError("Specify either --hours or --days (not both).")
    if args.hours is not None:
        return float(args.hours)
    if args.days is not None:
        return float(args.days) * 24
    raise ValueError("Must supply --hours or --days.")


def format_window_label(hours: float, env: str) -> str:
    if hours >= 24 and hours % 24 == 0:
        label = f"{int(hours / 24)}d"
    else:
        label = f"{int(hours)}h" if hours.is_integer() else f"{hours:g}h"
    return f"{label}_{env}"


def resolve_log_path(env: str, explicit: Path | None) -> Path:
    if explicit:
        return explicit
    env_path = Path(f"results/mt5_{env}_exec_log.csv")
    if env_path.exists():
        return env_path
    return DEFAULT_LOG_PATH


def run_export_bundle(
    *,
    hours: float,
    env: str,
    log_path: Path | None = None,
    include_historical: bool = False,
    export_dir: Path = DEFAULT_EXPORT_DIR,
) -> tuple[Path, Path]:
    export_dir.mkdir(parents=True, exist_ok=True)

    resolved_log = resolve_log_path(env, log_path)
    if not resolved_log.exists():
        raise FileNotFoundError(f"Log file not found at {resolved_log}")

    window_label = format_window_label(hours, env)
    csv_path = export_dir / f"exec_log_last_{window_label}.csv"
    summary_path = export_dir / f"behavior_summary_last_{window_label}.txt"

    export_recent_logs(
        log_path=resolved_log,
        hours=hours,
        env=env,
        output_path=csv_path,
        include_historical=include_historical,
    )

    analysis = analyze_logs(log_path=csv_path, include_historical=include_historical)
    report = generate_markdown_report(
        analysis=analysis,
        hours=hours,
        env=env,
        notion_format=True,
    )
    summary_path.write_text(report, encoding="utf-8")

    print("Export bundle completed:")
    print(f"- CSV: {csv_path}")
    print(f"- Behavior summary: {summary_path}")
    return csv_path, summary_path


def main() -> int:
    args = parse_args()
    try:
        hours = resolve_hours(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    resolved_log = resolve_log_path(args.env, args.log_path)

    try:
        run_export_bundle(
            hours=hours,
            env=args.env,
            log_path=resolved_log,
            include_historical=args.include_historical,
        )
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - runtime guard
        print(f"ERROR: Unexpected failure: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
