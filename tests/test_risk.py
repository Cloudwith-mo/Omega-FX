"""Risk engine tests."""

from core.risk import RiskMode, RiskState


def test_initial_state_conservative_and_tradable():
    state = RiskState(initial_equity=10_000.0)
    assert state.current_mode == RiskMode.CONSERVATIVE
    assert state.total_dd_from_peak == 0
    assert state.can_trade_today() is True


def test_step_down_thresholds_and_pause():
    state = RiskState(initial_equity=10_000.0)

    state.update_equity(9_850.0)  # 1.5% drawdown
    state.update_mode_based_on_performance(None, None)
    assert state.current_mode == RiskMode.ULTRA_CONSERVATIVE
    assert state.trading_paused is False

    state.update_equity(9_750.0)  # 2.5% drawdown
    state.update_mode_based_on_performance(None, None)
    assert state.current_mode == RiskMode.ULTRA_ULTRA_CONSERVATIVE
    assert state.trading_paused is False

    state.update_equity(9_700.0)  # 3% drawdown
    state.update_mode_based_on_performance(None, None)
    assert state.current_mode == RiskMode.ULTRA_ULTRA_CONSERVATIVE
    assert state.trading_paused is True


def test_daily_loss_stop_blocks_until_new_day():
    state = RiskState(initial_equity=10_000.0)
    state.update_equity(9_790.0)  # >2% same-day loss
    assert state.can_trade_today() is False

    state.on_new_day()
    assert state.can_trade_today() is True


def test_step_up_requires_peak_and_good_stats():
    state = RiskState(initial_equity=10_000.0)
    # Force step-down pause.
    state.update_equity(9_700.0)
    state.update_mode_based_on_performance(None, None)
    assert state.current_mode == RiskMode.ULTRA_ULTRA_CONSERVATIVE
    assert state.trading_paused is True

    # Recover to new peak with solid stats.
    state.update_equity(10_100.0)
    state.update_mode_based_on_performance(0.60, 0.01)
    assert state.current_mode == RiskMode.ULTRA_CONSERVATIVE
    assert state.trading_paused is False

    # Another good block promotes back to CONSERVATIVE.
    state.update_mode_based_on_performance(0.65, 0.005)
    assert state.current_mode == RiskMode.CONSERVATIVE


def test_explicit_pause_blocks_trading():
    state = RiskState(initial_equity=10_000.0)
    state.trading_paused = True
    assert state.can_trade_today() is False
