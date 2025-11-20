from __future__ import annotations

from typing import Optional

import pandas as pd

from core.strategy import TradeDecision

OMEGA_MR_STRATEGY_ID = "OMEGA_MR_M15"
PIP_FACTOR = 10_000.0
ADX_THRESHOLD = 30.0
RSI_LOW = 30.0
RSI_HIGH = 70.0


def generate_mean_reversion_signal(current_row: pd.Series, previous_row: Optional[pd.Series] = None) -> Optional[TradeDecision]:
    """Bollinger/RSI fade strategy on M15 bars."""
    adx = float(current_row.get("ADX_14", 0.0) or 0.0)
    if adx >= ADX_THRESHOLD or pd.isna(adx):
        return None
    close_price = float(current_row.get("close", 0.0) or 0.0)
    lower = current_row.get("BB_LOWER_20_2")
    upper = current_row.get("BB_UPPER_20_2")
    mid = current_row.get("BB_MID_20")
    rsi = float(current_row.get("RSI_14", 50.0) or 50.0)
    atr = float(current_row.get("ATR_14", 0.0) or 0.0)
    if any(pd.isna(val) for val in (lower, upper, mid, atr)):
        return None
    stop_pips = max(atr * PIP_FACTOR * 1.5, 1.0)
    if close_price < float(lower) and rsi < RSI_LOW:
        tp_pips = max((float(mid) - close_price) * PIP_FACTOR, 0.0)
        if tp_pips <= 0:
            tp_pips = stop_pips
        return TradeDecision(
            "long",
            stop_pips,
            tp_pips,
            "Omega MR M15 long",
            variant="mr_bb_rsi",
            signal_reason="bb_rsi_fade_long",
            strategy_id=OMEGA_MR_STRATEGY_ID,
        )
    if close_price > float(upper) and rsi > RSI_HIGH:
        tp_pips = max((close_price - float(mid)) * PIP_FACTOR, 0.0)
        if tp_pips <= 0:
            tp_pips = stop_pips
        return TradeDecision(
            "short",
            stop_pips,
            tp_pips,
            "Omega MR M15 short",
            variant="mr_bb_rsi",
            signal_reason="bb_rsi_fade_short",
            strategy_id=OMEGA_MR_STRATEGY_ID,
        )
    return None


__all__ = ["OMEGA_MR_STRATEGY_ID", "generate_mean_reversion_signal"]
