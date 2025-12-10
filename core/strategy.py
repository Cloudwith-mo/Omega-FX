"""Simple SMA crossover strategy with ATR-based stops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from config.settings import DEFAULT_BREAKOUT_CONFIG
from core.constants import DEFAULT_STRATEGY_ID
from core.position_sizing import get_symbol_meta


@dataclass
class TradeDecision:
    """Container for strategy output."""

    action: Literal["long", "short", "flat"]
    stop_distance_pips: float | None
    take_profit_distance_pips: float | None
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
    _annotate_bollinger(out)
    _annotate_rsi(out, period=14)
    _annotate_adx(out, period=14)
    lookback = DEFAULT_BREAKOUT_CONFIG.lookback_bars
    out["HIGH_BREAKOUT"] = (
        out["high"].rolling(lookback, min_periods=lookback).max()
    )
    out["LOW_BREAKOUT"] = (
        out["low"].rolling(lookback, min_periods=lookback).min()
    )
    return out


def _annotate_bollinger(
    df: pd.DataFrame, period: int = 20, std_factor: float = 2.0
) -> None:
    mean = df["close"].rolling(period, min_periods=period).mean()
    std = df["close"].rolling(period, min_periods=period).std()
    df["BB_MID_20"] = mean
    df["BB_UPPER_20_2"] = mean + std_factor * std
    df["BB_LOWER_20_2"] = mean - std_factor * std


def _annotate_rsi(df: pd.DataFrame, period: int = 14) -> None:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    df["RSI_14"] = rsi.fillna(0.0)


def _annotate_adx(df: pd.DataFrame, period: int = 14) -> None:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean().replace(0, pd.NA)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0.0) * 100
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    df["ADX_14"] = adx.fillna(0.0)


def generate_signal(
    current_row: pd.Series, previous_row: pd.Series, symbol: str = "EURUSD"
) -> TradeDecision:
    """
    Generate SMA crossover decisions with ATR-based stops/take-profit.
    """
    required = ("SMA_fast", "SMA_slow", "ATR_14")
    if any(
        pd.isna(current_row[col]) or pd.isna(previous_row[col])
        for col in required
    ):
        return TradeDecision(
            "flat",
            None,
            None,
            "Insufficient data",
            signal_reason="insufficient_data",
            strategy_id=DEFAULT_STRATEGY_ID,
        )

    fast_now = current_row["SMA_fast"]
    slow_now = current_row["SMA_slow"]
    fast_prev = previous_row["SMA_fast"]
    slow_prev = previous_row["SMA_slow"]

    meta = get_symbol_meta(symbol)
    # 1 pip = meta.pip_size.
    # If ATR is 0.0020 and pip_size is 0.0001, then ATR in pips = 20.
    atr_value = float(current_row["ATR_14"])
    atr_pips = atr_value / meta.pip_size
    stop_distance = 1.5 * atr_pips
    tp_distance = 3.0 * atr_pips

    if fast_prev <= slow_prev and fast_now > slow_now:
        return TradeDecision(
            "long",
            stop_distance,
            tp_distance,
            "SMA bullish crossover",
            variant="v1_cross",
            signal_reason="breakout_pullback",
            strategy_id=DEFAULT_STRATEGY_ID,
        )

    if fast_prev >= slow_prev and fast_now < slow_now:
        return TradeDecision(
            "short",
            stop_distance,
            tp_distance,
            "SMA bearish crossover",
            variant="v1_cross",
            signal_reason="breakout_pullback",
            strategy_id=DEFAULT_STRATEGY_ID,
        )

    momentum_variant = _momentum_signal(current_row, previous_row)
    if momentum_variant:
        action = momentum_variant
        reason = "SMA momentum continuation"
        return TradeDecision(
            action,
            stop_distance,
            tp_distance,
            reason,
            variant="v2_momentum",
            signal_reason="trend_continuation",
            strategy_id=DEFAULT_STRATEGY_ID,
        )

    return TradeDecision(
        "flat",
        None,
        None,
        "No signal",
        signal_reason="no_signal",
        strategy_id=DEFAULT_STRATEGY_ID,
    )


def _momentum_signal(current_row: pd.Series, previous_row: pd.Series) -> str | None:
    fast_now = current_row["SMA_fast"]
    slow_now = current_row["SMA_slow"]
    fast_prev = previous_row["SMA_fast"]
    slow_prev = previous_row["SMA_slow"]
    close_price = current_row["close"]

    if (
        pd.isna(fast_now)
        or pd.isna(slow_now)
        or pd.isna(fast_prev)
        or pd.isna(slow_prev)
    ):
        return None

    band = 0.001  # ~10 pips band around SMA
    if (
        fast_now > slow_now
        and fast_prev > slow_prev
        and close_price >= slow_now * (1 - band)
    ):
        return "long"
    if (
        fast_now < slow_now
        and fast_prev < slow_prev
        and close_price <= slow_now * (1 + band)
    ):
        return "short"
    return None
