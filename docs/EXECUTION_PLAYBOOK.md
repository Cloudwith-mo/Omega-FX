# Execution Playbook (Phase 1a)

Omega’s execution stack is intentionally layered:

```
Strategy (e.g. Omega M15) → Trade signal → OrderSpec → ExecutionBackend
```

- **Strategy:** produces normalized trade signals (direction, SL/TP, risk scale).
- **OrderSpec:** wraps those signals with actual sizing (lots) and metadata.
- **ExecutionBackend:** handles orders. In Phase 1a we ship a **Simulated backend** only.

## 1. Position sizing helpers

`core/position_sizing.py` exposes `calculate_position_size()` which uses account equity, risk fraction, and stop distance (plus symbol metadata) to produce MT5-ready lot sizes. This keeps sizing consistent between the backtester and execution.

## 2. Simulated backend

- Module: `execution_backends/simulated.py`
- Implements the generic `ExecutionBackend` interface (connect/disconnect/sync/submit/close).
- Logs fills to `results/execution_sim_log.csv` and tracks realized equity / drawdown, so you can compare with `run_minimal_ftmo_eval.py`.
- No broker or network dependencies.

## 3. Replay script

Recreate historical runs by replaying Omega’s signals through the simulated backend:

```bash
source .venv/bin/activate
python scripts/run_exec_sim_from_signals.py --starting_equity 100000 --limit_trades 200
```

Outputs:

- `results/execution_sim_log.csv` – per-order log.
- `results/execution_sim_summary.json` – PnL, win-rate, drawdown, etc.

These numbers should be in the same ballpark as `python scripts/run_minimal_ftmo_eval.py --step 10000`.

## 4. Next steps

- Phase 1a = strategy-agnostic interface + simulated backend.
- Phase 1b adds the MT5 demo / dry-run backend. See [EXECUTION_MT5_DEMO.md](EXECUTION_MT5_DEMO.md) for the sandbox walkthrough.

**Safety note:** Until Phase 1b is complete, all execution remains offline. Do **not** use these tools on a live or paid FTMO account yet.
