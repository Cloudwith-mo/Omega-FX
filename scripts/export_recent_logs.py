#!/usr/bin/env python3
"""Export recent execution logs to filtered CSV files.

This CLI tool reads MT5 execution logs and exports rows within a specified
time window to a new CSV file with a summary report.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_daily_exec_report import (  # noqa: E402
    _parse_timestamp,
    _safe_float,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Export recent execution logs with time filtering."
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Export logs from the last N hours.",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=None,
        help="Export logs from the last N days (converted to hours).",
    )
    parser.add_argument(
        "--env",
        type=str,
        default="demo",
        help="Environment label (demo, live, etc.)",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help="Input log path (default: results/mt5_{env}_exec_log.csv)",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Output CSV path (default: results/mt5_exec_log_last_{window}_{env}.csv)",
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Include historical (non-live) log rows.",
    )
    return parser.parse_args()


def export_recent_logs(
    log_path: Path,
    hours: float,
    env: str,
    output_path: Path | None = None,
    include_historical: bool = False,
) -> tuple[Path, dict]:
    """Export recent logs and return summary stats.
    
    Args:
        log_path: Path to input execution log CSV
        hours: Number of hours to look back
        env: Environment label (for naming)
        output_path: Optional explicit output path
        include_historical: Include non-live rows
        
    Returns:
        Tuple of (output_path, summary_stats)
    """
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=max(hours, 0.0))

    # Determine output path
    if output_path is None:
        if hours >= 24 and hours % 24 == 0:
            window_label = f"{int(hours / 24)}d"
        else:
            window_label = f"{int(hours)}h"
        output_path = Path(f"results/mt5_exec_log_last_{window_label}_{env}.csv")

    # Read and filter rows
    filtered_rows = []
    fieldnames = None
    
    with log_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        
        for row in reader:
            timestamp = _parse_timestamp(row["timestamp"])
            
            # Filter by data mode
            row_mode = (row.get("data_mode") or "live").strip().lower()
            if not include_historical and row_mode != "live":
                continue
            
            # Filter by time window
            if window_start <= timestamp <= window_end:
                filtered_rows.append(row)

    # Write filtered CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        if fieldnames:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_rows)

    # Compute summary statistics
    summary = _compute_summary(filtered_rows)
    summary["window_start"] = window_start.isoformat()
    summary["window_end"] = window_end.isoformat()
    summary["total_rows"] = len(filtered_rows)

    return output_path, summary


def _compute_summary(rows: list[dict]) -> dict:
    """Compute summary statistics from filtered rows."""
    open_count = 0
    close_count = 0
    filter_count = 0
    strategy_open_counts = defaultdict(int)
    strategy_close_counts = defaultdict(int)
    trade_pnls = []
    
    for row in rows:
        event = row.get("event", "").strip()
        strategy_id = row.get("strategy_id", "").strip() or "unknown"
        
        if event == "OPEN":
            open_count += 1
            strategy_open_counts[strategy_id] += 1
        elif event == "CLOSE":
            close_count += 1
            strategy_close_counts[strategy_id] += 1
            
            # Try to extract PnL
            pnl = _safe_float(row.get("pnl"))
            if pnl is not None:
                trade_pnls.append(pnl)
        elif event == "FILTER":
            filter_count += 1

    total_pnl = sum(trade_pnls) if trade_pnls else 0.0
    avg_pnl = total_pnl / len(trade_pnls) if trade_pnls else 0.0
    wins = sum(1 for p in trade_pnls if p > 0)
    win_rate = wins / len(trade_pnls) if trade_pnls else 0.0

    return {
        "open_trades": open_count,
        "close_trades": close_count,
        "filter_events": filter_count,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "win_rate": win_rate,
        "strategy_open_counts": dict(strategy_open_counts),
        "strategy_close_counts": dict(strategy_close_counts),
    }


def print_summary(output_path: Path, summary: dict) -> None:
    """Print summary statistics to stdout."""
    print(f"\n{'='*70}")
    print(f"EXPORTED RECENT LOGS")
    print(f"{'='*70}")
    print(f"\nOutput: {output_path}")
    print(f"Total rows: {summary['total_rows']}")
    print(f"\nWindow:")
    print(f"  Start: {summary['window_start']}")
    print(f"  End:   {summary['window_end']}")
    
    print(f"\nEvents:")
    print(f"  OPEN trades:   {summary['open_trades']}")
    print(f"  CLOSE trades:  {summary['close_trades']}")
    print(f"  FILTER events: {summary['filter_events']}")
    
    print(f"\nPerformance:")
    print(f"  Total P&L:  ${summary['total_pnl']:,.2f}")
    print(f"  Avg P&L:    ${summary['avg_pnl']:,.2f}")
    print(f"  Win rate:   {summary['win_rate']:.1%}")
    
    if summary['strategy_close_counts']:
        print(f"\nPer-Strategy Trade Counts (CLOSE events):")
        for strategy_id, count in sorted(summary['strategy_close_counts'].items()):
            print(f"  {strategy_id}: {count}")
    
    print(f"\n{'='*70}\n")


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Determine time window
    if args.hours is not None and args.days is not None:
        print("ERROR: Cannot specify both --hours and --days")
        return 1
    elif args.hours is not None:
        hours = args.hours
    elif args.days is not None:
        hours = args.days * 24
    else:
        print("ERROR: Must specify either --hours or --days")
        return 1
    
    # Determine input log path
    if args.log_path:
        log_path = args.log_path
    else:
        log_path = Path(f"results/mt5_{args.env}_exec_log.csv")
    
    # Export logs
    try:
        output_path, summary = export_recent_logs(
            log_path=log_path,
            hours=hours,
            env=args.env,
            output_path=args.output_path,
            include_historical=args.include_historical,
        )
        print_summary(output_path, summary)
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
