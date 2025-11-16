"""Lightweight MT5 stub for offline smoke tests."""

from __future__ import annotations

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
TIMEFRAME_M15 = "M15"
TIMEFRAME_H1 = "H1"

_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def initialize() -> bool:  # pragma: no cover - trivial stub
    return True


def shutdown() -> None:  # pragma: no cover
    return None


def last_error() -> tuple[int, str]:  # pragma: no cover
    return (0, "OK")


def copy_rates_from_pos(symbol: str, timeframe, start: int, count: int):
    tf_label = "M15" if timeframe == TIMEFRAME_M15 else "H1"
    key = (symbol.upper(), tf_label)
    if key not in _CACHE:
        filename = f"{symbol.upper()}_{tf_label}.csv"
        path = DATA_DIR / filename
        if not path.exists():
            return []
        df = pd.read_csv(path)
        if "timestamp" not in df.columns:
            return []
        df["timestamp"] = pd.to_datetime(df["timestamp"]) + pd.Timedelta(hours=12)
        _CACHE[key] = df
    df = _CACHE[key]
    tail = df.tail(count)
    return [
        {
            "time": int(row["timestamp"].timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "tick_volume": float(row.get("volume", 0.0)),
        }
        for _, row in tail.iterrows()
    ]
