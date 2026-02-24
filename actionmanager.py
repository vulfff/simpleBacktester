from __future__ import annotations

from dataclasses import dataclass
from typing import List

from events import OrderEvent, SignalEvent

# Canonical action names accepted by Portfolio.apply_fill
_VALID_ACTIONS = {"buy", "sell", "short", "cover"}

# Aliases the frontend / strategy might emit
_ACTION_ALIASES = {
    "buy":   "buy",
    "long":  "buy",
    "sell":  "sell",
    "short": "short",
    "cover": "cover",
    "exit":  "sell",   # generic exit from long
}


@dataclass
class ActionManager:
    default_quantity: float = 1.0

    def on_signal(self, signal: SignalEvent) -> List[OrderEvent]:
        action = self._normalize(signal.action)
        quantity = signal.quantity if signal.quantity > 0 else self.default_quantity
        return [OrderEvent(symbol=signal.symbol, action=action, quantity=quantity)]

    @staticmethod
    def _normalize(action: str) -> str:
        key = action.lower().strip()
        result = _ACTION_ALIASES.get(key)
        if result is None:
            raise ValueError(
                f"Unknown action {action!r}. Expected one of: "
                + ", ".join(sorted(_ACTION_ALIASES))
            )
        return result