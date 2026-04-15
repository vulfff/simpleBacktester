"""
fill_model.py  –  Realistic, semi-stochastic order fill simulation.

Model
-----
For each bar:
  available_liquidity = bar.volume × participation_rate
  filled_qty          = min(order_qty, available_liquidity)
  price_impact        = (filled_qty / bar.volume) × price_impact_factor × base_price
  slippage            = Gauss(0, slippage_sigma × base_price)
  fill_price          = base_price ± price_impact ± slippage   (adverse direction)

When bar.volume == 0 the model falls back to zero-impact immediate fill at close
(equivalent to the old naive engine behaviour) and records a warning.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from events import OrderEvent, FillEvent
from tickdata import TickData


@dataclass
class FillModel:
    # ── parameters ───────────────────────────────────────────────────────────
    participation_rate: float  = 0.25    # max fraction of bar volume we can consume
    price_impact_factor: float = 0.001   # price impact at 100 % participation (0.1 %)
    slippage_sigma: float      = 0.0003  # std dev of stochastic slippage as fraction of price
    seed: Optional[int]        = None    # set for reproducible runs

    # ── internal ─────────────────────────────────────────────────────────────
    _rng: random.Random = field(init=False, repr=False)
    _no_volume_warned: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # ── public API ───────────────────────────────────────────────────────────

    def compute_fill(
        self,
        order: OrderEvent,
        tick: TickData,
        use_open: bool = False,
    ) -> tuple[float, float, float, list[str]]:
        """
        Compute fill details for an order against a bar.

        Parameters
        ----------
        order     : the order to fill
        tick      : the bar being used for execution
        use_open  : if True, use tick.open as base price (next-bar-open fills);
                    if False, use tick.close (same-bar fills)

        Returns
        -------
        (filled_qty, fill_price, unfilled_qty, warnings)
        """
        warnings: list[str] = []
        is_buy = order.action in ("buy", "cover")

        # Base price: open for next-bar-open fills, otherwise close
        if use_open:
            base = tick.open if tick.open > 0 else tick.close
        else:
            base = tick.close

        if base <= 0:
            base = max(tick.close, 1e-9)

        # ── liquidity ────────────────────────────────────────────────────────
        if tick.volume <= 0:
            # No volume data – fall back to full fill, no impact
            if not self._no_volume_warned:
                warnings.append(
                    "Bar volume is 0; fill model falling back to full fill at close. "
                    "Supply volume data for realistic liquidity simulation."
                )
                self._no_volume_warned = True
            return order.quantity, base, 0.0, warnings

        available_liquidity = tick.volume * self.participation_rate
        filled_qty = min(order.quantity, available_liquidity)
        unfilled_qty = order.quantity - filled_qty

        # ── price impact (linear in participation) ────────────────────────────
        participation = filled_qty / tick.volume   # 0 .. participation_rate
        impact = participation * self.price_impact_factor * base

        # ── stochastic slippage ───────────────────────────────────────────────
        slippage = self._rng.gauss(0.0, self.slippage_sigma * base)

        # ── final fill price (adverse: buys pay more, sells receive less) ─────
        if is_buy:
            fill_price = base + impact + abs(slippage)
        else:
            fill_price = base - impact - abs(slippage)

        fill_price = max(fill_price, 1e-9)

        return filled_qty, fill_price, unfilled_qty, warnings

    def to_dict(self) -> dict:
        return {
            "participation_rate":  self.participation_rate,
            "price_impact_factor": self.price_impact_factor,
            "slippage_sigma":      self.slippage_sigma,
            "seed":                self.seed,
        }
