#!/usr/bin/env python3
"""Generate richly formatted execution reports over rolling windows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - CLI entry point
    sys.path.insert(0, str(REPO_ROOT))

from core.position_sizing import get_symbol_meta  # noqa: E402
from core.constants import DEFAULT_STRATEGY_ID  # noqa: E402

DEFAULT_SUMMARY_PATH = Path("results/mt5_demo_exec_live_summary.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MT5 execution reports for arbitrary windows.")
    parser.add_argument("--log_path", type=Path, default=Path("results/mt5_demo_exec_log.csv"))
    parser.add_argument("--hours", type=float, default=24.0, help="Rolling window size in hours.")
    parser.add_argument("--tag", type=str, default="demo", help="Label used in the report filename.")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional explicit markdown output path. When omitted a default is used.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="Live summary JSON path used to infer the latest risk tier.",
    )
    parser.add_argument("--risk-tier", type=str, default=None, help="Override risk tier label in the report.")
    parser.add_argument("--session-id", type=str, default=None, help="Filter log rows to a session id.")
    parser.add_argument(
        "--use-latest-session",
        action="store_true",
        help="Ignore the time window and focus on the latest recorded session.",
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Include historical (non-live) log rows when computing the report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    risk_tier = args.risk_tier or read_latest_risk_tier(args.summary_path)
    env_label = read_latest_risk_env(args.summary_path)
    session_filter = args.session_id
    session_only = False
    if args.use_latest_session:
        session_filter = session_filter or read_latest_session_id(args.summary_path)
        session_only = bool(session_filter)
    report_path = generate_exec_report(
        log_path=args.log_path,
        hours=args.hours,
        tag=args.tag,
        output_path=args.output_path,
        risk_tier=risk_tier,
        session_id=session_filter,
        risk_env=env_label,
        session_only=session_only,
        include_historical=args.include_historical,
    )
    print(f"Wrote report to {report_path}")
    return 0


def generate_exec_report(
    log_path: Path,
    hours: float,
    tag: str,
    output_path: Path | None = None,
    *,
    risk_tier: str | None = None,
    session_id: str | None = None,
    risk_env: str | None = None,
    session_only: bool = False,
    include_historical: bool = False,
) -> Path:
    """Create a markdown report for an execution log window."""
    if not log_path.exists():
        raise FileNotFoundError(f"Log file {log_path} not found.")
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=max(hours, 0.0))
    summary_data = None
    if session_only or session_id:
        candidate = _load_summary_data()
        if candidate and (session_id is None or candidate.get("session_id") == session_id):
            summary_data = candidate
    stats = _summarize_window(
        log_path,
        window_start,
        window_end,
        session_id=session_id,
        summary_data=summary_data,
        session_only=session_only,
        include_historical=include_historical,
    )
    tier_label = risk_tier or read_latest_risk_tier()
    env_label = risk_env or read_latest_risk_env()
    session_label = stats.get('session_id') or session_id or read_latest_session_id()

    stats["risk_env"] = env_label
    report_path = output_path or _default_report_path(tag, hours, window_end)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {tag.upper()} Execution Report ({hours:g}h)",
        "",
        f"- Window start (UTC): {stats['window_start'].isoformat()}",
        f"- Window end   (UTC): {stats['window_end'].isoformat()}",
        f"- Start equity: {stats['start_equity']:.2f}",
        f"- End equity: {stats['end_equity']:.2f}",
        f"- PnL: {stats['pnl']:.2f}",
        f"- PnL %: {stats['pnl_pct']:.2%}",
        f"- Start balance: {stats['start_balance']:.2f}",
        f"- End balance: {stats['end_balance']:.2f}",
        f"- Balance PnL: {stats['balance_pnl']:.2f} ({stats['balance_pnl_pct']:.2%})",
        f"- Closed trades: {stats['trades']}",
        f"- Win rate: {stats['win_rate']:.1%}",
        f"- Risk tier: {tier_label}",
        f"- Environment: {env_label}",
        f"- Session id: {session_label}",
        f"- Strategy id: {stats.get('strategy_id', 'unknown')}",
        "",
        "## Filter Counts",
        f"- filtered_max_positions: {stats['filters']['filtered_max_positions']}",
        f"- filtered_daily_loss: {stats['filters']['filtered_daily_loss']}",
        f"- filtered_invalid_stops: {stats['filters']['filtered_invalid_stops']}",
    ]
    trades_rows = stats.get("last_trades") or []
    lines.append("")
    lines.append("## Last 10 trades in window")
    lines.append("")
    if trades_rows:
        lines.append("| Timestamp | Session | Strategy | Symbol | Direction | Volume | PnL | Signal Reason |")
        lines.append("| --- | --- | --- | --- | --- | ---: | ---: | --- |")
        for trade in trades_rows:
            ts = trade.get("timestamp")
            ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
            lines.append(
                f"| {ts_str} | {trade.get('session_id', '')} | {trade.get('strategy_id', '')} | {trade.get('symbol', '')} | "
                f"{trade.get('direction', '')} | {float(trade.get('volume', 0.0)):.2f} | "
                f"{float(trade.get('pnl', 0.0)):.2f} | {trade.get('signal_reason', '')} |"
            )
    else:
        lines.append("No trades in this window.")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _default_report_path(tag: str, hours: float, window_end: datetime) -> Path:
    if float(int(hours)) == float(hours):
        hours_label = str(int(hours))
    else:
        hours_label = str(hours).replace(".", "p")
    filename = f"exec_report_{tag}_{hours_label}h_{window_end.strftime('%Y%m%d%H%M')}.md"
    return Path("results") / filename


def _summarize_window(
    log_path: Path,
    window_start: datetime,
    window_end: datetime,
    *,
    session_id: str | None = None,
    summary_data: dict | None = None,
    session_only: bool = False,
    include_historical: bool = False,
) -> dict:
    open_positions: dict[str, dict] = {}
    raw_filter_counts: dict[str, int] = defaultdict(int)
    trade_results: list[float] = []
    last_trades: list[dict] = []
    equity_points: list[tuple[datetime, float]] = []
    prior_equity: float | None = None
    post_window_equity: float | None = None
    session_filter = session_id
    last_session_id: str | None = None
    last_strategy_id: str | None = None
    strategy_stats: dict[str, dict[str, float]] = {}

    with log_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            timestamp = _parse_timestamp(row["timestamp"])
            ticket = row["ticket"]
            event = row["event"]
            price = _safe_float(row.get("price"))
            volume = _safe_float(row.get("volume"))
            equity = _safe_float(row.get("equity"))

            row_session = (row.get("session_id") or "").strip()
            row_mode = (row.get("data_mode") or "live").strip().lower() or "live"
            if not include_historical and row_mode != "live":
                continue
            row_strategy = (row.get("strategy_id") or row.get("strategy_tag") or DEFAULT_STRATEGY_ID).strip()
            if row_strategy:
                last_strategy_id = row_strategy

            if equity is not None:
                if timestamp < window_start and (not session_filter or row_session == session_filter):
                    prior_equity = equity
                elif (
                    timestamp > window_end
                    and post_window_equity is None
                    and (not session_filter or row_session == session_filter)
                ):
                    post_window_equity = equity

            if event == "OPEN" and price is not None and volume is not None:
                open_positions[ticket] = {
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "volume": volume,
                    "price": price,
                    "session_id": row_session,
                    "signal_reason": row.get("signal_reason", ""),
                    "strategy_id": row_strategy or DEFAULT_STRATEGY_ID,
                }
            entry_record = open_positions.pop(ticket, None) if event == "CLOSE" else None

            if not session_only and not (window_start <= timestamp <= window_end):
                continue
            if session_filter and row_session != session_filter:
                continue
            if row_session:
                last_session_id = row_session

            if equity is not None:
                equity_points.append((timestamp, equity))
            if event == "FILTER":
                raw_filter_counts[row.get("reason", "").strip() or "unknown"] += 1
            elif event == "CLOSE" and price is not None and entry_record:
                trade_pnl = _pnl_from_prices(
                    entry_record["symbol"],
                    entry_record["direction"],
                    entry_record["price"],
                    price,
                    entry_record["volume"],
                )
                trade_results.append(trade_pnl)
                trade_session = row_session or entry_record.get("session_id", "")
                strategy_id = row_strategy or entry_record.get("strategy_id") or DEFAULT_STRATEGY_ID
                entry_record["strategy_id"] = strategy_id
                last_trades.append(
                    {
                        "timestamp": timestamp,
                        "session_id": trade_session,
                        "symbol": entry_record["symbol"],
                        "direction": entry_record["direction"],
                        "volume": entry_record["volume"],
                        "pnl": trade_pnl,
                        "signal_reason": entry_record.get("signal_reason", ""),
                        "strategy_id": strategy_id,
                    }
                )
                bucket = strategy_stats.setdefault(strategy_id, {"trades": 0, "wins": 0, "pnl": 0.0})
                bucket["trades"] += 1
                bucket["pnl"] += trade_pnl
                if trade_pnl > 0:
                    bucket["wins"] += 1

    if last_trades:
        last_trades = last_trades[-10:]

    total_pnl = sum(trade_results)
    session_summary = None
    if summary_data and (not session_filter or summary_data.get("session_id") == session_filter):
        session_summary = summary_data

    if session_only and session_summary:
        start_equity = float(
            session_summary.get("session_start_equity")
            or session_summary.get("initial_equity")
            or prior_equity
            or 0.0
        )
        end_equity = float(
            session_summary.get("session_end_equity")
            or (start_equity + total_pnl)
        )
    else:
        equity_points.sort(key=lambda item: item[0])
        if equity_points:
            start_equity = equity_points[0][1]
            end_equity = equity_points[-1][1]
        else:
            start_equity = prior_equity if prior_equity is not None else 0.0
            end_equity = post_window_equity if post_window_equity is not None else start_equity

    pnl = end_equity - start_equity
    pnl_pct = (pnl / start_equity) if start_equity else 0.0

    if session_summary and session_summary.get("starting_balance") is not None:
        start_balance = float(session_summary.get("starting_balance"))
    else:
        start_balance = start_equity
    if session_summary and session_summary.get("ending_balance") is not None:
        end_balance = float(session_summary.get("ending_balance"))
    else:
        fallback_balance = start_balance + (session_summary.get("session_balance_pnl") if session_summary else pnl)
        end_balance = float(fallback_balance)
    balance_pnl = end_balance - start_balance
    balance_pnl_pct = (balance_pnl / start_balance) if start_balance else 0.0
    wins = sum(1 for pnl_value in trade_results if pnl_value > 0)
    win_rate = wins / len(trade_results) if trade_results else 0.0

    filters = {
        "filtered_max_positions": raw_filter_counts.get("max_positions", 0),
        "filtered_daily_loss": raw_filter_counts.get("daily_loss", 0),
        "filtered_invalid_stops": raw_filter_counts.get("invalid_stops", 0),
    }

    strategy_breakdown: dict[str, dict[str, float]] = {}
    for strategy_id, bucket in strategy_stats.items():
        trades = bucket["trades"]
        wins_value = bucket.get("wins", 0)
        pnl_value = bucket.get("pnl", 0.0)
        strategy_breakdown[strategy_id] = {
            "trades": trades,
            "win_rate": (wins_value / trades) if trades else 0.0,
            "pnl": pnl_value,
            "avg_pnl_per_trade": (pnl_value / trades) if trades else 0.0,
        }

    if not strategy_breakdown and session_summary and session_summary.get("per_strategy"):
        for strategy_id, entry in session_summary.get("per_strategy", {}).items():
            trades = int(entry.get("trades", 0))
            pnl_value = float(entry.get("pnl", 0.0) or 0.0)
            win_rate_value = float(entry.get("win_rate", 0.0) or 0.0)
            avg_value = float(entry.get("avg_pnl_per_trade", 0.0) or 0.0)
            strategy_breakdown[strategy_id] = {
                "trades": trades,
                "win_rate": win_rate_value,
                "pnl": pnl_value,
                "avg_pnl_per_trade": avg_value,
            }

    strategy_id_value = ""
    if session_summary and session_summary.get("strategy_id"):
        strategy_id_value = str(session_summary.get("strategy_id"))
    elif strategy_breakdown:
        strategy_id_value = next(iter(strategy_breakdown.keys()))
    elif last_strategy_id:
        strategy_id_value = last_strategy_id
    else:
        strategy_id_value = DEFAULT_STRATEGY_ID

    return {
        "window_start": window_start,
        "window_end": window_end,
        "start_equity": start_equity,
        "end_equity": end_equity,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "trades": len(trade_results),
        "win_rate": win_rate,
        "filters": filters,
        "session_id": session_filter or last_session_id or "",
        "strategy_id": strategy_id_value,
        "strategy_breakdown": strategy_breakdown,
        "last_trades": last_trades,
        "start_balance": start_balance,
        "end_balance": end_balance,
        "balance_pnl": balance_pnl,
        "balance_pnl_pct": balance_pnl_pct,
    }
def _pnl_from_prices(symbol: str, direction: str, entry_price: float, exit_price: float, volume: float) -> float:
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


def read_latest_risk_tier(summary_path: Path | None = None) -> str:
    path = summary_path or DEFAULT_SUMMARY_PATH
    if not path.exists():
        return "unknown"
    try:
        data = json.loads(path.read_text())
        return str(data.get("risk_tier") or "unknown")
    except Exception:
        return "unknown"


def read_latest_session_id(summary_path: Path | None = None) -> str:
    path = summary_path or DEFAULT_SUMMARY_PATH
    if not path.exists():
        return "unknown"
    try:
        data = json.loads(path.read_text())
        return str(data.get("session_id") or "unknown")
    except Exception:
        return "unknown"


def read_latest_risk_env(summary_path: Path | None = None) -> str:
    path = summary_path or DEFAULT_SUMMARY_PATH
    if not path.exists():
        return "unknown"
    try:
        data = json.loads(path.read_text())
        return str(data.get("risk_env") or "unknown")
    except Exception:
        return "unknown"


def _load_summary_data(path: Path | None = None) -> dict:
    target = path or DEFAULT_SUMMARY_PATH
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text())
    except json.JSONDecodeError:
        return {}

if __name__ == "__main__":
    raise SystemExit(main())
