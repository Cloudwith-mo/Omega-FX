from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.constants import DEFAULT_STRATEGY_ID
from core.mt5_state import fetch_open_positions_snapshot
from scripts.run_daily_exec_report import (
    DEFAULT_SUMMARY_PATH,
    _summarize_window,
    read_latest_risk_env,
    read_latest_risk_tier,
)

DEFAULT_LOG_PATH = Path("results/mt5_demo_exec_log.csv")
DEFAULT_SNAPSHOT_PATH = Path("results/notification_snapshot_demo.txt")
RECONCILIATION_EPSILON = 1.0

STRATEGY_FAMILY_HINTS = {
    "OMEGA_M15_TF1": "trend",
    "OMEGA_MR_M15": "mean_reversion",
    "OMEGA_SESSION_LDN_M15": "session_momentum",
}


def _infer_strategy_family(strategy_id: str) -> str:
    return STRATEGY_FAMILY_HINTS.get(strategy_id, "unknown")


def load_summary(path: Path = DEFAULT_SUMMARY_PATH) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def read_snapshot(path: Path = DEFAULT_SNAPSHOT_PATH) -> str:
    return path.read_text().strip() if path.exists() else ""


def compute_report_stats(
    *,
    hours: float,
    log_path: Path = DEFAULT_LOG_PATH,
    session_id: str | None = None,
    session_only: bool = False,
    include_historical: bool = False,
    summary_data: dict[str, Any] | None = None,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, Any]:
    if not log_path.exists():
        raise FileNotFoundError(f"Execution log not found at {log_path}")
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=max(hours, 0.0))
    summary_source = summary_data
    if summary_source is None and (session_only or session_id):
        candidate = load_summary(summary_path)
        if candidate and (
            session_id is None or candidate.get("session_id") == session_id
        ):
            summary_source = candidate
    return _summarize_window(
        log_path,
        window_start,
        window_end,
        session_id=session_id,
        summary_data=summary_source,
        session_only=session_only,
        include_historical=include_historical,
    )


