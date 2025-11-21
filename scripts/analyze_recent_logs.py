#!/usr/bin/env python3
"""Analyze recent execution logs to compute trading behavior metrics.

This script reads execution logs, computes distributions and analytics,
and outputs formatted reports for analysis and Notion integration.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure UTF-8 stdout so emoji/special chars don't crash on Windows terminals
try:  # pragma: no cover - platform/terminal dependent
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from scripts.export_recent_logs import export_recent_logs  # noqa: E402
from scripts.run_daily_exec_report import _parse_timestamp, _safe_float  # noqa: E402
from core.position_sizing import get_symbol_meta  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze execution logs for trading behavior patterns."
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Analyze logs from the last N hours.",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=None,
        help="Analyze logs from the last N days (converted to hours).",
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
        "--output-md",
        type=Path,
        default=None,
        help="Markdown output path (default: results/behavior_report_{window}_{env}.md)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional CSV output for per-strategy aggregates",
    )
    parser.add_argument(
        "--notion-format",
        action="store_true",
        help="Include Notion-friendly formatted sections",
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Include historical (non-live) log rows.",
    )
    return parser.parse_args()


def analyze_logs(
    log_path: Path,
    include_historical: bool = False,
) -> dict[str, Any]:
    """Analyze execution log and compute behavior metrics.
    
    Returns dict with:
        - trades: list of trade dicts (with computed metrics)
        - per_strategy: dict of per-strategy aggregates
        - overall: overall statistics
    """
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    # Track open positions to compute hold times
    open_positions: dict[str, dict] = {}
    completed_trades: list[dict] = []
    
    with log_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        
        for row in reader:
            timestamp = _parse_timestamp(row["timestamp"])
            ticket = row["ticket"]
            event = row.get("event", "").strip()
            
            # Filter by data mode
            row_mode = (row.get("data_mode") or "live").strip().lower()
            if not include_historical and row_mode != "live":
                continue
            
            if event == "OPEN":
                open_positions[ticket] = {
                    "ticket": ticket,
                    "symbol": row.get("symbol", ""),
                    "direction": row.get("direction", ""),
                    "volume": _safe_float(row.get("volume")),
                    "entry_price": _safe_float(row.get("price")),
                    "entry_time": timestamp,
                    "strategy_id": row.get("strategy_id", "").strip() or "unknown",
                    "session_id": row.get("session_id", "").strip(),
                    "signal_reason": row.get("signal_reason", "").strip(),
                }
            
            elif event == "CLOSE" and ticket in open_positions:
                entry = open_positions.pop(ticket)
                exit_price = _safe_float(row.get("price"))
                pnl = _safe_float(row.get("pnl"))
                
                if exit_price is not None and entry["entry_price"] is not None:
                    # Compute hold time
                    hold_seconds = (timestamp - entry["entry_time"]).total_seconds()
                    
                    # Compute SL/TP in pips (estimate from price movement)
                    symbol = entry["symbol"]
                    meta = get_symbol_meta(symbol)
                    price_diff = abs(exit_price - entry["entry_price"])
                    pips_moved = price_diff / meta.pip_size
                    
                    # Estimate R-multiple (PnL / risk)
                    # We don't have exact SL in logs, so estimate from typical risk
                    typical_sl_pips = 20.0  # Default assumption
                    r_multiple = None
                    if pnl is not None and abs(pnl) > 0.01:
                        # Rough estimate: assume SL was ~20 pips
                        risk_estimate = typical_sl_pips * meta.pip_value_per_standard_lot * (entry["volume"] or 1.0)
                        if risk_estimate > 0:
                            r_multiple = pnl / risk_estimate
                    
                    completed_trades.append({
                        **entry,
                        "exit_price": exit_price,
                        "exit_time": timestamp,
                        "pnl": pnl or 0.0,
                        "hold_seconds": hold_seconds,
                        "pips_moved": pips_moved,
                        "r_multiple": r_multiple,
                        "is_win": (pnl or 0.0) > 0,
                    })
    
    # Aggregate per strategy
    per_strategy = _aggregate_by_strategy(completed_trades)
    
    # Compute overall stats
    overall = _compute_overall_stats(completed_trades)
    
    return {
        "trades": completed_trades,
        "per_strategy": per_strategy,
        "overall": overall,
    }


def _aggregate_by_strategy(trades: list[dict]) -> dict[str, dict]:
    """Aggregate trade metrics by strategy."""
    strategy_buckets: dict[str, list[dict]] = defaultdict(list)
    
    for trade in trades:
        strategy_id = trade.get("strategy_id", "unknown")
        strategy_buckets[strategy_id].append(trade)
    
    result = {}
    for strategy_id, strategy_trades in strategy_buckets.items():
        result[strategy_id] = _compute_strategy_stats(strategy_trades, strategy_id)
    
    return result


def _compute_strategy_stats(trades: list[dict], strategy_id: str = "unknown") -> dict[str, Any]:
    """Compute statistics for a single strategy's trades."""
    if not trades:
        return {}
    
    total_trades = len(trades)
    wins = sum(1 for t in trades if t.get("is_win", False))
    losses = total_trades - wins
    
    total_pnl = sum(t.get("pnl", 0.0) for t in trades)
    avg_pnl = total_pnl / total_trades if total_trades else 0.0
    
    # Hold times
    hold_times = [t.get("hold_seconds", 0) for t in trades if t.get("hold_seconds")]
    avg_hold_seconds = sum(hold_times) / len(hold_times) if hold_times else 0.0
    
    # Pips
    pips_list = [t.get("pips_moved", 0) for t in trades if t.get("pips_moved")]
    avg_pips = sum(pips_list) / len(pips_list) if pips_list else 0.0
    
    # R-multiples
    r_multiples = [t.get("r_multiple") for t in trades if t.get("r_multiple") is not None]
    avg_r_multiple = sum(r_multiples) / len(r_multiples) if r_multiples else None
    
    # Trades per day (rough estimate based on time span)
    if len(trades) >= 2:
        first_time = min(t["entry_time"] for t in trades)
        last_time = max(t["exit_time"] for t in trades)
        days = (last_time - first_time).total_seconds() / 86400
        trades_per_day = total_trades / max(days, 1.0)
    else:
        trades_per_day = 0.0
    
    return {
        "strategy_id": strategy_id,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total_trades if total_trades else 0.0,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "avg_hold_seconds": avg_hold_seconds,
        "avg_hold_minutes": avg_hold_seconds / 60.0,
        "avg_pips": avg_pips,
        "avg_r_multiple": avg_r_multiple,
        "trades_per_day": trades_per_day,
        "hold_time_dist": _histogram(hold_times, bins=[0, 1800, 3600, 7200, 14400, float("inf")]),
        "r_multiple_dist": _histogram(r_multiples, bins=[-5, -2, -1, 0, 1, 2, 5, float("inf")]) if r_multiples else {},
    }



