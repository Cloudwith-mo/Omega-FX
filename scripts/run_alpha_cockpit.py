#!/usr/bin/env python3
"""OmegaFX Alpha Cockpit – dark curved HUD powered by the local API."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
import yaml

API_BASE = "http://127.0.0.1:8000"
REPO_ROOT = Path(__file__).parent.parent


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
def fetch_trades(limit: int = 100) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            f"{API_BASE}/trades", params={"hours": 48, "limit": limit}, timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def load_safety_config() -> dict:
    try:
        config_path = REPO_ROOT / "config" / "execution_limits.yaml"
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f).get("safety_rails", {})
    except Exception:
        pass
    return {}


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
            <div class="header-title">ALPHA COCKPIT // SYS.ACTIVE</div>
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


def render_safety_rails(status: dict, config: dict) -> None:
    # Extract limits
    max_hourly = config.get("max_trades_per_symbol_per_hour", 2)
    max_daily = config.get("max_trades_per_strategy_per_day", 10)
    min_hold = config.get("min_hold_seconds", 600)
    
    # Extract current usage (mocked for now as status doesn't fully expose counters yet)
    # In a real scenario, status should carry these counters
    filtered_daily = status.get("filtered_daily_loss", 0)
    filtered_stops = status.get("filtered_invalid_stops", 0)
    
    # Status indicators
    hft_status = "ACTIVE"
    hft_color = "#00ff9d"
    
    kill_switch = "OK"
    kill_color = "#00ff9d"
    if filtered_daily > 0:
        kill_switch = "TRIPPED"
        kill_color = "#ff4d6b"

    st.markdown(
        f"""
        <div class="safety-strip">
            <div class="safety-item">
                <span class="safety-label">HFT GUARD</span>
                <span class="safety-val" style="color:{hft_color}">{hft_status}</span>
            </div>
            <div class="safety-item">
                <span class="safety-label">KILL SWITCH</span>
                <span class="safety-val" style="color:{kill_color}">{kill_switch}</span>
            </div>
            <div class="safety-item">
                <span class="safety-label">MAX HOURLY/SYM</span>
                <span class="safety-val">{max_hourly}</span>
            </div>
            <div class="safety-item">
                <span class="safety-label">MAX DAILY/STRAT</span>
                <span class="safety-val">{max_daily}</span>
            </div>
            <div class="safety-item">
                <span class="safety-label">MIN HOLD</span>
                <span class="safety-val">{min_hold}s</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
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
    <div class='alpha-card' style='text-align:center;height:100%;display:flex;flex-direction:column;justify-content:center;'>
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


