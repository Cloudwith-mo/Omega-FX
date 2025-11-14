"""Strategy signal tests with synthetic data."""

from __future__ import annotations

import pandas as pd
import pytest

from core.strategy import TradeDecision, annotate_indicators, generate_signal


def test_indicator_annotation_adds_columns():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=60, freq="h"),
            "open": 1.10,
            "high": 1.105,
            "low": 1.095,
            "close": [1.10 + i * 0.0001 for i in range(60)],
            "volume": 1000,
        }
    )
    enriched = annotate_indicators(df)
    assert {"SMA_fast", "SMA_slow", "ATR_14"} <= set(enriched.columns)
    assert enriched["ATR_14"].iloc[-1] > 0


def _row(sma_fast: float, sma_slow: float, atr: float) -> pd.Series:
    return pd.Series(
        {
            "SMA_fast": sma_fast,
            "SMA_slow": sma_slow,
            "ATR_14": atr,
        }
    )


def test_bullish_crossover_triggers_long_signal():
    prev = _row(1.20, 1.21, 0.0005)
    curr = _row(1.25, 1.23, 0.0006)
    signal = generate_signal(curr, prev)
    assert signal.action == "long"
    assert signal.stop_distance_pips == pytest.approx(1.5 * 0.0006 * 10_000)


def test_bearish_crossover_triggers_short_signal():
    prev = _row(1.20, 1.19, 0.0005)
    curr = _row(1.18, 1.19, 0.0006)
    signal = generate_signal(curr, prev)
    assert signal.action == "short"


def test_insufficient_data_returns_flat():
    row = _row(float("nan"), 1.0, 0.0005)
    decision = generate_signal(row, row)
    assert decision == TradeDecision("flat", None, None, "Insufficient data")
