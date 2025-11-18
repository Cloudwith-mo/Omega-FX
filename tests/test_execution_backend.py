from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from types import SimpleNamespace

from core.execution_accounts import load_account_profiles, resolve_account_config
from core.execution_base import OrderSpec
from core.position_sizing import calculate_position_size
from execution_backends.simulated import SimulatedExecutionBackend
from execution_backends.mt5_demo import Mt5DemoExecutionBackend
from scripts.run_exec_mt5_smoketest import perform_smoketest


def test_calculate_position_size_basic() -> None:
    size = calculate_position_size(
        equity=100_000,
        risk_fraction=0.01,
        entry_price=1.1000,
        stop_price=1.0900,
        symbol="EURUSD",
    )
    assert pytest.approx(size, 0.01) == 1.0

    size_small = calculate_position_size(
        equity=50_000,
        risk_fraction=0.002,
        entry_price=1.2000,
        stop_price=1.1980,
        symbol="GBPUSD",
    )
    assert size_small >= 0.01


def test_calculate_position_size_invalid() -> None:
    with pytest.raises(ValueError):
        calculate_position_size(100_000, 0.0, 1.1, 1.0, "EURUSD")
    with pytest.raises(ValueError):
        calculate_position_size(100_000, 0.01, 1.1, 1.1, "EURUSD")


def test_simulated_backend_logs_and_summary(tmp_path: Path) -> None:
    log_path = tmp_path / "sim_log.csv"
    backend = SimulatedExecutionBackend(initial_equity=100_000, log_path=log_path)
    backend.connect()
    order = OrderSpec(
        symbol="EURUSD",
        direction="long",
        volume=1.0,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        timestamp=datetime(2024, 1, 1, 9, 0),
        tag="TEST",
    )
    ticket = backend.submit_order(order)
    backend.close_position(
        ticket,
        "TP",
        close_price=1.1050,
        timestamp=datetime(2024, 1, 1, 12, 0),
    )
    summary = backend.summary()
    assert summary["number_of_trades"] == 1
    assert summary["final_equity"] > summary["initial_equity"]
    rows = log_path.read_text().strip().splitlines()
    assert len(rows) == 3  # header + open + close


class DummyMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_FILLING_FOK = 0
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 0
    TRADE_RETCODE_INVALID_STOPS = 10016

    def __init__(self) -> None:
        self.logged_in = False
        self.order_result = SimpleNamespace(retcode=0, order=1, comment="ok")

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def login(self, login=None, password=None, server=None) -> bool:
        self.logged_in = True
        return True

    def account_info(self):
        return type("Info", (), {"equity": 100_000.0, "balance": 100_000.0})()

    def positions_get(self):
        return []

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.1, ask=1.1)

    def symbol_info(self, symbol):
        return SimpleNamespace(trade_stops_level=0, point=0.0001)

    def order_send(self, request):
        return self.order_result

    def last_error(self):
        return (0, "ok")


def test_mt5_backend_risk_blocks(monkeypatch, tmp_path: Path) -> None:
    dummy = DummyMT5()
    monkeypatch.setattr("execution_backends.mt5_demo.mt5", dummy)
    backend = Mt5DemoExecutionBackend(
        login=1,
        password="x",
        server="demo",
        dry_run=True,
        per_trade_risk_fraction=0.0001,
        log_path=tmp_path / "log.csv",
        summary_path=tmp_path / "summary.json",
    )
    backend.connect()
    spec = OrderSpec(
        symbol="EURUSD",
        direction="long",
        volume=10.0,
        entry_price=1.1000,
        stop_loss=1.0990,
    )
    with pytest.raises(RuntimeError):
        backend.submit_order(spec)


def test_mt5_backend_daily_loss(monkeypatch, tmp_path: Path) -> None:
    dummy = DummyMT5()
    monkeypatch.setattr("execution_backends.mt5_demo.mt5", dummy)
    backend = Mt5DemoExecutionBackend(
        login=1,
        password="x",
        server="demo",
        dry_run=True,
        daily_loss_fraction=0.002,
        log_path=tmp_path / "log2.csv",
        summary_path=tmp_path / "summary2.json",
    )
    backend.connect()
    spec = OrderSpec(
        symbol="EURUSD",
        direction="long",
        volume=0.5,
        entry_price=1.1000,
        stop_loss=1.0990,
    )
    ticket = backend.submit_order(spec)
    backend.close_position(ticket, "loss", close_price=1.0950)
    rejected = backend.submit_order(spec)
    assert rejected is None
    assert backend.last_limit_reason == "daily_loss"
    assert backend.summary()["filtered_daily_loss"] == 1