def render_quality_of_trade(trades: list[dict]) -> None:
    if not trades:
        return

    df = pd.DataFrame(trades)
    # Filter for closed trades only
    closed = df[df["event"] == "CLOSE"].copy()
    
    if closed.empty:
        st.markdown("<div class='alpha-card'><div class='alpha-title'>Quality of Trade</div><div style='color:#888'>No closed trades yet</div></div>", unsafe_allow_html=True)
        return

    # Parse metrics
    def safe_float(x):
        try:
            return float(x)
        except (ValueError, TypeError):
            return None

    closed["r_multiple"] = closed["r_multiple"].apply(safe_float)
    closed["hold_seconds"] = closed["hold_seconds"].apply(safe_float)
    closed["sl_distance_pips"] = closed["sl_distance_pips"].apply(safe_float)

    avg_r = closed["r_multiple"].mean()
    hit_rate_1r = (closed[closed["r_multiple"] > 1.0].shape[0] / closed.shape[0] * 100) if not closed.empty else 0
    avg_hold_min = (closed["hold_seconds"].mean() / 60) if closed["hold_seconds"].mean() else 0
    avg_sl = closed["sl_distance_pips"].mean()

    # Grade
    grade = "C"
    if avg_r > 1.5: grade = "A"
    elif avg_r > 0.8: grade = "B"
    
    grade_color = {"A": "#00ff9d", "B": "#00b7ff", "C": "#f59e0b"}.get(grade, "#888")

    html = f"""
    <div class='alpha-card'>
        <div class='alpha-title'>Quality of Trade</div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div style="text-align:center;">
                <div style="font-size:32px;font-weight:bold;color:{grade_color}">{grade}</div>
                <div style="font-size:10px;color:#888">GRADE</div>
            </div>
            <div style="flex-grow:1;margin-left:20px;display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                <div>
                    <div class="q-label">AVG R-MULTIPLE</div>
                    <div class="q-val">{avg_r:.2f}R</div>
                </div>
                <div>
                    <div class="q-label">HIT RATE >1R</div>
                    <div class="q-val">{hit_rate_1r:.0f}%</div>
                </div>
                <div>
                    <div class="q-label">AVG HOLD</div>
                    <div class="q-val">{avg_hold_min:.1f}m</div>
                </div>
                <div>
                    <div class="q-label">AVG SL</div>
                    <div class="q-val">{avg_sl:.1f} pips</div>
                </div>
            </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_strategy_grid(trades: list[dict]) -> None:
    if not trades:
        return
        
    df = pd.DataFrame(trades)
    # Group by strategy
    strategies = df["strategy_id"].unique()
    
    st.markdown("<div class='section-header'>ACTIVE STRATEGIES</div>", unsafe_allow_html=True)
    
    cols = st.columns(len(strategies)) if len(strategies) > 0 else []
    
    for idx, strat in enumerate(strategies):
        strat_trades = df[df["strategy_id"] == strat]
        closed = strat_trades[strat_trades["event"] == "CLOSE"]
        
        pnl = 0.0
        wins = 0
        count = len(closed)
        
        if not closed.empty:
            pnl = closed["pnl"].astype(float).sum()
            wins = closed[closed["pnl"].astype(float) > 0].shape[0]
        
        win_rate = (wins / count * 100) if count > 0 else 0
        pnl_color = "#00ff9d" if pnl >= 0 else "#ff4d6b"
        
        # Sparkline data (cumulative PnL)
        chart_data = None
        if not closed.empty:
            closed = closed.sort_values("timestamp")
            closed["cum_pnl"] = closed["pnl"].astype(float).cumsum()
            chart_data = closed["cum_pnl"].tolist()

        with cols[idx]:
            st.markdown(
                f"""
                <div class="strat-card">
                    <div class="strat-name">{strat}</div>
                    <div class="strat-pnl" style="color:{pnl_color}">${pnl:,.2f}</div>
                    <div class="strat-stats">{wins}/{count} wins ({win_rate:.0f}%)</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if chart_data and len(chart_data) > 1:
                st.line_chart(chart_data, height=50)
            else:
                st.markdown("<div style='height:50px;display:flex;align-items:center;justify-content:center;color:#444;font-size:10px;'>NO DATA</div>", unsafe_allow_html=True)


