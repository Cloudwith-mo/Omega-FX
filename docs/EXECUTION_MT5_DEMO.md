# Execution Butler – MT5 Demo Backend

Phase 1b extends the execution pipeline to talk to a MetaTrader5 **demo/trial** account. This is still dry-run territory—use it to validate signals and risk controls on a sandbox before you even think about pointing at FTMO.

## TL;DR: do this next (fresh VPS)

If you just logged into a clean VPS and want the bot running, follow this condensed path:

1. Clone + enter the repo
   ```powershell
   git clone https://github.com/Cloudwith-mo/Omega-FX.git
   cd Omega-FX
   ```
2. Create/activate venv, install deps
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. Export your MetaQuotes demo credentials
   ```powershell
   $env:OMEGA_MT5_LOGIN="99295410"
   $env:OMEGA_MT5_PASSWORD="!oHdKt3u"
   $env:OMEGA_MT5_SERVER="MetaQuotes-Demo"
   ```
4. Smoke test (no live orders)
   ```powershell
   python scripts/run_exec_mt5_smoketest.py --account_profile METAQUOTES_DEMO --dry_run
   ```
5. Start the 7-day conservative loop (mean reversion only)
   ```powershell
   python scripts/run_autopilot.py `
     --bot demo_mr_only `
     --account_profile METAQUOTES_DEMO `
     --login $env:OMEGA_MT5_LOGIN `
     --password $env:OMEGA_MT5_PASSWORD `
     --server $env:OMEGA_MT5_SERVER `
     --hours 168 `
     --interval-seconds 60
   ```

Keep the window open; stop with `Ctrl+C`. For more context or tightening knobs, see the detailed sections below.

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
2. **Enable conservative limits** – use the `demo_mr_only` bot profile (conservative risk tier, mean reversion slice only) to stay within 0.05% per trade, 1% daily loss, and max 2 concurrent positions.
3. **Disable extra strategies** – the `demo_mr_only` profile already disables the London session overlay; stick with it until the feed is stable.
4. **Bound throughput** – keep `--limit_trades 25` (or lower) per loop and `--sleep-seconds 60` so the bot processes a finite batch each minute instead of hammering the account.
5. **Start a 7-day session** – example command for a full week on the default demo profile (mean reversion only, conservative ri
sk, 60s cadence):

```bash
export OMEGA_MT5_LOGIN=<your_login>
export OMEGA_MT5_PASSWORD='<your_password>'
export OMEGA_MT5_SERVER='MetaQuotes-Demo'

python scripts/run_autopilot.py \
  --bot demo_mr_only \
  --account_profile METAQUOTES_DEMO \
  --login "$OMEGA_MT5_LOGIN" \
  --password "$OMEGA_MT5_PASSWORD" \
  --server "$OMEGA_MT5_SERVER" \
  --hours 168 \
  --interval-seconds 60
```

Watch `results/mt5_demo_exec_summary.json` after a few hours: you should see single-digit trades per day, adherence to daily loss limits, and position counts ≤ 2. If trade counts spike again, stop the loop, archive the log, and re-run with tighter `--limit_trades` (e.g., 10) while inspecting the per-trade CSV for bad feed anomalies.

---

## Fresh VPS checklist (PowerShell, MetaQuotes-Demo)

Copy/paste these steps on a clean Windows VPS. They include cloning the repo, standing up Python, and starting the conservative 7-day loop on the MetaQuotes-Demo account.

1) **Open your VPS and PowerShell**
   - Connect via your provider’s console or RDP.
   - From the Start menu, type **PowerShell** and run it.

2) **Install Git + Python (skip if already installed)**
   ```powershell
   winget install --id Git.Git -e
   winget install --id Python.Python.3.11 -e
   ```
   Close/reopen PowerShell after installs so `git` and `python` land on PATH.

3) **Clone the repo and enter it**
   ```powershell
   git clone https://github.com/Cloudwith-mo/Omega-FX.git
   cd Omega-FX
   ```

4) **Create a virtual environment and install deps**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5) **Load the MetaQuotes demo credentials into env vars**
   ```powershell
   $env:OMEGA_MT5_LOGIN="99295410"
   $env:OMEGA_MT5_PASSWORD="!oHdKt3u"
   $env:OMEGA_MT5_SERVER="MetaQuotes-Demo"
   ```

6) **Smoke-test connectivity (dry run — no live orders)**
   ```powershell
   python scripts/run_exec_mt5_smoketest.py --account_profile METAQUOTES_DEMO --dry_run
   ```

7) **Start the 7-day conservative autopilot loop (mean reversion only, 60s cadence)**
   ```powershell
   python scripts/run_autopilot.py `
     --bot demo_mr_only `
     --account_profile METAQUOTES_DEMO `
     --login $env:OMEGA_MT5_LOGIN `
     --password $env:OMEGA_MT5_PASSWORD `
     --server $env:OMEGA_MT5_SERVER `
     --hours 168 `
     --interval-seconds 60
   ```
   Keep this window open; stop with `Ctrl+C`. The bot persists signals/alerts according to the bot profile; confirm placement and throughput in MT5 and logs.

8) **Optional tightening**
   - Drop `--limit_trades` to 10–15 if you see bursts.
   - Rerun the command after stopping the prior loop with `Ctrl+C`.
