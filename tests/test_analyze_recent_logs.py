"""Tests for analyze_recent_logs script."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.analyze_recent_logs import analyze_logs, _compute_strategy_stats


def test_analyze_logs_computes_metrics(tmp_path: Path) -> None:
    """Test that analyze_logs correctly computes behavior metrics."""
    log_path = tmp_path / "test_analyze_log.csv"
    now = datetime.now(timezone.utc)
    
    fieldnames = [
        "timestamp", "event", "ticket", "symbol", "direction",
        "volume", "price", "equity", "pnl", "data_mode",
        "strategy_id", "session_id", "signal_reason"
    ]
    
    # Create a trade with known metrics
    # Entry: 1.1000, Exit: 1.1020 (20 pips profit)
    # Hold time: 1 hour
    rows = [
        {
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "event": "OPEN",
            "ticket": "t1",
            "symbol": "EURUSD",
            "direction": "long",
            "volume": "1.0",
            "price": "1.1000",
            "equity": "100000.0",
            "pnl": "",
            "data_mode": "live",
            "strategy_id": "STRAT_A",
            "session_id": "sess1",
        },
        {
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "event": "CLOSE",
            "ticket": "t1",
            "symbol": "EURUSD",
            "direction": "long",
            "volume": "1.0",
            "price": "1.1020",
            "equity": "100200.0",
            "pnl": "200.0",
            "data_mode": "live",
            "strategy_id": "STRAT_A",
            "session_id": "sess1",
        },
    ]
    
    with log_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    # Analyze
    analysis = analyze_logs(log_path, include_historical=False)
    
    # Verify trades
    assert len(analysis["trades"]) == 1
    trade = analysis["trades"][0]
    assert trade["ticket"] == "t1"
    assert trade["pnl"] == 200.0
    assert trade["hold_seconds"] == 3600.0
    assert trade["pips_moved"] == pytest.approx(20.0)
    assert trade["is_win"] is True
    
    # Verify strategy stats
    strat_stats = analysis["per_strategy"]["STRAT_A"]
    assert strat_stats["total_trades"] == 1
    assert strat_stats["wins"] == 1
    assert strat_stats["win_rate"] == 1.0
    assert strat_stats["avg_pnl"] == 200.0
    assert strat_stats["avg_hold_minutes"] == 60.0
    assert strat_stats["avg_pips"] == pytest.approx(20.0)


def test_compute_strategy_stats_aggregation() -> None:
    """Test aggregation logic in _compute_strategy_stats."""
    trades = [
        # Win: $100, 10 pips, 1h hold
        {
            "pnl": 100.0,
            "is_win": True,
            "hold_seconds": 3600.0,
            "pips_moved": 10.0,
            "r_multiple": 2.0,
            "entry_time": datetime(2023, 1, 1, 10, 0),
            "exit_time": datetime(2023, 1, 1, 11, 0),
        },
        # Loss: -$50, 5 pips, 30m hold
        {
            "pnl": -50.0,
            "is_win": False,
            "hold_seconds": 1800.0,
            "pips_moved": 5.0,
            "r_multiple": -1.0,
            "entry_time": datetime(2023, 1, 1, 12, 0),
            "exit_time": datetime(2023, 1, 1, 12, 30),
        },
    ]
    
    stats = _compute_strategy_stats(trades, "TEST_STRAT")
    
    assert stats["strategy_id"] == "TEST_STRAT"
    assert stats["total_trades"] == 2
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["win_rate"] == 0.5
    assert stats["total_pnl"] == 50.0
    assert stats["avg_pnl"] == 25.0
    
    # Averages
    assert stats["avg_hold_seconds"] == 2700.0  # (3600 + 1800) / 2
    assert stats["avg_pips"] == 7.5  # (10 + 5) / 2
    assert stats["avg_r_multiple"] == 0.5  # (2.0 - 1.0) / 2
    
    # Distributions
    assert stats["hold_time_dist"]["1800-3600"] == 1
    assert stats["hold_time_dist"]["3600-7200"] == 1
    assert stats["r_multiple_dist"]["-1-0"] == 1
    assert stats["r_multiple_dist"]["2-5"] == 1


def test_analyze_logs_handles_empty_file(tmp_path: Path) -> None:
    """Test that analyze_logs handles empty logs gracefully."""
    log_path = tmp_path / "empty_log.csv"
    log_path.touch()
    
    # Should raise error for empty file (no header) or handle gracefully if header exists but no rows
    # The csv.DictReader needs a header line at minimum
    log_path.write_text("timestamp,event,ticket\n")
    
    analysis = analyze_logs(log_path)
    
    assert analysis["trades"] == []
    assert analysis["per_strategy"] == {}
    assert analysis["overall"]["total_trades"] == 0
