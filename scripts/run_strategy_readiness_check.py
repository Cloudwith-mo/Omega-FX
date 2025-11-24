#!/usr/bin/env python3
"""Quick readiness check per bot/strategy using a short backtest window."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from core.bot_profiles import load_bot_profile
from core.position_sizing import get_symbol_meta
from core.risk import RiskMode
from core.backtest import run_backtest
from config.deploy_ftmo_eval import FTMO_EVAL_PRESET
from config.settings import DEFAULT_BREAKOUT_CONFIG, SYMBOLS

LOOKBACK_DAYS_DEFAULT = 90


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strategy readiness snapshot for a given bot.")
    parser.add_argument("--bot", required=True, help="Bot id to check.")
    parser.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS_DEFAULT, help="Days of data to sample.")
    return parser.parse_args()


def load_symbol_payload(symbol: str, lookback_days: int) -> dict[str, pd.DataFrame] | None:
    symbol_cfg = next((cfg for cfg in SYMBOLS if cfg.name.upper() == symbol.upper()), None)
    if not symbol_cfg:
        print(f"[WARN] No symbol config found for {symbol}; skipping.")
        return None
    payload: dict[str, pd.DataFrame] = {}
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=lookback_days)
    for tf_key, path in {"H1": symbol_cfg.h1_path, "M15": symbol_cfg.m15_path}.items():
        if not path:
            continue
        p = Path(path)
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "timestamp" not in df.columns:
            continue
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df[df["timestamp"] >= cutoff]
        if df.empty:
            continue
        payload[tf_key] = df
    return payload or None


def trades_to_metrics(trades: list[dict], symbol: str) -> dict:
    if not trades:
        return {}
    meta = get_symbol_meta(symbol)
    entry_times = [pd.to_datetime(t["entry_time"]) for t in trades if t.get("entry_time")]
    exit_times = [pd.to_datetime(t["exit_time"]) for t in trades if t.get("exit_time")]
    days = 1
    if entry_times:
        span_days = (max(entry_times) - min(entry_times)).total_seconds() / 86400
        days = max(1, span_days)
    trades_per_day = len(trades) / days

    stop_pips = []
    take_pips = []
    holds_minutes = []
    r_values = []
    wins = 0
    for trade in trades:
        entry = float(trade.get("entry_price", 0.0) or 0.0)
        stop = float(trade.get("stop_loss", 0.0) or 0.0)
        take = float(trade.get("take_profit", 0.0) or 0.0)
        if entry and stop:
            stop_pips.append(abs(entry - stop) / meta.pip_size)
        if entry and take:
            take_pips.append(abs(entry - take) / meta.pip_size)
        try:
            entry_ts = pd.to_datetime(trade.get("entry_time"))
            exit_ts = pd.to_datetime(trade.get("exit_time"))
            holds_minutes.append(max(0.0, (exit_ts - entry_ts).total_seconds() / 60))
        except Exception:
            pass
        r_val = float(trade.get("r_multiple", 0.0) or 0.0)
        r_values.append(r_val)
        if r_val > 0:
            wins += 1
    win_rate = wins / len(trades) if trades else 0.0
    return {
        "trades_per_day": trades_per_day,
        "median_stop_pips": float(pd.Series(stop_pips).median()) if stop_pips else 0.0,
        "median_take_pips": float(pd.Series(take_pips).median()) if take_pips else 0.0,
        "median_hold_minutes": float(pd.Series(holds_minutes).median()) if holds_minutes else 0.0,
        "win_rate": win_rate,
        "avg_r": float(pd.Series(r_values).mean()) if r_values else 0.0,
    }


def flag_pathologies(metrics: dict) -> list[str]:
    warnings = []
    if metrics.get("trades_per_day", 0) > 20:
        warnings.append("trades/day > 20")
    if 0 < metrics.get("median_stop_pips", 0) < 5:
        warnings.append("median SL < 5 pips")
    if 0 < metrics.get("median_hold_minutes", 0) < 5:
        warnings.append("median hold < 5 min")
    return warnings


def main() -> int:
    args = parse_args()
    profile = load_bot_profile(args.bot)
    symbol_payloads: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol in profile.symbols:
        payload = load_symbol_payload(symbol, args.lookback_days)
        if payload:
            symbol_payloads[symbol] = payload
        else:
            print(f"[WARN] No data found for {symbol}; skipping.")
    if not symbol_payloads:
        print("No data available for requested symbols.")
        return 1

    risk_mode = RiskMode.ULTRA_ULTRA_CONSERVATIVE if profile.risk_tier.lower() == "conservative" else RiskMode.CONSERVATIVE
    result = run_backtest(
        df=None,
        starting_equity=100_000.0,
        initial_mode=risk_mode,
        symbol_data_map=symbol_payloads,
        entry_mode=FTMO_EVAL_PRESET.entry_mode,
        firm_profile=profile.firm_profile,
    )

    print(f"=== Strategy readiness for bot: {profile.bot_id} ===")
    for symbol in profile.symbols:
        if symbol not in symbol_payloads:
            print(f"{symbol}: skipped (no data loaded)")
            continue
        sym_trades = [t for t in result.trades if t.get("symbol") == symbol]
        metrics = trades_to_metrics(sym_trades, symbol)
        for strat in profile.strategies:
            print(
                f"{strat.id} @ {symbol}: trades/day={metrics.get('trades_per_day', 0):.2f} "
                f"med SL={metrics.get('median_stop_pips', 0):.1f} pips "
                f"med TP={metrics.get('median_take_pips', 0):.1f} pips "
                f"med hold={metrics.get('median_hold_minutes', 0):.1f} min "
                f"win%={metrics.get('win_rate', 0)*100:.1f}% avgR={metrics.get('avg_r', 0):.2f}"
            )
            warnings = flag_pathologies(metrics)
            if warnings:
                print(f"  WARNING: {', '.join(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
