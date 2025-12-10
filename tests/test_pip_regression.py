"""
Regression tests to prevent pip/point bugs from reappearing.

These tests verify that symbol-aware pip conversions work correctly
across different symbol families (4-decimal forex, 2-decimal JPY/Gold).
"""

import pytest
from core.risk_utils import calculate_sl_tp_prices, price_to_pips, pips_to_price


def test_gbpusd_sl_tp_long():
    """GBPUSD (4-decimal) long trade - verify 20/40 pips."""
    entry = 1.2700
    sl, tp = calculate_sl_tp_prices(
        entry_price=entry,
        direction="long",
        stop_pips=20,
        tp_pips=40,
        symbol="GBPUSD"
    )
    
    # Verify SL is 20 pips below entry
    assert abs(sl - 1.2680) < 1e-5, f"Expected SL=1.2680, got {sl}"
    sl_distance = abs(entry - sl)
    assert abs(price_to_pips(sl_distance, "GBPUSD") - 20.0) < 0.1
    
    # Verify TP is 40 pips above entry
    assert abs(tp - 1.2740) < 1e-5, f"Expected TP=1.2740, got {tp}"
    tp_distance = abs(tp - entry)
    assert abs(price_to_pips(tp_distance, "GBPUSD") - 40.0) < 0.1


def test_usdjpy_sl_tp_short():
    """USDJPY (2-decimal) short trade - verify 30/60 pips."""
    entry = 150.50
    sl, tp = calculate_sl_tp_prices(
        entry_price=entry,
        direction="short",
        stop_pips=30,
        tp_pips=60,
        symbol="USDJPY"
    )
    
    # Verify SL is 30 pips above entry (short)
    assert abs(sl - 150.80) < 1e-2, f"Expected SL=150.80, got {sl}"
    sl_distance = abs(sl - entry)
    assert abs(price_to_pips(sl_distance, "USDJPY") - 30.0) < 0.1
    
    # Verify TP is 60 pips below entry (short)
    assert abs(tp - 149.90) < 1e-2, f"Expected TP=149.90, got {tp}"
    tp_distance = abs(entry - tp)
    assert abs(price_to_pips(tp_distance, "USDJPY") - 60.0) < 0.1


def test_xauusd_sl_tp_long():
    """XAUUSD/Gold (2-decimal) long trade - verify 100/200 pips."""
    entry = 2000.00
    sl, tp = calculate_sl_tp_prices(
        entry_price=entry,
        direction="long",
        stop_pips=100,
        tp_pips=200,
        symbol="XAUUSD"
    )
    
    # Verify SL is 100 pips below entry
    assert abs(sl - 1999.00) < 1e-2, f"Expected SL=1999.00, got {sl}"
    sl_distance = abs(entry - sl)
    assert abs(price_to_pips(sl_distance, "XAUUSD") - 100.0) < 0.1
    
    # Verify TP is 200 pips above entry
    assert abs(tp - 2002.00) < 1e-2, f"Expected TP=2002.00, got {tp}"
    tp_distance = abs(tp - entry)
    assert abs(price_to_pips(tp_distance, "XAUUSD") - 200.0) < 0.1


def test_eurusd_no_hardcoded_10000():
    """Regression test: ensure we never use /10000 for all symbols."""
    # This would break for USDJPY and XAUUSD
    
    symbols_and_expected_pip_sizes = [
        ("EURUSD", 0.0001),
        ("GBPUSD", 0.0001),
        ("USDJPY", 0.01),
        ("XAUUSD", 0.01),
    ]
    
    for symbol, expected_pip_size in symbols_and_expected_pip_sizes:
        # Verify pips_to_price uses correct pip size
        price_dist = pips_to_price(20, symbol)
        expected_dist = 20 * expected_pip_size
        assert abs(price_dist - expected_dist) < 1e-6, \
            f"{symbol}: Expected {expected_dist}, got {price_dist}"


def test_multi_symbol_batch():
    """Simulate a batch of signals across different symbol families."""
    signals = [
        {"symbol": "EURUSD", "entry": 1.1000, "stop_pips": 25, "tp_pips": 50},
        {"symbol": "GBPUSD", "entry": 1.2800, "stop_pips": 30, "tp_pips": 60},
        {"symbol": "USDJPY", "entry": 150.00, "stop_pips": 35, "tp_pips": 70},
        {"symbol": "XAUUSD", "entry": 2050.00, "stop_pips": 150, "tp_pips": 300},
    ]
    
    for sig in signals:
        sl, tp = calculate_sl_tp_prices(
            entry_price=sig["entry"],
            direction="long",
            stop_pips=sig["stop_pips"],
            tp_pips=sig["tp_pips"],
            symbol=sig["symbol"]
        )
        
        # Verify SL distance matches requested pips
        sl_dist = abs(sig["entry"] - sl)
        sl_pips = price_to_pips(sl_dist, sig["symbol"])
        assert abs(sl_pips - sig["stop_pips"]) < 0.1, \
            f"{sig['symbol']}: SL pips={sl_pips:.1f}, expected={sig['stop_pips']}"
        
        # Verify TP distance matches requested pips
        tp_dist = abs(tp - sig["entry"])
        tp_pips = price_to_pips(tp_dist, sig["symbol"])
        assert abs(tp_pips - sig["tp_pips"]) < 0.1, \
            f"{sig['symbol']}: TP pips={tp_pips:.1f}, expected={sig['tp_pips']}"


def test_roundtrip_price_to_pips_to_price():
    """Ensure pips <-> price conversions are reversible."""
    test_cases = [
        ("EURUSD", 0.0025),
        ("GBPUSD", 0.0050),
        ("USDJPY", 0.50),
        ("XAUUSD", 2.50),
    ]
    
    for symbol, price_dist in test_cases:
        # Convert price -> pips -> price
        pips = price_to_pips(price_dist, symbol)
        price_back = pips_to_price(pips, symbol)
        
        assert abs(price_back - price_dist) < 1e-6, \
            f"{symbol}: {price_dist} -> {pips}pips -> {price_back} (roundtrip failed)"
