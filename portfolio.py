from dataclasses import dataclass, field
from typing import Dict

@dataclass
class Portfolio:
    starting_cash: float = 0.0
    cash: float = 0.0
    asset_value: float = 0.0
    unrealized_gains: float = 0.0
    realized_gains: float = 0.0
    positions: Dict[str, float] = field(default_factory=dict)
    last_prices: Dict[str, float] = field(default_factory=dict)

    def total_value(self) -> float:
        return self.cash + self.asset_value

    def update_market_price(self, name: str, price: float) -> None:
        self.last_prices[name] = price
        self.asset_value = sum(
            qty * self.last_prices.get(sym, 0.0) for sym, qty in self.positions.items()
        )

    def apply_fill(self, name: str, action: str, quantity: float, price: float, commission: float = 0.0) -> None:
        action_lower = action.lower()
        if action_lower not in {"buy", "sell"}:
            raise ValueError(f"Unsupported action: {action}")

        direction = 1.0 if action_lower == "buy" else -1.0
        self.positions[name] = self.positions.get(name, 0.0) + direction * quantity

        cash_delta = price * quantity + commission
        if action_lower == "buy":
            self.cash -= cash_delta
        else:
            self.cash += price * quantity - commission

        self.update_market_price(name, price)

    def __repr__(self) -> str:
        return (
            f"Portfolio(starting_cash={self.starting_cash}, cash={self.cash}, "
            f"asset_value={self.asset_value}, unrealized_gains={self.unrealized_gains}, "
            f"realized_gains={self.realized_gains}, positions={self.positions}, "
            f"last_prices={self.last_prices})"
        )