def build_status_payload(
    *,
    hours: float = 24.0,
    log_path: Path = DEFAULT_LOG_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    include_historical: bool = False,
) -> dict[str, Any]:
    summary = load_summary(summary_path)
    stats = compute_report_stats(
        hours=hours,
        log_path=log_path,
        include_historical=include_historical,
        summary_path=summary_path,
    )
    open_positions = fetch_open_positions_snapshot()

    def _pick(*values: Any) -> Any:
        for candidate in values:
            if candidate is not None:
                return candidate
        return None

    session_start_equity = _pick(
        summary.get("session_start_equity"),
        summary.get("starting_equity"),
        summary.get("initial_equity"),
        stats.get("start_equity"),
        0.0,
    )
    session_start_equity = float(session_start_equity or 0.0)
    session_end_equity = _pick(
        summary.get("session_end_equity"),
        summary.get("ending_equity"),
        summary.get("final_equity"),
        stats.get("end_equity"),
        session_start_equity,
    )
    session_end_equity = float(
        session_end_equity if session_end_equity is not None else session_start_equity
    )
    session_pnl = summary.get("session_pnl")
    if session_pnl is None:
        session_pnl = session_end_equity - session_start_equity
    synthetic_equity = stats.get("end_equity", 0.0)
    balance_start = _pick(
        summary.get("starting_balance"),
        summary.get("session_start_balance"),
        session_start_equity,
        0.0,
    )
    balance_start = float(balance_start or 0.0)
    balance_end = _pick(
        summary.get("ending_balance"),
        summary.get("session_end_balance"),
    )
    if balance_end is None:
        balance_delta = summary.get("session_balance_pnl")
        if balance_delta is None:
            balance_delta = stats.get("balance_pnl", stats.get("pnl", 0.0))
        balance_end = balance_start + float(balance_delta or 0.0)
    balance_end = float(balance_end)
    balance_pnl = balance_end - balance_start
    balance_pnl_pct = (balance_pnl / balance_start) if balance_start else 0.0
    reconciliation = _build_reconciliation_payload(
        summary=summary,
        log_path=log_path,
        include_historical=include_historical,
        balance_start=balance_start,
        balance_end=balance_end,
    )
    latest_session_id = summary.get("session_id")
    session_stats = None
    if latest_session_id:
        try:
            session_stats = compute_report_stats(
                hours=hours,
                log_path=log_path,
                session_id=latest_session_id,
                session_only=True,
                include_historical=include_historical,
                summary_data=summary,
                summary_path=summary_path,
            )
        except FileNotFoundError:
            session_stats = None
    expected_latest = (
        summary.get("active_strategies")
        or (session_stats.get("active_strategies") if session_stats else None)
        or [DEFAULT_STRATEGY_ID]
    )
    strategy_breakdown_latest = build_strategy_breakdown_entries(
        summary.get("per_strategy"),
        session_stats.get("strategy_breakdown") if session_stats else None,
        expected_ids=list(dict.fromkeys(expected_latest)),
    )
    expected_report = stats.get("active_strategies") or [DEFAULT_STRATEGY_ID]
    strategy_breakdown_report = build_strategy_breakdown_entries(
        stats.get("strategy_breakdown"),
        expected_ids=list(dict.fromkeys(expected_report)),
    )
    primary_strategy_id = summary.get("strategy_id") or (
        strategy_breakdown_latest[0]["strategy_id"]
        if strategy_breakdown_latest
        else DEFAULT_STRATEGY_ID
    )
    payload = {
        "equity": session_end_equity,
        "account_equity": session_end_equity,
        "synthetic_equity": synthetic_equity,
        "session_start_equity": session_start_equity,
        "session_end_equity": session_end_equity,
        "session_pnl": session_pnl,
        "account_balance": balance_end,
        "balance_start": balance_start,
        "balance_end": balance_end,
        "balance_pnl": balance_pnl,
        "balance_pnl_pct": balance_pnl_pct,
        "tier": summary.get("risk_tier") or read_latest_risk_tier(summary_path),
        "env": summary.get("risk_env") or read_latest_risk_env(summary_path),
        "session_id": summary.get("session_id", "unknown"),
        "strategy_id": primary_strategy_id,
        "last_24h_pnl": stats.get("pnl", 0.0),
        "last_24h_pnl_pct": stats.get("pnl_pct", 0.0),
        "last_24h_trades": stats.get("trades", 0),
        "last_24h_win_rate": stats.get("win_rate", 0.0),
        "filter_counts": stats.get("filters", {}),
        "snapshot": read_snapshot(snapshot_path),
        "strategy_breakdown_latest": strategy_breakdown_latest,
        "strategy_breakdown_report": strategy_breakdown_report,
        "strategy_breakdown": strategy_breakdown_latest,
        "open_positions": open_positions,
        "reconciliation": reconciliation,
    }
    return payload


def _build_reconciliation_payload(
    *,
    summary: dict[str, Any],
    log_path: Path,
    include_historical: bool,
    balance_start: float,
    balance_end: float,
) -> dict[str, Any]:
    session_id = summary.get("session_id")
    if not session_id:
        return {
            "session_id": "",
            "balance_delta": 0.0,
            "logged_balance_pnl": 0.0,
            "difference": 0.0,
            "ok": True,
        }
    session_stats = compute_report_stats(
        hours=24.0,
        log_path=log_path,
        session_id=session_id,
        session_only=True,
        include_historical=include_historical,
    )
    logged_balance_pnl = session_stats.get("balance_pnl", 0.0)
    balance_delta = balance_end - balance_start
    difference = balance_delta - logged_balance_pnl
    return {
        "session_id": session_id,
        "balance_delta": balance_delta,
        "logged_balance_pnl": logged_balance_pnl,
        "difference": difference,
        "ok": abs(difference) <= RECONCILIATION_EPSILON,
    }


