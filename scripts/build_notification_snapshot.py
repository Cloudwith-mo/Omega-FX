#!/usr/bin/env python3
"""Build a consolidated notification snapshot from the latest exec reports."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assemble notification summary from exec reports.")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--tag", type=str, default="demo")
    parser.add_argument("--hours-fast", type=str, default="6", help="Short window hours label (default 6).")
    parser.add_argument("--hours-slow", type=str, default="24", help="Long window hours label (default 24).")
    parser.add_argument("--session-id", type=str, default=None, help="Prefer reports from this session id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary, path = build_notification_snapshot(
        tag=args.tag,
        results_dir=args.results_dir,
        hours_fast=args.hours_fast,
        hours_slow=args.hours_slow,
        session_id=args.session_id,
    )
    print(summary)
    print(f"Saved snapshot to {path}")
    return 0


def build_notification_snapshot(
    *,
    tag: str,
    results_dir: Path,
    hours_fast: str,
    hours_slow: str,
    session_id: str | None = None,
) -> Tuple[str, Path]:
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory {results_dir} not found.")
    report_fast = _latest_report(results_dir, tag, hours_fast, session_id=session_id)
    report_slow = _latest_report(results_dir, tag, hours_slow, session_id=session_id)
    data_fast = _parse_report(report_fast)
    data_slow = _parse_report(report_slow)

    summary = (
        f"OmegaFX {tag} | Equity: {data_slow['End equity']:.2f} | "
        f"Tier: {data_slow['Risk tier']} | Env: {data_slow['Environment']} | Session: {data_slow['Session id']} | "
        f"{hours_slow}h PnL: {data_slow['PnL']:.2f} ({data_slow['PnL %']})"
        f", trades: {data_slow['Closed trades']} (win {data_slow['Win rate']}) | "
        f"{hours_fast}h PnL: {data_fast['PnL']:.2f} ({data_fast['PnL %']}), trades: {data_fast['Closed trades']} | "
        f"Filters ({hours_slow}h): max_pos {data_slow['filtered_max_positions']}, "
        f"daily_loss {data_slow['filtered_daily_loss']}, invalid_stops {data_slow['filtered_invalid_stops']}"
    )

    output_path = results_dir / f"notification_snapshot_{tag}.txt"
    output_path.write_text(summary + "\n", encoding="utf-8")
    return summary, output_path


def _latest_report(results_dir: Path, tag: str, hours_label: str, session_id: str | None = None) -> Path:
    pattern = f"exec_report_{tag}_{hours_label}h_*.md"
    matches = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No report matching {pattern} in {results_dir}")
    if session_id:
        for candidate in matches:
            data = _parse_report(candidate)
            if data.get('Session id') == session_id:
                return candidate
        raise FileNotFoundError(f"No report for session {session_id} matching {pattern}")
    return matches[0]


def _parse_report(path: Path) -> Dict[str, float | str]:
    content = path.read_text(encoding="utf-8").splitlines()
    data: Dict[str, float | str] = {
        "filtered_max_positions": 0,
        "filtered_daily_loss": 0,
        "filtered_invalid_stops": 0,
        "Session id": "unknown",
        "Environment": "unknown",
    }

    for line in content:
        line = line.strip()
        if not line.startswith("- "):
            continue
        key_value = line[2:]
        if ":" not in key_value:
            continue
        key, value = key_value.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in {"Start equity", "End equity", "PnL"}:
            data[key] = float(value)
        elif key == "PnL %":
            data[key] = value
        elif key == "Closed trades":
            data[key] = int(value)
        elif key == "Win rate":
            data[key] = value
        elif key == "Risk tier":
            data[key] = value
        elif key == "Environment":
            data[key] = value or "unknown"
        elif key == "Session id":
            data[key] = value or "unknown"
        elif key.startswith("filtered_"):
            data[key] = int(value)

    required = [
        "End equity",
        "PnL",
        "PnL %",
        "Closed trades",
        "Win rate",
        "Risk tier",
        "Environment",
        "Session id",
        "filtered_max_positions",
        "filtered_daily_loss",
        "filtered_invalid_stops",
    ]
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"Report {path} missing fields: {missing}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
