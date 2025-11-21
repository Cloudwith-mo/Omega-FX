"""Configuration settings for Omega FX"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from core.risk import RiskMode

INITIAL_EQUITY = 100_000.0
PIP_VALUE_PER_STANDARD_LOT = 10.0  # EUR/USD pip value at 1 standard lot
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 2.0
DEFAULT_DATA_PATH = "data/eurusd_h1.csv"
ENTRY_MODE = "H1_ONLY"
MAX_CONCURRENT_POSITIONS = 2


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
        h1_path="data/EURUSD_1h.csv",
        m15_path="data/EURUSD_15m.csv",
        h4_path="data/EURUSD_4h.csv",
    ),
    SymbolConfig(
        name="GBPUSD",
        h1_path="data/GBPUSD_1h.csv",
        m15_path="data/GBPUSD_15m.csv",
        h4_path="data/GBPUSD_4h.csv",
    ),
    SymbolConfig(
        name="USDJPY",
        h1_path="data/USDJPY_1h.csv",
        m15_path="data/USDJPY_15m.csv",
        h4_path="data/USDJPY_4h.csv",
    ),
    SymbolConfig(
        name="GCF",
        h1_path="data/GCF_1h.csv",
        m15_path="data/GCF_15m.csv",
        h4_path="data/GCF_4h.csv",
    ),
]


@dataclass(frozen=True)
class FirmProfile:
    name: str
    internal_max_daily_loss_fraction: float
    internal_max_trailing_dd_fraction: float
    prop_max_daily_loss_fraction: float
    prop_max_total_loss_fraction: float


FIRM_PROFILES = {
    "TIGHT_PROP": FirmProfile(
        name="TIGHT_PROP",
        internal_max_daily_loss_fraction=0.022,
        internal_max_trailing_dd_fraction=0.05,
        prop_max_daily_loss_fraction=0.03,
        prop_max_total_loss_fraction=0.06,
    ),
    "LOOSE_PROP": FirmProfile(
        name="LOOSE_PROP",
        internal_max_daily_loss_fraction=0.03,
        internal_max_trailing_dd_fraction=0.08,
        prop_max_daily_loss_fraction=0.05,
        prop_max_total_loss_fraction=0.10,
    ),
    "FTMO_CHALLENGE": FirmProfile(
        name="FTMO_CHALLENGE",
        internal_max_daily_loss_fraction=0.025,
        internal_max_trailing_dd_fraction=0.07,
        prop_max_daily_loss_fraction=0.05,
        prop_max_total_loss_fraction=0.10,
    ),
    "FUNDEDNEXT": FirmProfile(
        name="FUNDEDNEXT",
        internal_max_daily_loss_fraction=0.022,
        internal_max_trailing_dd_fraction=0.05,
        prop_max_daily_loss_fraction=0.03,
        prop_max_total_loss_fraction=0.06,
    ),
    "AQUA_INSTANT": FirmProfile(
        name="AQUA_INSTANT",
        internal_max_daily_loss_fraction=0.022,
        internal_max_trailing_dd_fraction=0.05,
        prop_max_daily_loss_fraction=0.03,
        prop_max_total_loss_fraction=0.06,
    ),
}

DEFAULT_FIRM_PROFILE = "TIGHT_PROP"


@dataclass(frozen=True)
class TradingProfile:
    name: str
    firm_profile: str
    entry_mode: str
    tier_scales: dict[str, float]
    max_concurrent_positions: int


ACCOUNT_PHASE_PROFILES = {
    "ftmo": {
        "EVAL": TradingProfile(
            name="FTMO_EVAL_DEFAULT",
            firm_profile="FTMO_CHALLENGE",
            entry_mode="M15_WITH_H1_CTX",
            tier_scales={"A": 1.5, "B": 0.75, "UNKNOWN": 0.5},
            max_concurrent_positions=2,
        ),
        "FUNDED": TradingProfile(
            name="FTMO_FUNDED_DEFAULT",
            firm_profile="FTMO_CHALLENGE",
            entry_mode="M15_WITH_H1_CTX",
            tier_scales={"A": 1.0, "B": 0.5, "UNKNOWN": 0.3},
            max_concurrent_positions=1,
        ),
    },
    "fundednext": {
        "EVAL": TradingProfile(
            name="FUNDEDNEXT_EVAL_DEFAULT",
            firm_profile="FUNDEDNEXT",
            entry_mode="M15_WITH_H1_CTX",
            tier_scales={"A": 1.5, "B": 0.75, "UNKNOWN": 0.5},
            max_concurrent_positions=2,
        ),
        "FUNDED": TradingProfile(
            name="FUNDEDNEXT_FUNDED_DEFAULT",
            firm_profile="FUNDEDNEXT",
            entry_mode="M15_WITH_H1_CTX",
            tier_scales={"A": 1.0, "B": 0.5, "UNKNOWN": 0.3},
            max_concurrent_positions=1,
        ),
    },
    "aqua": {
        "EVAL": TradingProfile(
            name="AQUA_EVAL_DEFAULT",
            firm_profile="AQUA_INSTANT",
            entry_mode="M15_WITH_H1_CTX",
            tier_scales={"A": 1.5, "B": 0.75, "UNKNOWN": 0.5},
            max_concurrent_positions=2,
        ),
        "FUNDED": TradingProfile(
            name="AQUA_FUNDED_DEFAULT",
            firm_profile="AQUA_INSTANT",
            entry_mode="M15_WITH_H1_CTX",
            tier_scales={"A": 1.0, "B": 0.5, "UNKNOWN": 0.3},
            max_concurrent_positions=1,
        ),
    },
}

DEFAULT_TRADING_FIRM = "ftmo"

EVAL_PROFILES = {
    "FTMO_EVAL_DEFAULT": ACCOUNT_PHASE_PROFILES["ftmo"]["EVAL"],
    "FUNDEDNEXT_EVAL_DEFAULT": ACCOUNT_PHASE_PROFILES["fundednext"]["EVAL"],
    "AQUA_EVAL_DEFAULT": ACCOUNT_PHASE_PROFILES["aqua"]["EVAL"],
}

DEFAULT_EVAL_PROFILE_PER_FIRM = {
    "ftmo": "FTMO_EVAL_DEFAULT",
    "fundednext": "FUNDEDNEXT_EVAL_DEFAULT",
    "aqua": "AQUA_EVAL_DEFAULT",
}


def resolve_trading_phase_profile(
    trading_firm: str | None, account_phase: str | None
) -> TradingProfile | None:
    if not account_phase:
        return None
    firm_key = (trading_firm or DEFAULT_TRADING_FIRM).lower()
    phase_key = account_phase.upper()
    return ACCOUNT_PHASE_PROFILES.get(firm_key, {}).get(phase_key)


def resolve_firm_profile(name: str | None = None) -> FirmProfile:
    resolved = (name or DEFAULT_FIRM_PROFILE).upper()
    base = FIRM_PROFILES.get(resolved, FIRM_PROFILES[DEFAULT_FIRM_PROFILE])
    overrides: dict = {}
    daily = os.environ.get("OMEGA_INTERNAL_MAX_DAILY_LOSS")
    trailing = os.environ.get("OMEGA_INTERNAL_MAX_TRAILING_DD")
    prop_daily = os.environ.get("OMEGA_PROP_MAX_DAILY_LOSS")
    prop_total = os.environ.get("OMEGA_PROP_MAX_TOTAL_LOSS")
    if daily:
        overrides["internal_max_daily_loss_fraction"] = float(daily)
    if trailing:
        overrides["internal_max_trailing_dd_fraction"] = float(trailing)
    if prop_daily:
        overrides["prop_max_daily_loss_fraction"] = float(prop_daily)
    if prop_total:
        overrides["prop_max_total_loss_fraction"] = float(prop_total)
    if overrides:
        return replace(base, **overrides)
    return base
