from __future__ import annotations

import pandas as pd

from strategies.omega_mr_m15 import OMEGA_MR_STRATEGY_ID, generate_mean_reversion_signal


def _base_row() -> pd.Series:
    return pd.Series(
        {
            "close": 1.0000,
            "BB_LOWER_20_2": 1.0050,
            "BB_UPPER_20_2": 0.9950,
            "BB_MID_20": 1.0020,
            "RSI_14": 50.0,
            "ADX_14": 25.0,
            "ATR_14": 0.0005,
        }
    )


def test_mean_reversion_long_signal() -> None:
    row = _base_row().copy()
    row["close"] = 0.9900
    row["RSI_14"] = 20.0
    decision = generate_mean_reversion_signal(row)
    assert decision is not None
    assert decision.action == "long"
    assert decision.strategy_id == OMEGA_MR_STRATEGY_ID
    assert decision.signal_reason == "bb_rsi_fade_long"


def test_mean_reversion_short_signal() -> None:
    row = _base_row().copy()
    row["close"] = 1.0200
    row["BB_UPPER_20_2"] = 1.0100
    row["BB_MID_20"] = 1.0050
    row["RSI_14"] = 80.0
    decision = generate_mean_reversion_signal(row)
    assert decision is not None
    assert decision.action == "short"
    assert decision.signal_reason == "bb_rsi_fade_short"


def test_mean_reversion_rejects_high_adx() -> None:
    row = _base_row().copy()
    row["ADX_14"] = 40.0
    assert generate_mean_reversion_signal(row) is None
