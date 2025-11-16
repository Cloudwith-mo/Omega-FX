from __future__ import annotations

import pandas as pd

from core.backtest import run_backtest
from core.strategy import TradeDecision


def _build_symbol_df(name: str, start_price: float) -> pd.DataFrame:
    timestamps = pd.date_range("2020-01-01 09:00:00", periods=3, freq="h", tz="UTC")
    closes = [start_price, start_price + 0.005, start_price + 0.015]
    data = {
        "timestamp": timestamps,
        "open": closes,
        "high": [price + 0.001 for price in closes],
        "low": [price - 0.001 for price in closes],
        "close": closes,
        "volume": [100] * len(closes),
        "ATR_14": [0.0015] * len(closes),
        "SMA_fast": [start_price + 0.02] * len(closes),
        "SMA_slow": [start_price + 0.01] * len(closes),
        "SMA_trend": [start_price] * len(closes),
        "symbol": [name] * len(closes),
    }
    return pd.DataFrame(data)


def test_portfolio_enforces_single_position(monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_MAX_CONCURRENT_POSITIONS", "1")
    symbol_data = {
        "EURUSD": _build_symbol_df("EURUSD", 1.10),
        "GBPUSD": _build_symbol_df("GBPUSD", 1.30),
    }

    plan = {
        ("EURUSD", 1): "long",  # opens trade
        ("GBPUSD", 1): "long",  # should be blocked
    }

    def fake_generate_signal(current_row: pd.Series, previous_row: pd.Series) -> TradeDecision:
        symbol = current_row.get("symbol")
        idx = int(current_row.name)
        action = plan.get((symbol, idx), "flat")
        if action == "flat":
            return TradeDecision("flat", None, None, "flat")
        return TradeDecision(action, 50.0, 100.0, "test", variant="unit_test")

    monkeypatch.setattr("core.strategy.generate_signal", fake_generate_signal)

    result = run_backtest(symbol_data_map=symbol_data, starting_equity=100_000.0)

    assert result.filtered_trades_by_reason.get("max_open_positions", 0) == 1
    assert result.trades_per_symbol.get("GBPUSD", 0) == 0
    assert result.raw_signal_count > 0
