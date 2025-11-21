#!/usr/bin/env python3
"""OmegaFX Alpha Cockpit – race-car styled HUD powered by the local API."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import requests
import streamlit as st
from streamlit.components.v1 import html as st_html

API_BASE = "http://127.0.0.1:8000"


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


@st.cache_data(ttl=10)
def fetch_status() -> dict | None:
    try:
        resp = requests.get(f"{API_BASE}/status", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=10)
def fetch_trades(limit: int = 5) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(f"{API_BASE}/trades", params={"hours": 24, "limit": limit}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def build_hud_metrics(status: dict) -> dict:
    account_equity = float(status.get("account_equity") or status.get("equity") or 0.0)
    synthetic_equity = float(status.get("synthetic_equity") or account_equity or 1.0)
    session_pnl = float(status.get("session_pnl", status.get("pnl", 0.0)) or 0.0)
    pnl_usd = session_pnl if session_pnl != 0 else float(status.get("last_24h_pnl", 0.0) or 0.0)
    daily_target_usd = 500.0
    pnl_pct_of_target = clamp(pnl_usd / daily_target_usd if daily_target_usd else 0, 0, 1)

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

    equity_load_pct = clamp(100 * account_equity / synthetic_equity if synthetic_equity else 0, 0, 100)

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


def render_alpha_cockpit(status: dict, trades: list[dict]) -> None:
    hud = build_hud_metrics(status)
    pnl_color = "#12d68a" if hud["pnl_usd"] >= 0 else "#ff4d6b"
    pnl_sign = "+" if hud["pnl_usd"] >= 0 else "-"
    pnl_value = abs(hud["pnl_usd"])
    open_count = hud["open_positions"].get("count", 0)
    open_pnl = hud["open_positions"].get("total_pnl", 0.0)

    trade_rows = ""
    if trades:
        for t in trades:
            direction = (t.get("direction", "") or "").upper()
            trade_color = "#12d68a" if float(t.get("pnl", 0.0) or 0.0) >= 0 else "#ff4d6b"
            trade_rows += f"<div class=\"trade-row\">"
            trade_rows += f"<div class=\"trade-cell\">{t.get('timestamp','')}</div>"
            trade_rows += f"<div class=\"trade-cell\">{t.get('symbol','')}</div>"
            trade_rows += f"<div class=\"trade-cell\" style=\"color:{'#12d68a' if direction=='LONG' else '#ff4d6b'}\">{direction}</div>"
            trade_rows += f"<div class=\"trade-cell\">{t.get('volume','')}</div>"
            trade_rows += f"<div class=\"trade-cell\">{t.get('price','')}</div>"
            trade_rows += f"<div class=\"trade-cell\" style=\"color:{trade_color}\">{float(t.get('pnl',0.0)):+.2f}</div>"
            trade_rows += "</div>"
    else:
        trade_rows = '<div class="trade-row"><div class="trade-cell" style="grid-column:1/7;color:#ccc;">No recent trades</div></div>'

    html = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    body {{ background: #050910; color: #e8ecf2; font-family: 'Inter', sans-serif; }}
    .cockpit {{ padding: 12px; }}
    .header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
    .badge {{ background:#111827; padding:6px 10px; border:1px solid #1f2937; border-radius:8px; font-size:12px; letter-spacing:0.05em; }}
    .grid {{ display:grid; grid-template-columns: 1.1fr 1.5fr 1.1fr; gap:14px; }}
    .panel {{ background:#0b111b; border:1px solid #1f2937; border-radius:10px; padding:12px; }}
    .panel h3 {{ margin:0 0 8px 0; font-size:13px; letter-spacing:0.08em; color:#7dd3fc; }}
    .telemetry-item {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #111827; }}
    .telemetry-item:last-child {{ border-bottom:none; }}
    .tach {{ position:relative; height:320px; display:flex; align-items:center; justify-content:center; }}
    .tach .ring {{ width:260px; height:260px; border-radius:50%; background:conic-gradient(#12d68a {hud['pnl_pct_of_target']*360}deg, #1f2937 0deg); position:absolute; filter: drop-shadow(0 0 12px rgba(18,214,138,0.35)); }}
    .tach .center {{ position:absolute; width:210px; height:210px; border-radius:50%; background:#050910; border:2px solid #1f2937; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
    .tach .value {{ font-size:32px; font-weight:700; color:{pnl_color}; }}
    .tach .label {{ font-size:12px; letter-spacing:0.08em; color:#94a3b8; }}
    .bar {{ height:12px; background:#111827; border-radius:999px; overflow:hidden; border:1px solid #1f2937; margin-bottom:8px; }}
    .bar-fill-green {{ height:100%; background:linear-gradient(90deg,#0ea5e9,#12d68a); width:50%; transition:width 0.3s ease; }}
    .bar-fill-red {{ height:100%; background:linear-gradient(90deg,#f97316,#ef4444); width:50%; transition:width 0.3s ease; }}
    .statline {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:13px; }}
    .trade-log {{ margin-top:10px; border-top:1px solid #1f2937; padding-top:10px; }}
    .trade-header, .trade-row {{ display:grid; grid-template-columns: 1.4fr 0.9fr 0.8fr 0.8fr 0.9fr 0.9fr; gap:6px; padding:6px 0; font-size:12px; }}
    .trade-header {{ color:#94a3b8; border-bottom:1px solid #1f2937; }}
    .trade-cell {{ overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
    </style>

    <div class="cockpit">
      <div class="header">
        <div style="font-weight:700; letter-spacing:0.12em;">ALPHA COCKPIT // V12</div>
        <div style="display:flex; gap:8px;">
          <div class="badge">ENV: {hud['env'] or 'N/A'}</div>
          <div class="badge">TIER: {hud['risk_tier'] or 'N/A'}</div>
          <div class="badge">SESSION: {hud['session_id'] or 'N/A'}</div>
        </div>
      </div>
      <div class="grid">
        <div class="panel">
          <h3>Performance Telemetry</h3>
          <div class="telemetry-item"><span>Win Rate</span><span>{hud['win_rate']:.1f}%</span></div>
          <div class="telemetry-item"><span>Profit Factor</span><span>{hud['profit_factor'] if hud['profit_factor'] is not None else '–'}</span></div>
          <div class="telemetry-item"><span>Sharpe</span><span>{hud['sharpe'] if hud['sharpe'] is not None else '–'}</span></div>
          <div class="telemetry-item"><span>Avg Win</span><span>{hud['avg_win'] if hud['avg_win'] is not None else '–'}</span></div>
          <div class="telemetry-item"><span>Avg Loss</span><span>{hud['avg_loss'] if hud['avg_loss'] is not None else '–'}</span></div>
          <div class="telemetry-item"><span>Open Positions</span><span>{open_count} ({open_pnl:+.2f})</span></div>
        </div>

        <div class="panel tach">
          <div class="ring"></div>
          <div class="center">
            <div class="label">EQUITY PNL</div>
            <div class="value">{pnl_sign}${pnl_value:,.2f}</div>
            <div class="label">Target ${hud['daily_target_usd']:,.0f}</div>
          </div>
        </div>

        <div class="panel">
          <h3>System Health</h3>
          <div class="statline"><span>Margin Fuel</span><span>{hud['margin_fuel_pct']:.0f}%</span></div>
          <div class="bar"><div class="bar-fill-green" style="width:{hud['margin_fuel_pct']}%;"></div></div>
          <div class="statline"><span>Engine Temp (DD)</span><span>{hud['dd_temp_pct']:.0f}%</span></div>
          <div class="bar"><div class="bar-fill-red" style="width:{hud['dd_temp_pct']}%;"></div></div>
          <div class="statline"><span>Equity Load</span><span>{hud['equity_load_pct']:.0f}%</span></div>
          <div class="bar"><div class="bar-fill-green" style="width:{hud['equity_load_pct']}%;"></div></div>
        </div>
      </div>

      <div class="panel trade-log">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <div style="letter-spacing:0.08em; color:#7dd3fc; font-size:13px;">TRANSMISSION LOG // Recent Orders</div>
        </div>
        <div class="trade-header">
          <div>Time</div><div>Symbol</div><div>Dir</div><div>Vol</div><div>Price</div><div>PnL</div>
        </div>
        {trade_rows}
      </div>
    </div>
    """
    st_html(html, height=840, scrolling=False)


def main() -> None:
    st.set_page_config(page_title="OmegaFX Alpha Cockpit", layout="wide")
    st.title("OmegaFX Alpha Cockpit")

    status = fetch_status()
    st.sidebar.header("Session")
    if status:
        st.sidebar.write(f"Env: {status.get('env','-').upper()}")
        st.sidebar.write(f"Tier: {status.get('tier','-')}")
        st.sidebar.write(f"Session: {status.get('session_id','-')}")
    refresh = st.sidebar.button("Refresh Telemetry")
    if refresh:
        st.cache_data.clear()
        status = fetch_status()

    if not status:
        st.error("API OFFLINE – start scripts/run_local_api.py and try again.")
        return

    trades = fetch_trades()
    render_alpha_cockpit(status, trades)


if __name__ == "__main__":
    main()
