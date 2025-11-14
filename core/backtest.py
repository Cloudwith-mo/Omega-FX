"""Backtesting engine for Omega FX."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from pathlib import Path

import pandas as pd

from config.settings import (
    DEFAULT_BREAKOUT_CONFIG,
    DEFAULT_CHALLENGE,
    DEFAULT_CHALLENGE_CONFIG,
    DEFAULT_DATA_PATH,
    DEFAULT_RISK_MODE,
    ENTRY_MODE,
    PIP_VALUE_PER_STANDARD_LOT,
    SYMBOLS,
    BreakoutConfig,
    PropChallengeConfig,
    SymbolConfig,
)
from core.filters import TradeFilterResult, TradeTags, should_allow_trade
from core.risk import (
    RISK_PROFILES,
    ModeTransition,
    RiskMode,
    RiskModeController,
    RiskState,
    can_open_new_trade,
)
from core.risk_aggression import should_allow_risk_aggression
from core.sizing import compute_position_size
from core.strategy import annotate_indicators, generate_signal


REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


@dataclass
class SymbolFrameSet:
    symbol: str
    entry_frames: dict[str, pd.DataFrame]
    entry_atr_stats: dict[str, tuple[float, float]]
    default_timeframe: str
    context_h1_df: pd.DataFrame | None
    context_h1_atr_low: float
    context_h1_atr_high: float
    context_index: pd.Index | None

    def entry_timeframes(self) -> list[str]:
        return list(self.entry_frames.keys())

    def get_entry_row(self, timeframe: str, row_index: int) -> pd.Series:
        return self.entry_frames[timeframe].iloc[row_index]

    def entry_atr(self, timeframe: str) -> tuple[float, float]:
        return self.entry_atr_stats.get(timeframe, (0.0, 0.0))

    def context_row(self, timestamp: pd.Timestamp) -> pd.Series | None:
        if self.context_h1_df is None or self.context_index is None:
            return None
        pos = self.context_index.searchsorted(timestamp, side="right") - 1
        if pos < 0:
            return None
        return self.context_h1_df.iloc[pos]


@dataclass
class ActivePosition:
    symbol: str
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    lot_size: float
    stop_loss: float
    take_profit: float
    risk_mode_at_entry: RiskMode
    reason: str
    risk_amount: float
    atr_value_at_entry: float
    session_tag: str
    volatility_regime: str
    trend_regime: str
    breakout_high: float
    breakout_low: float
    risk_per_unit: float
    trail_activated: bool = False
    breakeven_activated: bool = False
    pattern_tag: str = ""
    risk_scale: float = 1.0
    risk_tier: str = "UNKNOWN"
    entry_timeframe: str = "H1"

    @property
    def max_loss_amount(self) -> float:
        return self.risk_amount


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: List[dict]
    total_return: float
    max_drawdown: float
    win_rate: float
    number_of_trades: int
    final_equity: float
    average_rr: float
    risk_mode: RiskMode
    prop_config: PropChallengeConfig
    internal_limits: dict
    internal_stop_out_triggered: bool
    prop_fail_triggered: bool
    max_daily_loss_fraction: float
    daily_stats: List["DailyStats"]
    mode_transitions: List[ModeTransition]
    mode_transition_summary: dict
    internal_stop_timestamp: pd.Timestamp | None
    prop_fail_timestamp: pd.Timestamp | None
    filtered_trades_by_reason: dict
    breakout_config: BreakoutConfig
    raw_signal_count: int
    after_session_count: int
    after_trend_count: int
    after_volatility_count: int
    after_breakout_count: int
    after_risk_aggression_count: int
    signal_variant_counts: dict[str, int]
    pre_risk_combo_counts: dict[tuple[str | None, str | None, str | None, str | None], int]
    tier_counts: dict[str, int]
    tier_expectancy: dict[str, float]
    tier_trades_per_year: dict[str, float]
    trades_per_symbol: dict[str, int]


@dataclass
class DailyStats:
    date: date
    equity_start_of_day: float
    equity_end_of_day: float
    realized_pnl: float
    max_intraday_dd_fraction: float
    risk_mode: str


def _pip_pnl(entry: float, exit: float, direction: str, lot_size: float) -> float:
    pip_diff = (exit - entry) * 10_000
    if direction == "short":
        pip_diff = -pip_diff
    return pip_diff * PIP_VALUE_PER_STANDARD_LOT * lot_size


def _recent_drawdown(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    series = pd.Series(values)
    running_max = series.cummax()
    # Avoid division-by-zero
    running_max[running_max == 0] = 1e-12
    dd = ((running_max - series) / running_max).max()
    return float(dd)


def _format_source_label(source: str | Path | None) -> str:
    return f" in {source}" if source else ""


def _session_tag(timestamp: pd.Timestamp) -> str:
    hour = timestamp.hour
    if 0 <= hour < 8:
        return "ASIA"
    if 8 <= hour < 16:
        return "LONDON"
    return "NY"


def _volatility_regime(atr_value: float | float, low: float, high: float) -> str:
    if pd.isna(atr_value):
        return "UNKNOWN"
    if atr_value < low:
        return "LOW"
    if atr_value <= high:
        return "NORMAL"
    return "HIGH"


def _trend_regime(direction: str, row: pd.Series) -> str:
    sma_short = row.get("SMA_slow")
    sma_trend = row.get("SMA_trend")
    if pd.isna(sma_short) or pd.isna(sma_trend):
        return "UNKNOWN"
    diff = sma_short - sma_trend
    if abs(diff) < 0.00015:
        return "SIDEWAYS"
    if direction == "long":
        return "WITH_TREND" if diff > 0 else "COUNTER_TREND"
    elif direction == "short":
        return "WITH_TREND" if diff < 0 else "COUNTER_TREND"
    return "UNKNOWN"


def _meets_breakout_conditions(
    direction: str,
    entry_price: float,
    sma_fast: float,
    sma_trend: float,
    breakout_level: float,
    atr_value: float,
    config: BreakoutConfig,
) -> bool:
    if pd.isna(sma_fast) or pd.isna(sma_trend) or pd.isna(breakout_level) or pd.isna(atr_value):
        return False
    distance_limit = config.atr_distance_max * atr_value
    if direction == "long":
        if not (entry_price > sma_fast and entry_price > sma_trend):
            return False
        if pd.isna(breakout_level) or entry_price < breakout_level:
            return False
        if abs(entry_price - sma_fast) > distance_limit:
            return False
    else:
        if not (entry_price < sma_fast and entry_price < sma_trend):
            return False
        if pd.isna(breakout_level) or entry_price > breakout_level:
            return False
        if abs(entry_price - sma_fast) > distance_limit:
            return False
    return True


def _update_dynamic_exit(
    position: ActivePosition,
    current_price: float,
    config: BreakoutConfig,
    current_atr: float,
) -> tuple[float | None, str | None]:
    atr = current_atr if not pd.isna(current_atr) else position.atr_value_at_entry
    risk_unit = position.risk_per_unit
    if risk_unit <= 0:
        return None, None

    if position.direction == "long":
        r_multiple = (current_price - position.entry_price) / risk_unit
        if not position.breakeven_activated and r_multiple >= config.breakeven_trigger_r_multiple:
            position.breakeven_activated = True
            position.stop_loss = max(position.stop_loss, position.entry_price)
        if r_multiple >= config.extended_tp_r_multiple:
            return current_price, "Extended TP"
        if position.breakeven_activated:
            trail_stop = current_price - config.trailing_atr_multiple * atr
            position.stop_loss = max(position.stop_loss, trail_stop)
    else:
        r_multiple = (position.entry_price - current_price) / risk_unit
        if not position.breakeven_activated and r_multiple >= config.breakeven_trigger_r_multiple:
            position.breakeven_activated = True
            position.stop_loss = min(position.stop_loss, position.entry_price)
        if r_multiple >= config.extended_tp_r_multiple:
            return current_price, "Extended TP"
        if position.breakeven_activated:
            trail_stop = current_price + config.trailing_atr_multiple * atr
            position.stop_loss = min(position.stop_loss, trail_stop)

    return None, None


def _prepare_price_data(df: pd.DataFrame, *, source: str | Path | None = None) -> pd.DataFrame:
    """Validate and normalize OHLCV data for backtesting."""
    if df.empty:
        raise ValueError(
            f"No usable rows found{_format_source_label(source)}. "
            "Make sure you exported real EUR/USD H1 data with the required columns."
        )

    working = df.dropna(how="all").copy()

    if working.empty:
        raise ValueError(
            f"No usable rows found{_format_source_label(source)}. "
            "Make sure you exported real EUR/USD H1 data with the required columns."
        )

    lower_map = {col.lower(): col for col in working.columns}
    missing = [col for col in REQUIRED_COLUMNS if col not in lower_map]
    if missing:
        raise ValueError(
            f"Missing required columns {missing}{_format_source_label(source)}. "
            "Expected columns: timestamp, open, high, low, close, volume."
        )

    rename_map = {lower_map[col]: col for col in REQUIRED_COLUMNS}
    prepared = working.rename(columns=rename_map)

    try:
        prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], utc=True)
    except Exception as exc:  # pragma: no cover - depends on input file
        raise ValueError(f"timestamp column could not be parsed{_format_source_label(source)}: {exc}") from exc

    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        try:
            prepared[col] = pd.to_numeric(prepared[col], errors="raise")
        except Exception as exc:  # pragma: no cover - depends on input file
            raise ValueError(f"{col} column must be numeric{_format_source_label(source)}: {exc}") from exc

    prepared = prepared.dropna(subset=list(REQUIRED_COLUMNS))

    if prepared.empty:
        raise ValueError(
            f"No usable rows found{_format_source_label(source)}. "
            "Make sure you exported real EUR/USD H1 data with the required columns."
        )

    prepared = prepared.sort_values("timestamp").reset_index(drop=True)
    return prepared


def _infer_symbol_name(source: str | Path | None) -> str:
    if not source:
        return "PRIMARY"
    try:
        return Path(source).stem.upper()
    except Exception:
        return "PRIMARY"


def _annotate_dataframe(
    symbol: str,
    df: pd.DataFrame,
    breakout_cfg: BreakoutConfig,
    source: str | Path | None = None,
) -> tuple[pd.DataFrame, float, float]:
    prepared = _prepare_price_data(df, source=source)
    annotated = annotate_indicators(prepared)
    annotated = annotated.copy()
    annotated["symbol"] = symbol

    lookback = breakout_cfg.lookback_bars
    annotated["HIGH_BREAKOUT"] = annotated["high"].rolling(lookback, min_periods=lookback).max()
    annotated["LOW_BREAKOUT"] = annotated["low"].rolling(lookback, min_periods=lookback).min()
    atr_series = annotated.get("ATR_14", pd.Series(dtype=float)).dropna()
    if atr_series.empty:
        atr_low = atr_high = 0.0
    else:
        atr_low = float(atr_series.quantile(0.33))
        atr_high = float(atr_series.quantile(0.66))
    return annotated, atr_low, atr_high


def _prepare_annotated_frame(
    symbol: str,
    raw_df: pd.DataFrame,
    breakout_cfg: BreakoutConfig,
    *,
    source: str | Path | None = None,
) -> tuple[pd.DataFrame, float, float]:
    """Ensure a dataframe carries indicators/ATR stats expected by the engine."""

    base_cols = {"SMA_slow", "SMA_trend", "ATR_14"}
    if base_cols.issubset(raw_df.columns):
        annotated = raw_df.copy().reset_index(drop=True)
        if "timestamp" in annotated.columns:
            annotated["timestamp"] = pd.to_datetime(annotated["timestamp"], utc=True)
        lookback = breakout_cfg.lookback_bars
        if "HIGH_BREAKOUT" not in annotated.columns:
            annotated["HIGH_BREAKOUT"] = annotated["high"].rolling(lookback, min_periods=lookback).max()
        if "LOW_BREAKOUT" not in annotated.columns:
            annotated["LOW_BREAKOUT"] = annotated["low"].rolling(lookback, min_periods=lookback).min()
        atr_series = annotated.get("ATR_14", pd.Series(dtype=float)).dropna()
        if atr_series.empty:
            atr_low = atr_high = 0.0
        else:
            atr_low = float(atr_series.quantile(0.33))
            atr_high = float(atr_series.quantile(0.66))
        return annotated, atr_low, atr_high

    return _annotate_dataframe(symbol, raw_df, breakout_cfg, source=source)


def _load_and_annotate(
    symbol: str,
    path: str | Path,
    breakout_cfg: BreakoutConfig,
) -> tuple[pd.DataFrame, float, float]:
    csv_path = Path(path)
    if not csv_path.exists():
        alt = csv_path.with_name(csv_path.name.lower())
        if alt.exists():
            csv_path = alt
        else:
            raise ValueError(f"Data file not found for symbol '{symbol}': {path}")

    try:
        raw_df = pd.read_csv(csv_path)
    except Exception as exc:  # pragma: no cover - depends on CSV contents
        raise ValueError(f"Failed to load CSV for symbol '{symbol}' from {path}: {exc}") from exc

    return _annotate_dataframe(symbol, raw_df, breakout_cfg, source=csv_path)


@dataclass(frozen=True)
class BarEvent:
    timestamp: pd.Timestamp
    symbol: str
    timeframe: str
    row_index: int


def build_event_stream(symbol_frames: dict[str, SymbolFrameSet | pd.DataFrame]) -> list[BarEvent]:
    """Merge entry timeframes into a single chronological event list."""
    events: list[BarEvent] = []
    for symbol, frames in symbol_frames.items():
        if isinstance(frames, SymbolFrameSet):
            frame_items = [
                (timeframe, df.reset_index(drop=True), True)
                for timeframe, df in frames.entry_frames.items()
            ]
        else:
            df = frames.reset_index(drop=True)
            frame_items = [("H1", df, False)]
        for timeframe, df, skip_first in frame_items:
            if df.empty:
                continue
            if "timestamp" not in df.columns:
                raise ValueError(f"Symbol '{symbol}' dataframe is missing 'timestamp' column.")
            timestamps = df["timestamp"].reset_index(drop=True)
            start_idx = 1 if skip_first else 0
            for idx in range(start_idx, len(timestamps)):
                ts = timestamps.iloc[idx]
                events.append(
                    BarEvent(
                        timestamp=pd.Timestamp(ts),
                        symbol=symbol,
                    timeframe=timeframe,
                    row_index=idx,
                )
            )
    events.sort(key=lambda evt: evt.timestamp)
    return events


def _build_symbol_frame_sets(
    entry_mode: str,
    breakout_cfg: BreakoutConfig,
    df: pd.DataFrame | None,
    data_source: str | Path | None,
    symbol_data_map: dict[str, pd.DataFrame] | None,
    symbols_config: list[SymbolConfig] | None,
) -> dict[str, SymbolFrameSet]:
    entry_mode = entry_mode.upper()
    symbol_sets: dict[str, SymbolFrameSet] = {}

    if symbol_data_map:
        for symbol, raw_payload in symbol_data_map.items():
            entry_frames: dict[str, pd.DataFrame] = {}
            entry_stats: dict[str, tuple[float, float]] = {}
            context_df: pd.DataFrame | None = None
            context_low = context_high = 0.0

            if isinstance(raw_payload, dict):
                annotated_by_tf: dict[str, tuple[pd.DataFrame, float, float]] = {}
                for tf_name, tf_df in raw_payload.items():
                    if tf_df is None or tf_df.empty:
                        continue
                    tf_key = tf_name.upper()
                    annotated, atr_low, atr_high = _prepare_annotated_frame(symbol, tf_df, breakout_cfg)
                    annotated_by_tf[tf_key] = (annotated, atr_low, atr_high)

                if not annotated_by_tf:
                    continue

                if "H1" not in annotated_by_tf:
                    print(f"[!] {symbol}: H1 context missing; skipping symbol.")
                    continue

                context_df, context_low, context_high = annotated_by_tf["H1"]

                if entry_mode == "M15_WITH_H1_CTX":
                    m15_tuple = annotated_by_tf.get("M15")
                    if m15_tuple is None:
                        print(f"[!] {symbol}: M15 data missing for M15 entry mode; skipping symbol.")
                        continue
                    entry_frames = {"M15": m15_tuple[0]}
                    entry_stats = {"M15": (m15_tuple[1], m15_tuple[2])}
                    default_tf = "M15"
                elif entry_mode == "HYBRID":
                    entry_frames = {"H1": context_df}
                    entry_stats = {"H1": (context_low, context_high)}
                    if "M15" in annotated_by_tf:
                        m15_tuple = annotated_by_tf["M15"]
                        entry_frames["M15"] = m15_tuple[0]
                        entry_stats["M15"] = (m15_tuple[1], m15_tuple[2])
                    default_tf = "H1"
                else:
                    entry_frames = {"H1": context_df}
                    entry_stats = {"H1": (context_low, context_high)}
                    default_tf = "H1"
            else:
                annotated, atr_low, atr_high = _prepare_annotated_frame(symbol, raw_payload, breakout_cfg)
                entry_frames = {"H1": annotated}
                entry_stats = {"H1": (atr_low, atr_high)}
                context_df = annotated
                context_low = atr_low
                context_high = atr_high
                default_tf = "H1"

            if not entry_frames or context_df is None:
                continue

            symbol_sets[symbol] = SymbolFrameSet(
                symbol=symbol,
                entry_frames=entry_frames,
                entry_atr_stats=entry_stats,
                default_timeframe=default_tf,
                context_h1_df=context_df,
                context_h1_atr_low=context_low,
                context_h1_atr_high=context_high,
                context_index=pd.Index(context_df.get("timestamp", pd.Series(dtype="datetime64[ns, UTC]"))),
            )
        return symbol_sets

    if df is not None:
        symbol = _infer_symbol_name(data_source)
        annotated, atr_low, atr_high = _annotate_dataframe(symbol, df, breakout_cfg, source=data_source)
        symbol_sets[symbol] = SymbolFrameSet(
            symbol=symbol,
            entry_frames={"H1": annotated},
            entry_atr_stats={"H1": (atr_low, atr_high)},
            default_timeframe="H1",
            context_h1_df=annotated,
            context_h1_atr_low=atr_low,
            context_h1_atr_high=atr_high,
            context_index=pd.Index(annotated["timestamp"]),
        )
        return symbol_sets

    configs = symbols_config or SYMBOLS
    if not configs:
        raise ValueError("No symbols configured. Update config.settings.SYMBOLS.")

    for cfg in configs:
        try:
            h1_df, h1_low, h1_high = _load_and_annotate(cfg.name, cfg.h1_path, breakout_cfg)
        except ValueError as exc:
            print(f"[!] {cfg.name} H1 disabled: {exc}")
            continue

        entry_frames: dict[str, pd.DataFrame] = {"H1": h1_df}
        entry_stats: dict[str, tuple[float, float]] = {"H1": (h1_low, h1_high)}
        default_tf = "H1"

        if entry_mode == "M15_WITH_H1_CTX":
            if not cfg.m15_path:
                print(f"[!] {cfg.name}: M15 path not configured; skipping symbol.")
                continue
            try:
                m15_df, m15_low, m15_high = _load_and_annotate(cfg.name, cfg.m15_path, breakout_cfg)
            except ValueError as exc:
                print(f"[!] {cfg.name} M15 disabled: {exc}")
                continue
            entry_frames = {"M15": m15_df}
            entry_stats = {"M15": (m15_low, m15_high)}
            default_tf = "M15"
        elif entry_mode == "HYBRID":
            if cfg.m15_path:
                try:
                    m15_df, m15_low, m15_high = _load_and_annotate(cfg.name, cfg.m15_path, breakout_cfg)
                except ValueError as exc:
                    print(f"[!] {cfg.name} M15 disabled: {exc}")
                else:
                    entry_frames["M15"] = m15_df
                    entry_stats["M15"] = (m15_low, m15_high)
            else:
                print(f"[!] {cfg.name}: M15 path not configured; HYBRID falling back to H1-only.")

        symbol_sets[cfg.name] = SymbolFrameSet(
            symbol=cfg.name,
            entry_frames=entry_frames,
            entry_atr_stats=entry_stats,
            default_timeframe=default_tf,
            context_h1_df=h1_df,
            context_h1_atr_low=h1_low,
            context_h1_atr_high=h1_high,
            context_index=pd.Index(h1_df["timestamp"]),
        )

    if not symbol_sets:
        raise ValueError("No symbols could be loaded; check your SYMBOLS configuration and CSV paths.")

    return symbol_sets




def _resolve_entry_mode(entry_mode: str | None) -> str:
    env_mode = os.environ.get("OMEGA_ENTRY_MODE")
    mode = (entry_mode or env_mode or ENTRY_MODE).upper()
    valid = {"H1_ONLY", "M15_WITH_H1_CTX", "HYBRID"}
    if mode not in valid:
        return "H1_ONLY"
    return mode


def run_backtest(
    df: pd.DataFrame | None = None,
    starting_equity: float | None = None,
    initial_mode: RiskMode | None = None,
    data_source: str | Path | None = None,
    challenge_config: PropChallengeConfig | None = None,
    breakout_config: BreakoutConfig | None = None,
    *,
    symbol_data_map: dict[str, pd.DataFrame] | None = None,
    symbols_config: list[SymbolConfig] | None = None,
    entry_mode: str | None = None,
) -> BacktestResult:
    """Run a FundedNext-aware backtest over one or multiple symbols."""

    challenge = challenge_config or DEFAULT_CHALLENGE
    equity_start = starting_equity or challenge.start_equity
    mode = initial_mode or DEFAULT_RISK_MODE
    breakout_cfg = breakout_config or DEFAULT_BREAKOUT_CONFIG
    resolved_entry_mode = _resolve_entry_mode(entry_mode)

    symbol_sets = _build_symbol_frame_sets(
        resolved_entry_mode,
        breakout_cfg,
        df,
        data_source,
        symbol_data_map,
        symbols_config,
    )
    events = build_event_stream(symbol_sets)
    if not events:
        raise ValueError("No events generated for backtest; ensure your CSVs contain data.")

    risk_state = RiskState(equity_start, mode)
    mode_controller = RiskModeController(risk_state)

    position: Optional[ActivePosition] = None
    current_day: Optional[date] = None
    todays_realized_pnl = 0.0
    daily_realized_pnl = 0.0
    max_daily_loss_fraction = 0.0
    daily_start_equity = equity_start
    daily_peak = equity_start
    daily_min = equity_start
    daily_mode = risk_state.current_mode.value
    last_equity_value = equity_start

    equity_curve_points: List[tuple[pd.Timestamp, float]] = []
    trades: List[dict] = []
    daily_stats: List[DailyStats] = []
    filtered_counts = {
        "session": 0,
        "trend": 0,
        "low_volatility": 0,
        "high_vol_sideways": 0,
        "volatility": 0,
        "breakout": 0,
        "risk_aggression": 0,
        "max_open_positions": 0,
    }
    signal_variant_counts: dict[str, int] = {}
    pre_risk_combo_counts: dict[tuple[str | None, str | None, str | None, str | None], int] = {}
    raw_signal_count = after_session_count = after_trend_count = after_volatility_count = after_breakout_count = after_risk_aggression_count = 0

    def finalize_current_day(day_date: Optional[date], equity_end: float) -> None:
        if day_date is None:
            return
        peak = daily_peak if daily_peak > 0 else 0.0
        intraday_dd = (peak - daily_min) / peak if peak > 0 else 0.0
        daily_stats.append(
            DailyStats(
                date=day_date,
                equity_start_of_day=daily_start_equity,
                equity_end_of_day=equity_end,
                realized_pnl=daily_realized_pnl,
                max_intraday_dd_fraction=intraday_dd,
                risk_mode=daily_mode,
            )
        )

    for event in events:
        frames = symbol_sets.get(event.symbol)
        if not frames:
            continue
        entry_df = frames.entry_frames.get(event.timeframe)
        if entry_df is None or event.row_index >= len(entry_df):
            continue

        row = frames.get_entry_row(event.timeframe, event.row_index)
        prev_row = frames.get_entry_row(event.timeframe, event.row_index - 1)
        timestamp = pd.to_datetime(row["timestamp"])
        timestamp_dt = timestamp.to_pydatetime()

        trade_date = timestamp.date()
        if current_day != trade_date:
            if todays_realized_pnl < 0 and risk_state.start_of_day_equity > 0:
                loss_frac = abs(todays_realized_pnl) / risk_state.start_of_day_equity
                max_daily_loss_fraction = max(max_daily_loss_fraction, loss_frac)

            finalize_current_day(current_day, last_equity_value)
            risk_state.on_new_day()
            todays_realized_pnl = 0.0
            daily_realized_pnl = 0.0
            current_day = trade_date
            daily_start_equity = risk_state.start_of_day_equity
            daily_peak = daily_start_equity
            daily_min = daily_start_equity
            daily_mode = risk_state.current_mode.value

        signal = generate_signal(row, prev_row)
        profile = RISK_PROFILES[risk_state.current_mode]
        risk_state.enforce_drawdown_limits(profile, challenge, timestamp=timestamp_dt)
        mode_controller.step_down_for_drawdown(timestamp_dt, risk_state.total_dd_from_peak)
        profile = RISK_PROFILES[risk_state.current_mode]

        context_row = row if event.timeframe == "H1" else frames.context_row(timestamp)
        if event.timeframe != "H1" and context_row is None:
            continue
        if context_row is None:
            context_row = row

        if event.timeframe == "H1":
            context_atr_low, context_atr_high = frames.entry_atr_stats.get("H1", (0.0, 0.0))
        else:
            context_atr_low = frames.context_h1_atr_low
            context_atr_high = frames.context_h1_atr_high

        entry_atr_low, entry_atr_high = frames.entry_atr_stats.get(event.timeframe, (0.0, 0.0))

        if position and position.symbol == event.symbol:
            exit_price = None
            exit_reason = None
            close_price = float(row["close"])

            if position.direction == "long":
                if close_price <= position.stop_loss:
                    exit_price = position.stop_loss
                    exit_reason = "Stop Loss"
                elif close_price >= position.take_profit:
                    exit_price = position.take_profit
                    exit_reason = "Take Profit"
            else:
                if close_price >= position.stop_loss:
                    exit_price = position.stop_loss
                    exit_reason = "Stop Loss"
                elif close_price <= position.take_profit:
                    exit_price = position.take_profit
                    exit_reason = "Take Profit"

            opposite_signal = (
                signal.action == "long" and position.direction == "short"
            ) or (signal.action == "short" and position.direction == "long")
            if exit_price is None and opposite_signal:
                exit_price = close_price
                exit_reason = "Opposite signal"

            if exit_price is None:
                current_atr = float(row.get("ATR_14", position.atr_value_at_entry))
                exit_price, exit_reason = _update_dynamic_exit(position, close_price, config=breakout_cfg, current_atr=current_atr)

            if exit_price is not None:
                pnl = _pip_pnl(position.entry_price, exit_price, position.direction, position.lot_size)
                risk_state.update_equity(risk_state.current_equity + pnl)
                todays_realized_pnl += pnl
                daily_realized_pnl += pnl
                if todays_realized_pnl < 0 and risk_state.start_of_day_equity > 0:
                    loss_frac = abs(todays_realized_pnl) / risk_state.start_of_day_equity
                    max_daily_loss_fraction = max(max_daily_loss_fraction, loss_frac)

                risk = abs(position.entry_price - position.stop_loss)
                reward = abs(position.take_profit - position.entry_price)
                risk_reward = reward / risk if risk > 1e-12 else None
                r_multiple = pnl / position.risk_amount if position.risk_amount else 0.0
                trades.append(
                    {
                        "symbol": position.symbol,
                        "entry_time": position.entry_time,
                        "exit_time": timestamp,
                        "direction": position.direction,
                        "entry_price": position.entry_price,
                        "exit_price": exit_price,
                        "stop_loss": position.stop_loss,
                        "take_profit": position.take_profit,
                        "lot_size": position.lot_size,
                        "pnl": pnl,
                        "risk_mode_at_entry": position.risk_mode_at_entry.value,
                        "reason": exit_reason,
                        "risk_reward": risk_reward,
                        "session_tag": position.session_tag,
                        "volatility_regime": position.volatility_regime,
                        "trend_regime": position.trend_regime,
                        "atr_value_at_entry": position.atr_value_at_entry,
                        "pattern_tag": position.pattern_tag,
                        "r_multiple": r_multiple,
                        "risk_scale": position.risk_scale,
                        "risk_tier": position.risk_tier,
                    }
                )
                mode_controller.record_trade(pnl, risk_state.current_equity, timestamp_dt)
                position = None

        entry_allowed = (
            signal.action in {"long", "short"}
            and signal.stop_distance_pips is not None
            and signal.take_profit_distance_pips is not None
            and risk_state.can_trade()
        )
        if entry_allowed:
            raw_signal_count += 1
            variant = getattr(signal, "variant", "unknown")
            signal_variant_counts[variant] = signal_variant_counts.get(variant, 0) + 1
            if profile.max_open_trades <= 0:
                continue

            session_tag = _session_tag(timestamp)
            atr_value = float(context_row.get("ATR_14", float("nan")))
            if pd.isna(atr_value):
                fallback_atr = context_atr_high if context_atr_high > 0 else context_atr_low
                atr_value = max(fallback_atr, 1e-6)
            entry_atr_value = float(row.get("ATR_14", float("nan")))
            if pd.isna(entry_atr_value):
                fallback_entry_atr = entry_atr_high if entry_atr_high > 0 else entry_atr_low
                entry_atr_value = max(fallback_entry_atr, 1e-6)
            vol_regime = _volatility_regime(atr_value, context_atr_low, context_atr_high)
            trend_regime = _trend_regime(signal.action, context_row)

            filter_result = should_allow_trade(
                TradeTags(
                    session_tag=session_tag,
                    trend_regime=trend_regime,
                    volatility_regime=vol_regime,
                )
            )
            if not filter_result.session_passed:
                filtered_counts["session"] += 1
                continue
            after_session_count += 1

            if not filter_result.trend_passed:
                filtered_counts["trend"] += 1
                continue
            after_trend_count += 1

            if not filter_result.volatility_passed:
                reason = (filter_result.reason or "volatility").lower()
                filtered_counts[reason] = filtered_counts.get(reason, 0) + 1
                continue
            after_volatility_count += 1

            lot_size = compute_position_size(
                account_equity=risk_state.current_equity,
                risk_mode=risk_state.current_mode,
                stop_distance_pips=signal.stop_distance_pips,
            )
            pip_to_price = signal.stop_distance_pips / 10_000
            tp_to_price = signal.take_profit_distance_pips / 10_000
            entry_price = float(row["close"])

            breakout_high = float(row.get("HIGH_BREAKOUT", float("nan")))
            breakout_low = float(row.get("LOW_BREAKOUT", float("nan")))
            sma_fast = float(row.get("SMA_slow", float("nan")))
            sma_trend = float(row.get("SMA_trend", float("nan")))

            is_breakout = _meets_breakout_conditions(
                direction=signal.action,
                entry_price=entry_price,
                sma_fast=sma_fast,
                sma_trend=sma_trend,
                breakout_level=breakout_high if signal.action == "long" else breakout_low,
                atr_value=atr_value,
                config=breakout_cfg,
            )
            pattern_tag = "breakout_v1" if is_breakout else "non_breakout"

            stop_loss = entry_price - pip_to_price if signal.action == "long" else entry_price + pip_to_price
            take_profit = entry_price + tp_to_price if signal.action == "long" else entry_price - tp_to_price

            combo_key = (session_tag, trend_regime, vol_regime, pattern_tag)
            pre_risk_combo_counts[combo_key] = pre_risk_combo_counts.get(combo_key, 0) + 1

            after_breakout_count += 1

            risk_aggr_result = should_allow_risk_aggression(
                combo_key,
                risk_state.current_mode,
            )
            risk_tier = risk_aggr_result.tier or "UNKNOWN"
            if not risk_aggr_result.allowed:
                filtered_counts["risk_aggression"] += 1
                continue
            after_risk_aggression_count += 1
            risk_scale = max(0.0, risk_aggr_result.risk_scale)

            lot_size *= risk_scale
            if lot_size < 0.0:
                lot_size = 0.0

            risk_amount = signal.stop_distance_pips * PIP_VALUE_PER_STANDARD_LOT * lot_size

            if lot_size < 1e-4:
                continue

            if position is not None:
                filtered_counts["max_open_positions"] += 1
                continue

            if can_open_new_trade(
                todays_realized_pnl=todays_realized_pnl,
                open_positions=[position] if position else [],
                proposed_trade_risk_amount=risk_amount,
                equity_start_of_day=risk_state.start_of_day_equity,
                profile=profile,
                challenge=challenge,
            ):
                position = ActivePosition(
                    symbol=event.symbol,
                    direction=signal.action,
                    entry_time=timestamp,
                    entry_price=entry_price,
                    lot_size=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_mode_at_entry=risk_state.current_mode,
                    reason=signal.reason,
                    risk_amount=risk_amount,
                    atr_value_at_entry=entry_atr_value,
                    session_tag=session_tag,
                    volatility_regime=vol_regime,
                    trend_regime=trend_regime,
                    breakout_high=breakout_high,
                    breakout_low=breakout_low,
                    risk_per_unit=pip_to_price,
                    risk_scale=risk_scale,
                    risk_tier=risk_tier,
                    pattern_tag=pattern_tag,
                    entry_timeframe=event.timeframe,
                )

        equity_value = last_equity_value
        if position and position.symbol == event.symbol and position.entry_timeframe == event.timeframe:
            unrealized_pnl = _pip_pnl(position.entry_price, float(row["close"]), position.direction, position.lot_size)
            equity_value = risk_state.current_equity + unrealized_pnl
        elif not position:
            equity_value = risk_state.current_equity
        equity_curve_points.append((timestamp, equity_value))
        daily_peak = max(daily_peak, equity_value)
        daily_min = min(daily_min, equity_value)
        last_equity_value = equity_value

        if (
            position
            and risk_state.internal_stop_out_triggered
            and position.symbol == event.symbol
            and position.entry_timeframe == event.timeframe
        ):
            exit_price = float(row["close"])
            pnl = _pip_pnl(position.entry_price, exit_price, position.direction, position.lot_size)
            risk_state.update_equity(risk_state.current_equity + pnl)
            todays_realized_pnl += pnl
            daily_realized_pnl += pnl
            r_multiple = pnl / position.risk_amount if position.risk_amount else 0.0
            trades.append(
                {
                    "symbol": position.symbol,
                    "entry_time": position.entry_time,
                    "exit_time": timestamp,
                    "direction": position.direction,
                    "entry_price": position.entry_price,
                    "exit_price": exit_price,
                    "stop_loss": position.stop_loss,
                    "take_profit": position.take_profit,
                    "lot_size": position.lot_size,
                    "pnl": pnl,
                    "risk_mode_at_entry": position.risk_mode_at_entry.value,
                    "reason": "Internal stop-out",
                    "risk_reward": None,
                    "session_tag": position.session_tag,
                    "volatility_regime": position.volatility_regime,
                    "trend_regime": position.trend_regime,
                    "atr_value_at_entry": position.atr_value_at_entry,
                    "pattern_tag": position.pattern_tag,
                    "r_multiple": r_multiple,
                    "risk_scale": position.risk_scale,
                    "risk_tier": position.risk_tier,
                }
            )
            mode_controller.record_trade(pnl, risk_state.current_equity, timestamp_dt)
            position = None

    if todays_realized_pnl < 0 and risk_state.start_of_day_equity > 0:
        loss_frac = abs(todays_realized_pnl) / risk_state.start_of_day_equity
        max_daily_loss_fraction = max(max_daily_loss_fraction, loss_frac)

    finalize_current_day(current_day, last_equity_value)

    if equity_curve_points:
        index = pd.Index([ts for ts, _ in equity_curve_points], name="timestamp")
        values = [val for _, val in equity_curve_points]
        equity_curve = pd.Series(values, index=index)
    else:
        equity_curve = pd.Series(dtype=float)

    final_equity = equity_curve.iloc[-1] if not equity_curve.empty else equity_start
    total_return = (final_equity - equity_start) / equity_start
    max_dd = _recent_drawdown(list(equity_curve)) or 0.0
    win_rate = (
        sum(1 for trade in trades if trade["pnl"] > 0) / len(trades)
        if trades
        else 0.0
    )
    rr_values = [t["risk_reward"] for t in trades if t.get("risk_reward") is not None]
    average_rr = sum(rr_values) / len(rr_values) if rr_values else 0.0

    initial_mode_used = initial_mode or DEFAULT_RISK_MODE
    internal_limits = {
        "daily_loss_limit_fraction": RISK_PROFILES[initial_mode_used].daily_loss_limit_fraction,
        "max_trailing_dd_fraction": RISK_PROFILES[initial_mode_used].max_trailing_dd_fraction,
    }

    transition_summary: dict[str, int] = {}
    for transition in mode_controller.transitions:
        key = f"{transition.old_mode.value}->{transition.new_mode.value}"
        transition_summary[key] = transition_summary.get(key, 0) + 1

    tier_counts: dict[str, int] = {}
    tier_returns: dict[str, list[float]] = {}
    for trade in trades:
        tier = (trade.get("risk_tier") or "UNKNOWN").upper()
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        tier_returns.setdefault(tier, []).append(float(trade.get("r_multiple", 0.0)))

    tier_expectancy: dict[str, float] = {
        tier: (sum(values) / len(values) if values else 0.0)
        for tier, values in tier_returns.items()
    }
    trading_days_for_ratio = max(1, len(daily_stats))
    trading_years = max(1.0, trading_days_for_ratio / 252.0)
    tier_trades_per_year: dict[str, float] = {
        tier: count / trading_years for tier, count in tier_counts.items()
    }
    for key in ("A", "B", "UNKNOWN", "C"):
        tier_counts.setdefault(key, 0)
        tier_expectancy.setdefault(key, 0.0)
        tier_trades_per_year.setdefault(key, 0.0)

    trades_per_symbol: dict[str, int] = {}
    for trade in trades:
        sym = trade.get("symbol") or "UNKNOWN"
        trades_per_symbol[sym] = trades_per_symbol.get(sym, 0) + 1

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        total_return=total_return,
        max_drawdown=max_dd,
        win_rate=win_rate,
        number_of_trades=len(trades),
        final_equity=final_equity,
        average_rr=average_rr,
        risk_mode=risk_state.current_mode,
        prop_config=challenge,
        internal_limits=internal_limits,
        internal_stop_out_triggered=risk_state.internal_stop_out_triggered,
        prop_fail_triggered=risk_state.prop_fail_triggered,
        max_daily_loss_fraction=max_daily_loss_fraction,
        daily_stats=daily_stats,
        mode_transitions=mode_controller.transitions,
        mode_transition_summary=transition_summary,
        internal_stop_timestamp=pd.Timestamp(risk_state.internal_stop_timestamp)
        if risk_state.internal_stop_timestamp
        else None,
        prop_fail_timestamp=pd.Timestamp(risk_state.prop_fail_timestamp)
        if risk_state.prop_fail_timestamp
        else None,
        filtered_trades_by_reason=filtered_counts,
        breakout_config=breakout_cfg,
        raw_signal_count=raw_signal_count,
        after_session_count=after_session_count,
        after_trend_count=after_trend_count,
        after_volatility_count=after_volatility_count,
        after_breakout_count=after_breakout_count,
        after_risk_aggression_count=after_risk_aggression_count,
        signal_variant_counts=signal_variant_counts,
        pre_risk_combo_counts=pre_risk_combo_counts,
        tier_counts=tier_counts,
        tier_expectancy=tier_expectancy,
        tier_trades_per_year=tier_trades_per_year,
        trades_per_symbol=trades_per_symbol,
    )
