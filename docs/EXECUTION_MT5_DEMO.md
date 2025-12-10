# Execution Butler – MT5 Demo Backend

Phase 1b extends the execution pipeline to talk to a MetaTrader5 **demo/trial** account. This is still dry-run territory—use it to validate signals and risk controls on a sandbox before you even think about pointing at FTMO.

## 1. Configure MT5 demo credentials

1. Copy `config/mt5_accounts.example.yaml` → `config/mt5_accounts.yaml` (this file is gitignored so secrets stay local).
2. For each profile (METAQUOTES_DEMO, FTMO_TRIAL, etc.) fill in your real login/password:
   ```yaml
   profiles:
     METAQUOTES_DEMO:
       server: MetaQuotes-Demo
       login: 98997498
       password: my-demo-password
       default_symbol: EURUSD
     FTMO_TRIAL:
       server: OANDA-Demo-1
       login: 1600047919
       password: ftmo-trial-password
   ```
3. Optionally export env variables (or pass CLI flags) to override profile defaults:
   ```bash
   export OMEGA_MT5_LOGIN=12345678
   export OMEGA_MT5_PASSWORD='your-demo-password'
   export OMEGA_MT5_SERVER='MetaQuotes-Demo'
   ```
   (Resolution order is CLI > env vars > profile config.)

## 2. Smoke-test the connection

1. **Connectivity check (dry run – no orders)**
   ```bash
   python scripts/run_exec_mt5_smoketest.py --account_profile METAQUOTES_DEMO --dry_run
   ```
2. **Tiny live trade (only after you’re ready)**  
   Sends a 10-pip, ~$5 risk buy on the selected symbol and closes it a couple seconds later.
   ```bash
   python scripts/run_exec_mt5_smoketest.py --account_profile METAQUOTES_DEMO --no-dry_run
   ```
3. Repeat the same commands with `--account_profile FTMO_TRIAL` to verify your FTMO trial credentials.

Each run emits `results/mt5_demo_smoketest_summary.json` so you can confirm the backend connected, submitted, and closed a trade (or logged the error if risk limits stopped it).

## 3. Run the replay script (dry-run by default)

```bash
source .venv/bin/activate
python scripts/run_exec_mt5_demo_from_signals.py \
  --account_profile METAQUOTES_DEMO \
  --dry_run \
  --max_positions 2 \
  --per_trade_risk_fraction 0.004 \
  --daily_loss_fraction 0.02 \
  --limit_trades 50
```

- Reuses the FTMO M15 preset to generate historical signals.
- Pipes them through `adapters.mt5_backend.Mt5DemoExecutionBackend`.
- Dry-run mode logs everything to `results/mt5_demo_exec_log.csv` and `results/mt5_demo_exec_summary.json` **without** sending orders to MT5.
- Swap `--account_profile FTMO_TRIAL` when you want to shadow the FTMO trial feed.

### Turning off dry-run

The backend enforces those limits internally—if a request would breach them, it fails closed and stops submitting new orders.

## 3. What’s logged

- `results/mt5_demo_exec_log.csv` – per-order events (open/close, price, equity). Same schema as the simulated backend.
- `results/mt5_demo_exec_summary.json` – aggregate stats (equity, win rate, daily loss tallies).

Use these side-by-side with `results/execution_sim_summary.json` to ensure the MT5 path mirrors the simulated numbers.

## 4. Safety reminders

- This backend is **demo only**. Do not point this script at a live FTMO or funded account until we complete a future phase that explicitly says it’s safe.
- Leave `--dry_run` in place for your first passes; watch the logs and MT5 terminal to confirm everything lines up.
- The backend fails safe: connection errors, order rejections, or risk-limit breaches stop new orders immediately and log the reason.

Once you’re comfortable with demo execution metrics matching the simulated backend, we can design Phase 1c for trial/prop wiring under the funded risk profile.

---

## Realign a runaway demo session + start a fresh week

If you see micro-scalping or trade counts that don’t match the playbook (e.g., thousands of trades, 1% win rate), reset the loop with the conservative profile and only the mean-reversion leg enabled.

1. **Confirm config** – copy `config/mt5_accounts.example.yaml` → `config/mt5_accounts.yaml` and add your MetaQuotes demo profile (server `MetaQuotes-Demo`, default symbol `XAUUSD` or `EURUSD`). Keep credentials local (gitignored file or env vars) and avoid committing secrets.
2. **Enable conservative limits** – run `run_demo_autopilot.py` with `--risk_tier conservative --risk_env demo` so it locks to 0.05% per trade, 1% daily loss, and max 2 concurrent positions.
3. **Disable extra strategies** – pass `--enable_session_momentum=false` to avoid the London session overlay until the feed is stable; leave `--enable_mean_reversion` on.
4. **Bound throughput** – keep `--limit_trades 25` (or lower) per loop and `--sleep-seconds 60` so the bot processes a finite batch each minute instead of hammering the account.
5. **Start a 7-day session** – example command for a full week on the default demo profile:

```bash
export OMEGA_MT5_LOGIN=<your_login>
export OMEGA_MT5_PASSWORD='<your_password>'
export OMEGA_MT5_SERVER='MetaQuotes-Demo'

python scripts/run_demo_autopilot.py \
  --account_profile METAQUOTES_DEMO \
  --risk_tier conservative \
  --risk_env demo \
  --hours 168 \
  --sleep-seconds 60 \
  --limit_trades 25 \
  --max_positions 2 \
  --enable_mean_reversion=true \
  --mr_risk_scale 0.5 \
  --enable_session_momentum=false \
  --summary_path results/mt5_demo_exec_live_summary.json \
  --log_path results/mt5_demo_exec_log.csv
```

Watch `results/mt5_demo_exec_summary.json` after a few hours: you should see single-digit trades per day, adherence to daily loss limits, and position counts ≤ 2. If trade counts spike again, stop the loop, archive the log, and re-run with tighter `--limit_trades` (e.g., 10) while inspecting the per-trade CSV for bad feed anomalies.