def render_top_row(hud: dict, trades: list[dict]) -> None:
    col_left, col_center, col_right = st.columns([1.1, 1.4, 1.1])
    with col_left:
        render_performance_card(hud)
    with col_center:
        render_tachometer_card(hud)
    with col_right:
        render_system_card(hud)
        render_quality_of_trade(trades)


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
            "sl_distance_pips": "sl_pips",
            "r_multiple": "R",
        }
        df = df.rename(columns=rename_map)
        for col in rename_map.values():
            if col not in df.columns:
                df[col] = ""
        display_cols = ["time", "symbol", "side", "size", "price", "pnl", "R", "sl_pips", "strategy"]
        # Filter to cols that exist
        display_cols = [c for c in display_cols if c in df.columns]
        df = df[display_cols]

        def _color(val):
            try:
                fval = float(val)
                return (
                    "color: #00ff9d"
                    if fval > 0
                    else ("color: #ff4d6b" if fval < 0 else "")
                )
            except Exception:
                return ""

        styled = df.style.applymap(lambda v: _color(v), subset=["pnl"] if "pnl" in df.columns else []).hide(
            axis="index"
        )
        st.dataframe(styled, use_container_width=True, height=260)
    else:
        st.markdown(
            "<div style='padding:12px;color:#8b95a5;text-align:center;'>No recent trades</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_actions() -> None:
    st.markdown("<div class='section-header'>ACTIONS</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 3])
    
    with c1:
        if st.button("Export 24h Logs"):
            # In a real app this would trigger the export script and serve the file
            # For now we'll just show a toast
            st.toast("Exporting logs... (Simulation)", icon="💾")
            
    with c2:
        if st.button("Open Behavior Report"):
            st.toast("Opening report... (Simulation)", icon="📊")


def inject_global_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Share+Tech+Mono&family=Inter:wght@400;600&display=swap');
        
        [data-testid="stAppViewContainer"] > .main {
            background:
                radial-gradient(circle at 50% 10%, #1a1d24 0%, #05060a 60%, #000 100%),
                repeating-linear-gradient(0deg, rgba(0,0,0,0.2) 0px, rgba(0,0,0,0.2) 1px, transparent 1px, transparent 2px);
            padding: 10px 0 30px 0;
        }
        
        /* Curved Screen Effect */
        .alpha-shell {
            max-width: 1400px;
            margin: 0 auto;
            transform: perspective(2000px) rotateX(2deg);
            transform-style: preserve-3d;
            border: 1px solid rgba(0,255,157,0.05);
            border-radius: 20px;
            padding: 20px;
            background: rgba(0,0,0,0.2);
            box-shadow: 0 0 50px rgba(0,0,0,0.5);
        }

        .alpha-header {
            background: linear-gradient(180deg, rgba(14, 20, 30, 0.95) 0%, rgba(5, 6, 10, 0.95) 100%);
            border-bottom: 1px solid rgba(0,255,157,0.15);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
            color: #e8f2ff;
            padding: 12px 20px;
            border-radius: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: 'Orbitron', system-ui, sans-serif;
            letter-spacing: 0.08em;
            margin-bottom: 20px;
        }
        
        .header-title {
            font-size: 18px;
            background: linear-gradient(90deg, #fff, #7dd3fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 0 20px rgba(125, 211, 252, 0.3);
        }

        .alpha-pill {
            padding: 6px 12px;
            border-radius: 4px;
            border: 1px solid rgba(0, 255, 157, 0.2);
            background: rgba(0, 255, 157, 0.05);
            color: #9ce9ff;
            font-size: 11px;
            margin-left: 8px;
            font-family: 'Share Tech Mono', monospace;
        }

        .safety-strip {
            display: flex;
            gap: 2px;
            background: #0b0f16;
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 4px;
            margin-bottom: 20px;
            overflow: hidden;
        }
        
        .safety-item {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 8px;
            background: rgba(255,255,255,0.02);
            border-right: 1px solid rgba(0,0,0,0.5);
        }
        .safety-item:last-child { border-right: none; }
        
        .safety-label {
            font-size: 9px;
            color: #6b7280;
            font-family: 'Inter', sans-serif;
            font-weight: 600;
            margin-bottom: 2px;
        }
        
        .safety-val {
            font-size: 12px;
            color: #e5e7eb;
            font-family: 'Share Tech Mono', monospace;
        }

        .alpha-card {
            position: relative;
            background: rgba(14, 18, 26, 0.8);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            padding: 16px;
            overflow: hidden;
            font-family: 'Share Tech Mono', monospace;
            color: #e8ecf2;
            backdrop-filter: blur(10px);
            margin-bottom: 16px;
        }
        
        .alpha-card::before {
            content: "";
            position: absolute;
            top: 0; left: 0; width: 3px; height: 100%;
            background: linear-gradient(180deg, rgba(0,255,157,0.6), rgba(0,255,255,0.1));
        }

        .alpha-title {
            font-family: 'Orbitron', system-ui, sans-serif;
            letter-spacing: 0.05em;
            font-size: 12px;
            color: #7dd3fc;
            margin-bottom: 12px;
            text-transform: uppercase;
            opacity: 0.8;
        }

        .telemetry-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 13px; }
        .telemetry-row:last-child { border-bottom: 0; }
        .telemetry-label { color: #9ca3af; }
        .telemetry-value { color: #f3f4f6; font-family: 'Share Tech Mono', monospace; }
        
        .tach-value { font-size: 42px; font-weight: 700; font-family: 'Share Tech Mono', monospace; text-shadow: 0 0 30px rgba(0,0,0,0.5); }
        .tach-sub { font-size: 13px; color: #9ca3af; margin-bottom: 10px; }
        
        .tacho-ring {
            --p: 0.5;
            width: 220px;
            height: 220px;
            border-radius: 50%;
            background:
                radial-gradient(circle at 50% 50%, #0e121a 0, #0e121a 58%, transparent 59%),
                conic-gradient(
                    from -120deg,
                    #ff0055 0deg,
                    #ffae00 calc(120deg * var(--p)),
                    #00ff9d calc(240deg * var(--p)),
                    #333 calc(240deg * var(--p)),
                    #111 300deg,
                    transparent 360deg
                );
            box-shadow: 0 0 40px rgba(0, 255, 157, 0.1);
            margin: 0 auto;
        }

        .progress-outer { background: #050608; border: 1px solid rgba(255,255,255,0.05); border-radius: 4px; height: 8px; overflow: hidden; margin-bottom: 10px; }
        .progress-inner { height: 100%; border-radius: 4px; box-shadow: 0 0 10px currentColor; }
        .progress-green { background: linear-gradient(90deg,#00ff9d,#00b7ff); color: rgba(0,255,157,0.5); }
        .progress-amber { background: linear-gradient(90deg,#f59e0b,#f97316); color: rgba(245,158,11,0.5); }
        .progress-red { background: linear-gradient(90deg,#ff3b5f,#ff6b00); color: rgba(255,59,95,0.5); }
        
        .statline { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; font-size:12px; font-family:'Share Tech Mono', monospace; color: #d1d5db; }

        .q-label { font-size: 9px; color: #6b7280; margin-bottom: 2px; }
        .q-val { font-size: 14px; color: #e5e7eb; font-family: 'Share Tech Mono', monospace; }
        
        .section-header {
            font-family: 'Orbitron', sans-serif;
            font-size: 14px;
            color: #9ca3af;
            margin: 20px 0 10px 0;
            padding-left: 10px;
            border-left: 2px solid #00ff9d;
        }
        
        .strat-card {
            background: rgba(14, 18, 26, 0.6);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .strat-name { font-size: 11px; color: #9ca3af; font-family: 'Inter', sans-serif; font-weight: 600; margin-bottom: 4px; }
        .strat-pnl { font-size: 18px; font-family: 'Share Tech Mono', monospace; margin-bottom: 4px; }
        .strat-stats { font-size: 10px; color: #6b7280; }
        
        /* Streamlit overrides */
        .stButton button {
            background: rgba(0, 255, 157, 0.1);
            border: 1px solid rgba(0, 255, 157, 0.3);
            color: #00ff9d;
            font-family: 'Orbitron', sans-serif;
            font-size: 12px;
            transition: all 0.2s;
        }
        .stButton button:hover {
            background: rgba(0, 255, 157, 0.2);
            box-shadow: 0 0 15px rgba(0, 255, 157, 0.3);
            border-color: #00ff9d;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="OmegaFX Alpha Cockpit", layout="wide")
    status = fetch_status()
    
    # Sidebar
    st.sidebar.header("Session Control")
    if status:
        st.sidebar.write(f"Env: {status.get('env', '-').upper()}")
        st.sidebar.write(f"Tier: {status.get('tier', '-')}")
        st.sidebar.write(f"Session: {status.get('session_id', '-')}")
    
    if st.sidebar.button("Refresh Telemetry"):
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
    trades = fetch_trades(limit=100)
    hud = build_hud_metrics(status)
    safety_config = load_safety_config()

    st.markdown('<div class="alpha-shell">', unsafe_allow_html=True)
    render_header(status)
    render_safety_rails(status, safety_config)
    render_top_row(hud, trades)
    render_strategy_grid(trades)
    render_transmission_log(trades)
    render_actions()
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
