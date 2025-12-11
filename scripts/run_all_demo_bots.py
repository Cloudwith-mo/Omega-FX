#!/usr/bin/env python3
"""Launch all demo bots in parallel (one MT5 terminal per bot)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.bot_profiles import load_bot_profile  # noqa: E402

BOT_IDS = [
    "demo_trend_only",
    "demo_mr_only",
    "demo_session_only",
    "demo_trend_mr_london",
]

LOG_DIR = REPO_ROOT / "logs" / "autopilot"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start all demo bots in parallel.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without launching child processes.",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Optional runtime budget in hours for each bot (passed through to run_autopilot).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=900,
        help="Polling interval for each bot when --hours is used (defaults to 15 minutes).",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=None,
        help="Alias for --interval-seconds to match older docs/commands.",
    )
    return parser.parse_args()


def _resolve_interval(args: argparse.Namespace) -> int:
    if args.sleep_seconds is not None:
        return int(args.sleep_seconds)
    return int(args.interval_seconds)


def launch_bot(bot_id: str, args: argparse.Namespace, dry_run: bool = False) -> Optional[int]:
    interval = _resolve_interval(args)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_autopilot.py"),
        "--bot",
        bot_id,
    ]
    if args.hours:
        cmd += ["--hours", str(args.hours), "--interval-seconds", str(interval)]
    log_path = LOG_DIR / f"{bot_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)} -> {log_path}")
        return None
    with log_path.open("w") as log_fh:
        process = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    return process.pid


def main() -> int:
    args = parse_args()
    pids: dict[str, Optional[int]] = {}
    for bot_id in BOT_IDS:
        profile = load_bot_profile(bot_id)
        strategies = ", ".join(f"{s.id} (x{s.risk_scale})" for s in profile.strategies)
        print(
            f"Launching {bot_id} | account={profile.mt5_account} firm={profile.firm_profile} "
            f"tier={profile.risk_tier} symbols={','.join(profile.symbols)} strategies=[{strategies}]"
        )
        pid = launch_bot(bot_id, args, dry_run=args.dry_run)
        pids[bot_id] = pid
        if pid:
            print(f"Started {bot_id} (PID {pid})")
    if args.dry_run:
        print("Dry run complete; no processes started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
