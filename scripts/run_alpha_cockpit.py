#!/usr/bin/env python3
"""OmegaFX Alpha Cockpit – dark curved HUD powered by the local API."""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def format_usd(value: float | None) -> str:
    if value is None:
        return "–"
    return f"${value:,.2f}"


@st.cache_data(ttl=10)
def fetch_status() -> dict | None:
    try:
        resp = requests.get(f"{API_BASE}/status", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=10)
def fetch_trades(limit: int = 8) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            f"{API_BASE}/trades", params={"hours": 24, "limit": limit}, timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def build_hud_metrics(status: dict) -> dict:
    account_equity = float(status.get("account_equity") or status.get("equity") or 0.0)
    synthetic_equity = float(status.get("synthetic_equity") or account_equity or 1.0)
    session_pnl = float(status.get("session_pnl", status.get("pnl", 0.0)) or 0.0)
    pnl_usd = (
        session_pnl
        if session_pnl != 0
        else float(status.get("last_24h_pnl", 0.0) or 0.0)
    )
    session_pnl_pct = (session_pnl / account_equity) if account_equity else 0.0
    daily_target_usd = 500.0
    pnl_pct_of_target = clamp(
        pnl_usd / daily_target_usd if daily_target_usd else 0, 0, 1
    )

    free_margin = float(status.get("free_margin", 0.0) or 0.0)
    if free_margin and account_equity:
        margin_fuel_pct = clamp(100 * free_margin / account_equity, 0, 100)
    else:
        open_pos = status.get("open_positions", {}).get("count", 0)
        margin_fuel_pct = clamp(100 - (open_pos * 10), 0, 100)

    max_daily_loss = status.get("max_daily_loss")
    if max_daily_loss is None:
        max_daily_loss = 0.03 * account_equity if account_equity else 1.0
    dd = max(0.0, -session_pnl)
    dd_temp_pct = clamp(100 * dd / max_daily_loss if max_daily_loss else 0, 0, 100)

    equity_load_pct = clamp(
        100 * account_equity / synthetic_equity if synthetic_equity else 0, 0, 100
    )

    win_rate = status.get("last_24h_win_rate", 0.0) * 100
    profit_factor = status.get("profit_factor")
    avg_win = status.get("avg_win")
    avg_loss = status.get("avg_loss")

    return {
        "env": status.get("env", "").upper(),
        "risk_tier": status.get("tier", "").title(),
        "session_id": status.get("session_id", ""),
        "account_equity": account_equity,
        "pnl_usd": pnl_usd,
        "pnl_pct_of_target": pnl_pct_of_target,
        "session_pnl_pct": session_pnl_pct,
        "daily_target_usd": daily_target_usd,
        "open_positions": status.get("open_positions", {}),
        "margin_fuel_pct": margin_fuel_pct,
        "dd_temp_pct": dd_temp_pct,
        "equity_load_pct": equity_load_pct,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe": status.get("sharpe", None),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def render_header(status: dict) -> None:
    reconciliation = status.get("reconciliation", {}) or {}
    ok = reconciliation.get("ok", True)
    dot_color = "#00ff9d" if ok else "#ff4d6b"
    st.markdown(
        f"""
        <div class="alpha-header">
            <div>ALPHA COCKPIT // SYS.ACTIVE</div>
            <div style="display:flex;align-items:center;gap:8px;">
                <span class="alpha-pill">ENV: {status.get("env", "-").upper()}</span>
                <span class="alpha-pill">TIER: {status.get("tier", "-")}</span>
                <span class="alpha-pill">SESSION: {status.get("session_id", "-")}</span>
                <span style="display:flex;align-items:center;gap:6px;color:#9ca3af;font-size:11px;">LATENCY: n/a <span style="width:10px;height:10px;border-radius:50%;background:{dot_color};box-shadow:0 0 10px {dot_color};"></span></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_performance_card(hud: dict) -> None:
    open_count = hud["open_positions"].get("count", 0)
    open_pnl = hud["open_positions"].get("total_pnl", 0.0)
    telemetry_rows = [
        ("Win rate", f"{hud['win_rate']:.1f}%"),
        (
            "Profit factor",
            f"{hud['profit_factor']:.2f}" if hud["profit_factor"] is not None else "–",
        ),
        (
            "Sharpe (approx)",
            f"{hud['sharpe']:.2f}" if hud["sharpe"] is not None else "–",
        ),
        ("Avg win", format_usd(hud.get("avg_win"))),
        ("Avg loss", format_usd(hud.get("avg_loss"))),
        ("Open positions", f"{open_count} ({format_usd(open_pnl)})"),
    ]
    html = (
        "<div class='alpha-card'><div class='alpha-title'>Performance Telemetry</div>"
    )
    for label, val in telemetry_rows:
        html += f"<div class='telemetry-row'><span class='telemetry-label'>{label}</span><span class='telemetry-value'>{val}</span></div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_tachometer_card(hud: dict) -> None:
    pnl_color = "#00ff9d" if hud["pnl_usd"] >= 0 else "#ff4d6b"
    pnl_sign = "+" if hud["pnl_usd"] >= 0 else "-"
    pnl_value = abs(hud["pnl_usd"])
    # map session pnl pct to -3%..+3%
    frac = hud.get("session_pnl_pct", 0.0)
    tach_frac = clamp((frac - (-0.03)) / 0.06, 0, 1)
    percent_label = hud.get("session_pnl_pct", 0.0) * 100
    html = f"""
    <div class='alpha-card' style='text-align:center;'>
      <div class='alpha-title'>Daily Net PnL</div>
      <div class='tach-value' style='color:{pnl_color};'>{pnl_sign}${pnl_value:,.2f}</div>
      <div class='tach-sub'>Δ {percent_label:+.2f}% today</div>
      <div style='margin-top:12px;'>
        <div class='tacho-ring' style='--p:{tach_frac};'></div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_system_card(hud: dict) -> None:
    health_rows = [
        ("Margin fuel", hud["margin_fuel_pct"], "amber"),
        ("DD temp", hud["dd_temp_pct"], "red"),
        ("Equity load", hud["equity_load_pct"], "green"),
    ]
    html = "<div class='alpha-card'><div class='alpha-title'>System Health</div>"
    for label, pct, tone in health_rows:
        pct_display = f"{pct:.0f}%"
        critical = " CRITICAL" if label == "DD temp" and pct >= 80 else ""
        bar_class = {
            "amber": "progress-amber",
            "red": "progress-red",
            "green": "progress-green",
        }.get(tone, "progress-green")
        html += f"<div class='statline'><span>{label}</span><span>{pct_display}{critical}</span></div>"
        html += f"<div class='progress-outer'><div class='progress-inner {bar_class}' style='width:{pct:.1f}%;'></div></div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_top_row(hud: dict) -> None:
    col_left, col_center, col_right = st.columns([1.05, 1.4, 1.05])
    with col_left:
        render_performance_card(hud)
    with col_center:
        render_tachometer_card(hud)
    with col_right:
        render_system_card(hud)


def render_transmission_log(trades: list[dict]) -> None:
    st.markdown(
        "<div class='alpha-card' style='margin-top:14px;'><div class='alpha-title'>Transmission Log // Recent Orders</div>",
        unsafe_allow_html=True,
    )
    if trades:
        df = pd.DataFrame(trades)
        rename_map = {
            "timestamp": "time",
            "symbol": "symbol",
            "direction": "side",
            "volume": "size",
            "price": "price",
            "pnl": "pnl",
            "strategy_id": "strategy",
        }
        df = df.rename(columns=rename_map)
        for col in rename_map.values():
            if col not in df.columns:
                df[col] = ""
        display_cols = ["time", "symbol", "side", "size", "price", "pnl", "strategy"]
        df = df[display_cols]

        def _color(val):
            try:
                return (
                    "color: #00ff9d"
                    if float(val) > 0
                    else ("color: #ff4d6b" if float(val) < 0 else "")
                )
            except Exception:
                return ""

        styled = df.style.applymap(lambda v: _color(v), subset=["pnl"]).hide(
            axis="index"
        )
        st.dataframe(styled, use_container_width=True, height=260)
    else:
        st.markdown(
            "<div style='padding:12px;color:#8b95a5;text-align:center;'>No recent trades</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def inject_global_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Share+Tech+Mono&display=swap');
        [data-testid="stAppViewContainer"] > .main {
            background:
                radial-gradient(circle at 50% 10%, #222 0%, #05060a 55%, #000 100%),
                repeating-linear-gradient(45deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 2px, transparent 2px, transparent 6px);
            padding: 10px 0 30px 0;
        }
        .alpha-shell {
            max-width: 1400px;
            margin: 0 auto;
            transform: perspective(1600px) rotateX(4deg);
        }
        .alpha-header {
            background: rgba(0,0,0,0.85);
            border-bottom: 1px solid rgba(0,255,157,0.15);
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
            color: #e8f2ff;
            padding: 10px 14px;
            border-radius: 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: 'Orbitron', system-ui, sans-serif;
            letter-spacing: 0.08em;
        }
        .alpha-pill {
            padding: 6px 10px;
            border-radius: 12px;
            border: 1px solid rgba(0, 255, 157, 0.3);
            background: rgba(14, 20, 30, 0.9);
            color: #9ce9ff;
            font-size: 11px;
            margin-left: 6px;
        }
        .alpha-card {
            position: relative;
            background: rgba(9, 11, 18, 0.95);
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: inset 0 0 30px rgba(0,0,0,0.8), 0 12px 30px rgba(0,0,0,0.35);
            padding: 14px;
            overflow: hidden;
            font-family: 'Share Tech Mono', monospace;
            color: #e8ecf2;
        }
        .alpha-card::before {
            content: "";
            position: absolute;
            top: 0; left: 0; right:0; height: 3px;
            background: linear-gradient(90deg, rgba(0,255,157,0.6), rgba(0,255,255,0.1), rgba(0,255,157,0.6));
        }
        .alpha-title {
            font-family: 'Orbitron', system-ui, sans-serif;
            letter-spacing: 0.1em;
            font-size: 13px;
            color: #7dd3fc;
            margin-bottom: 10px;
        }
        .telemetry-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; }
        .telemetry-row:last-child { border-bottom: 0; }
        .telemetry-label { color: #9ca3af; }
        .telemetry-value { color: #00d4ff; font-family: 'Share Tech Mono', monospace; }
        .tach-value { font-size: 38px; font-weight: 700; font-family: 'Share Tech Mono', monospace; }
        .tach-sub { font-size: 13px; color: #9ca3af; }
        .tacho-ring {
            --p: 0.5;
            width: 260px;
            height: 260px;
            border-radius: 50%;
            background:
                radial-gradient(circle at 50% 50%, #050608 0, #050608 58%, transparent 59%),
                conic-gradient(
                    from -120deg,
                    #ff0055 0deg,
                    #ffae00 calc(120deg * var(--p)),
                    #00ff9d calc(240deg * var(--p)),
                    #333 calc(240deg * var(--p)),
                    #111 300deg,
                    transparent 360deg
                );
            box-shadow: 0 0 30px rgba(0, 255, 157, 0.4);
            margin: 0 auto;
        }
        .progress-outer { background: #0b0f16; border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; height: 12px; overflow: hidden; margin-bottom: 8px; }
        .progress-inner { height: 100%; border-radius: 8px; box-shadow: 0 0 12px currentColor; }
        .progress-green { background: linear-gradient(90deg,#00ff9d,#00b7ff); }
        .progress-amber { background: linear-gradient(90deg,#f59e0b,#f97316); }
        .progress-red { background: linear-gradient(90deg,#ff3b5f,#ff6b00); }
        .statline { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:13px; font-family:'Share Tech Mono', monospace; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="OmegaFX Alpha Cockpit", layout="wide")
    status = fetch_status()
    st.sidebar.header("Session")
    if status:
        st.sidebar.write(f"Env: {status.get('env', '-').upper()}")
        st.sidebar.write(f"Tier: {status.get('tier', '-')}")
        st.sidebar.write(f"Session: {status.get('session_id', '-')}")
    refresh = st.sidebar.button("Refresh Telemetry")
    if refresh:
        st.cache_data.clear()
        status = fetch_status()

    if not status:
        st.markdown(
            """
            <div style='padding:18px;border:1px solid #ff4d6b;background:rgba(55,0,14,0.6);color:#ffcbd9;border-radius:10px;'>
                API DISCONNECTED – Start scripts/run_local_api.py and retry.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    inject_global_style()
    trades = fetch_trades(limit=10)
    hud = build_hud_metrics(status)

    st.markdown('<div class="alpha-shell">', unsafe_allow_html=True)
    render_header(status)
    render_top_row(hud)
    render_transmission_log(trades)
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
