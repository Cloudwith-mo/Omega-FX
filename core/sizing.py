"""Position sizing calculations."""

from __future__ import annotations

from core.risk import RISK_CONFIG, RiskMode
from config.settings import MAX_LOT_SIZE, MIN_LOT_SIZE, PIP_VALUE_PER_STANDARD_LOT


def compute_position_size(
    account_equity: float,
    risk_mode: RiskMode,
    stop_distance_pips: float,
    pip_value_per_standard_lot: float = PIP_VALUE_PER_STANDARD_LOT,
) -> float:
    """
    Compute lot size for a trade based on risk configuration.

    Args:
        account_equity: current account equity in currency.
        risk_mode: chosen RiskMode enum.
        stop_distance_pips: stop size in pips; must be >0.
        pip_value_per_standard_lot: pip value; defaults to EUR/USD $10.

    Returns:
        float: lot size capped to [MIN_LOT_SIZE, MAX_LOT_SIZE].
    """
    if stop_distance_pips <= 0:
        raise ValueError("stop_distance_pips must be positive to compute position size.")

    config = RISK_CONFIG[risk_mode]
    risk_amount = account_equity * config["max_risk_per_trade"]

    raw_lots = risk_amount / (stop_distance_pips * pip_value_per_standard_lot)
    clipped_lots = min(max(raw_lots, MIN_LOT_SIZE), MAX_LOT_SIZE)
    return round(clipped_lots, 4)
