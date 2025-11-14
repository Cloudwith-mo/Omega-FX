"""Risk engine tests for FundedNext-aware configuration."""

from dataclasses import dataclass

import pytest

from config.settings import FUNDEDNEXT_100K
from core.risk import RISK_PROFILES, RiskMode, RiskState, can_open_new_trade


@dataclass
class DummyPosition:
    max_loss_amount: float


def test_risk_state_enforces_internal_stop_before_prop_fail():
    state = RiskState(initial_equity=100_000.0, initial_mode=RiskMode.CONSERVATIVE)
    profile = RISK_PROFILES[RiskMode.CONSERVATIVE]

    # 5% drawdown should breach internal 4% cap but stay below prop 6%.
    state.update_equity(95_000.0)
    state.enforce_drawdown_limits(profile, FUNDEDNEXT_100K)

    assert state.internal_stop_out_triggered is True
    assert state.prop_fail_triggered is False
    assert state.trading_paused is True


def test_can_open_new_trade_blocks_when_daily_loss_would_exceed_cap():
    profile = RISK_PROFILES[RiskMode.ULTRA_CONSERVATIVE]
    equity_start = 100_000.0
    internal_limit = profile.daily_loss_limit_fraction * equity_start
    assert internal_limit == pytest.approx(1_500.0)

    allowed = can_open_new_trade(
        todays_realized_pnl=-500.0,
        open_positions=[DummyPosition(max_loss_amount=400.0)],
        proposed_trade_risk_amount=200.0,
        equity_start_of_day=equity_start,
        profile=profile,
        challenge=FUNDEDNEXT_100K,
    )
    assert allowed is True

    blocked = can_open_new_trade(
        todays_realized_pnl=-1_200.0,
        open_positions=[DummyPosition(max_loss_amount=400.0)],
        proposed_trade_risk_amount=200.0,
        equity_start_of_day=equity_start,
        profile=profile,
        challenge=FUNDEDNEXT_100K,
    )
    assert blocked is False


def test_can_open_new_trade_raises_if_internal_limit_gt_prop_cap():
    profile = RISK_PROFILES[RiskMode.CONSERVATIVE]
    # Temporarily tamper with profile to simulate invalid config.
    bad_profile = profile.__class__(
        risk_per_trade_fraction=profile.risk_per_trade_fraction,
        daily_loss_limit_fraction=0.05,
        max_trailing_dd_fraction=profile.max_trailing_dd_fraction,
        max_open_trades=profile.max_open_trades,
    )

    with pytest.raises(ValueError):
        can_open_new_trade(
            todays_realized_pnl=0.0,
            open_positions=[],
            proposed_trade_risk_amount=0.0,
            equity_start_of_day=100_000.0,
            profile=bad_profile,
            challenge=FUNDEDNEXT_100K,
        )
