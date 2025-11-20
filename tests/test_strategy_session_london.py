from __future__ import annotations

import pandas as pd

from strategies.omega_session_london import (
    OMEGA_SESSION_LDN_STRATEGY_ID,
    LondonSessionConfig,
    make_london_session_strategy,
)


def _row(ts: str, high: float, low: float, symbol: str = "GBPUSD") -> pd.Series:
    return pd.Series({
        "timestamp": pd.Timestamp(ts),
        "symbol": symbol,
        "high": high,
        "low": low,
    })


def test_london_session_long_trigger() -> None:
    strategy = make_london_session_strategy(LondonSessionConfig())
    # Asian session accumulation
    for hour in range(0, 7):
        ts = f"2024-01-01T0{hour}:00:00Z"
        strategy(_row(ts, 1.2500 + hour * 0.0001, 1.2490 - hour * 0.00005))
    # London bar crossing buy trigger
    decision = strategy(_row("2024-01-01T07:15:00Z", 1.2530, 1.2510))
    assert decision is not None
    assert decision.action == "long"
    assert decision.strategy_id == OMEGA_SESSION_LDN_STRATEGY_ID
    assert decision.signal_reason == "ldn_long"


def test_london_session_short_trigger() -> None:
    cfg = LondonSessionConfig(trigger_buffer_pips=2.0)
    strategy = make_london_session_strategy(cfg)
    for hour in range(0, 7):
        strategy(_row(f"2024-01-02T0{hour}:00:00Z", 1.2700, 1.2680 - hour * 0.0001))
    decision = strategy(_row("2024-01-02T07:05:00Z", 1.2685, 1.2650))
    assert decision is not None
    assert decision.action == "short"
    assert decision.signal_reason == "ldn_short"


def test_strategy_only_targets_gbpusd() -> None:
    strategy = make_london_session_strategy()
    strategy(_row("2024-01-03T00:30:00Z", 1.2600, 1.2580))
    assert strategy(_row("2024-01-03T07:00:00Z", 1.2605, 1.2595, symbol="EURUSD")) is None
