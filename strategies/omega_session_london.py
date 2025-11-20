"""London session breakout momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.strategy import TradeDecision

OMEGA_SESSION_LDN_STRATEGY_ID = "OMEGA_SESSION_LDN_M15"
PIP_FACTOR = 10_000.0


@dataclass
class LondonSessionConfig:
    symbol: str = "GBPUSD"
    asian_start_hour: int = 0
    asian_end_hour: int = 7
    london_end_hour: int = 12
    min_range_pips: float = 15.0
    max_range_pips: float = 60.0
    trigger_buffer_pips: float = 3.0


def _to_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC")
    return ts


def make_london_session_strategy(config: LondonSessionConfig | None = None):
    """Return a callable strategy function bound to internal day state."""

    cfg = config or LondonSessionConfig()

    state: dict[str, object | None] = {
        "current_day": None,
        "asian_high": None,
        "asian_low": None,
        "buy_trigger": None,
        "sell_trigger": None,
        "box_height": None,
        "box_mid": None,
        "box_ready": False,
        "box_invalid": False,
        "triggered_side": None,
    }

    def _reset(new_day):
        state["current_day"] = new_day
        state["asian_high"] = None
        state["asian_low"] = None
        state["buy_trigger"] = None
        state["sell_trigger"] = None
        state["box_height"] = None
        state["box_mid"] = None
        state["box_ready"] = False
        state["box_invalid"] = False
        state["triggered_side"] = None

    def _record_asian_range(high: float, low: float) -> None:
        asian_high = state["asian_high"]
        asian_low = state["asian_low"]
        state["asian_high"] = high if asian_high is None else max(asian_high, high)
        if asian_low is None:
            state["asian_low"] = low
        else:
            state["asian_low"] = min(asian_low, low)

    def _finalize_box() -> None:
        if state["asian_high"] is None or state["asian_low"] is None:
            state["box_invalid"] = True
            state["box_ready"] = False
            return
        height = float(state["asian_high"]) - float(state["asian_low"])
        height_pips = height * PIP_FACTOR
        if not (cfg.min_range_pips <= height_pips <= cfg.max_range_pips):
            state["box_invalid"] = True
            state["box_ready"] = False
            return
        buffer_price = cfg.trigger_buffer_pips / PIP_FACTOR
        state["buy_trigger"] = float(state["asian_high"]) + buffer_price
        state["sell_trigger"] = float(state["asian_low"]) - buffer_price
        state["box_height"] = height
        state["box_mid"] = (float(state["asian_high"]) + float(state["asian_low"])) / 2
        state["box_ready"] = True
        state["box_invalid"] = False

    def strategy(current_row: pd.Series, previous_row: Optional[pd.Series] = None) -> Optional[TradeDecision]:
        symbol = str(current_row.get("symbol") or "").upper()
        if symbol != cfg.symbol:
            return None

        timestamp = _to_timestamp(current_row.get("timestamp"))
        day = timestamp.date()
        if state["current_day"] != day:
            _reset(day)

        hour = timestamp.hour
        high = float(current_row.get("high", float("nan")))
        low = float(current_row.get("low", float("nan")))
        if pd.isna(high) or pd.isna(low):
            return None

        if cfg.asian_start_hour <= hour < cfg.asian_end_hour:
            _record_asian_range(high, low)
            state["box_ready"] = False
            state["box_invalid"] = False
            return None

        if not state["box_ready"] and not state["box_invalid"] and hour >= cfg.asian_end_hour:
            _finalize_box()

        if state["box_invalid"] or not state["box_ready"]:
            return None

        if hour < cfg.asian_end_hour or hour >= cfg.london_end_hour:
            return None

        if state["triggered_side"]:
            return None

        buy_trigger = state["buy_trigger"]
        sell_trigger = state["sell_trigger"]
        triggered_direction: Optional[str] = None
        entry_price: Optional[float] = None

        if buy_trigger is not None and high >= buy_trigger:
            triggered_direction = "long"
            entry_price = buy_trigger
        elif sell_trigger is not None and low <= sell_trigger:
            triggered_direction = "short"
            entry_price = sell_trigger

        if not triggered_direction or entry_price is None:
            return None

        state["triggered_side"] = triggered_direction
        box_mid = float(state["box_mid"])
        box_height = float(state["box_height"])
        stop_distance_pips = abs(entry_price - box_mid) * PIP_FACTOR
        if stop_distance_pips <= 0:
            stop_distance_pips = max(box_height * PIP_FACTOR * 0.5, 1.0)
        take_profit_pips = max(box_height * PIP_FACTOR, 1.0)
        return TradeDecision(
            triggered_direction,
            stop_distance_pips,
            take_profit_pips,
            "London session breakout",
            variant="ldn_session",
            signal_reason=f"ldn_{triggered_direction}",
            strategy_id=OMEGA_SESSION_LDN_STRATEGY_ID,
        )

    return strategy


__all__ = ["OMEGA_SESSION_LDN_STRATEGY_ID", "LondonSessionConfig", "make_london_session_strategy"]
