"""Configuration settings for Omega FX"""

from __future__ import annotations

from dataclasses import dataclass

from core.risk import RiskMode


INITIAL_EQUITY = 100_000.0
PIP_VALUE_PER_STANDARD_LOT = 10.0  # EUR/USD pip value at 1 standard lot
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 2.0
DEFAULT_DATA_PATH = "data/eurusd_h1.csv"
ENTRY_MODE = "H1_ONLY"


@dataclass(frozen=True)
class PropChallengeConfig:
    start_equity: float
    profit_target_fraction: float
    max_total_loss_fraction: float
    max_daily_loss_fraction: float


FUNDEDNEXT_100K = PropChallengeConfig(
    start_equity=100_000.0,
    profit_target_fraction=0.10,
    max_total_loss_fraction=0.06,
    max_daily_loss_fraction=0.03,
)

DEFAULT_CHALLENGE = FUNDEDNEXT_100K
DEFAULT_RISK_MODE = RiskMode.ULTRA_CONSERVATIVE


@dataclass(frozen=True)
class ChallengeConfig:
    start_equity: float = 100_000.0
    profit_target_fraction: float = 0.10
    max_total_loss_fraction: float = 0.06
    max_daily_loss_fraction: float = 0.03
    min_trading_days: int = 2
    max_trading_days: int = 60
    max_calendar_days: int = 90
    symbol: str = "EURUSD"


DEFAULT_CHALLENGE_CONFIG = ChallengeConfig()


@dataclass(frozen=True)
class BreakoutConfig:
    lookback_bars: int = 5
    atr_distance_max: float = 2.0
    trailing_atr_multiple: float = 1.0
    extended_tp_r_multiple: float = 3.0
    breakeven_trigger_r_multiple: float = 1.5
    initial_tp_r_multiple: float = 2.0


DEFAULT_BREAKOUT_CONFIG = BreakoutConfig()


@dataclass(frozen=True)
class SymbolConfig:
    name: str
    h1_path: str
    m15_path: str | None = None
    h4_path: str | None = None


# Filter toggles
ENABLE_SESSION_FILTER = True
ENABLE_TREND_FILTER = True
ENABLE_LOW_VOL_FILTER = False
ENABLE_HIGH_VOL_SIDEWAYS_FILTER = False
ENABLE_RISK_AGGRESSION_FILTER = True

# Risk aggression tuning
RISK_AGGRESSION_MAP_PATH = "config/risk_aggression_map.csv"
RISK_AGGRESSION_MIN_TRADES = 30
RISK_AGGRESSION_A_EXPECTANCY = 0.20
RISK_AGGRESSION_B_EXPECTANCY = 0.0
RISK_AGGRESSION_A_SCALE = 1.0
RISK_AGGRESSION_B_SCALE = 0.5
RISK_AGGRESSION_UNKNOWN_SCALE = 0.5
RISK_AGGRESSION_C_SCALE = 0.0

# Risk preset control (overridden by OMEGA_RISK_PRESET env var when set)
RISK_PROFILE_PRESET = "FULL"

# Symbol configuration for multi-pair backtesting
SYMBOLS = [
    SymbolConfig(
        name="EURUSD",
        h1_path="data/EURUSD_H1.csv",
        m15_path="data/EURUSD_M15.csv",
        h4_path="data/EURUSD_H4.csv",
    ),
    SymbolConfig(
        name="GBPUSD",
        h1_path="data/GBPUSD_H1.csv",
        m15_path="data/GBPUSD_M15.csv",
        h4_path="data/GBPUSD_H4.csv",
    ),
    SymbolConfig(
        name="USDJPY",
        h1_path="data/USDJPY_H1.csv",
        m15_path="data/USDJPY_M15.csv",
        h4_path="data/USDJPY_H4.csv",
    ),
]
