from __future__ import annotations

import pandas as pd

from config.settings import ChallengeConfig
from core.challenge import run_challenge_sweep
from core.strategy import TradeDecision


def _build_symbol_df(name: str, start_price: float) -> pd.DataFrame:
    timestamps = pd.date_range("2020-01-01 09:00:00", periods=4, freq="h", tz="UTC")
    closes = [
        start_price,
        start_price + 0.002,
        start_price + 0.004,
        start_price + 0.006,
    ]
    data = {
        "timestamp": timestamps,
        "open": closes,
        "high": [price + 0.001 for price in closes],
        "low": [price - 0.001 for price in closes],
        "close": closes,
        "volume": [100] * len(closes),
        "ATR_14": [0.0015] * len(closes),
        "SMA_fast": [start_price + 0.01] * len(closes),
        "SMA_slow": [start_price + 0.02] * len(closes),
        "SMA_trend": [start_price + 0.03] * len(closes),
        "symbol": [name] * len(closes),
    }
    return pd.DataFrame(data)


def test_portfolio_challenge_generates_outcomes(monkeypatch) -> None:
    symbol_data = {
        "EURUSD": _build_symbol_df("EURUSD", 1.10),
        "GBPUSD": _build_symbol_df("GBPUSD", 1.30),
    }

    plan = {
        ("EURUSD", 1): "long",
    }

    def fake_generate_signal(
        current_row: pd.Series, previous_row: pd.Series
    ) -> TradeDecision:
        key = (current_row.get("symbol"), int(current_row.name))
        action = plan.get(key, "flat")
        if action == "flat":
            return TradeDecision("flat", None, None, "flat")
        return TradeDecision(action, 50.0, 100.0, "test", variant="unit_test")

    monkeypatch.setattr("core.strategy.generate_signal", fake_generate_signal)

    challenge_cfg = ChallengeConfig(
        start_equity=100_000.0,
        profit_target_fraction=0.10,
        max_total_loss_fraction=0.06,
        max_daily_loss_fraction=0.03,
        min_trading_days=1,
        max_trading_days=10,
        max_calendar_days=10,
    )
    outcomes = run_challenge_sweep(
        price_data=None,
        symbol_data_map=symbol_data,
        challenge_config=challenge_cfg,
        step=2,
    )
    assert outcomes
    first = outcomes[0]
    assert isinstance(first.trades_per_symbol, dict)
    assert first.trades_per_symbol.get("EURUSD", 0) >= 0