def _compute_overall_stats(trades: list[dict]) -> dict[str, Any]:
    """Compute overall statistics across all trades."""
    if not trades:
        return {"total_trades": 0}
    
    total_trades = len(trades)
    wins = sum(1 for t in trades if t.get("is_win", False))
    total_pnl = sum(t.get("pnl", 0.0) for t in trades)
    
    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": total_trades - wins,
        "win_rate": wins / total_trades,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / total_trades,
    }


def _histogram(values: list[float], bins: list[float]) -> dict[str, int]:
    """Create histogram from values and bin edges."""
    if not values:
        return {}
    
    hist = defaultdict(int)
    for value in values:
        for i in range(len(bins) - 1):
            if bins[i] <= value < bins[i + 1]:
                hist[f"{bins[i]}-{bins[i+1]}"] +=1
                break
    
    return dict(hist)


def generate_markdown_report(
    analysis: dict[str, Any],
    hours: float,
    env: str,
    notion_format: bool = False,
) -> str:
    """Generate markdown report from analysis results."""
    overall = analysis["overall"]
    per_strategy = analysis["per_strategy"]
    
    lines = [
        f"# Trading Behavior Analysis ({hours:.0f}h - {env.upper()})",
        "",
        f"**Report Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        "## Overall Summary",
        "",
        f"- **Total Trades**: {overall.get('total_trades', 0)}",
        f"- **Win Rate**: {overall.get('win_rate', 0):.1%}",
        f"- **Total P&L**: ${overall.get('total_pnl', 0):,.2f}",
        f"- **Avg P&L**: ${overall.get('avg_pnl', 0):.2f}",
        "",
    ]
    
    # Per-strategy breakdown
    lines.append("## Per-Strategy Metrics")
    lines.append("")
    
    if per_strategy:
        lines.append("| Strategy | Trades | Win% | P&L | Avg Hold (min) | Avg Pips | Trades/Day | Avg R |")
        lines.append("|----------|--------|------|-----|----------------|----------|------------|-------|")
        
        for strategy_id, stats in sorted(per_strategy.items()):
            r_display = (
                f"{stats['avg_r_multiple']:.2f}" if stats['avg_r_multiple'] else "N/A"
            )
            lines.append(
                f"| {strategy_id} | "
                f"{stats['total_trades']} | "
                f"{stats['win_rate']:.1%} | "
                f"${stats['total_pnl']:,.2f} | "
                f"{stats['avg_hold_minutes']:.1f} | "
                f"{stats['avg_pips']:.1f} | "
                f"{stats['trades_per_day']:.2f} | "
                f"{r_display}"
            )
    else:
        lines.append("No trades found in the analyzed period.")
    
    lines.append("")
    
    # Detailed per-strategy sections
    for strategy_id, stats in sorted(per_strategy.items()):
        lines.extend(_strategy_detail_section(strategy_id, stats))
    
    # Notion format section
    if notion_format:
        lines.append("")
        lines.extend(_notion_format_section(per_strategy, hours, env))
    
    return "\n".join(lines)


