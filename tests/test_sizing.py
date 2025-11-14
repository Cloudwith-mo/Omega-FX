"""Position sizing tests."""

import math

import pytest

from core.risk import RiskMode
from core.sizing import compute_position_size


def test_higher_equity_scales_size_within_caps():
    base = compute_position_size(10_000, RiskMode.CONSERVATIVE, stop_distance_pips=20)
    double_equity = compute_position_size(20_000, RiskMode.CONSERVATIVE, stop_distance_pips=20)
    assert double_equity > base


def test_larger_stop_distance_reduces_size():
    short_stop = compute_position_size(10_000, RiskMode.CONSERVATIVE, 10)
    long_stop = compute_position_size(10_000, RiskMode.CONSERVATIVE, 40)
    assert long_stop < short_stop


def test_mode_impacts_lot_size():
    ultra = compute_position_size(10_000, RiskMode.ULTRA_ULTRA_CONSERVATIVE, 20)
    conservative = compute_position_size(10_000, RiskMode.CONSERVATIVE, 20)
    assert conservative > ultra


def test_clipping_to_min_and_max():
    min_size = compute_position_size(100, RiskMode.ULTRA_ULTRA_CONSERVATIVE, 200)
    assert math.isclose(min_size, 0.01, rel_tol=0, abs_tol=1e-6)

    max_size = compute_position_size(1_000_000, RiskMode.CONSERVATIVE, 5)
    assert math.isclose(max_size, 2.0, rel_tol=0, abs_tol=1e-6)


def test_invalid_stop_distance_raises():
    with pytest.raises(ValueError):
        compute_position_size(10_000, RiskMode.CONSERVATIVE, 0)
