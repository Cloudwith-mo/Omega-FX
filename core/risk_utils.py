"""Risk and pip conversion utilities."""

from __future__ import annotations

from core.position_sizing import get_symbol_meta


def pip_size(symbol: str) -> float:
    """
    Return pip size for symbol in price terms.
    
    Examples:
        EURUSD, GBPUSD: 0.0001 (4 decimals)
        USDJPY: 0.01 (2 decimals)
        XAUUSD: 0.01 (gold)
    """
    meta = get_symbol_meta(symbol)
    return meta.pip_size


def pips_to_price(pips: float, symbol: str) -> float:
    """
    Convert pip distance to price distance.
    
    Args:
        pips: Distance in pips
        symbol: Symbol name
        
    Returns:
        Price distance
        
    Examples:
        20 pips on GBPUSD = 0.0020
        50 pips on USDJPY = 0.50
    """
    return pips * pip_size(symbol)


def price_to_pips(price_distance: float, symbol: str) -> float:
    """
    Convert price distance to pips.
    
    Args:
        price_distance: Distance in price terms
        symbol: Symbol name
        
    Returns:
        Distance in pips
        
    Examples:
        0.0020 on GBPUSD = 20 pips
        0.50 on USDJPY = 50 pips
    """
    return price_distance / pip_size(symbol)


def calculate_sl_tp_prices(
    entry_price: float,
    direction: str,
    stop_pips: float,
    tp_pips: float | None,
    symbol: str,
) -> tuple[float, float | None]:
    """
    Calculate stop loss and take profit prices from pip distances.
    
    Args:
        entry_price: Entry price
        direction: "long" or "short"
        stop_pips: Stop loss distance in pips
        tp_pips: Take profit distance in pips (optional)
        symbol: Symbol name
        
    Returns:
        (stop_loss_price, take_profit_price)
        
    Examples:
        Long EURUSD at 1.1000, 20 pip stop, 40 pip TP:
        -> (1.0980, 1.1040)
        
        Short EURUSD at 1.1000, 20 pip stop, 40 pip TP:
        -> (1.1020, 1.0960)
    """
    stop_distance = pips_to_price(stop_pips, symbol)
    
    if direction == "long":
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + pips_to_price(tp_pips, symbol) if tp_pips else None
    else:  # short
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - pips_to_price(tp_pips, symbol) if tp_pips else None
    
    return stop_loss, take_profit
