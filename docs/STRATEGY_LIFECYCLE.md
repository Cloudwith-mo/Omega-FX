# Strategy Lifecycle & Interface

## 1. Strategy Interface

All trade-generating ideas inherit from `core.strategy_base.Strategy`:

```python
class Strategy(ABC):
    name = "strategy"

    def required_features(self) -> dict[str, list[str]]:
        ...

    def on_bar(self, timestamp, features_by_tf) -> dict:
        ...
```

- `required_features()` declares which pre-computed features are needed
  per timeframe (e.g. M15 indicators, H1 context).
- `on_bar()` receives those features and returns a signal dict with
  `action` (`long` / `short` / `flat`), `risk_tier` (`A` / `B` /
  `UNKNOWN` / `C`), and optional metadata.

## 2. Promotion Pipeline

Every strategy follows the same gauntlet before it is allowed to run
real capital:

1. **Lab** – research notebooks, rough prototyping.
2. **Backtest** – plug into the backtester through the Strategy
   interface and validate historical stats.
3. **Robustness** – sensitivity, multi-period checks, out-of-sample
   evaluation.
4. **Prop Sim** – run via `run_challenge_sim.py` to ensure it respects
   prop rules.
5. **Demo** – execute on free trials / demo accounts to match backtests.
6. **Small Live** – deploy on a small funded account with lower risk.
7. **Scaled Live** – production once the prior stages succeed.

## 3. Current Status

- `OmegaM15Strategy` (Ω-FX M15 with H1 context) is Strategy #1 on these
  rails.  It currently powers the minimal FTMO preset.
- Future strategies (e.g. H4 trend, BTC overlays) should inherit from
  the same interface and walk through the lifecycle before touching real
  capital.

