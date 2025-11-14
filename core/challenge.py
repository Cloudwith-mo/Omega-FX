"""FundedNext challenge simulator utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Dict

import pandas as pd

from config.settings import (
    ChallengeConfig,
    DEFAULT_CHALLENGE,
    DEFAULT_CHALLENGE_CONFIG,
    DEFAULT_RISK_MODE,
    PropChallengeConfig,
)
from core.backtest import BacktestResult, DailyStats, BarEvent, build_event_stream, run_backtest


@dataclass
class ChallengeOutcome:
    passed: bool
    hit_profit_target: bool
    hit_total_loss: bool
    hit_internal_stop: bool
    hit_prop_violation: bool
    timed_out: bool
    final_equity: float
    peak_equity: float
    min_equity: float
    num_trading_days: int
    num_trades: int
    start_index: int
    end_index: int
    max_daily_loss_fraction: float
    failure_reason: str | None
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp
    max_observed_daily_loss_fraction: float
    trades_per_symbol: Dict[str, int] = field(default_factory=dict)


def _first_index_meeting(condition: pd.Series) -> int | None:
    matches = condition.to_numpy().nonzero()[0]
    return int(matches[0]) if len(matches) > 0 else None


def _prepare_window(df: pd.DataFrame, seed_index: int, max_calendar_days: int | None) -> pd.DataFrame:
    window = df.iloc[seed_index:].copy()
    if window.empty:
        return window
    window = window.reset_index().rename(columns={"index": "orig_index"})
    window["timestamp"] = pd.to_datetime(window["timestamp"], utc=True)
    start_ts = window["timestamp"].iloc[0]
    if max_calendar_days:
        cutoff = start_ts + pd.Timedelta(days=max_calendar_days)
        window = window[window["timestamp"] <= cutoff].copy()
    return window


def _day_end_map(equity_index: pd.Index) -> tuple[dict, str | None]:
    mapping: dict = {}
    tz = getattr(equity_index, "tz", None)
    for ts in equity_index:
        day = pd.Timestamp(ts).date()
        mapping[day] = pd.Timestamp(ts)
    return mapping, tz


def _get_day_end_timestamp(day_map: dict, tz: str | None, day: pd.Timestamp | pd.Timestamp | object) -> pd.Timestamp:
    if isinstance(day, pd.Timestamp):
        day_key = day.date()
    else:
        day_key = pd.Timestamp(day).date()
    ts = day_map.get(day_key)
    if ts is not None:
        return ts
    normalized = pd.Timestamp(day_key)
    if tz is not None:
        normalized = normalized.tz_localize(tz)
    return normalized


def _daily_loss_fraction(stat: DailyStats) -> float:
    if stat.equity_start_of_day <= 0:
        return 0.0
    loss = max(0.0, -stat.realized_pnl)
    return loss / stat.equity_start_of_day


def _slice_symbol_map(
    symbol_map: dict[str, pd.DataFrame],
    start_ts: pd.Timestamp,
    max_calendar_days: int | None,
) -> dict[str, pd.DataFrame]:
    end_ts = None
    if max_calendar_days:
        end_ts = start_ts + pd.Timedelta(days=max_calendar_days)
    sliced: dict[str, pd.DataFrame] = {}
    for symbol, df in symbol_map.items():
        mask = df["timestamp"] >= start_ts
        if end_ts is not None:
            mask &= df["timestamp"] <= end_ts
        subset = df.loc[mask].copy()
        if not subset.empty:
            sliced[symbol] = subset.reset_index(drop=True)
    return sliced


def _build_challenge_outcome(
    backtest: BacktestResult,
    start_timestamp: pd.Timestamp,
    start_index: int,
    challenge_config: ChallengeConfig,
    prop: PropChallengeConfig,
    window: pd.DataFrame | None,
) -> ChallengeOutcome:
    equity_series = backtest.equity_curve
    if equity_series.empty:
        return ChallengeOutcome(
            passed=False,
            hit_profit_target=False,
            hit_total_loss=False,
            hit_internal_stop=False,
            hit_prop_violation=False,
            timed_out=True,
            final_equity=challenge_config.start_equity,
            peak_equity=challenge_config.start_equity,
            min_equity=challenge_config.start_equity,
            num_trading_days=0,
            num_trades=0,
            start_index=start_index,
            end_index=start_index,
            max_daily_loss_fraction=0.0,
            failure_reason="no_data",
            start_timestamp=pd.Timestamp(start_timestamp),
            end_timestamp=pd.Timestamp(start_timestamp),
            max_observed_daily_loss_fraction=0.0,
            trades_per_symbol=backtest.trades_per_symbol,
        )

    equity_index = equity_series.index
    day_end_map, tz = _day_end_map(equity_index)

    target_equity = challenge_config.start_equity * (1 + challenge_config.profit_target_fraction)
    loss_equity = challenge_config.start_equity * (1 - challenge_config.max_total_loss_fraction)

    profit_idx = _first_index_meeting(equity_series >= target_equity)
    loss_idx = _first_index_meeting(equity_series <= loss_equity)
    profit_ts = equity_index[profit_idx] if profit_idx is not None else None
    loss_ts = equity_index[loss_idx] if loss_idx is not None else None

    prop_violation_ts = None
    for stat in backtest.daily_stats:
        loss_fraction = _daily_loss_fraction(stat)
        if loss_fraction > challenge_config.max_daily_loss_fraction:
            prop_violation_ts = _get_day_end_timestamp(day_end_map, tz, stat.date)
            break

    internal_stop_ts = backtest.internal_stop_timestamp
    prop_fail_ts = backtest.prop_fail_timestamp

    trading_days_records: list[tuple[pd.Timestamp, DailyStats]] = []
    for stat in backtest.daily_stats:
        day_ts = _get_day_end_timestamp(day_end_map, tz, stat.date)
        trading_days_records.append((day_ts, stat))

    pass_ts = None
    if profit_ts is not None:
        for day_index, (day_ts, _) in enumerate(trading_days_records, start=1):
            if day_ts >= profit_ts and day_index >= challenge_config.min_trading_days:
                pass_ts = day_ts
                break

    max_trading_days_ts = None
    if challenge_config.max_trading_days and len(trading_days_records) >= challenge_config.max_trading_days:
        max_trading_days_ts = trading_days_records[challenge_config.max_trading_days - 1][0]

    events: list[tuple[pd.Timestamp, str]] = []
    if pass_ts is not None:
        events.append((pd.Timestamp(pass_ts), "pass"))
    if loss_ts is not None:
        events.append((pd.Timestamp(loss_ts), "total_loss"))
    if prop_violation_ts is not None:
        events.append((pd.Timestamp(prop_violation_ts), "prop_violation"))
    if internal_stop_ts is not None:
        events.append((pd.Timestamp(internal_stop_ts), "internal_stop"))
    if prop_fail_ts is not None:
        events.append((pd.Timestamp(prop_fail_ts), "prop_fail"))
    if max_trading_days_ts is not None:
        events.append((pd.Timestamp(max_trading_days_ts), "max_trading_days"))
    if challenge_config.max_calendar_days:
        deadline = pd.Timestamp(start_timestamp) + pd.Timedelta(days=challenge_config.max_calendar_days)
        if deadline > equity_index[-1]:
            deadline = equity_index[-1]
        events.append((deadline, "max_calendar_days"))

    if not events:
        events.append((equity_index[-1], "timeout"))

    events.sort(key=lambda item: item[0])
    end_timestamp = pd.Timestamp(events[0][0])
    reason = events[0][1]

    def _trading_days_up_to(ts: pd.Timestamp) -> int:
        count = 0
        for day_ts, _ in trading_days_records:
            if day_ts <= ts:
                count += 1
        return count

    num_trading_days = _trading_days_up_to(end_timestamp)
    num_trades = sum(
        1 for trade in backtest.trades if trade.get("exit_time") and pd.Timestamp(trade["exit_time"]) <= end_timestamp
    )

    slice_equity = equity_series[equity_series.index <= end_timestamp]
    final_equity = slice_equity.iloc[-1]
    peak_equity = slice_equity.max()
    min_equity = slice_equity.min()

    hit_profit_target = profit_ts is not None and pd.Timestamp(profit_ts) <= end_timestamp
    hit_total_loss = reason == "total_loss"
    hit_internal_stop = reason == "internal_stop"
    hit_prop_violation = reason == "prop_violation"
    timed_out = reason in {"timeout", "max_trading_days", "max_calendar_days"}
    passed = reason == "pass"

    max_obs_daily_loss = 0.0
    for day_ts, stat in trading_days_records:
        if day_ts <= end_timestamp:
            max_obs_daily_loss = max(max_obs_daily_loss, _daily_loss_fraction(stat))

    end_index = start_index
    if window is not None:
        end_index_candidates = window.loc[window["timestamp"] <= end_timestamp, "orig_index"]
        if not end_index_candidates.empty:
            end_index = int(end_index_candidates.iloc[-1])

    failure_reason = None if passed else reason

    return ChallengeOutcome(
        passed=passed,
        hit_profit_target=hit_profit_target,
        hit_total_loss=hit_total_loss,
        hit_internal_stop=hit_internal_stop,
        hit_prop_violation=hit_prop_violation,
        timed_out=timed_out,
        final_equity=final_equity,
        peak_equity=peak_equity,
        min_equity=min_equity,
        num_trading_days=num_trading_days,
        num_trades=num_trades,
        start_index=start_index,
        end_index=end_index,
        max_daily_loss_fraction=backtest.max_daily_loss_fraction,
        failure_reason=failure_reason,
        start_timestamp=pd.Timestamp(start_timestamp),
        end_timestamp=end_timestamp,
        max_observed_daily_loss_fraction=max_obs_daily_loss,
        trades_per_symbol=backtest.trades_per_symbol,
    )


def run_single_challenge(
    price_data: pd.DataFrame | None = None,
    challenge_config: ChallengeConfig = DEFAULT_CHALLENGE_CONFIG,
    prop_config: PropChallengeConfig | None = None,
    seed_index: int = 0,
    symbol_data_map: dict[str, pd.DataFrame] | None = None,
    event_stream: list[BarEvent] | None = None,
) -> ChallengeOutcome:
    prop = prop_config or DEFAULT_CHALLENGE

    if symbol_data_map is not None:
        if event_stream is None:
            raise ValueError("Portfolio challenge requires an event stream.")
        if seed_index >= len(event_stream):
            raise ValueError("Seed index exceeds event stream length.")
        start_event = event_stream[seed_index]
        sliced_map = _slice_symbol_map(symbol_data_map, start_event.timestamp, challenge_config.max_calendar_days)
        if not sliced_map:
            raise ValueError("Insufficient data for challenge window.")
        backtest = run_backtest(
            symbol_data_map=sliced_map,
            starting_equity=challenge_config.start_equity,
            initial_mode=DEFAULT_RISK_MODE,
            challenge_config=prop,
        )
        return _build_challenge_outcome(
            backtest=backtest,
            start_timestamp=start_event.timestamp,
            start_index=seed_index,
            challenge_config=challenge_config,
            prop=prop,
            window=None,
        )

    if price_data is None:
        raise ValueError("price_data must be provided for single-symbol challenges.")

    window = _prepare_window(price_data, seed_index, challenge_config.max_calendar_days)
    if window.empty:
        raise ValueError("Insufficient data for challenge window.")

    start_timestamp = window["timestamp"].iloc[0]
    start_index = int(window["orig_index"].iloc[0])

    backtest = run_backtest(
        window,
        starting_equity=challenge_config.start_equity,
        initial_mode=DEFAULT_RISK_MODE,
        challenge_config=prop,
    )

    return _build_challenge_outcome(
        backtest=backtest,
        start_timestamp=start_timestamp,
        start_index=start_index,
        challenge_config=challenge_config,
        prop=prop,
        window=window,
    )


def run_challenge_sweep(
    price_data: pd.DataFrame | None,
    challenge_config: ChallengeConfig = DEFAULT_CHALLENGE_CONFIG,
    prop_config: PropChallengeConfig | None = None,
    step: int = 500,
    symbol_data_map: dict[str, pd.DataFrame] | None = None,
) -> list[ChallengeOutcome]:
    outcomes: list[ChallengeOutcome] = []
    prop = prop_config or DEFAULT_CHALLENGE

    if symbol_data_map is not None:
        events = build_event_stream(symbol_data_map)
        for seed in range(0, len(events), step):
            try:
                outcome = run_single_challenge(
                    price_data=None,
                    challenge_config=challenge_config,
                    prop_config=prop,
                    seed_index=seed,
                    symbol_data_map=symbol_data_map,
                    event_stream=events,
                )
            except ValueError:
                break
            outcomes.append(outcome)
        return outcomes

    if price_data is None:
        raise ValueError("price_data or symbol_data_map must be provided.")

    for seed in range(0, len(price_data), step):
        window = price_data.iloc[seed:]
        if window.empty:
            break
        try:
            outcome = run_single_challenge(
                price_data=price_data,
                challenge_config=challenge_config,
                prop_config=prop,
                seed_index=seed,
            )
        except ValueError:
            break
        outcomes.append(outcome)
    return outcomes
