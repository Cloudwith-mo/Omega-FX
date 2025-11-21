#!/usr/bin/env python3
"""Generate FTMO live signals from MT5 data without auto-trading."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:  # pragma: no cover - requires local MT5 setup
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None

from config.deploy_ftmo_eval import FTMO_EVAL_PRESET  # noqa: E402
from config.settings import (  # noqa: E402
    DEFAULT_BREAKOUT_CONFIG,
    DEFAULT_CHALLENGE,
    DEFAULT_RISK_MODE,
    resolve_firm_profile,
)
from core.backtest import (  # noqa: E402
    SymbolFrameSet,
    _build_symbol_frame_sets,
    _meets_breakout_conditions,
    _session_tag,
    _trend_regime,
    _volatility_regime,
    build_event_stream,
)
from core.filters import TradeTags, should_allow_trade  # noqa: E402
from core.position_sizing import compute_position_size, get_symbol_meta  # noqa: E402
from core.risk import RISK_PROFILES, RiskMode, RiskState  # noqa: E402
from core.risk_utils import pips_to_price  # noqa: E402
from core.risk_aggression import (  # noqa: E402
    set_custom_tier_scales,
    should_allow_risk_aggression,
)
from core.strategy import generate_signal  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Produce FTMO live signal suggestions every M15 bar."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["EURUSD", "GBPUSD", "USDJPY"],
        help="Symbols to poll from MT5.",
    )
    parser.add_argument(
        "--m15-bars",
        type=int,
        default=500,
        help="Number of M15 bars to fetch per symbol.",
    )
    parser.add_argument(
        "--h1-bars",
        type=int,
        default=500,
        help="Number of H1 bars to fetch per symbol.",
    )
    parser.add_argument(
        "--account-equity",
        type=float,
        default=100_000.0,
        help="Notional equity used to size risk fractions (defaults to 100k).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/live_signals_ftmo.csv"),
        help="CSV destination for signal logs.",
    )
    parser.add_argument(
        "--firm",
        type=str,
        default=FTMO_EVAL_PRESET.firm_profile,
        help="Firm profile label (defaults to the FTMO eval preset).",
    )
    parser.add_argument(
        "--alert_mode",
        choices=["none", "telegram", "slack"],
        default="none",
        help="Optional alert emission (stdout stubs for now).",
    )
    return parser.parse_args()


def init_mt5() -> None:
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 package not installed. pip install MetaTrader5 before running."
        )
    if not mt5.initialize():
        raise RuntimeError(f"Failed to initialize MT5 terminal: {mt5.last_error()}")


def fetch_rates(symbol: str, timeframe, bars: int) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"MT5 returned no data for {symbol} timeframe={timeframe}")
    df = pd.DataFrame(rates)
    df.rename(
        columns={
            "time": "timestamp",
            "tick_volume": "volume",
        },
        inplace=True,
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def build_symbol_data(
    symbols: list[str], m15_bars: int, h1_bars: int
) -> dict[str, dict[str, pd.DataFrame]]:
    payload: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol in symbols:
        m15_df = fetch_rates(symbol, mt5.TIMEFRAME_M15, m15_bars)
        h1_df = fetch_rates(symbol, mt5.TIMEFRAME_H1, h1_bars)
        payload[symbol] = {"M15": m15_df, "H1": h1_df}
    return payload


def evaluate_signals(
    symbol_sets: dict[str, SymbolFrameSet],
    account_equity: float,
    firm_label: str,
) -> list[dict]:
    firm_cfg = resolve_firm_profile(firm_label)
    challenge = DEFAULT_CHALLENGE
    risk_state = RiskState(account_equity, DEFAULT_RISK_MODE, firm_profile=firm_cfg)
    risk_profile = RISK_PROFILES[risk_state.current_mode]
    max_open_positions = FTMO_EVAL_PRESET.max_concurrent_positions
    events = build_event_stream(symbol_sets)
    entry_tfs = {"M15"} if FTMO_EVAL_PRESET.entry_mode == "M15_WITH_H1_CTX" else {"H1"}
    latest_ts = None
    for event in events:
        if event.timeframe in entry_tfs:
            if latest_ts is None or event.timestamp > latest_ts:
                latest_ts = event.timestamp
    if latest_ts is None:
        return []

    signals: list[dict] = []
    set_custom_tier_scales(FTMO_EVAL_PRESET.tier_scales)
    try:
        open_positions = []
        todays_realized_pnl = 0.0
        for event in events:
            if event.timeframe not in entry_tfs or event.timestamp != latest_ts:
                continue
            frames = symbol_sets.get(event.symbol)
            if not frames:
                continue
            entry_df = frames.entry_frames.get(event.timeframe)
            if (
                entry_df is None
                or event.row_index >= len(entry_df)
                or event.row_index < 1
            ):
                continue
            row = frames.get_entry_row(event.timeframe, event.row_index)
            prev_row = frames.get_entry_row(event.timeframe, event.row_index - 1)
            context_row = frames.context_row(event.timestamp)
            if context_row is None:
                continue

            signal = generate_signal(row, prev_row)
            if signal.action not in {"long", "short"}:
                continue

            session_tag = _session_tag(event.timestamp)
            atr_value = float(context_row.get("ATR_14", 0.0))
            entry_atr_value = float(row.get("ATR_14", 0.0))
            vol_regime = _volatility_regime(
                atr_value, frames.context_h1_atr_low, frames.context_h1_atr_high
            )
            trend_regime = _trend_regime(signal.action, context_row)

            filter_result = should_allow_trade(
                TradeTags(
                    session_tag=session_tag,
                    trend_regime=trend_regime,
                    volatility_regime=vol_regime,
                )
            )
            if not (
                filter_result.session_passed
                and filter_result.trend_passed
                and filter_result.volatility_passed
            ):
                continue

            lot_size = compute_position_size(
                account_equity=risk_state.current_equity,
                risk_mode=risk_state.current_mode,
                stop_distance_pips=signal.stop_distance_pips,
            )
            pip_to_price = pips_to_price(signal.stop_distance_pips, symbol)
            entry_price = float(row["close"])
            stop_loss = (
                entry_price - pip_to_price
                if signal.action == "long"
                else entry_price + pip_to_price
            )
            tp_to_price = pips_to_price(signal.take_profit_distance_pips, symbol) if signal.take_profit_distance_pips else 0.0
            take_profit = (
                entry_price + tp_to_price
                if signal.action == "long"
                else entry_price - tp_to_price
            )

            breakout_high = float(row.get("HIGH_BREAKOUT", float("nan")))
            breakout_low = float(row.get("LOW_BREAKOUT", float("nan")))
            sma_fast = float(row.get("SMA_slow", float("nan")))
            sma_trend = float(row.get("SMA_trend", float("nan")))
            if not _meets_breakout_conditions(
                direction=signal.action,
                entry_price=entry_price,
                sma_fast=sma_fast,
                sma_trend=sma_trend,
                breakout_level=breakout_high
                if signal.action == "long"
                else breakout_low,
                atr_value=atr_value,
                config=DEFAULT_BREAKOUT_CONFIG,
            ):
                continue

            combo_key = (
                session_tag,
                trend_regime,
                vol_regime,
                signal.variant if hasattr(signal, "variant") else "unknown",
            )
            risk_aggr = should_allow_risk_aggression(combo_key, risk_state.current_mode)
            if not risk_aggr.allowed:
                continue

            risk_scale = max(0.0, risk_aggr.risk_scale)
            lot_size *= risk_scale
            if lot_size <= 0 or len(open_positions) >= max_open_positions:
                continue

            risk_amount = signal.stop_distance_pips * 10 * lot_size
            projected_loss = max(0.0, -todays_realized_pnl) + risk_amount
            internal_limit = (
                risk_profile.daily_loss_limit_fraction * risk_state.start_of_day_equity
            )
            if projected_loss > internal_limit:
                continue

            signals.append(
                {
                    "timestamp": event.timestamp.isoformat(),
                    "symbol": event.symbol,
                    "direction": signal.action,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "risk_fraction": risk_amount / risk_state.current_equity
                    if risk_state.current_equity
                    else 0.0,
                    "session": session_tag,
                    "trend_regime": trend_regime,
                    "volatility_regime": vol_regime,
                    "tier": risk_aggr.tier,
                    "variant": getattr(signal, "variant", "unknown"),
                    "entry_timeframe": event.timeframe,
                    "atr_value": entry_atr_value,
                }
            )
        return signals
    finally:
        set_custom_tier_scales(None)


def append_signals(output_path: Path, signals: list[dict]) -> None:
    if not signals:
        print("No qualifying signals for the latest bar.")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "symbol",
        "direction",
        "entry_price",
        "stop_loss",
        "take_profit",
        "risk_fraction",
        "session",
        "trend_regime",
        "volatility_regime",
        "tier",
        "variant",
        "entry_timeframe",
        "atr_value",
    ]
    file_exists = output_path.exists()
    with output_path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in signals:
            writer.writerow(row)
    print(f"Wrote {len(signals)} signal(s) to {output_path}")


def emit_alerts(signals: list[dict], mode: str) -> None:
    if mode == "none" or not signals:
        return
    prefix = f"[{mode.upper()} ALERT]" if mode != "none" else "[ALERT]"
    for sig in signals:
        line = (
            f"{prefix} {sig['timestamp']} {sig['symbol']} {sig['direction'].upper()} "
            f"SL={sig['stop_loss']:.5f} TP={sig['take_profit']:.5f} "
            f"risk={sig['risk_fraction'] * 100:.2f}% tier={sig['tier']}"
        )
        print(line)


def main() -> int:
    args = parse_args()
    init_mt5()
    try:
        symbol_map = build_symbol_data(args.symbols, args.m15_bars, args.h1_bars)
        symbol_sets = _build_symbol_frame_sets(
            FTMO_EVAL_PRESET.entry_mode,
            DEFAULT_BREAKOUT_CONFIG,
            df=None,
            data_source=None,
            symbol_data_map=symbol_map,
            symbols_config=None,
        )
        signals = evaluate_signals(
            symbol_sets, account_equity=args.account_equity, firm_label=args.firm
        )
        append_signals(args.output, signals)
        emit_alerts(signals, args.alert_mode)
    finally:
        if mt5 is not None:
            mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
