# Omega FX Development Roadmap

Consolidated roadmap for evolving the Omega FX system from single-strategy to multi-strategy autonomous trading.

---

## Phase 0 – Boringly Stable Single-Strategy Node (Mostly Done)

- [x] Code + config backed up to private git + password manager.
- [x] MT5 demo account logged in, Algo Trading enabled.
- [x] Autopilot demo session runs end-to-end without errors.
- [ ] Healthcheck script passes.
- [x] `/status` and dashboard show equity, balance, 24h PnL, open positions.
- [ ] "Storm / rebuild" runbook written in Notion (section above).

**Status**: ~80% complete. Need healthcheck validation and disaster recovery docs.

---

## Phase 1 – Multi-Strategy Telemetry + Cockpit

- [x] `strategy_id` pushed through TradeDecision, logs, summaries, API.
- [x] Per-strategy aggregation helper implemented.
- [x] `/status` and `/report` expose `strategy_breakdown`.
- [x] Dashboard shows **Strategy Breakdown** table.
- [ ] Docs explain "session vs 24h vs MT5 account tab".
- [ ] MT5 + autopilot scheduled tasks updated for reboot safety.

**Status**: ~70% complete. Infrastructure exists but needs documentation and hardening.

---

## Phase 2 – Add Mean-Reversion M15 Strategy (MR)

- [x] New module `strategies/omega_mr_m15.py` (BB/RSI/ADX rules).
- [x] Autopilot runs both `omega_trend_m15` and `omega_mr_m15`.
- [x] `OMEGA_MR_M15` orders carry `strategy_id` + `signal_reason`.
- [x] Risk profile: smaller size than trend; per-strategy risk caps.
- [x] Logs / reports / dashboard show per-strategy PnL + win-rate.
- [ ] Demo-only incubation period finished (say 50-100 trades).

**Status**: ~85% complete. Code is ready, needs live validation on demo.

**Action**: Run demo for 2-4 weeks to collect 50-100 MR trades.

---

## Phase 3 – Add London Session Momentum Strategy

- [ ] New module `strategies/omega_session_london.py`:
  - Asian box: 00:00-07:00 (configurable by server time).
  - Range filters (min/max size).
  - Breakout with buffer, OCO logic, time exit.
- [ ] Autopilot only calls this strategy during configured session window.
- [ ] Per-strategy stats for `OMEGA_SESSION_LONDON`.
- [ ] Demo incubation: at least a few dozen sessions.

**Status**: Not started.

**Estimated Effort**: 2-3 weeks (design, implement, test, validate).

---

## Phase 4 – Strategy Registry + Mini "Council"

- [ ] `config/strategy_registry.yaml` listing all strategies:
  - id, family, enabled, max_fraction_risk, notes.
- [ ] Loader that reads registry into autopilot.
- [ ] Autopilot respects:
  - `enabled` flags.
  - per-strategy risk fractions.
- [ ] Simple evaluation script:
  - reads per-strategy live stats.
  - suggests downgrading strategies failing win-rate / PnL thresholds.
- [ ] Registry + evaluation surfaced in Notion (one row per strategy).

**Status**: Not started.

**Estimated Effort**: 1 week (config + automation).

**Purpose**: Governance layer for enabling/disabling strategies without code changes.

---

## Phase 5 – Omega Lab (Research Sandbox)

- [ ] Separate folder/repo `omega-lab/`.
- [ ] Shared `Strategy`/`TradeDecision` interface with live engine.
- [ ] Historical data loaders (MT5 exports, etc.).
- [ ] Backtester supports:
  - multi-strategy runs,
  - walk-forward (train/test windows),
  - saving metrics to CSV/SQLite.
- [ ] Promotion checklist: a strategy must pass Lab tests before going live.

**Status**: Partially exists (current backtest engine could be refactored).

**Estimated Effort**: 2-3 weeks.

**Purpose**: Formalize research workflow and strategy promotion process.

---

## Phase 6 – Workflow 100x (Async + Telegram + Zero-Trust)

