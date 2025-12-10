"""Tests for pip/price conversion utilities."""

from __future__ import annotations

import pytest

from core.risk_utils import (
    calculate_sl_tp_prices,
    pip_size,
    pips_to_price,
    price_to_pips,
)


def test_pip_size_eurusd():
    """EUR/USD has 4 decimal places, pip = 0.0001."""
    assert pip_size("EURUSD") == 0.0001


def test_pip_size_gbpusd():
    """GBP/USD has 4 decimal places, pip = 0.0001."""
    assert pip_size("GBPUSD") == 0.0001


def test_pip_size_usdjpy():
    """USD/JPY has 2 decimal places, pip = 0.01."""
    assert pip_size("USDJPY") == 0.01


def test_pip_size_xauusd():
    """Gold has 2 decimal places, pip = 0.01."""
    assert pip_size("XAUUSD") == 0.01


def test_pips_to_price_20_pips_gbpusd():
    """20 pips on GBPUSD = 0.0020."""
    assert pips_to_price(20, "GBPUSD") == pytest.approx(0.0020)


def test_pips_to_price_50_pips_usdjpy():
    """50 pips on USDJPY = 0.50."""
    assert pips_to_price(50, "USDJPY") == pytest.approx(0.50)


def test_pips_to_price_40_pips_eurusd():
    """40 pips on EURUSD = 0.0040."""
    assert pips_to_price(40, "EURUSD") == pytest.approx(0.0040)


def test_price_to_pips_0002_gbpusd():
    """0.0020 on GBPUSD = 20 pips."""
    assert price_to_pips(0.0020, "GBPUSD") == pytest.approx(20)


def test_price_to_pips_050_usdjpy():
    """0.50 on USDJPY = 50 pips."""
    assert price_to_pips(0.50, "USDJPY") == pytest.approx(50)


def test_calculate_sl_tp_long_eurusd():
    """
    Long EURUSD at 1.1000, 20 pip stop, 40 pip TP:
    -> SL = 1.0980, TP = 1.1040
    """
    stop, tp = calculate_sl_tp_prices(
        entry_price=1.1000,
        direction="long",
        stop_pips=20,
        tp_pips=40,
        symbol="EURUSD",
    )
    assert stop == pytest.approx(1.0980)
    assert tp == pytest.approx(1.1040)


def test_calculate_sl_tp_short_eurusd():
    """
    Short EURUSD at 1.1000, 20 pip stop, 40 pip TP:
    -> SL = 1.1020, TP = 1.0960
    """
    stop, tp = calculate_sl_tp_prices(
        entry_price=1.1000,
        direction="short",
        stop_pips=20,
        tp_pips=40,
        symbol="EURUSD",
    )
    assert stop == pytest.approx(1.1020)
    assert tp == pytest.approx(1.0960)


def test_calculate_sl_tp_long_usdjpy():
    """
    Long USDJPY at 150.00, 30 pip stop, 60 pip TP:
    -> SL = 149.70, TP = 150.60
    """
    stop, tp = calculate_sl_tp_prices(
        entry_price=150.00,
        direction="long",
        stop_pips=30,
        tp_pips=60,
        symbol="USDJPY",
    )
    assert stop == pytest.approx(149.70)
    assert tp == pytest.approx(150.60)


def test_calculate_sl_tp_no_tp():
    """Test with no take profit."""
    stop, tp = calculate_sl_tp_prices(
        entry_price=1.1000,
        direction="long",
        stop_pips=20,
        tp_pips=None,
        symbol="EURUSD",
    )
    assert stop == pytest.approx(1.0980)
    assert tp is None


def test_pips_to_price_prevents_hardcoded_10000_bug():
    """
    This test ensures we don't regress to the /10_000 bug.
    The bug manifested when using /10_000 for all symbols, which breaks USDJPY.
    """
    # EURUSD: 20 pips = 0.0020 (happens to equal 20/10000, but only for 4-decimal pairs)
    eurusd_distance = pips_to_price(20, "EURUSD")
    assert eurusd_distance == pytest.approx(0.0020)
    
    # USDJPY: 20 pips = 0.20 (NOT 0.002!)
    # This is where the /10_000 bug fails
    usdjpy_distance = pips_to_price(20, "USDJPY")
    assert usdjpy_distance == pytest.approx(0.20)
    
    # The bug: using /10_000 for USDJPY gives wrong result
    buggy_calculation = 20 / 10_000  # = 0.002
    assert usdjpy_distance != buggy_calculation  # Our fix prevents this!
    assert usdjpy_distance == pytest.approx(0.20), "USDJPY pips must account for 2-decimal pip_size"
