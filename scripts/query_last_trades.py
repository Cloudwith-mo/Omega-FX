#!/usr/bin/env python3
"""Query recent MT5 demo trades from the execution log."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.constants import DEFAULT_STRATEGY_ID
from core.position_sizing import get_symbol_meta

DEFAULT_LOG_PATH = Path("results/mt5_demo_exec_log.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the latest MT5 demo trades.")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Restrict to trades within the last N hours.",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Filter trades for a specific session id.",
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Maximum number of trades to output."
    )
    parser.add_argument(
        "--include-historical", action="store_true", help="Include non-live log rows."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trades = load_trades(
        args.log_path,
        hours=args.hours,
        session_id=args.session_id,
        limit=args.limit,
        include_historical=args.include_historical,
    )
    print(json.dumps(trades, indent=2))
    return 0


def load_trades(
    log_path: Path,
    *,
    hours: float | None,
    session_id: str | None,
    limit: int,
    include_historical: bool = False,
) -> list[dict[str, Any]]:
    if not log_path.exists():
        raise FileNotFoundError(f"Log file {log_path} not found.")
    cutoff = None
    if hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(hours, 0.0))
    open_positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            timestamp = (
                _parse_timestamp(row["timestamp"]) if row.get("timestamp") else None
            )
            if timestamp is None:
                continue
            row_mode = (row.get("data_mode") or "live").strip().lower() or "live"
            if not include_historical and row_mode != "live":
                continue
            row_session = (row.get("session_id") or "").strip()
            if session_id and row_session != session_id:
                continue
            row_strategy = (
                row.get("strategy_id") or row.get("strategy_tag") or DEFAULT_STRATEGY_ID
            ).strip()
            event = row.get("event")
            ticket = row.get("ticket") or ""
            price = _safe_float(row.get("price"))
            volume = _safe_float(row.get("volume"))
            if event == "OPEN" and price is not None and volume is not None:
                open_positions[ticket] = {
                    "symbol": row.get("symbol", ""),
                    "direction": row.get("direction", ""),
                    "price": price,
                    "volume": volume,
                    "signal_reason": row.get("signal_reason", ""),
                    "session_id": row_session,
                    "strategy_id": row_strategy,
                }
                continue
            if event == "CLOSE" and price is not None:
                if cutoff and timestamp < cutoff:
                    continue
                entry = open_positions.pop(ticket, None)
                if not entry:
                    continue
                pnl = _pnl_from_prices(
                    entry["symbol"],
                    entry["direction"],
                    entry["price"],
                    price,
                    entry["volume"],
                )
                trade_entry = {
                    "timestamp": timestamp.isoformat(),
                    "session_id": row_session or entry.get("session_id", ""),
                    "symbol": entry["symbol"],
                    "direction": entry["direction"],
                    "volume": entry["volume"],
                    "pnl": pnl,
                    "signal_reason": entry.get("signal_reason", ""),
                    "strategy_id": entry.get("strategy_id")
                    or row_strategy
                    or DEFAULT_STRATEGY_ID,
                }
                trades.append(trade_entry)
    trades.sort(key=lambda item: item["timestamp"], reverse=True)
    return trades[: max(0, limit)]


def _pnl_from_prices(
    symbol: str, direction: str, entry_price: float, exit_price: float, volume: float
) -> float:
    meta = get_symbol_meta(symbol)
    pip_distance = (exit_price - entry_price) / meta.pip_size
    if direction == "short":
        pip_distance = -pip_distance
    return pip_distance * meta.pip_value_per_standard_lot * volume


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


if __name__ == "__main__":
    raise SystemExit(main())