def _strategy_detail_section(strategy_id: str, stats: dict) -> list[str]:
    """Generate detailed section for a single strategy."""
    lines = [
        f"### {strategy_id}",
        "",
        f"**Trades**: {stats['total_trades']} ({stats['wins']}W / {stats['losses']}L)",
        f"**Win Rate**: {stats['win_rate']:.1%}",
        f"**P&L**: ${stats['total_pnl']:,.2f} (Avg: ${stats['avg_pnl']:.2f})",
        f"**Hold Time**: {stats['avg_hold_minutes']:.1f} min average",
        f"**Trades/Day**: {stats['trades_per_day']:.2f}",
        "",
    ]
    
    # Hold time distribution
    if stats.get("hold_time_dist"):
        lines.append("**Hold Time Distribution (seconds)**:")
        for bucket, count in sorted(stats['hold_time_dist'].items()):
            lines.append(f"- {bucket}: {count} trades")
        lines.append("")
    
    # R-multiple distribution
    if stats.get("r_multiple_dist"):
        lines.append("**R-Multiple Distribution**:")
        for bucket, count in sorted(stats['r_multiple_dist'].items()):
            lines.append(f"- {bucket}R: {count} trades")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return lines


def _notion_format_section(per_strategy: dict, hours: float, env: str) -> list[str]:
    """Generate Notion-friendly formatted section."""
    lines = [
        "---",
        "",
        "## Notion Copy/Paste Format",
        "",
        f"### Session: {env.upper()} - Last {hours:.0f}h",
        "",
    ]
    
    for strategy_id, stats in sorted(per_strategy.items()):
        r_display = f"{stats['avg_r_multiple']:.2f}" if stats['avg_r_multiple'] else "N/A"
        
        lines.extend([
            f"**{strategy_id}**",
            f"- P&L: ${stats['total_pnl']:,.2f}",
            f"- Win%: {stats['win_rate']:.1%}",
            f"- Avg Pips: {stats['avg_pips']:.1f}",
            f"- Trades/Day: {stats['trades_per_day']:.2f}",
            f"- Avg Hold: {stats['avg_hold_minutes']:.1f} min",
            f"- Avg R: {r_display}",
            "",
        ])
    
    lines.extend([
        "---",
        "",
        "_Paste the above blocks into your Notion Session Log for quick tracking._",
        "",
    ])
    
    return lines


def save_csv_aggregates(per_strategy: dict, output_path: Path) -> None:
    """Save per-strategy aggregates to CSV."""
    fieldnames = [
        "strategy_id",
        "total_trades",
        "wins",
        "losses",
        "win_rate",
        "total_pnl",
        "avg_pnl",
        "avg_hold_minutes",
        "avg_pips",
        "avg_r_multiple",
        "trades_per_day",
    ]
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        
        for strategy_id, stats in sorted(per_strategy.items()):
            row = {k: stats.get(k, "") for k in fieldnames}
            writer.writerow(row)


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
    
    # First export the logs (filter by time)
    try:
        temp_export = Path(f"results/.temp_export_{args.env}.csv")
        export_recent_logs(
            log_path=log_path,
            hours=hours,
            env=args.env,
            output_path=temp_export,
            include_historical=args.include_historical,
        )
        
        # Analyze the exported logs
        analysis = analyze_logs(
            log_path=temp_export,
            include_historical=args.include_historical,
        )
        
        # Generate markdown report
        report = generate_markdown_report(
            analysis=analysis,
            hours=hours,
            env=args.env,
            notion_format=args.notion_format,
        )
        
        # Determine output paths
        if args.output_md:
            md_path = args.output_md
        else:
            if hours >= 24 and hours % 24 == 0:
                window_label = f"{int(hours / 24)}d"
            else:
                window_label = f"{int(hours)}h"
            md_path = Path(f"results/behavior_report_{window_label}_{args.env}.md")
        
        # Save markdown report
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(report, encoding="utf-8")
        print(f"\n[OK] Markdown report saved: {md_path}")
        
        # Save CSV if requested
        if args.output_csv:
            save_csv_aggregates(analysis["per_strategy"], args.output_csv)
            print(f"[OK] CSV aggregates saved: {args.output_csv}")
        
        # Clean up temp file
        if temp_export.exists():
            temp_export.unlink()
        
        # Print summary
        overall = analysis["overall"]
        print(f"\n{'='*70}")
        print(f"ANALYSIS SUMMARY")
        print(f"{'='*70}")
        print(f"Total Trades: {overall.get('total_trades', 0)}")
        print(f"Win Rate: {overall.get('win_rate', 0):.1%}")
        print(f"Total P&L: ${overall.get('total_pnl', 0):,.2f}")
        print(f"\nStrategies analyzed: {len(analysis['per_strategy'])}")
        for sid in sorted(analysis['per_strategy'].keys()):
            print(f"  - {sid}")
        print(f"{'='*70}\n")
        
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
