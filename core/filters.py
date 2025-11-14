"""Trade-filter utilities for session/trend/volatility gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.settings import (
    ENABLE_HIGH_VOL_SIDEWAYS_FILTER,
    ENABLE_LOW_VOL_FILTER,
    ENABLE_SESSION_FILTER,
    ENABLE_TREND_FILTER,
)

@dataclass
class TradeTags:
    session_tag: Optional[str]
    trend_regime: Optional[str]
    volatility_regime: Optional[str]


@dataclass
class TradeFilterResult:
    allowed: bool
    reason: Optional[str] = None
    session_passed: bool = False
    trend_passed: bool = False
    volatility_passed: bool = False


def should_allow_trade(tags: TradeTags) -> TradeFilterResult:
    """Apply high-level filters to decide if a new trade is permitted."""
    session = (tags.session_tag or "").upper()
    trend = (tags.trend_regime or "").upper()
    volatility = (tags.volatility_regime or "").upper()

    session_passed = True
    if ENABLE_SESSION_FILTER:
        session_passed = session != "ASIA"
    if not session_passed:
        return TradeFilterResult(False, "session", session_passed=False)

    trend_passed = True
    if ENABLE_TREND_FILTER:
        trend_passed = trend != "COUNTER_TREND"
    if not trend_passed:
        return TradeFilterResult(False, "trend", session_passed=True, trend_passed=False)

    volatility_passed = True
    reason = None
    if ENABLE_LOW_VOL_FILTER and volatility == "LOW":
        volatility_passed = False
        reason = "low_volatility"
    elif ENABLE_HIGH_VOL_SIDEWAYS_FILTER and volatility == "HIGH" and trend == "SIDEWAYS":
        volatility_passed = False
        reason = "high_vol_sideways"
    elif volatility not in {"LOW", "NORMAL", "HIGH", "UNKNOWN"}:
        volatility_passed = False
        reason = "volatility"

    if not volatility_passed:
        return TradeFilterResult(
            False,
            reason,
            session_passed=True,
            trend_passed=True,
            volatility_passed=False,
        )

    return TradeFilterResult(True, None, True, True, True)
