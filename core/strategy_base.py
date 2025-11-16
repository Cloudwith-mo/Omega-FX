"""Base Strategy interface used by the execution engine.

The goal is to decouple *what* generates trade ideas from the
backtesting / risk engine that enforces prop rules.  Strategies expose
two capabilities:

```
required_features() -> {timeframe: [feature names]}
    Declares which features must be present in the data payload that is
    sent to ``on_bar``.

on_bar(timestamp, features_by_tf) -> dict
    Consumes the pre-computed feature dictionaries (per timeframe) and
    returns a signal dict containing at least ``action`` and
    ``risk_tier``.
```

Future strategy implementations (Ω-FX M15, H4 trend followers, etc.)
will inherit from :class:`Strategy` and can be mixed-and-matched by the
backtester without changing the engine logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping


class Strategy(ABC):
    """Abstract base class for trade-generating strategies."""

    #: Human-friendly identifier; subclasses should override this.
    name: str = "strategy"

    @abstractmethod
    def required_features(self) -> Dict[str, list[str]]:
        """Return the feature requirements per timeframe.

        The engine will ensure these features exist before calling
        :meth:`on_bar`.
        """

    @abstractmethod
    def on_bar(self, timestamp: Any, features_by_tf: Mapping[str, Any]) -> Dict[str, Any]:
        """Produce a trading signal for the current bar.

        The returned dict must include at least ``action`` (``long``,
        ``short`` or ``flat``) and ``risk_tier`` (``A``, ``B``,
        ``UNKNOWN`` or ``C``).  Additional metadata can be included in a
        ``meta`` sub-dictionary for debugging or analytics.
        """

