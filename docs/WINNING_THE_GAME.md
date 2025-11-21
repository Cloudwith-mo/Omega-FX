# Winning the Game: How to Pass Prop Firm Challenges

This guide synthesizes the "Omega FX" philosophy into actionable steps for passing evaluations (FTMO, FundedNext, etc.).

## 1. The "Campaign" Mindset
**Stop trying to pass in one try.**
Prop firm trading is a probability game, not a skill test of a single week.
-   **The Math**: If you have a strategy with a 40% pass rate (conservative), your odds of passing at least one of 4 accounts are **87%**.
-   **The Cost**: 4 evaluations cost ~$1,200. A single funded payout often exceeds $3,000.
-   **The Strategy**: Budget for a "campaign" of 3-5 attempts. Do not bet your rent money on one single evaluation.

## 2. Diversification is Key
**Do not trade EURUSD alone.**
The current repo defaults to EURUSD for simplicity, but "winning" requires a portfolio.
-   **Why?** If EURUSD ranges for 2 weeks, you fail due to time limits or lack of profit.
-   **What to add?**
    -   **GBPUSD**: Correlated but often moves when EUR lags.
    -   **XAUUSD (Gold)**: High volatility, great for catching the 3% profit bursts needed for passing.
    -   **USDJPY**: distinct driver (BoJ policy).
-   **How?** Run the bot on 3 pairs simultaneously with **lower risk per pair** (e.g., 0.3% risk per trade per pair instead of 1%).

## 3. Optimization & Parameter Tuning
The default settings are "safe" defaults. To win, you must tune them to current market conditions.
-   **SMA Lengths**: The default `20/50` crossover is generic. Test `10/30` for faster entries or `50/200` for major trends.
-   **ATR Multipliers**:
    -   Default: Stop = 1.5x ATR, TP = 3.0x ATR.
    -   **Optimization**: If markets are choppy, reduce TP to 2.0x ATR to bank profits sooner.

## 4. Data is Oxygen
You cannot win without high-quality data.
-   **Use the new tool**: `python scripts/download_yfinance_data.py`
-   **Workflow**:
    1.  Download last 60 days of data for EURUSD, GBPUSD, XAUUSD.
    2.  Run `scripts/run_backtest.py` on each.
    3.  Pick the 2 pairs performing best in the *last 30 days*.
    4.  Deploy those 2 pairs for your next challenge.

## 5. The "Cheat Code" (Risk Management)
Most traders fail because they oversize.
-   **The Rule**: Never risk more than 1% of your daily drawdown limit on a single trade.
-   **Example**:
    -   Daily Limit: $1,000 (on a $20k account).
    -   Max Risk Per Trade: $10 (which is 0.05% account risk, or 1% of the *limit*).
    -   *Omega FX defaults are already conservative, stick to them!*

## Summary Checklist
1.  [ ] **Data**: Download fresh H1 data for 3+ pairs.
2.  [ ] **Select**: Pick the top 2 performing pairs from recent backtests.
3.  [ ] **Budget**: Buy 2 cheap evaluations instead of 1 expensive one.
4.  [ ] **Execute**: Run the bot 24/7 (VPS recommended).