def test_mt5_backend_invalid_stops_filtered(monkeypatch, tmp_path: Path) -> None:
    dummy = DummyMT5()
    dummy.order_result = SimpleNamespace(
        retcode=dummy.TRADE_RETCODE_INVALID_STOPS,
        order=0,
        comment="invalid stops",
    )
    monkeypatch.setattr("execution_backends.mt5_demo.mt5", dummy)
    backend = Mt5DemoExecutionBackend(
        login=1,
        password="x",
        server="demo",
        dry_run=False,
        log_path=tmp_path / "log3.csv",
        summary_path=tmp_path / "summary3.json",
    )
    backend.connect()
    spec = OrderSpec(
        symbol="EURUSD",
        direction="long",
        volume=0.1,
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1010,
    )
    rejected = backend.submit_order(spec)
    assert rejected is None
    assert backend.last_limit_reason == "invalid_stops"
    summary = backend.summary()
    assert summary["filtered_invalid_stops"] == 1


def test_account_loader_merges(tmp_path: Path) -> None:
    example = tmp_path / "example.yaml"
    example.write_text(
        "profiles:\n  DEMO:\n    server: EXAMPLE\n    description: test\n    default_symbol: EURUSD\n"
    )
    config = tmp_path / "config.yaml"
    config.write_text("profiles:\n  demo:\n    login: 111\n    password: secret\n")
    profiles = load_account_profiles(config_path=config, example_path=example)
    assert "DEMO" in profiles
    account = resolve_account_config("DEMO", config_path=config, example_path=example)
    assert account.login == 111
    assert account.password == "secret"
    assert account.server == "EXAMPLE"


class _FakeBackend:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.initial_equity = 100_000.0
        self.current_equity = 100_000.0

    def connect(self) -> None:
        self.connected = True

    def submit_order(self, order: OrderSpec) -> str:
        self.order = order
        return "FAKE-1"

    def close_position(self, ticket, reason, close_price=None, timestamp=None):
        self.closed = True

    def disconnect(self) -> None:
        self.disconnected = True


class _FailingBackend(_FakeBackend):
    def submit_order(self, order: OrderSpec) -> str | None:
        self.last_limit_reason = "daily_loss"
        return None


def test_smoketest_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.run_exec_mt5_smoketest.mt5",
        SimpleNamespace(symbol_info_tick=lambda symbol: SimpleNamespace(bid=1.1, ask=1.1)),
    )
    account = SimpleNamespace(name="TEST", login=1, password="x", server="demo", default_symbol="EURUSD")
    args = SimpleNamespace(
        dry_run=True,
        max_positions=1,
        per_trade_risk_fraction=0.0005,
        daily_loss_fraction=0.005,
        risk_amount=5.0,
        stop_pips=5.0,
        hold_seconds=0.0,
    )
    summary = perform_smoketest(account, args, backend_cls=_FakeBackend)
    assert summary["dry_run"] is True
    assert summary["order_sent"] is True
    assert summary["order_closed"] is True


def test_smoketest_handles_daily_loss(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.run_exec_mt5_smoketest.mt5",
        SimpleNamespace(symbol_info_tick=lambda symbol: SimpleNamespace(bid=1.1, ask=1.1)),
    )
    account = SimpleNamespace(name="TEST", login=1, password="x", server="demo", default_symbol="EURUSD")
    args = SimpleNamespace(
        dry_run=False,
        max_positions=1,
        per_trade_risk_fraction=0.0005,
        daily_loss_fraction=0.0001,
        risk_amount=5.0,
        stop_pips=5.0,
        hold_seconds=0.0,
    )
    summary = perform_smoketest(account, args, backend_cls=_FailingBackend)
    assert summary["error"] and "filtered" in summary["error"]
    assert summary["order_sent"] is False
