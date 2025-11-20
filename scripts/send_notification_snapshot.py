#!/usr/bin/env python3
"""Send the most recent notification snapshot to Telegram."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.notifications import send_telegram_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send notification snapshot via Telegram.")
    parser.add_argument("--tag", type=str, default="demo")
    parser.add_argument(
        "--snapshot-path",
        type=Path,
        default=None,
        help="Optional explicit path to the snapshot file.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path("config/notifications.yaml"),
        help="Notification config path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_path = args.snapshot_path or Path(f"results/notification_snapshot_{args.tag}.txt")
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot file {snapshot_path} not found. Run build_notification_snapshot first.")
    text = snapshot_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Snapshot file {snapshot_path} is empty.")

    success = send_telegram_message(text, config_path=args.config_path)
    if success:
        print(f"Notification sent via Telegram from {snapshot_path}.")
        return 0
    print("Notification send skipped or failed; see log above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
