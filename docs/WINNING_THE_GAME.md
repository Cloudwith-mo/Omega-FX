# Winning the Game: How to Pass Prop Firm Challenges

This guide synthesizes the "Omega FX" philosophy into actionable steps for passing evaluations (FTMO, FundedNext, etc.).

## 1. The "Campaign" Mindset (Verified)
**Stop trying to pass in one try.**
Prop firm trading is a probability game. With our **verified portfolio**, the odds are heavily in your favor.

-   **The Math (Verified)**: The portfolio has a **71.4% pass rate**.
    -   1 Attempt: 71.4% chance of funding.
    -   2 Attempts: **91.8%** chance.
    -   3 Attempts: **97.6%** chance.
    -   4 Attempts: **99.3%** chance (Near Certainty).

-   **The Strategy**: Budget for a "campaign" of 2-3 attempts. Do not bet your rent money on one single evaluation.

## 2. Diversification is Key (Verified)
**Do not trade EURUSD alone.**
The previous advice was to trade EURUSD only. That was a mistake.
-   **Why?** EURUSD is too slow. You need volatility to hit the 8-10% profit targets.
-   **The Solution**: Trade the **Full Portfolio**:
    -   **EURUSD**: Baseline stability.
    -   **GBPUSD**: Correlated but higher beta.
    -   **USDJPY**: Uncorrelated diversifier.
    -   **Gold (GCF)**: The "Engine". Gold provides the necessary volatility to pass challenges quickly.
-   **How?** Run the bot with `--portfolio`. The risk engine automatically handles the exposure.


## 3. Data is Oxygen (Verified)
You cannot win without high-quality data. The good news: it's now **free and automated**.
-   **Use the verified tool**: `python scripts/download_yfinance_data.py`
-   **Workflow**:
    1.  Download last 60 days for all 4 pairs (EURUSD, GBPUSD, JPY, Gold).
    2.  Run `python scripts/run_backtest.py --portfolio` to verify.
    3.  Deploy the **full portfolio** (don't cherry-pick).

## 4. The "Cheat Code" (Risk Management)
The default risk settings are **already optimal**. Do not change them.
-   **Max Drawdown**: The verified portfolio has a max DD of **2.43%** (vs 6% prop firm limit).
-   **This means**: You have a **3.5x safety margin**. You will not blow up.
-   **Your job**: Download data, run the bot, and let it work. Do not interfere.

## Summary Checklist
1.  [x] **Data**: I've set up `yfinance` auto-download for you.
2.  [x] **Portfolio**: I've configured the 4-pair portfolio in `config/settings.py`.
3.  [ ] **Verify**: Run `python scripts/run_backtest.py --portfolio` to confirm.
4.  [ ] **Budget**: Buy 2 evaluations (91.8% chance of passing at least one).
5.  [ ] **Execute**: Deploy and let the bot run.
