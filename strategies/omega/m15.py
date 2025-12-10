"""Ω-FX M15 strategy wrapper.

This class exposes the existing SMA/ATR based M15 logic through the
:class:`~core.strategy_base.Strategy` interface.  Phase 1 keeps the
backtester wiring intact; future phases can instantiate this strategy
and feed it pre-computed features.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from core.strategy import generate_signal
from core.strategy_base import Strategy


class OmegaM15Strategy(Strategy):
    """Thin wrapper around the current Ω-FX M15 signal logic."""

    name = "omega_m15"

    def required_features(self) -> dict[str, list[str]]:
        # The existing generate_signal() helper needs the close price,
        # two SMAs, and ATR.  We expose both the current and previous
        # bar requirements explicitly.
        return {
            "M15_current": ["close", "SMA_fast", "SMA_slow", "ATR_14"],
            "M15_previous": ["close", "SMA_fast", "SMA_slow", "ATR_14"],
        }

    def on_bar(
        self, timestamp: Any, features_by_tf: Mapping[str, Any]
    ) -> dict[str, Any]:
        entry = features_by_tf.get("M15_current")
        prev = features_by_tf.get("M15_previous")
        current_row = self._to_series(entry)
        previous_row = self._to_series(prev)
        if current_row is None or previous_row is None:
            return {
                "action": "flat",
                "risk_tier": "UNKNOWN",
                "meta": {"reason": "missing_features"},
            }
        decision = generate_signal(current_row, previous_row)
        meta = {
            "reason": decision.reason,
            "variant": decision.variant,
            "stop_distance_pips": decision.stop_distance_pips,
            "take_profit_distance_pips": decision.take_profit_distance_pips,
            "signal_reason": getattr(decision, "signal_reason", "unknown"),
        }
        return {
            "action": decision.action,
            "risk_tier": "UNKNOWN",
            "meta": meta,
        }

    @staticmethod
    def _to_series(payload: Any) -> pd.Series | None:
        if isinstance(payload, pd.Series):
            return payload
        if isinstance(payload, Mapping):
            return pd.Series(payload)
        return None
