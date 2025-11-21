"""Utility helpers for execution-time position sizing."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import MAX_LOT_SIZE, MIN_LOT_SIZE


@dataclass(frozen=True)
class SymbolMeta:
    symbol: str
    pip_value_per_standard_lot: float
    pip_size: float
    lot_step: float = 0.01


DEFAULT_SYMBOL_META = {
    "EURUSD": SymbolMeta(
        "EURUSD", pip_value_per_standard_lot=10.0, pip_size=0.0001
    ),
    "GBPUSD": SymbolMeta(
        "GBPUSD", pip_value_per_standard_lot=10.0, pip_size=0.0001
    ),
    "USDJPY": SymbolMeta("USDJPY", pip_value_per_standard_lot=9.0, pip_size=0.01),
}


def get_symbol_meta(symbol: str) -> SymbolMeta:
    return DEFAULT_SYMBOL_META.get(symbol.upper(), DEFAULT_SYMBOL_META["EURUSD"])


def calculate_position_size(
    equity: float,
    risk_fraction: float,
    entry_price: float,
    stop_price: float,
    symbol: str,
) -> float:
    """Return MT5 lot-size given equity, risk fraction, and stop distance."""

    if equity <= 0:
        raise ValueError("Equity must be positive for position sizing.")
    if risk_fraction <= 0:
        raise ValueError("Risk fraction must be positive.")
    if entry_price <= 0 or stop_price <= 0:
        raise ValueError("Prices must be positive for position sizing.")
    if entry_price == stop_price:
        raise ValueError("Entry and stop prices must differ for position sizing.")

    meta = get_symbol_meta(symbol)
    pip_distance = abs(entry_price - stop_price) / meta.pip_size
    if pip_distance <= 0:
        raise ValueError("Stop distance must be positive.")

    risk_amount = equity * risk_fraction
    cost_per_standard_lot = (
        pip_distance * meta.pip_value_per_standard_lot
    )
    if cost_per_standard_lot <= 0:
        raise ValueError("Cost per lot must be positive.")

    raw_lots = risk_amount / cost_per_standard_lot
    clipped = max(MIN_LOT_SIZE, min(raw_lots, MAX_LOT_SIZE))
    rounded = round(clipped / meta.lot_step) * meta.lot_step
    return round(max(MIN_LOT_SIZE, min(rounded, MAX_LOT_SIZE)), 2)
