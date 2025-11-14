"""Backtesting engine for Omega FX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pathlib import Path

import pandas as pd

from config.settings import DEFAULT_DATA_PATH, INITIAL_EQUITY, PIP_VALUE_PER_STANDARD_LOT
from core.risk import RISK_CONFIG, RiskMode, RiskState
from core.sizing import compute_position_size
from core.strategy import annotate_indicators, generate_signal


REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


@dataclass
class ActivePosition:
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    lot_size: float
    stop_loss: float
    take_profit: float
    mode_at_entry: RiskMode
    reason: str


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


def run_backtest(
    df: pd.DataFrame,
    starting_equity: float = INITIAL_EQUITY,
    initial_mode: RiskMode = RiskMode.CONSERVATIVE,
    data_source: str | Path | None = None,
) -> BacktestResult:
    """
    Run a single-position backtest using SMA signals and ATR stops.

    Assumptions:
        * One position at a time.
        * Entries/exits take the close of the bar that triggers the event.
        * SL/TP are simple price levels derived from ATR; no intrabar simulation.
    """
    price_df = annotate_indicators(_prepare_price_data(df, source=data_source))

    risk_state = RiskState(starting_equity, initial_mode)
    position: Optional[ActivePosition] = None
    current_day = None
    trades_today = 0

    equity_curve_points: List[tuple[pd.Timestamp, float]] = []
    trades: List[dict] = []
    recent_trade_pnls: List[float] = []

    for idx in range(1, len(price_df)):
        row = price_df.iloc[idx]
        prev_row = price_df.iloc[idx - 1]
        timestamp = pd.to_datetime(row["timestamp"])

        trade_date = timestamp.date()
        if current_day != trade_date:
            risk_state.on_new_day()
            current_day = trade_date
            trades_today = 0

        signal = generate_signal(row, prev_row)

        # Handle exits first.
        trade_closed = False
        if position:
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

            if exit_price is not None:
                pnl = _pip_pnl(position.entry_price, exit_price, position.direction, position.lot_size)
                risk_state.update_equity(risk_state.current_equity + pnl)
                risk = abs(position.entry_price - position.stop_loss)
                reward = abs(position.take_profit - position.entry_price)
                risk_reward = reward / risk if risk > 1e-12 else None
                trades.append(
                    {
                        "entry_time": position.entry_time,
                        "exit_time": timestamp,
                        "direction": position.direction,
                        "entry_price": position.entry_price,
                        "exit_price": exit_price,
                        "stop_loss": position.stop_loss,
                        "take_profit": position.take_profit,
                        "lot_size": position.lot_size,
                        "pnl": pnl,
                        "mode_at_entry": position.mode_at_entry.value,
                        "reason": exit_reason,
                        "risk_reward": risk_reward,
                    }
                )
                recent_trade_pnls.append(pnl)
                if len(recent_trade_pnls) > 25:
                    recent_trade_pnls.pop(0)
                position = None
                trade_closed = True

        # Consider entries if flat.
        if position is None and signal.action in {"long", "short"}:
            if signal.stop_distance_pips is not None and signal.take_profit_distance_pips is not None:
                config = RISK_CONFIG[risk_state.current_mode]
                if trades_today < config["max_trades_per_day"] and risk_state.can_trade_today():
                    lot_size = compute_position_size(
                        account_equity=risk_state.current_equity,
                        risk_mode=risk_state.current_mode,
                        stop_distance_pips=signal.stop_distance_pips,
                    )
                    pip_to_price = signal.stop_distance_pips / 10_000
                    tp_to_price = signal.take_profit_distance_pips / 10_000
                    entry_price = float(row["close"])

                    if signal.action == "long":
                        stop_loss = entry_price - pip_to_price
                        take_profit = entry_price + tp_to_price
                    else:
                        stop_loss = entry_price + pip_to_price
                        take_profit = entry_price - tp_to_price

                    position = ActivePosition(
                        direction=signal.action,
                        entry_time=timestamp,
                        entry_price=entry_price,
                        lot_size=lot_size,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        mode_at_entry=risk_state.current_mode,
                        reason=signal.reason,
                    )
                    trades_today += 1

        # Record equity including unrealized PnL.
        unrealized_pnl = 0.0
        if position:
            unrealized_pnl = _pip_pnl(position.entry_price, float(row["close"]), position.direction, position.lot_size)

        equity_value = risk_state.current_equity + unrealized_pnl
        equity_curve_points.append((timestamp, equity_value))

        if trade_closed:
            win_rate = (
                sum(1 for pnl in recent_trade_pnls if pnl > 0) / len(recent_trade_pnls)
                if recent_trade_pnls
                else None
            )
            recent_values = [val for _, val in equity_curve_points[-50:]]
            dd_recent = _recent_drawdown(recent_values)
            risk_state.update_mode_based_on_performance(win_rate, dd_recent)

    if equity_curve_points:
        index = pd.Index([ts for ts, _ in equity_curve_points], name="timestamp")
        values = [val for _, val in equity_curve_points]
        equity_curve = pd.Series(values, index=index)
    else:
        equity_curve = pd.Series(dtype=float)

    final_equity = equity_curve.iloc[-1] if not equity_curve.empty else starting_equity
    total_return = (final_equity - starting_equity) / starting_equity
    max_dd = _recent_drawdown(list(equity_curve)) or 0.0
    win_rate = (
        sum(1 for trade in trades if trade["pnl"] > 0) / len(trades)
        if trades
        else 0.0
    )
    rr_values = [t["risk_reward"] for t in trades if t.get("risk_reward") is not None]
    average_rr = sum(rr_values) / len(rr_values) if rr_values else 0.0

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        total_return=total_return,
        max_drawdown=max_dd,
        win_rate=win_rate,
        number_of_trades=len(trades),
        final_equity=final_equity,
        average_rr=average_rr,
    )
