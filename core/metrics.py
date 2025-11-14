"""Performance metrics calculations"""

import pandas as pd
import numpy as np
from typing import List
from core.backtest import Trade


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calculate Sharpe ratio"""
    if returns.std() == 0:
        return 0
    excess_returns = returns.mean() - risk_free_rate / 252  # Daily risk-free rate
    return excess_returns / returns.std() * np.sqrt(252)


def calculate_max_consecutive_losses(trades: List[Trade]) -> int:
    """Calculate maximum consecutive losing trades"""
    if not trades:
        return 0
    
    max_consecutive = 0
    current_consecutive = 0
    
    for trade in trades:
        if trade.pnl < 0:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return max_consecutive


def calculate_profit_factor(trades: List[Trade]) -> float:
    """Calculate profit factor (gross profit / gross loss)"""
    if not trades:
        return 0
    
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    
    return gross_profit / gross_loss if gross_loss > 0 else float('inf')


def generate_performance_report(equity_curve: pd.Series, trades: List[Trade]) -> dict:
    """Generate comprehensive performance report"""
    if len(equity_curve) == 0:
        return {"error": "No data available"}
    
    returns = equity_curve.pct_change().dropna()
    initial_equity = equity_curve.iloc[0]
    final_equity = equity_curve.iloc[-1]
    
    return {
        "total_return": (final_equity - initial_equity) / initial_equity,
        "total_trades": len(trades),
        "winning_trades": sum(1 for t in trades if t.pnl > 0),
        "losing_trades": sum(1 for t in trades if t.pnl < 0),
        "win_rate": sum(1 for t in trades if t.pnl > 0) / len(trades) if trades else 0,
        "avg_win": np.mean([t.pnl for t in trades if t.pnl > 0]) if any(t.pnl > 0 for t in trades) else 0,
        "avg_loss": np.mean([t.pnl for t in trades if t.pnl < 0]) if any(t.pnl < 0 for t in trades) else 0,
        "max_drawdown": (equity_curve.cummax() - equity_curve).max() / equity_curve.cummax().max(),
        "sharpe_ratio": calculate_sharpe_ratio(returns),
        "profit_factor": calculate_profit_factor(trades),
        "max_consecutive_losses": calculate_max_consecutive_losses(trades),
        "final_equity": final_equity
    }