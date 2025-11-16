"""Risk management engine with conservative modes."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - avoid circular imports
    from config.settings import PropChallengeConfig, FirmProfile
    from core.backtest import ActivePosition


class RiskMode(Enum):
    ULTRA_ULTRA_CONSERVATIVE = "ultra_ultra_conservative"
    ULTRA_CONSERVATIVE = "ultra_conservative"
    CONSERVATIVE = "conservative"


@dataclass(frozen=True)
class RiskProfile:
    risk_per_trade_fraction: float
    daily_loss_limit_fraction: float
    max_trailing_dd_fraction: float
    max_open_trades: int


RISK_PROFILES = {
    # Assumes up to 2 sequential full-loss trades → theoretical daily loss <= 0.4%.
    RiskMode.ULTRA_ULTRA_CONSERVATIVE: RiskProfile(
        risk_per_trade_fraction=0.0020,
        daily_loss_limit_fraction=0.01,
        max_trailing_dd_fraction=0.02,
        max_open_trades=1,
    ),
    # Assumes up to 3 sequential full-loss trades → <= 1.2% daily loss.
    RiskMode.ULTRA_CONSERVATIVE: RiskProfile(
        risk_per_trade_fraction=0.0040,
        daily_loss_limit_fraction=0.015,
        max_trailing_dd_fraction=0.03,
        max_open_trades=1,
    ),
    # Assumes up to 3 sequential full-loss trades → <= 1.8% daily loss (<2% cap).
    RiskMode.CONSERVATIVE: RiskProfile(
        risk_per_trade_fraction=0.0060,
        daily_loss_limit_fraction=0.02,
        max_trailing_dd_fraction=0.04,
        max_open_trades=1,
    ),
}


@dataclass(init=False)
class RiskState:
    """Track equity, drawdown, and mode switching rules."""

    equity_peak: float
    current_equity: float
    start_of_day_equity: float
    current_mode: RiskMode
    trading_paused: bool

    def __init__(
        self,
        initial_equity: float,
        initial_mode: RiskMode = RiskMode.CONSERVATIVE,
        firm_profile: "FirmProfile" | None = None,
    ) -> None:
        self.equity_peak = initial_equity
        self.current_equity = initial_equity
        self.start_of_day_equity = initial_equity
        self.current_mode = initial_mode
        self.trading_paused = False
        self.firm_profile: "FirmProfile" | None = firm_profile
        self.internal_stop_out_triggered = False
        self.prop_fail_triggered = False
        self.internal_stop_timestamp: datetime | None = None
        self.prop_fail_timestamp: datetime | None = None

    @property
    def total_dd_from_peak(self) -> float:
        """Total drawdown fraction relative to the highest equity."""
        if self.equity_peak <= 0:
            return 0.0
        return (self.equity_peak - self.current_equity) / self.equity_peak

    @property
    def daily_dd(self) -> float:
        """Same-day drawdown fraction relative to the daily opening equity."""
        if self.start_of_day_equity <= 0:
            return 0.0
        return (self.start_of_day_equity - self.current_equity) / self.start_of_day_equity

    def update_equity(self, new_equity: float) -> None:
        """Update equity and peak when a realized PnL occurs."""
        self.current_equity = new_equity
        if new_equity > self.equity_peak:
            self.equity_peak = new_equity

    def on_new_day(self) -> None:
        """Reset daily metrics for a fresh trading day."""
        self.start_of_day_equity = self.current_equity

    def enforce_drawdown_limits(
        self,
        profile: RiskProfile,
        challenge: "PropChallengeConfig",
        timestamp: datetime | None = None,
    ) -> None:
        dd = self.total_dd_from_peak

        if dd >= challenge.max_total_loss_fraction:
            self.prop_fail_triggered = True
            self.trading_paused = True
            if self.prop_fail_timestamp is None and timestamp is not None:
                self.prop_fail_timestamp = timestamp

        internal_limit = (
            self.firm_profile.internal_max_trailing_dd_fraction
            if self.firm_profile is not None
            else profile.max_trailing_dd_fraction
        )
        if dd >= internal_limit:
            self.internal_stop_out_triggered = True
            self.trading_paused = True
            if self.internal_stop_timestamp is None and timestamp is not None:
                self.internal_stop_timestamp = timestamp

    def can_trade(self) -> bool:
        return not (self.trading_paused or self.internal_stop_out_triggered)


def can_open_new_trade(
    todays_realized_pnl: float,
    open_positions: Iterable["ActivePosition"],
    proposed_trade_risk_amount: float,
    equity_start_of_day: float,
    profile: RiskProfile,
    challenge: "PropChallengeConfig",
    firm_profile: "FirmProfile" | None = None,
) -> bool:
    internal_fraction = (
        firm_profile.internal_max_daily_loss_fraction
        if firm_profile is not None
        else profile.daily_loss_limit_fraction
    )
    internal_daily_limit = internal_fraction * equity_start_of_day
    prop_daily_limit = challenge.max_daily_loss_fraction * equity_start_of_day
    if internal_daily_limit - prop_daily_limit > 1e-9:
        raise ValueError("Internal daily limit exceeds prop firm daily cap.")

    realized_loss = max(0.0, -todays_realized_pnl)
    worst_case_open_loss = realized_loss
    for pos in open_positions:
        worst_case_open_loss += pos.max_loss_amount

    worst_case_open_loss += proposed_trade_risk_amount
    return worst_case_open_loss <= internal_daily_limit


@dataclass
class ModeTransition:
    timestamp: datetime
    old_mode: RiskMode
    new_mode: RiskMode
    reason: str


@dataclass
class RiskModeController:
    state: RiskState
    window_size: int = 40
    transitions: list[ModeTransition] = field(default_factory=list)
    trade_pnls: deque[float] = field(default_factory=lambda: deque(maxlen=40))
    equity_history: deque[float] = field(default_factory=lambda: deque(maxlen=40))

    def __post_init__(self) -> None:  # pragma: no cover - trivial
        self.trade_pnls = deque(maxlen=self.window_size)
        self.equity_history = deque(maxlen=self.window_size)

    @property
    def current_mode(self) -> RiskMode:
        return self.state.current_mode

    def transition(self, timestamp: datetime, new_mode: RiskMode, reason: str) -> None:
        old_mode = self.state.current_mode
        if new_mode == old_mode:
            return
        self.transitions.append(
            ModeTransition(timestamp=timestamp, old_mode=old_mode, new_mode=new_mode, reason=reason)
        )
        self.state.current_mode = new_mode

    def step_down_for_drawdown(self, timestamp: datetime, dd_fraction: float) -> None:
        if dd_fraction >= 0.03:
            self.transition(timestamp, RiskMode.ULTRA_ULTRA_CONSERVATIVE, "Drawdown >= 3%")
        elif dd_fraction >= 0.02 and self.state.current_mode == RiskMode.CONSERVATIVE:
            self.transition(timestamp, RiskMode.ULTRA_CONSERVATIVE, "Drawdown >= 2%")

    def record_trade(self, pnl: float, equity_after_trade: float, timestamp: datetime) -> None:
        self.trade_pnls.append(pnl)
        self.equity_history.append(equity_after_trade)
        self.maybe_step_up(timestamp)

    def maybe_step_up(self, timestamp: datetime) -> None:
        if len(self.trade_pnls) < self.window_size:
            return
        if self.state.current_equity < self.state.equity_peak - 1e-9:
            return

        win_rate = sum(1 for pnl in self.trade_pnls if pnl > 0) / len(self.trade_pnls)
        dd_recent = self._recent_drawdown_from_history()

        if win_rate < 0.58 or dd_recent > 0.015:
            return

        if self.state.current_mode == RiskMode.ULTRA_ULTRA_CONSERVATIVE:
            self.transition(timestamp, RiskMode.ULTRA_CONSERVATIVE, "Performance step-up")
        elif self.state.current_mode == RiskMode.ULTRA_CONSERVATIVE:
            self.transition(timestamp, RiskMode.CONSERVATIVE, "Performance step-up")

    def _recent_drawdown_from_history(self) -> float:
        if len(self.equity_history) < 2:
            return 0.0
        max_equity = max(self.equity_history)
        min_equity = min(self.equity_history)
        if max_equity == 0:
            return 0.0
        return (max_equity - min_equity) / max_equity