- [ ] Wrap MT5 calls behind `asyncio` (use `run_in_executor`).
- [ ] Central event loop with queues:
  - Market data in,
  - Signals out,
  - Orders + logging,
  - Notifications.
- [ ] Telegram bot:
  - `/status`, `/open_trades`, `/pause`, `/resume`, `/flatten`, `/risk_tier`.
- [ ] MT5 runs headless (Task Scheduler or NSSM as service).
- [ ] Dead-man's switch:
  - healthcheck pings external service,
  - alerts when no heartbeat.

**Status**: Not started.

**Estimated Effort**: 3-4 weeks.

**Purpose**: Production-grade reliability and remote control.

**Priority**: HIGH once you go live with real evaluations.

---

## Phase 7 – Advanced Quant Toys

- [ ] Kalman pairs strategy integrated into Lab.
- [ ] HRP allocator for risk across strategies.
- [ ] Maybe one ML model (TFT or simple RL) in Lab only.
- [ ] Only promoted through the same governance pipeline as everything else.

**Status**: Not started (research phase).

**Estimated Effort**: 4-8 weeks per experiment.

**Purpose**: Edge research and alpha generation.

**Priority**: LOW (only after core system is profitable and stable).

---

## Current Recommendation

**You are at**: End of Phase 1 / Beginning of Phase 2

### What to Do Next (Priority Order)

#### 1. Complete Phase 0 (1-2 days)
- [ ] Write disaster recovery runbook
- [ ] Verify healthcheck script works
- [ ] Document VPS rebuild process

#### 2. Validate Phase 2 (2-4 weeks) ⭐ **DO THIS NOW**
- [ ] Let demo run with MR strategy enabled
- [ ] Collect 50-100 MR trades
- [ ] Analyze per-strategy performance
- [ ] Decide: Keep MR or disable it?

#### 3. Build Phase 6 (Before Live Evals) ⭐ **CRITICAL**
- [ ] Telegram bot for remote monitoring
- [ ] Dead-man's switch / healthcheck
- [ ] Async event loop for stability

**Why Phase 6 before Phase 3-5?**

Once you buy paid evaluations, you NEED:
1. Remote monitoring (Telegram)
2. Ability to pause/resume without VPS access
3. Alerts when bot crashes
4. Healthcheck to detect silent failures

Phases 3-5 are "nice to have" alpha generators, but Phase 6 is **operational necessity** for live trading.

---

## Suggested Timeline (Next 12 Weeks)

### Weeks 1-2: Finish Phase 0
- Write runbooks
- Harden deployment
- Document everything

### Weeks 3-6: Validate Phase 2
- Run demo with MR strategy
- Analyze performance
- Make go/no-go decision

### Weeks 7-10: Build Phase 6
- Async loop
- Telegram bot
- Dead-man's switch

### Weeks 11-12: Buy Evaluations
- Deploy Phase 6 to VPS
- Buy 2 evaluations
- Monitor via Telegram

**After passing evals**: Consider Phase 4 (strategy registry) and Phase 5 (lab).

**Phase 3 and 7**: Only if you have spare capacity or want more alpha sources.

---

## Risk Assessment

### High Priority (Do Before Live)
1. ✅ Autopilot stability (mostly done)
2. ⚠️ Remote monitoring (Telegram bot)
3. ⚠️ Healthcheck + alerts
4. ⚠️ Disaster recovery docs

### Medium Priority (Do After Funding)
1. Strategy registry
2. Research lab formalization
3. London session strategy

### Low Priority (Research Projects)
1. Kalman pairs
2. ML models
3. Advanced portfolio optimization

---

## Bottom Line

**Your roadmap is excellent.** It's well-structured and realistic.

**My advice**: 
1. Skip to Phase 6 (Telegram + monitoring) before buying evals
2. Phase 2 validation can happen in parallel with demo trading
3. Phases 3, 4, 5, 7 are post-funding projects

**You're 2-3 weeks away from being ready for paid evaluations** if you prioritize operational hardening over new strategies.
