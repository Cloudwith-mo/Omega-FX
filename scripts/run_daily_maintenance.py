#!/usr/bin/env python3
"""Run nightly maintenance: reports, exports, sanity checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(cmd: list[str]) -> str:
    """Run a subprocess and echo stdout; raise on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): rc={proc.returncode}")
    return proc.stdout


def parse_last_line(output: str, prefix: str) -> Path | None:
    for line in reversed(output.splitlines()):
        if prefix in line:
            return Path(line.split(prefix, 1)[1].strip()).resolve()
    return None


def run_daily_maintenance() -> int:
    print("=== Quarterly report (6h, latest session) ===")
    quarterly_out = run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts/run_exec_quarterly_report.py"),
            "--hours",
            "6",
            "--tag",
            "demo",
            "--use-latest-session",
        ]
    )
    quarterly_path = parse_last_line(quarterly_out, "Wrote report to")

    print("\n=== Daily report (24h, latest session) ===")
    daily_out = run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts/run_daily_exec_report.py"),
            "--hours",
            "24",
            "--tag",
            "demo",
            "--use-latest-session",
        ]
    )
    daily_path = parse_last_line(daily_out, "Wrote report to")

    print("\n=== Export bundle (30d demo) ===")
    export_out = run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts/run_export_bundle.py"),
            "--days",
            "30",
            "--env",
            "demo",
        ]
    )
    csv_path = parse_last_line(export_out, "- CSV:")
    behavior_path = parse_last_line(export_out, "- Behavior summary:")

    print("\n=== Sanity check (72h) ===")
    sanity_out = run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts/run_sanity_check_recent_trades.py"),
            "--hours",
            "72",
        ]
    )
    sanity_line = "WARNING: see sanity check output"
    if "SANITY CHECK PASSED" in sanity_out:
        sanity_line = "OK: safety rails respected (see sanity check section)"

    print("\n=== Summary ===")
    if daily_path:
        print(f"- Latest 24h report: {daily_path}")
    if csv_path:
        print(f"- Exec log export: {csv_path}")
    if behavior_path:
        print(f"- Behavior summary: {behavior_path}")
    print(f"- Sanity: {sanity_line}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_daily_maintenance())
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
