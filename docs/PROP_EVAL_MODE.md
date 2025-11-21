# Prop Firm Evaluation Mode

This document outlines the configuration and rules of engagement for running OmegaFX in **Prop Firm Evaluation Mode**.

## 1. Risk Configuration

The `PROP_EVAL` risk profile is designed to pass a standard 2-step prop firm challenge (e.g., FTMO, FundedNext) while strictly adhering to drawdown limits.

| Metric | Limit | Description |
| :--- | :--- | :--- |
| **Max Daily Loss** | **3%** | Hard limit. Trading stops for the day if equity drops 3% from the daily starting balance. |
| **Max Total Loss** | **8%** | Hard limit. Trading stops permanently if equity drops 8% from the High Water Mark. |
| **Profit Target** | **10%** | The goal to reach to pass the evaluation phase. |
| **Risk Per Trade** | **0.25% - 0.50%** | Conservative sizing to allow for a string of losses without hitting daily limits. |

### Activation
To run in this mode, ensure your configuration uses the `PROP_EVAL` profile:
```python
# config/settings.py
DEFAULT_FIRM_PROFILE = "PROP_EVAL"
```
Or pass `risk_profile="PROP_EVAL"` when initializing the execution backend.

## 2. Kill-Switches

The execution engine (`mt5_demo.py`) has built-in kill-switches that enforce the risk limits defined above.

-   **Daily Kill-Switch**: Triggers when `(Daily Start Equity - Current Equity) >= 3%`.
-   **Global Kill-Switch**: Triggers when `(High Water Mark - Current Equity) >= 8%`.

**Behavior**:
-   When a kill-switch is triggered, **NEW ORDER SUBMISSIONS ARE BLOCKED**.
-   Existing positions are **NOT** automatically closed (to avoid panic exits during temporary wicks).
-   The system logs a `kill_switch_daily` or `kill_switch_global` event.

## 3. Behavioral Targets (Soft Limits)

Beyond hard risk limits, we monitor "soft targets" to ensure the bot behaves like a professional human trader and avoids HFT classifications.

### Strategy Targets

| Strategy | Trades/Day | SL (pips) | TP (pips) | Hold Time |
| :--- | :--- | :--- | :--- | :--- |
| **Trend (TF1)** | 2 - 5 | 20 - 35 | 35 - 70 | 2 - 6 hours |
| **Mean Reversion** | 1 - 4 | 15 - 25 | 10 - 40 | 30 - 90 mins |
| **London Breakout**| 0 - 2 | 10 - 30 | 20 - 60 | 1 - 3 hours |

### Monitoring
Run the sanity checker to verify recent behavior against these targets:
```bash
python scripts/run_sanity_check_recent_trades.py --hours 72
```
The script will flag violations with `WARN` (soft limit) or `FAIL` (hard limit).

## 4. Telemetry & Dashboard

The execution logs (`mt5_demo_exec_log.csv`) and status summary (`mt5_demo_exec_summary.json`) now include enriched metrics:

-   `daily_loss_pct`: Current daily drawdown %.
-   `total_dd_pct`: Current drawdown from High Water Mark %.
-   `eval_progress_pct`: Progress towards the 10% profit target.
-   `trades_today_count`: Number of trades executed today.

These metrics feed into the dashboard HUD to provide a real-time "Pass/Fail" status.

## 5. What This Means in English (Plain Language)

For a standard **$100,000 Evaluation Account**:

### 1. How much can I lose?
-   **Daily Limit ($3,000)**: You cannot lose more than $3,000 in a single day. If your equity drops by $3,000 from the day's starting balance, the bot stops trading for the day.
-   **Total Limit ($8,000)**: You cannot lose more than $8,000 from your highest recorded equity (High Water Mark). If you make $2,000 profit (Equity = $102,000), your new "fail level" is $93,840 ($102k - 8%).

### 2. How much does the bot risk per trade?
-   **Typical Risk**: 0.25% to 0.50% of the account balance.
-   **Dollar Amount**: ~$250 to $500 per trade.
-   **Why?**: This allows you to take 6-12 consecutive losses in a single day without hitting the daily limit, providing a massive safety buffer.

### 3. What should I expect to see?
-   **Trades Per Day**: 
    -   **Conservative**: 1-3 trades/day.
    -   **Aggressive**: 3-8 trades/day.
-   **Holding Time**: Trades usually last 1-4 hours. We avoid "scalping" (seconds/minutes) to stay compliant with all firm rules.
-   **Win Rate**: Expect ~40-55%. The edge comes from winning trades being larger than losing trades (Avg R > 1.5).

