#!/usr/bin/env python3
"""OmegaFX Sunday healthcheck."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_notification_snapshot import (
    build_notification_snapshot,  # noqa: E402
)
from scripts.run_daily_exec_report import generate_exec_report  # noqa: E402

RESULTS_DIR = Path("results")


def run_command(description: str, cmd: list[str]) -> None:
    print(f"[Healthcheck] {description} ...", flush=True)
    subprocess.run(cmd, check=True)


def main() -> int:
    failures: list[str] = []
    generated_reports: list[Path] = []
    snapshot_path: Path | None = None

    steps = [
        (
            "pytest execution backend",
            [sys.executable, "-m", "pytest", "tests/test_execution_backend.py"],
        ),
        (
            "MT5 smoketest",
            [
                sys.executable,
                "scripts/run_exec_mt5_smoketest.py",
                "--account_profile",
                "METAQUOTES_DEMO",
                "--dry_run",
            ],
        ),
        (
            "autopilot dry-run sanity",
            [
                sys.executable,
                "scripts/run_demo_autopilot.py",
                "--hours",
                "0.03",
                "--sleep-seconds",
                "5",
                "--risk_tier",
                "conservative",
                "--dry_run",
                "--limit_trades",
                "5",
            ],
        ),
    ]

    for description, cmd in steps:
        try:
            run_command(description, cmd)
        except subprocess.CalledProcessError as exc:
            failures.append(f"{description} failed ({exc})")
            break

    if not failures:
        try:
            report_6h = generate_exec_report(
                Path("results/mt5_demo_exec_log.csv"), 6, "demo"
            )
            report_24h = generate_exec_report(
                Path("results/mt5_demo_exec_log.csv"), 24, "demo"
            )
            generated_reports.extend([report_6h, report_24h])
        except Exception as exc:
            failures.append(f"Report generation failed: {exc}")

    if not failures:
        try:
            _, snapshot_path = build_notification_snapshot(
                tag="demo", results_dir=RESULTS_DIR, hours_fast="6", hours_slow="24"
            )
        except Exception as exc:
            failures.append(f"Notification snapshot failed: {exc}")

    if failures:
        print("OmegaFX healthcheck: FAIL")
        for msg in failures:
            print(f" - {msg}")
        return 1

    print(
        "OmegaFX healthcheck: PASS (tests ok, MT5 smoketest ok, reports generated: "
        + ", ".join(str(p) for p in generated_reports)
        + (f", snapshot: {snapshot_path}" if snapshot_path else "")
        + ")"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
