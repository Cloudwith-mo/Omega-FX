# Pip Handling in Omega FX

## What is a "Pip"?

A **pip** (percentage in point) is the smallest price movement unit in forex trading. The size varies by symbol:

| Symbol Family | Pip Size | Example |
|--------------|----------|---------|
| **Major Forex** (EURUSD, GBPUSD) | 0.0001 | 1.1000 → 1.1001 = 1 pip |
| **JPY Pairs** (USDJPY, EURJPY) | 0.01 | 150.00 → 150.01 = 1 pip |
| **Gold** (XAUUSD, GCF) | 0.01 | 2000.00 → 2000.01 = 1 pip |

## Helper Functions

All pip/price conversions **must** use symbol-aware helpers from [`core/risk_utils.py`](file:///Users/muhammadadeyemi/Trading%20Bot/Omega-FX/core/risk_utils.py).

### `pip_size(symbol: str) -> float`

Returns the pip size for a symbol.

```python
from core.risk_utils import pip_size

pip_size("EURUSD")  # 0.0001
pip_size("USDJPY")  # 0.01
pip_size("XAUUSD")  # 0.01
```

### `pips_to_price(pips: float, symbol: str) -> float`

Converts pip distance to price distance.

```python
from core.risk_utils import pips_to_price

pips_to_price(20, "EURUSD")  # 0.0020
pips_to_price(20, "USDJPY")  # 0.20
pips_to_price(100, "XAUUSD")  # 1.00
```

### `price_to_pips(price_distance: float, symbol: str) -> float`

Converts price distance to pips.

```python
from core.risk_utils import price_to_pips

price_to_pips(0.0020, "EURUSD")  # 20.0
price_to_pips(0.20, "USDJPY")    # 20.0
price_to_pips(1.50, "XAUUSD")    # 150.0
```

### `calculate_sl_tp_prices(...)`

Calculates SL/TP prices from entry price and pip distances.

```python
from core.risk_utils import calculate_sl_tp_prices

sl, tp = calculate_sl_tp_prices(
    entry_price=1.1000,
    direction="long",
    stop_pips=20,
    tp_pips=40,
    symbol="EURUSD"
)
# sl = 1.0980, tp = 1.1040
```

## When to Use Which Helper

| Scenario | Function | Example |
|----------|----------|---------|
| **Get symbol pip size** | `pip_size()` | Validating strategy parameters |
| **Convert pips → price** | `pips_to_price()` | Calculating SL/TP from ATR-based pips |
| **Convert price → pips** | `price_to_pips()` | Logging/reporting stop distances |
| **Calculate SL/TP levels** | `calculate_sl_tp_prices()` | Order submission |

## ❌ Anti-Patterns

**Never** hardcode pip conversions:

```python
# ❌ WRONG - assumes all symbols have 4 decimals
stop_price = entry - (stop_pips / 10_000)

# ✅ CORRECT - symbol-aware
from core.risk_utils import pips_to_price
stop_price = entry - pips_to_price(stop_pips, symbol)
```

**Never** use magic numbers for pip sizes:

```python
# ❌ WRONG - breaks for JPY pairs and Gold
atr_pips = atr_value / 0.0001

# ✅ CORRECT - symbol-aware
from core.risk_utils import price_to_pips
atr_pips = price_to_pips(atr_value, symbol)
```

**Never** hardcode pip values for risk calculations:

```python
# ❌ WRONG - assumes $10/pip for all symbols
risk_usd = stop_pips * 10 * lot_size

# ✅ CORRECT - symbol-aware
from core.position_sizing import get_symbol_meta
meta = get_symbol_meta(symbol)
risk_usd = stop_pips * meta.pip_value_per_standard_lot * lot_size
```

## Symbol Metadata

Symbol pip sizes and pip values are defined in [`core/position_sizing.py`](file:///Users/muhammadadeyemi/Trading%20Bot/Omega-FX/core/position_sizing.py):

```python
SYMBOL_METADATA = {
    "EURUSD": SymbolMeta(
        "EURUSD", 
        pip_value_per_standard_lot=10.0,  # $10 per pip
        pip_size=0.0001  # 4 decimals
    ),
    "USDJPY": SymbolMeta(
        "USDJPY",
        pip_value_per_standard_lot=9.0,  # ~$9 per pip (varies with JPY rate)
        pip_size=0.01  # 2 decimals
    ),
    "XAUUSD": SymbolMeta(
        "XAUUSD",
        pip_value_per_standard_lot=1.0,  # $1 per pip (for 1 oz contract)
        pip_size=0.01  # 2 decimals
    ),
}
```

To add a new symbol, update this dictionary with the correct `pip_size` and `pip_value_per_standard_lot`.

## Common Scenarios

### Strategy Signal Generation

```python
from core.risk_utils import price_to_pips

# Calculate ATR in pips
atr_pips = price_to_pips(atr_value, symbol)

# Set stops as multiple of ATR
stop_distance_pips = 1.5 * atr_pips  # Store as pips
tp_distance_pips = 3.0 * atr_pips
```

### Order Execution

```python
from core.risk_utils import pips_to_price

# Convert pip distances to prices for order placement
stop_distance = pips_to_price(signal.stop_distance_pips, symbol)
tp_distance = pips_to_price(signal.take_profit_distance_pips, symbol)

if direction == "long":
    stop_loss = entry_price - stop_distance
    take_profit = entry_price + tp_distance
else:
    stop_loss = entry_price + stop_distance
    take_profit = entry_price - tp_distance
```

### Logging & Reporting

```python
from core.risk_utils import price_to_pips

# Convert price distances back to pips for human-readable logs
sl_distance = abs(entry_price - stop_loss)
sl_pips = price_to_pips(sl_distance, symbol)

print(f"Trade: {symbol} SL at {sl_pips:.1f} pips")
```

## Testing

All pip handling code should be tested across multiple symbol types:

```python
def test_my_function():
    # Test with 4-decimal pair
    result_eur = my_function("EURUSD", ...)
    
    # Test with 2-decimal JPY
    result_jpy = my_function("USDJPY", ...)
    
    # Test with Gold
    result_xau = my_function("XAUUSD", ...)
```

This ensures code works correctly regardless of symbol decimal places.
