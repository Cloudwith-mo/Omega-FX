# Ω-FX Trading Philosophy

> “Each successful eval → funded account → payout cycle is one **Capital Mint**.  
> The goal is to maximize expected Capital Mints per year while keeping real-world drawdown survivable.”

This document defines the high-level philosophy behind Ω-FX. Every change to code, presets, or workflows should be checked against these principles.

---

## 1. Core Objective

**Primary goal**

- Convert **prop evaluations** into **funded accounts** and then into **cash payouts**, with:
  - Controlled risk relative to **real bankroll**.
  - Low probability of catastrophic loss.
  - Realistic expectations about variance and “soft failures.”

In plainer terms:

- **Lab:** Build a system that has a **stable, repeatable edge** under prop firm constraints.
- **Life:** Turn that edge into **capital coupons** (payouts) that can fund other projects.

---

## 2. Constraints & Reality

1. **Prop firm rules (FTMO / FundedNext / Aqua)**  
   - Daily loss caps ≈ **3–5%**.  
   - Total loss caps ≈ **6–10%**.  
   - Violations = account death, regardless of strategy quality.

2. **Internal risk limits (by design)**  
   - Eval phase: daily risk budget typically **≤ 2–2.5%** of account.  
   - Multi-position: number of open trades and worst-case R are always checked against that daily budget.  
   - Funded phase: **risk is reduced** (not increased) once payouts begin.

3. **Soft failure is real**  
   - Most failures are **not blow-ups**, but evals that:
     - Drift between **–3% and +5%**
     - Never hit +10%
     - Consume time, attention, and psychological capital

Ω-FX is designed to make **hard failure rare**, and to **manage soft failure with explicit stopping rules** and multi-eval campaigns.

---

## 3. Structure of the System

### 3.1 Phases

1. **Evaluation Phase (EVAL)**  
   - Objective: Hit firm profit target (e.g., **+10%**) without breaking rules.  
   - Engine:
     - **M15 entries with H1 context** on **EURUSD / GBPUSD / USDJPY**.
     - Tiered risk by context:
       - A-tier (strong edge): highest allowed risk per trade.
       - B-tier: reduced size.
       - UNKNOWN: small or optional.
       - C-tier: blocked.
     - Firm-aware profile:
       - FTMO / FundedNext / Aqua caps are encoded in presets.
       - Max positions typically **2**, subject to daily risk budget.
   - Time-boxed:
     - Each eval is allowed **up to 20 trading days**.  
     - If it has not passed by then, it is treated as **statistically exhausted** (soft fail).

2. **Funded Phase (FUNDED)**  
   - Objective: **Extract payouts**, not speedrun risk.  
   - Engine:
     - Same directional logic as eval but with **reduced risk scales**.
     - Payout ratchet: when equity crosses thresholds (e.g., +5%, +10%), simulate taking payouts and lowering risk further.
   - Priority:
     - Preserve the account.
     - Allow payouts to **accumulate across multiple funded accounts**.

3. **Campaign Level (Multi-Eval / Multi-Firm)**  
   - Objective: Over many evals + funded periods, maximize **expected total payout** for a given real-world bankroll.  
   - Use campaign sims to answer:
     - “What is the probability of at least one pass over N evals?”
     - “What is the distribution of total payout over 6–12 months?”
     - “How bad can a campaign go before I hit my bankroll floor?”

---

### 3.2 Capital Mint Framework

We define a **Capital Mint** as:

> One Eval → Pass → Funded Account → At least one payout.

The system is evaluated not just on individual trades or evals, but on:

- **Capital Mints per year**
- **Expected payout per Mint**
- **Risk of losing the real-world bankroll allocated to eval fees**

---

## 4. Risk Philosophy

1. **Bankroll-first**

   - The true risk is **fees + time + emotional energy**, not the virtual 100k balance.
   - Internal caps (daily and trailing) are tuned such that:
     - Single-day outcomes do **not** threaten the trader’s real bankroll.
     - Account death is rare under backtests and challenge sims.

2. **State-dependent risk**

   - Risk is a **function of equity state**, not a fixed constant:
     - Base risk when near starting balance.
     - Slightly higher risk when significantly ahead (within caps).
     - Reduced risk in the **funded** phase after first payout.

3. **Context-dependent risk (tiers)**

   - A-tier (strong historical expectancy):  
     - highest risk per trade (within per-day caps).
   - B-tier: smaller risk or disabled during evals.
   - UNKNOWN: small exploratory risk, or disabled in live evals.
   - C-tier: blocked.

4. **Tradeoffs are explicit**

   - Higher pass rates come with:
     - More trades.
     - Higher realized variance.
   - Ω-FX chooses **firm-aware profiles** where:
     - Pass probability is high enough to justify eval fees.
     - Risk of account death remains within acceptable bounds.

---

## 5. Stopping Rules & Timeboxing

**Eval Stopping Rule**

- Maximum horizon: **20 trading days** (configurable).
- If by that time:
  - Equity ≥ target (e.g., +10%): eval is a **success**.
  - Equity ≤ hard internal DD / near prop caps: eval considered **failed**.
  - Equity in [–3%, +5%]: **soft fail** → eval is de-prioritized or parked.

The point: Ω-FX does **not** chase every eval indefinitely.  
It treats evals as **options with limited time value** and allocates attention and fees accordingly.

---

## 6. Design Rules for Future Work

Any new feature, agent, or preset should answer:

1. **Which layer is this improving?**
   - Trade-level edge?
   - Eval pass rates?
   - Funded payout stability?
   - Campaign-level risk / reward?

2. **What metric does it aim to move?**
   - Pass rate?
   - Max drawdown?
   - Mean payout per funded account?
   - Probability of ≥$X payout in Y months?

3. **Does it respect the constraints?**
   - Firm rules (daily/total loss).
   - Internal bankroll risk.
   - Timeboxing / stopping rules.

4. **Can we measure it?**
   - Backtest → Challenge sim → Campaign sim.
   - Compare against a tagged baseline (e.g., `phase4_ftmo_deploy_preset_v1`).

If a change improves a metric **only by violating these principles**, it is **rejected**.

---

## 7. Operational Defaults (Current)

These are not immutable, but describe the current intended defaults:

- **Primary firm target:** FTMO (with FundedNext / Aqua as backup profiles).
- **Primary entry mode:** `M15_WITH_H1_CTX` multi-pair portfolio.
- **Max concurrent positions:** 2 (eval), possibly lower for funded.
- **Risk scales:** firm-profile + tier-based presets from config.
- **Campaign template:** multiple evals per campaign, not a single “all-or-nothing” eval.

---

Ω-FX is not trying to “win every eval.”  
It is trying to **turn systematic edge + disciplined risk** into a stream of **Capital Mints** that grow the trader’s real wealth over time.

