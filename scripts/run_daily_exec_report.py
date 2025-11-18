#!/usr/bin/env python3
"""Generate a rolling MT5 demo execution report."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - CLI entry point
    sys.path.insert(0, str(REPO_ROOT))

from core.position_sizing import get_symbol_meta  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily MT5 demo execution summary.")
    parser.add_argument("--log_path", type=Path, default=Path("results/mt5_demo_exec_log.csv"))
    parser.add_argument("--hours", type=float, default=24.0, help="Rolling window size in hours.")
    parser.add_argument("--output_dir", type=Path, default=Path("results"))
    parser.add_argument("--tag", type=str, default="demo", help="Label used in the report filename.")
    parser.add_argument(
        "--alert_mode",
        choices=["none", "telegram", "slack"],
        default="none",
        help="Optional end-of-day alert emission (stdout stub).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.log_path.exists():
        raise SystemExit(f"Log file {args.log_path} not found.")
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=max(args.hours, 0.0))
    stats = _analyze_log(args.log_path, window_start)
    report_path = _write_report(args.output_dir, args.tag, window_start, now, stats)
    summary_line = (
        f"PnL {stats['pnl_total']:.2f} over {stats['trades']} trades "
        f"(win {stats['win_rate']:.1%}, max DD {stats['max_dd']:.2%}) "
        f"| filters mp={stats['filters'].get('max_positions', 0)} "
        f"daily={stats['filters'].get('daily_loss', 0)} "
        f"invalid={stats['filters'].get('invalid_stops', 0)}"
    )
    print(summary_line)
    print(f"Wrote report to {report_path}")
    _emit_alert(summary_line, args.alert_mode)
    return 0


def _analyze_log(log_path: Path, window_start: datetime) -> dict:
    open_positions: dict[str, dict] = {}
    filter_counts: dict[str, int] = defaultdict(int)
    trade_results: list[float] = []
    equity_points: list[tuple[datetime, float]] = []

    with log_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            timestamp = _parse_timestamp(row["timestamp"])
            ticket = row["ticket"]
            event = row["event"]
            price = _safe_float(row.get("price"))
            volume = _safe_float(row.get("volume"))
            if event == "OPEN" and price is not None and volume is not None:
                open_positions[ticket] = {
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "volume": volume,
                    "price": price,
                }
            entry_record = open_positions.pop(ticket, None) if event == "CLOSE" else None

            if timestamp >= window_start:
                equity = _safe_float(row.get("equity"))
                if equity is not None:
                    equity_points.append((timestamp, equity))
                if event == "FILTER":
                    filter_counts[row.get("reason", "").strip() or "unknown"] += 1
                elif event == "CLOSE" and price is not None and entry_record:
                    trade_results.append(
                        _pnl_from_prices(
                            entry_record["symbol"],
                            entry_record["direction"],
                            entry_record["price"],
                            price,
                            entry_record["volume"],
                        )
                    )

    wins = sum(1 for pnl in trade_results if pnl > 0)
    pnl_total = sum(trade_results)
    win_rate = wins / len(trade_results) if trade_results else 0.0
    max_dd = _max_drawdown(equity_points)
    return {
        "pnl_total": pnl_total,
        "trades": len(trade_results),
        "win_rate": win_rate,
        "max_dd": max_dd,
        "filters": dict(filter_counts),
    }


def _pnl_from_prices(symbol: str, direction: str, entry_price: float, exit_price: float, volume: float) -> float:
    meta = get_symbol_meta(symbol)
    pip_distance = (exit_price - entry_price) / meta.pip_size
    if direction == "short":
        pip_distance = -pip_distance
    return pip_distance * meta.pip_value_per_standard_lot * volume


def _max_drawdown(points: list[tuple[datetime, float]]) -> float:
    if not points:
        return 0.0
    peak = points[0][1]
    max_dd = 0.0
    for _, value in sorted(points, key=lambda item: item[0]):
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def _write_report(
    output_dir: Path,
    tag: str,
    start: datetime,
    end: datetime,
    stats: dict,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_exec_report_{tag}_{end.strftime('%Y%m%d')}.md"
    path = output_dir / filename
    lines = [
        f"# {tag.upper()} Execution Report",
        "",
        f"- Period (UTC): {start.isoformat()} → {end.isoformat()}",
        f"- Closed trades: {stats['trades']}",
        f"- Net PnL: {stats['pnl_total']:.2f}",
        f"- Win rate: {stats['win_rate']:.1%}",
        f"- Max drawdown: {stats['max_dd']:.2%}",
        "",
        "## Filter Counts",
        f"- Max positions: {stats['filters'].get('max_positions', 0)}",
        f"- Daily loss: {stats['filters'].get('daily_loss', 0)}",
        f"- Invalid stops: {stats['filters'].get('invalid_stops', 0)}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_float(value: str | None) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _emit_alert(message: str, mode: str) -> None:
    if mode == "none":
        return
    prefix = f"[{mode.upper()} ALERT]"
    print(f"{prefix} {message}")


if __name__ == "__main__":
    raise SystemExit(main())
