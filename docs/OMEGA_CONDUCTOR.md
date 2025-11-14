# Omega FX – Conductor

You (the AI in VS Code) are NOT the boss.  
Muhammad + this file are the boss.

## Project Goal

Build a safe, prop-firm-ready FX engine that:
- Trades multiple pairs (EURUSD, GBPUSD, USDJPY, …)
- Obeys FundedNext-style risk rules (2% daily, 4% trailing, 3%/6% prop caps)
- Gradually increases edge + trade frequency
- Can later be upgraded to a multi-agent system (fundamental + technical + risk agents).

## Active Phase

### Phase 2 – Multi-pair portfolio backtester

**Done so far**
- Single-pair engine with FundedNext risk guardrails.
- Challenge sim for EURUSD.
- Event stream builder for multiple symbols.

**Current Step**
- Step 2.3: Replace the old single-symbol backtest loop with a portfolio loop that:
  - Iterates over `build_event_stream(...)`
  - Maintains per-symbol state where needed
  - Still enforces:
    - Single *global* position at a time (for now)
    - 2% daily loss cap
    - 4% trailing DD cap
  - Produces the same metrics outputs as before.

### Next Phase (preview)

- Phase 3 – More trades / edge hunting:
  - Increase trade count safely.
  - Refine filters and risk tiers.
  - Prepare architecture for future “agents”.

## Rules for Any AI Working on This Repo

1. **Always read this file first** before making changes.
2. **Ask for approval** before:
   - Big refactors
   - Changing risk limits
   - Adding/removing symbols
3. **Never**:
   - Use toy/sample/random market data unless explicitly told.
   - Relax FundedNext guardrails by yourself.
4. **After each major change**, always run:

   ```bash
   source .venv/bin/activate  # or equivalent
   pytest
   python scripts/run_backtest.py
   python scripts/run_challenge_sim.py --data_path data/eurusd_h1.csv --step 2000
   ```

Report back in this format (in the chat + commit message):

“Changes: …”

“Files touched: …”

“Commands run: …”

“Key metrics: final equity, max DD, max daily loss, # trades, pass %.”

Commit that.