def build_strategy_breakdown_entries(
    *sources: Any, expected_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not source:
            continue
        if isinstance(source, dict):
            items = list(source.items())
        elif isinstance(source, list):
            items = [(entry.get("strategy_id"), entry) for entry in source]
        else:
            continue
        for strategy_id, entry in items:
            if not strategy_id:
                continue
            buckets[strategy_id] = _coerce_strategy_entry(str(strategy_id), entry)
    if expected_ids:
        ordered = []
        for sid in expected_ids:
            sid = (sid or "").strip()
            if not sid:
                continue
            ordered.append(sid)
        for sid in ordered:
            buckets.setdefault(sid, _coerce_strategy_entry(sid, {}))
    if not buckets:
        buckets[DEFAULT_STRATEGY_ID] = _coerce_strategy_entry(DEFAULT_STRATEGY_ID, {})
    return sorted(buckets.values(), key=lambda row: row["strategy_id"])


def _coerce_strategy_entry(strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    trades = int(payload.get("trades", 0) or 0)
    wins_value = payload.get("wins")
    win_rate_value = payload.get("win_rate")
    if wins_value is None and win_rate_value is not None and trades:
        wins_value = int(round(float(win_rate_value) * trades))
    wins = int(wins_value or 0)
    losses_value = payload.get("losses")
    if losses_value is None:
        losses_value = trades - wins if trades >= wins else 0
    losses = int(losses_value or 0)
    pnl_value = float(payload.get("pnl", 0.0) or 0.0)
    avg_value = payload.get("avg_pnl_per_trade")
    if avg_value is None:
        avg_value = payload.get("avg_pnl")
    if avg_value is None:
        avg_value = (pnl_value / trades) if trades else 0.0
    avg_pnl = float(avg_value or 0.0)
    if win_rate_value is None:
        win_rate_value = (wins / trades) if trades else 0.0
    win_rate = float(win_rate_value or 0.0)
    family = str(payload.get("family") or _infer_strategy_family(strategy_id))
    return {
        "strategy_id": strategy_id,
        "family": family,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "pnl": pnl_value,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
    }


def serialize_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for trade in trades:
        row = dict(trade)
        ts = row.get("timestamp")
        if isinstance(ts, datetime):
            row["timestamp"] = ts.isoformat()
        serialized.append(row)
    return serialized


def build_report_payload(
    *,
    hours: float = 24.0,
    log_path: Path = DEFAULT_LOG_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    session_id: str | None = None,
    session_only: bool = False,
    include_historical: bool = False,
) -> dict[str, Any]:
    summary = load_summary(summary_path)
    stats = compute_report_stats(
        hours=hours,
        log_path=log_path,
        session_id=session_id,
        session_only=session_only,
        include_historical=include_historical,
        summary_path=summary_path,
    )
    tier = read_latest_risk_tier(summary_path)
    env_label = read_latest_risk_env(summary_path)
    window_start = stats.get("window_start")
    window_end = stats.get("window_end")
    expected_report = stats.get("active_strategies") or (
        summary.get("active_strategies") if summary else None
    )
    strategy_breakdown_report = build_strategy_breakdown_entries(
        stats.get("strategy_breakdown"),
        expected_ids=list(dict.fromkeys(expected_report or [DEFAULT_STRATEGY_ID])),
    )
    primary_strategy_id = stats.get("strategy_id") or (
        strategy_breakdown_report[0]["strategy_id"]
        if strategy_breakdown_report
        else DEFAULT_STRATEGY_ID
    )
    payload = {
        "window_start": window_start.isoformat()
        if isinstance(window_start, datetime)
        else str(window_start),
        "window_end": window_end.isoformat()
        if isinstance(window_end, datetime)
        else str(window_end),
        "start_equity": stats.get("start_equity", 0.0),
        "end_equity": stats.get("end_equity", 0.0),
        "pnl": stats.get("pnl", 0.0),
        "pnl_pct": stats.get("pnl_pct", 0.0),
        "start_balance": stats.get(
            "start_balance", stats.get("start_equity", 0.0)
        ),
        "end_balance": stats.get("end_balance", stats.get("end_equity", 0.0)),
        "balance_pnl": stats.get("balance_pnl", stats.get("pnl", 0.0)),
        "balance_pnl_pct": stats.get("balance_pnl_pct", 0.0),
        "closed_trades": stats.get("trades", 0),
        "win_rate": stats.get("win_rate", 0.0),
        "filter_counts": stats.get("filters", {}),
        "risk_tier": tier,
        "environment": env_label,
        "session_id": stats.get("session_id") or session_id or "",
        "strategy_id": primary_strategy_id,
        "last_trades": serialize_trades(stats.get("last_trades") or []),
        "strategy_breakdown_report": strategy_breakdown_report,
        "strategy_breakdown": strategy_breakdown_report,
    }
    return payload
