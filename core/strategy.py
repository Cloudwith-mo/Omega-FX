"""Simple SMA crossover strategy with ATR-based stops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd
from config.settings import DEFAULT_BREAKOUT_CONFIG, BreakoutConfig
from core.constants import DEFAULT_STRATEGY_ID



@dataclass
class TradeDecision:
    """Container for strategy output."""

    action: Literal["long", "short", "flat"]
    stop_distance_pips: Optional[float]
    take_profit_distance_pips: Optional[float]
    reason: str
    variant: str = "v1_cross"
    signal_reason: str = "unknown"
    strategy_id: str = DEFAULT_STRATEGY_ID


def _wilder_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Wilder ATR using exponential smoothing."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def annotate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return copy of df with SMA/ATR columns required by generate_signal.
    """
    out = df.copy()
    out["SMA_fast"] = out["close"].rolling(20, min_periods=20).mean()
    out["SMA_slow"] = out["close"].rolling(50, min_periods=50).mean()
    out["SMA_trend"] = out["close"].rolling(200, min_periods=200).mean()
    out["ATR_14"] = _wilder_atr(out, 14)
    lookback = DEFAULT_BREAKOUT_CONFIG.lookback_bars
    out["HIGH_BREAKOUT"] = out["high"].rolling(lookback, min_periods=lookback).max()
    out["LOW_BREAKOUT"] = out["low"].rolling(lookback, min_periods=lookback).min()
    return out


def generate_signal(current_row: pd.Series, previous_row: pd.Series) -> TradeDecision:
    """
    Generate SMA crossover decisions with ATR-based stops/take-profit.
    """
    required = ("SMA_fast", "SMA_slow", "ATR_14")
    if any(pd.isna(current_row[col]) or pd.isna(previous_row[col]) for col in required):
        return TradeDecision("flat", None, None, "Insufficient data", signal_reason="insufficient_data", strategy_id=DEFAULT_STRATEGY_ID)

    fast_now = current_row["SMA_fast"]
    slow_now = current_row["SMA_slow"]
    fast_prev = previous_row["SMA_fast"]
    slow_prev = previous_row["SMA_slow"]

    atr_pips = float(current_row["ATR_14"]) * 10_000
    stop_distance = 1.5 * atr_pips
    tp_distance = 3.0 * atr_pips

    if fast_prev <= slow_prev and fast_now > slow_now:
        return TradeDecision("long", stop_distance, tp_distance, "SMA bullish crossover", variant="v1_cross", signal_reason="breakout_pullback", strategy_id=DEFAULT_STRATEGY_ID)

    if fast_prev >= slow_prev and fast_now < slow_now:
        return TradeDecision("short", stop_distance, tp_distance, "SMA bearish crossover", variant="v1_cross", signal_reason="breakout_pullback", strategy_id=DEFAULT_STRATEGY_ID)

    momentum_variant = _momentum_signal(current_row, previous_row)
    if momentum_variant:
        action = momentum_variant
        reason = "SMA momentum continuation"
        return TradeDecision(action, stop_distance, tp_distance, reason, variant="v2_momentum", signal_reason="trend_continuation", strategy_id=DEFAULT_STRATEGY_ID)

    return TradeDecision("flat", None, None, "No signal", signal_reason="no_signal", strategy_id=DEFAULT_STRATEGY_ID)


def _momentum_signal(current_row: pd.Series, previous_row: pd.Series) -> Optional[str]:
    fast_now = current_row["SMA_fast"]
    slow_now = current_row["SMA_slow"]
    fast_prev = previous_row["SMA_fast"]
    slow_prev = previous_row["SMA_slow"]
    close_price = current_row["close"]

    if pd.isna(fast_now) or pd.isna(slow_now) or pd.isna(fast_prev) or pd.isna(slow_prev):
        return None

    band = 0.001  # ~10 pips band around SMA
    if fast_now > slow_now and fast_prev > slow_prev and close_price >= slow_now * (1 - band):
        return "long"
    if fast_now < slow_now and fast_prev < slow_prev and close_price <= slow_now * (1 + band):
        return "short"
    return None
