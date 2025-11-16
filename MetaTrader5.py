"""Lightweight MT5 stub for offline smoke tests."""

from __future__ import annotations

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
TIMEFRAME_M15 = "M15"
TIMEFRAME_H1 = "H1"

TRADE_ACTION_DEAL = 1
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_FILLING_FOK = 0
ORDER_TIME_GTC = 0
TRADE_RETCODE_DONE = 0

_CACHE: dict[tuple[str, str], pd.DataFrame] = {}
_POSITIONS: dict[int, dict] = {}
_NEXT_TICKET = 1
_ACCOUNT_BALANCE = 100_000.0
_LOGIN = 123456
_SERVER = "DEMO"


def initialize() -> bool:  # pragma: no cover - trivial stub
    return True


def shutdown() -> None:  # pragma: no cover
    return None


def last_error() -> tuple[int, str]:  # pragma: no cover
    return (0, "OK")


def login(login: int | None = None, password: str | None = None, server: str | None = None) -> bool:
    global _LOGIN, _SERVER
    if login is not None:
        _LOGIN = login
    if server:
        _SERVER = server
    return True


def account_info():
    return type(
        "AccountInfo",
        (),
        {
            "balance": _ACCOUNT_BALANCE,
            "equity": _ACCOUNT_BALANCE,
            "profit": 0.0,
            "login": _LOGIN,
            "server": _SERVER,
        },
    )()


def positions_get(symbol: str | None = None):
    out = []
    for ticket, payload in _POSITIONS.items():
        if symbol and payload["symbol"] != symbol:
            continue
        out.append(
            type(
                "Position",
                (),
                {
                    "ticket": ticket,
                    "symbol": payload["symbol"],
                    "volume": payload["volume"],
                    "price_open": payload["price"],
                    "sl": payload.get("sl"),
                    "tp": payload.get("tp"),
                    "time": payload["time"],
                },
            )()
        )
    return out


def symbol_info_tick(symbol: str):
    return type("Tick", (), {"ask": 1.0, "bid": 1.0})()


def order_send(request: dict):
    global _NEXT_TICKET
    action = request.get("action")
    if action != TRADE_ACTION_DEAL:
        return type("Result", (), {"retcode": 1, "comment": "bad action", "order": 0})()
    position = request.get("position")
    if position:
        _POSITIONS.pop(position, None)
        return type("Result", (), {"retcode": TRADE_RETCODE_DONE, "comment": "closed", "order": position})()
    ticket = _NEXT_TICKET
    _NEXT_TICKET += 1
    _POSITIONS[ticket] = {
        "symbol": request.get("symbol", "EURUSD"),
        "volume": request.get("volume", 0.01),
        "price": request.get("price", 1.0),
        "sl": request.get("sl"),
        "tp": request.get("tp"),
        "time": int(pd.Timestamp.utcnow().timestamp()),
    }
    return type("Result", (), {"retcode": TRADE_RETCODE_DONE, "comment": "ok", "order": ticket})()


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
