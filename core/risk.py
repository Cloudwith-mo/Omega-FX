"""Risk management engine with conservative modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskMode(Enum):
    ULTRA_ULTRA_CONSERVATIVE = "ultra_ultra_conservative"
    ULTRA_CONSERVATIVE = "ultra_conservative"
    CONSERVATIVE = "conservative"


RISK_CONFIG = {
    RiskMode.ULTRA_ULTRA_CONSERVATIVE: {
        "max_risk_per_trade": 0.0010,  # 0.10%
        "max_trades_per_day": 2,
        "daily_loss_cap": 0.010,  # 1%
    },
    RiskMode.ULTRA_CONSERVATIVE: {
        "max_risk_per_trade": 0.0020,  # 0.20%
        "max_trades_per_day": 3,
        "daily_loss_cap": 0.015,  # 1.5%
    },
    RiskMode.CONSERVATIVE: {
        "max_risk_per_trade": 0.0030,  # 0.30%
        "max_trades_per_day": 4,
        "daily_loss_cap": 0.020,  # 2%
    },
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
    ) -> None:
        self.equity_peak = initial_equity
        self.current_equity = initial_equity
        self.start_of_day_equity = initial_equity
        self.current_mode = initial_mode
        self.trading_paused = False

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

    def update_mode_based_on_performance(
        self,
        win_rate_last_N: float | None,
        max_dd_last_N: float | None,
    ) -> None:
        """Toggle risk modes based on drawdown and recent performance."""
        dd = self.total_dd_from_peak

        # Step-down logic based purely on drawdown depth.
        if dd >= 0.03:
            self.trading_paused = True
            self.current_mode = RiskMode.ULTRA_ULTRA_CONSERVATIVE
        elif dd >= 0.025:
            self.current_mode = RiskMode.ULTRA_ULTRA_CONSERVATIVE
        elif dd >= 0.015:
            if self.current_mode == RiskMode.CONSERVATIVE:
                self.current_mode = RiskMode.ULTRA_CONSERVATIVE
            elif self.current_mode == RiskMode.ULTRA_CONSERVATIVE:
                self.current_mode = RiskMode.ULTRA_ULTRA_CONSERVATIVE

        # Step-up only when at peak equity and stats are strong.
        meets_stats = (
            win_rate_last_N is not None
            and win_rate_last_N >= 0.58
            and max_dd_last_N is not None
            and max_dd_last_N <= 0.015
        )
        if self.current_equity == self.equity_peak and meets_stats:
            if self.current_mode == RiskMode.ULTRA_ULTRA_CONSERVATIVE:
                self.current_mode = RiskMode.ULTRA_CONSERVATIVE
                self.trading_paused = False
            elif self.current_mode == RiskMode.ULTRA_CONSERVATIVE:
                self.current_mode = RiskMode.CONSERVATIVE

    def can_trade_today(self) -> bool:
        """True when trading is allowed under pause + daily loss rules."""
        if self.trading_paused:
            return False
        if self.daily_dd >= 0.02:
            return False
        return True
