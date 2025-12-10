#!/usr/bin/env python3
"""Streamlit dashboard for OmegaFX monitoring."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

THIS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:  # pragma: no cover - CLI entry
    sys.path.insert(0, REPO_ROOT)

from core.monitoring_helpers import (  # noqa: E402
    DEFAULT_LOG_PATH,
    DEFAULT_SUMMARY_PATH,
    build_report_payload,
    build_status_payload,
)
from scripts.query_last_trades import load_trades  # noqa: E402
from scripts.run_daily_exec_report import read_latest_session_id  # noqa: E402

BACKTEST_SUMMARY_PATH = Path("results/minimal_ftmo_eval_summary.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_backtest_summary() -> dict[str, Any]:
    if BACKTEST_SUMMARY_PATH.exists():
        try:
            return json.loads(BACKTEST_SUMMARY_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _format_currency(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.2f}"


def _metric_variant(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _strategy_breakdown_df(data: Any) -> pd.DataFrame:
    columns = [
        "strategy_id",
        "family",
        "trades",
        "wins",
        "losses",
        "win_rate",
        "pnl",
        "avg_pnl",
    ]
    if not data:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        iterable = list(data.items())
    else:
        iterable = [(entry.get("strategy_id"), entry) for entry in data]
    for strategy_id, entry in iterable:
        if not strategy_id:
            continue
        win_rate = float(entry.get("win_rate", 0.0) or 0.0) * 100
        rows.append(
            {
                "strategy_id": strategy_id,
                "family": entry.get("family", "-"),
                "trades": int(entry.get("trades", 0) or 0),
                "wins": int(entry.get("wins", 0) or 0),
                "losses": int(entry.get("losses", 0) or 0),
                "win_rate": win_rate,
                "pnl": float(entry.get("pnl", 0.0) or 0.0),
                "avg_pnl": float(
                    entry.get("avg_pnl", entry.get("avg_pnl_per_trade", 0.0)) or 0.0
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _apply_theme() -> None:
    st.set_page_config(
        page_title="OmegaFX Cockpit", layout="wide", initial_sidebar_state="collapsed"
    )
    st.markdown(
        """
        <style>
            .stApp { background-color: #050a0f; color: #f5f5f5; }
            div.block-container { padding-top: 1.5rem; }
            .metric-card { background-color: #111827; padding: 0.9rem 1.2rem; border-radius: 0.8rem; margin-bottom: 0.6rem; border: 1px solid #1f2937; }
            .metric-card .metric-label { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.08em; }
            .metric-card .metric-value { font-size: 1.6rem; font-weight: 600; color: #f8fafc; }
            .metric-card .metric-sub { font-size: 0.9rem; color: #cbd5f5; }
            .metric-card.positive { border-color: #10b981; }
            .metric-card.negative { border-color: #ef4444; }
            .status-strip { background-color: #111827; border-radius: 0.6rem; padding: 0.6rem 1rem; margin-bottom: 1rem; }
            .status-pill { background-color: #1f2937; border-radius: 999px; padding: 0.3rem 0.8rem; display: inline-block; font-size: 0.85rem; }
            .details-container { background-color: #0b1522; padding: 0.8rem 1rem; border-radius: 0.8rem; border: 1px solid #1f2937; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_card(
    column,
    label: str,
    value: str,
    *,
    subtitle: str | None = None,
    variant: str = "neutral",
) -> None:
    subtitle_html = f"<div class='metric-sub'>{subtitle}</div>" if subtitle else ""
    column.markdown(
        f"<div class='metric-card {variant}'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div>{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def _render_status_strip(status: dict[str, Any]) -> None:
    pnl = status.get("last_24h_pnl", 0.0)
    pnl_pct = status.get("last_24h_pnl_pct", 0.0) * 100
    trades = status.get("last_24h_trades", 0)
    win_rate = status.get("last_24h_win_rate", 0.0) * 100
    filters = status.get("filter_counts", {})
    filter_line = (
        "Filters (24h): max_pos {mp} / daily_loss {dl} / invalid {inv}".format(
            mp=filters.get("filtered_max_positions", 0),
            dl=filters.get("filtered_daily_loss", 0),
            inv=filters.get("filtered_invalid_stops", 0),
        )
    )
    strip = st.container()
    with strip:
        cols = st.columns([1, 1, 1, 1.5])
        cols[0].metric(
            "24h PnL", f"{pnl:+,.2f}", f"{pnl_pct:+.2f}%", delta_color="normal"
        )
        cols[1].metric("24h Trades", trades)
        cols[2].metric("24h Win %", f"{win_rate:.1f}%")
        cols[3].markdown(
            f"<div class='status-strip'><span class='status-pill'>{filter_line}</span></div>",
            unsafe_allow_html=True,
        )


def _render_details_section(
    *,
    status: dict[str, Any],
    report_stats: dict[str, Any],
    include_historical: bool,
    target_session: str,
    backtest_summary: dict[str, Any],
) -> None:
    with st.expander("Details", expanded=False):
        st.markdown("### Strategy breakdown (latest session)")
        latest_df = _strategy_breakdown_df(
            status.get("strategy_breakdown_latest") or status.get("strategy_breakdown")
        )
        if latest_df.empty:
            st.info("No strategy data for the latest session.")
        else:
            st.dataframe(latest_df)

        st.markdown("### Strategy breakdown (report window)")
        report_df = _strategy_breakdown_df(
            report_stats.get("strategy_breakdown_report")
            or report_stats.get("strategy_breakdown")
        )
        if report_df.empty:
            st.info("No strategy data for this report window.")
        else:
            st.dataframe(report_df)

        st.markdown("### Filter Counts")
        filters = status.get("filter_counts", {})
        st.dataframe(pd.DataFrame.from_dict(filters, orient="index", columns=["count"]))

        st.markdown("### Last N trades")
        trade_count = st.slider(
            "Trades to display", min_value=5, max_value=50, value=10, step=5
        )
        trades = load_trades(
            DEFAULT_LOG_PATH,
            hours=168.0,
            session_id=target_session or None,
            limit=trade_count,
            include_historical=include_historical,
        )
        if trades:
            st.dataframe(pd.DataFrame(trades))
        else:
            st.info("No trades for the selected session.")

        st.markdown("### Sim vs Live")
        live_win = report_stats.get("win_rate", 0.0)
        live_trades = report_stats.get("closed_trades", report_stats.get("trades", 0))
        live_avg_pnl = (
            report_stats.get("pnl", 0.0) / live_trades if live_trades else 0.0
        )
        comparison = pd.DataFrame(
            [
                {
                    "Metric": "Win rate",
                    "Backtest": f"{(backtest_summary.get('win_rate', 0.0) or 0) * 100:.1f}%",
                    "Live": f"{live_win * 100:.1f}%",
                },
                {
                    "Metric": "Avg PnL/trade",
                    "Backtest": f"{backtest_summary.get('average_pnl_per_trade', 0.0):,.2f}",
                    "Live": f"{live_avg_pnl:,.2f}",
                },
            ]
        )
        st.table(comparison)

        with st.expander("Raw report payload"):
            st.json(report_stats)


def _render_cockpit(status: dict[str, Any], reconciliation: dict[str, Any]) -> None:
    st.subheader("Cockpit")
    session_id = status.get("session_id", "unknown")
    open_positions = status.get("open_positions", {})
    open_error = open_positions.get("error")
    open_count = open_positions.get("count", 0)
    open_pnl = float(open_positions.get("total_pnl", 0.0) or 0.0)

    row_one = st.columns(4)
    _render_card(row_one[0], "Environment", str(status.get("env", "-")).upper())
    _render_card(row_one[1], "Risk tier", str(status.get("tier", "-")).title())
    _render_card(row_one[2], "Session", session_id)
    _render_card(
        row_one[3],
        "Open positions",
        str(open_count),
        subtitle=f"Open PnL {open_pnl:+,.2f}",
        variant=_metric_variant(open_pnl),
    )
    if open_error:
        st.warning(f"Open position snapshot unavailable: {open_error}")

    row_two = st.columns(4)
    start_equity = status.get("session_start_equity", 0.0)
    end_equity = status.get("session_end_equity", 0.0)
    equity_pnl = status.get("session_pnl", 0.0)
    balance_pnl = status.get("balance_pnl", 0.0)
    equity_pct = (equity_pnl / start_equity * 100) if start_equity else 0.0
    balance_pct = status.get("balance_pnl_pct", 0.0) * 100
    _render_card(row_two[0], "Start equity", _format_currency(start_equity))
    _render_card(row_two[1], "End equity", _format_currency(end_equity))
    _render_card(
        row_two[2],
        "Equity PnL",
        f"{equity_pnl:+,.2f}",
        subtitle=f"{equity_pct:+.2f}%",
        variant=_metric_variant(equity_pnl),
    )
    _render_card(
        row_two[3],
        "Balance PnL",
        f"{balance_pnl:+,.2f}",
        subtitle=f"{balance_pct:+.2f}%",
        variant=_metric_variant(balance_pnl),
    )

    if reconciliation and not reconciliation.get("ok", True):
        diff = reconciliation.get("difference", 0.0)
        st.error(f"? Reconciliation mismatch detected (? {diff:+.2f}).")


def main() -> None:
    _apply_theme()
    include_historical = st.sidebar.checkbox("Include historical rows", value=False)
    latest_session = read_latest_session_id(DEFAULT_SUMMARY_PATH)
    focus_latest = st.sidebar.checkbox("Use latest session", value=True)
    custom_session = st.sidebar.text_input("Custom session id", latest_session)
    target_session = latest_session if focus_latest else custom_session.strip()
    session_only = bool(target_session)

    status_payload = build_status_payload(
        hours=24.0,
        log_path=DEFAULT_LOG_PATH,
        summary_path=DEFAULT_SUMMARY_PATH,
        include_historical=include_historical,
    )
    report_stats = build_report_payload(
        hours=24.0,
        log_path=DEFAULT_LOG_PATH,
        summary_path=DEFAULT_SUMMARY_PATH,
        session_id=target_session if session_only else None,
        session_only=session_only,
        include_historical=include_historical,
    )

    _render_cockpit(status_payload, status_payload.get("reconciliation", {}))
    st.subheader("24h Health Strip")
    _render_status_strip(status_payload)
    backtest_summary = load_backtest_summary()
    _render_details_section(
        status=status_payload,
        report_stats=report_stats,
        include_historical=include_historical,
        target_session=target_session,
        backtest_summary=backtest_summary,
    )

    st.caption(
        "OmegaFX numbers reflect trades tagged by the strategy; MT5 account balances may include manual or other EA activity."
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
    except Exception:  # pragma: no cover - Streamlit fallback
        ctx = None
    if ctx is None:
        from streamlit.web import bootstrap

        bootstrap.run(__file__, "", [])
    else:
        main()
