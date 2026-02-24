from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Trade:
    symbol:   str
    action:   str   # buy | sell | short | cover
    quantity: float
    price:    float
    commission: float = 0.0


@dataclass
class Portfolio:
    starting_cash: float = 0.0
    cash:          float = 0.0
    asset_value:   float = 0.0

    # Long positions: symbol → quantity (positive = long, negative = short)
    positions:   Dict[str, float] = field(default_factory=dict)
    last_prices: Dict[str, float] = field(default_factory=dict)

    # Book-keeping
    realized_pnl:   float = 0.0
    unrealized_pnl: float = 0.0
    trade_log:      List[Trade] = field(default_factory=list)

    # ── derived ─────────────────────────────────────────────────────────────

    def total_value(self) -> float:
        """Cash + current market value of all positions."""
        return self.cash + self.asset_value

    def update_market_price(self, name: str, price: float) -> None:
        """Called on every tick to keep asset_value current."""
        if price and price == price:   # guard NaN/zero
            self.last_prices[name] = price
        # asset_value = Σ qty * price  (negative qty for shorts = negative value,
        # which correctly reduces total_value when we're short)
        self.asset_value = sum(
            qty * self.last_prices.get(sym, 0.0)
            for sym, qty in self.positions.items()
        )

    # ── trade execution ──────────────────────────────────────────────────────

    def apply_fill(
        self,
        name:       str,
        action:     str,
        quantity:   float,
        price:      float,
        commission: float = 0.0,
    ) -> None:
        """
        Apply a completed fill to the portfolio.

        action semantics
        ────────────────
        buy    – open/add to a long position; debit cash
        sell   – close/reduce a long position; credit cash
        short  – open/add to a short position; credit cash (borrow & sell)
        cover  – close/reduce a short position; debit cash (buy back)
        """
        action = action.lower()
        if action not in {"buy", "sell", "short", "cover"}:
            raise ValueError(f"Unsupported action: {action!r}")

        gross = price * quantity

        if action == "buy":
            self.positions[name] = self.positions.get(name, 0.0) + quantity
            self.cash -= gross + commission

        elif action == "sell":
            prev_qty = self.positions.get(name, 0.0)
            sold     = min(quantity, max(prev_qty, 0.0))   # can't sell more than held
            if sold <= 0:
                return
            self.positions[name] = prev_qty - sold
            self.cash += sold * price - commission
            # Clean up dust positions
            if abs(self.positions[name]) < 1e-9:
                del self.positions[name]

        elif action == "short":
            # Sell shares we don't own; position goes negative
            self.positions[name] = self.positions.get(name, 0.0) - quantity
            self.cash += gross - commission   # receive proceeds

        elif action == "cover":
            # Buy back shorted shares
            prev_qty  = self.positions.get(name, 0.0)
            cover_qty = min(quantity, max(-prev_qty, 0.0))  # can't cover more than shorted
            if cover_qty <= 0:
                return
            self.positions[name] = prev_qty + cover_qty
            self.cash -= cover_qty * price + commission
            if abs(self.positions[name]) < 1e-9:
                del self.positions[name]

        self.trade_log.append(Trade(name, action, quantity, price, commission))
        self.update_market_price(name, price)

    # ── repr ─────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Portfolio(cash={self.cash:.2f}, asset_value={self.asset_value:.2f}, "
            f"total={self.total_value():.2f}, positions={self.positions})"
        )