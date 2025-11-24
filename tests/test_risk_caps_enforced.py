import pytest
from execution_backends.mt5_demo import Mt5DemoExecutionBackend


def _backend():
    return Mt5DemoExecutionBackend(
        login=None,
        password=None,
        server=None,
        dry_run=True,
        max_positions=2,
        per_trade_risk_fraction=0.004,
        daily_loss_fraction=0.02,
        log_path='results/test_log.csv',
        summary_path='results/test_summary.json',
    )


def test_risk_caps_daily_loss_blocks_new_trades():
    backend = _backend()
    backend.daily_start_equity = 100_000
    backend.current_equity = 97_000  # already -3% down
    backend.high_water_mark = 105_000
    reason = backend._limit_reason(risk_amount=500)
    assert reason == "risk_cap_daily_loss"


def test_risk_caps_total_drawdown_blocks_new_trades():
    backend = _backend()
    backend.daily_start_equity = 100_000
    backend.current_equity = 97_500  # 2.5% daily loss, under daily cap
    backend.high_water_mark = 110_000  # ~11.4% drawdown
    reason = backend._limit_reason(risk_amount=0)
    assert reason == "risk_cap_total_dd"
