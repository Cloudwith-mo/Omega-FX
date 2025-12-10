from __future__ import annotations

import pandas as pd

from core.backtest import build_event_stream


def test_build_event_stream_orders_events_across_symbols() -> None:
    eurusd = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2020-01-01T00:00:00Z", "2020-01-01T01:00:00Z"], utc=True
            ),
            "open": [1.0, 1.1],
            "high": [1.1, 1.2],
            "low": [0.9, 1.0],
            "close": [1.05, 1.15],
            "volume": [100, 110],
        }
    )
    gbpusd = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2020-01-01T00:30:00Z", "2020-01-01T01:30:00Z"], utc=True
            ),
            "open": [1.3, 1.4],
            "high": [1.4, 1.5],
            "low": [1.2, 1.3],
            "close": [1.35, 1.45],
            "volume": [200, 210],
        }
    )

    symbol_map = {"EURUSD": eurusd, "GBPUSD": gbpusd}
    events = build_event_stream(symbol_map)

    assert [event.symbol for event in events] == [
        "EURUSD",
        "GBPUSD",
        "EURUSD",
        "GBPUSD",
    ]
    assert [event.row_index for event in events] == [0, 0, 1, 1]
    timestamps = [event.timestamp for event in events]
    assert timestamps == sorted(timestamps)
