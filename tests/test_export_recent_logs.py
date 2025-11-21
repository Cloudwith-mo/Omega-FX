"""Tests for export_recent_logs script."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.export_recent_logs import export_recent_logs


def test_export_recent_logs_filters_by_time(tmp_path: Path) -> None:
    """Test that export_recent_logs correctly filters rows by time window."""
    # Create a fake log file with timestamps spanning 4 days
    log_path = tmp_path / "test_exec_log.csv"
    now = datetime.now(timezone.utc)
    
    rows = []
    fieldnames = [
        "timestamp",
        "event",
        "ticket",
        "symbol",
        "direction",
        "volume",
        "price",
        "equity",
        "pnl",
        "data_mode",
        "strategy_id",
        "session_id",
    ]
    
    # Add trades from different time periods
    # Day 1: 2 trades (outside 48h window)
    for i in range(2):
        ts = now - timedelta(days=3, hours=i)
        rows.append({
            "timestamp": ts.isoformat(),
            "event": "CLOSE",
            "ticket": f"day1_{i}",
            "symbol": "EURUSD",
            "direction": "long",
            "volume": "1.0",
            "price": "1.1000",
            "equity": "100000.0",
            "pnl": "50.0",
            "data_mode": "live",
            "strategy_id": "OMEGA_M15_TF1",
            "session_id": "demo_session_1",
        })
    
    # Day 2: 3 trades (outside 48h window)
    for i in range(3):
        ts = now - timedelta(days=2, hours=13 + i)
        rows.append({
            "timestamp": ts.isoformat(),
            "event": "CLOSE",
            "ticket": f"day2_{i}",
            "symbol": "GBPUSD",
            "direction": "short",
            "volume": "0.5",
            "price": "1.2500",
            "equity": "100100.0",
            "pnl": "-25.0",
            "data_mode": "live",
            "strategy_id": "OMEGA_MR_M15",
            "session_id": "demo_session_2",
        })
    
    # Day 3: 4 trades (within 48h window)
    for i in range(4):
        ts = now - timedelta(hours=36 + i)
        rows.append({
            "timestamp": ts.isoformat(),
            "event": "CLOSE",
            "ticket": f"day3_{i}",
            "symbol": "USDJPY",
            "direction": "long",
            "volume": "1.0",
            "price": "150.00",
            "equity": "100050.0",
            "pnl": "75.0",
            "data_mode": "live",
            "strategy_id": "OMEGA_M15_TF1",
            "session_id": "demo_session_3",
        })
    
    # Day 4: 5 trades (within 48h window)
    for i in range(5):
        ts = now - timedelta(hours=12 + i)
        rows.append({
            "timestamp": ts.isoformat(),
            "event": "CLOSE",
            "ticket": f"day4_{i}",
            "symbol": "EURUSD",
            "direction": "short",
            "volume": "0.75",
            "price": "1.1100",
            "equity": "100150.0",
            "pnl": "100.0",
            "data_mode": "live",
            "strategy_id": "OMEGA_SESSION_LDN_M15",
            "session_id": "demo_session_4",
        })
    
    # Write CSV
    with log_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    # Export logs for last 48 hours
    output_path, summary = export_recent_logs(
        log_path=log_path,
        hours=48.0,
        env="test",
        output_path=tmp_path / "output.csv",
        include_historical=False,
    )
    
    # Verify output file exists
    assert output_path.exists()
    
    # Read output and verify row count
    with output_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        filtered_rows = list(reader)
    
    # Should have 9 rows (4 from day 3 + 5 from day 4)
    assert len(filtered_rows) == 9
    
    # Verify summary
    assert summary["total_rows"] == 9
    assert summary["close_trades"] == 9
    assert summary["open_trades"] == 0
    
    # Verify timestamps are within window
    for row in filtered_rows:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (now - ts).total_seconds() / 3600
        assert age_hours <= 48.0


def test_export_recent_logs_computes_pnl(tmp_path: Path) -> None:
    """Test that export_recent_logs correctly computes PnL statistics."""
    log_path = tmp_path / "test_pnl_log.csv"
    now = datetime.now(timezone.utc)
    
    fieldnames = [
        "timestamp",
        "event",
        "ticket",
        "symbol",
        "direction",
        "volume",
        "price",
        "equity",
        "pnl",
        "data_mode",
        "strategy_id",
        "session_id",
    ]
    
    # Create trades with known PnL values
    rows = [
        {
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "event": "CLOSE",
            "ticket": "1",
            "symbol": "EURUSD",
            "direction": "long",
            "volume": "1.0",
            "price": "1.1000",
            "equity": "100100.0",
            "pnl": "100.0",  # Win
            "data_mode": "live",
            "strategy_id": "OMEGA_M15_TF1",
            "session_id": "test",
        },
        {
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "event": "CLOSE",
            "ticket": "2",
            "symbol": "EURUSD",
            "direction": "short",
            "volume": "1.0",
            "price": "1.1000",
            "equity": "100050.0",
            "pnl": "-50.0",  # Loss
            "data_mode": "live",
            "strategy_id": "OMEGA_M15_TF1",
            "session_id": "test",
        },
        {
            "timestamp": (now - timedelta(hours=3)).isoformat(),
            "event": "CLOSE",
            "ticket": "3",
            "symbol": "GBPUSD",
            "direction": "long",
            "volume": "1.0",
            "price": "1.2500",
            "equity": "100200.0",
            "pnl": "150.0",  # Win
            "data_mode": "live",
            "strategy_id": "OMEGA_MR_M15",
            "session_id": "test",
        },
    ]
    
    with log_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    # Export
    output_path, summary = export_recent_logs(
        log_path=log_path,
        hours=24.0,
        env="test",
        output_path=tmp_path / "output.csv",
    )
    
    # Verify PnL calculations
    assert summary["total_rows"] == 3
    assert summary["close_trades"] == 3
    assert summary["total_pnl"] == 200.0  # 100 - 50 + 150
    assert summary["avg_pnl"] == pytest.approx(200.0 / 3)
    assert summary["win_rate"] == pytest.approx(2.0 / 3)  # 2 wins out of 3


def test_export_recent_logs_strategy_counts(tmp_path: Path) -> None:
    """Test that per-strategy counts are computed correctly."""
    log_path = tmp_path / "test_strategy_log.csv"
    now = datetime.now(timezone.utc)
    
    fieldnames = [
        "timestamp",
        "event",
        "ticket",
        "symbol",
        "direction",
        "volume",
        "price",
        "equity",
        "pnl",
        "data_mode",
        "strategy_id",
        "session_id",
    ]
    
    # Create trades for different strategies
    rows = []
    for i in range(3):
        rows.append({
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "event": "CLOSE",
            "ticket": f"tf1_{i}",
            "symbol": "EURUSD",
            "direction": "long",
            "volume": "1.0",
            "price": "1.1000",
            "equity": "100000.0",
            "pnl": "50.0",
            "data_mode": "live",
            "strategy_id": "OMEGA_M15_TF1",
            "session_id": "test",
        })
    
    for i in range(2):
        rows.append({
            "timestamp": (now - timedelta(hours=i + 3)).isoformat(),
            "event": "CLOSE",
            "ticket": f"mr_{i}",
            "symbol": "GBPUSD",
            "direction": "short",
            "volume": "0.5",
            "price": "1.2500",
            "equity": "100000.0",
            "pnl": "-25.0",
            "data_mode": "live",
            "strategy_id": "OMEGA_MR_M15",
            "session_id": "test",
        })
    
    with log_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    # Export
    output_path, summary = export_recent_logs(
        log_path=log_path,
        hours=24.0,
        env="test",
        output_path=tmp_path / "output.csv",
    )
    
    # Verify strategy counts
    assert summary["strategy_close_counts"]["OMEGA_M15_TF1"] == 3
    assert summary["strategy_close_counts"]["OMEGA_MR_M15"] == 2
    assert len(summary["strategy_close_counts"]) == 2
