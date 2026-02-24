from dataclasses import dataclass
from typing import List

from events import OrderEvent, SignalEvent


@dataclass
class ActionManager:
    default_quantity: float = 1.0

    def on_signal(self, signal: SignalEvent) -> List[OrderEvent]:
        action = self._normalize_action(signal.action)
        quantity = signal.quantity if signal.quantity > 0 else self.default_quantity
        return [
            OrderEvent(
                symbol=signal.symbol,
                action=action,
                quantity=quantity,
            )
        ]

    @staticmethod
    def _normalize_action(action: str) -> str:
        action_lower = action.lower()
        if action_lower in {"buy", "long"}:
            return "buy"
        if action_lower in {"sell", "short"}:
            return "sell"
        raise ValueError(f"Unsupported action: {action}")
    



