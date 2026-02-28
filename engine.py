from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List

from actionmanager import ActionManager
from eventqueue import EventQueue
from events import Event, FillEvent, OrderEvent, SignalEvent, TickEvent
from fill_model import FillModel
from portfolio import Portfolio
from strategy import Strategy
from tickdata import TickData


@dataclass
class BacktestEngine:
    data_feed:      Iterable[TickData]
    strategy:       Strategy
    action_manager: ActionManager
    portfolio:      Portfolio
    fill_model:     FillModel = field(default_factory=FillModel)

    # ── execution options ─────────────────────────────────────────────────────
    # "fixed"  – use quantity from the signal (rule.quantity)
    # "all_in" – compute quantity from all available cash × leverage
    #            (all_in also implies no-rebuy: entry signals are blocked
    #             while a position is already held)
    sizing_mode:      str   = "fixed"
    leverage:         float = 1.0
    # "none" | "pct" (% of trade value) | "flat" (fixed $ per fill)
    commission_mode:  str   = "none"
    commission_value: float = 0.0
    # True  = fractional units allowed (crypto)
    # False = whole units only; qty is floored and orders < 1 unit are skipped
    allow_fractional: bool  = False
    verbose:          bool  = True

    def __post_init__(self) -> None:
        self.events      = EventQueue()
        self._last_tick: dict[str, TickData] = {}
        self._tick_count = 0
        self._fill_count = 0

        # Orders queued at bar close → filled at next bar's open
        self._pending_orders: List[OrderEvent] = []

        # Equity curve: one snapshot per bar
        self._equity_curve: List[dict] = []

        # Accumulated warnings from fill model
        self._fill_warnings: List[str] = []

        # All signals that fired; blocked=True means the all_in no-rebuy
        # guard prevented the signal from becoming an order
        self._signal_log: List[dict] = []

        # Give the strategy a reference to the portfolio so that
        # exit conditions (P&L-based, time-based) can query it.
        if hasattr(self.strategy, "_portfolio"):
            self.strategy._portfolio = self.portfolio

    def _dbg(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    # ── main loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        for tick in self.data_feed:
            # 1. Fill yesterday's pending orders at this bar's open price
            self._fill_pending_at_open(tick)

            # 2. Put a tick event and drain (strategy evaluation + order queueing)
            self.events.put(TickEvent(tick=tick))
            self._drain_events()
            self._tick_count += 1

            # 3. Record equity snapshot after all processing for this bar
            self._record_equity(tick)
        if self.verbose:
            print(
                f"[ENGINE] Done — {self._tick_count} bars, "
                f"{self._fill_count} fills, "
                f"{len(self._signal_log)} signals"
            )

    def _drain_events(self) -> None:
        while not self.events.empty():
            event = self.events.get()
            if event is None:
                return
            self._handle_event(event)

    def _handle_event(self, event: Event) -> None:
        if isinstance(event, TickEvent):   self._handle_tick(event);   return
        if isinstance(event, SignalEvent): self._handle_signal(event); return
        if isinstance(event, OrderEvent):  self._handle_order(event);  return
        if isinstance(event, FillEvent):   self._handle_fill(event);   return

    # ── event handlers ───────────────────────────────────────────────────────

    def _handle_tick(self, event: TickEvent) -> None:
        tick = event.tick
        self._last_tick[tick.name] = tick
        mid = (tick.bid + tick.ask) / 2 if tick.ask else tick.bid
        self.portfolio.update_market_price(tick.name, mid)

        # Keep strategy in sync with live portfolio state so exit conditions
        # (P&L-based, time-based) and position guards can query it.
        self.strategy._portfolio = self.portfolio

        for signal in self.strategy.on_tick(tick):
            self.events.put(signal)

    def _handle_signal(self, event: SignalEvent) -> None:
        # Capture timestamp from the most-recently-seen tick for this symbol
        tick = self._last_tick.get(event.symbol)
        tick_time = tick.time.isoformat() if tick else ""

        # All-in mode implies no-rebuy: block new entry signals while a
        # position is already held so the portfolio stays fully invested
        blocked = False
        if self.sizing_mode == "all_in" and event.action in ("buy", "short"):
            pos = self.portfolio.positions.get(event.symbol, 0.0)
            if abs(pos) > 1e-9:
                blocked = True
            elif self.portfolio.cash <= 0:
                blocked = True

        if not blocked:
            self._signal_log.append({
                "t":       tick_time,
                "symbol":  event.symbol,
                "action":  event.action,
                "blocked": blocked,
            })
        status = "BLOCKED" if blocked else "SIGNAL"
        self._dbg(f"[{status}] {tick_time} | {event.symbol} {event.action.upper()}")

        if blocked:
            return
        for order in self.action_manager.on_signal(event):
            self.events.put(order)

    def _handle_order(self, event: OrderEvent) -> None:
        """Queue the order for execution at the next bar's open."""
        self._pending_orders.append(event)

    def _handle_fill(self, event: FillEvent) -> None:
        self.portfolio.apply_fill(
            name=event.symbol,
            action=event.action,
            quantity=event.quantity,
            price=event.price,
            commission=event.commission,
            time=event.time.isoformat() if event.time else "",
        )
        self._fill_count += 1

    # ── next-bar-open fill ────────────────────────────────────────────────────

    def _fill_pending_at_open(self, tick: TickData) -> None:
        """
        Fill all queued orders at this bar's open price using the fill model.
        Called at the very start of each bar before strategy evaluation.
        """
        if not self._pending_orders:
            return

        orders_to_process = self._pending_orders
        self._pending_orders = []

        for order in orders_to_process:
            # ── All-in sizing: override quantity from portfolio state ──────────
            if self.sizing_mode == "all_in":
                if order.action in ("buy", "short"):
                    # Guard: if a previous order in this batch already opened a
                    # position for this symbol, skip the duplicate entry
                    existing_pos = self.portfolio.positions.get(order.symbol, 0.0)
                    if abs(existing_pos) > 1e-9:
                        continue
                    base_price = tick.open if tick.open > 0 else (
                        tick.ask if order.action == "buy" else tick.bid
                    )
                    available_cash = max(0.0, self.portfolio.cash) * self.leverage
                    computed_qty = available_cash / base_price if base_price > 0 else 0.0
                    if computed_qty <= 1e-9:
                        continue   # no cash available – skip this order
                    order = OrderEvent(
                        symbol=order.symbol,
                        action=order.action,
                        quantity=computed_qty,
                    )
                elif order.action == "sell":
                    # Close entire long position
                    pos = self.portfolio.positions.get(order.symbol, 0.0)
                    qty = max(0.0, pos)
                    if qty <= 1e-9:
                        continue
                    order = OrderEvent(symbol=order.symbol, action=order.action, quantity=qty)
                elif order.action == "cover":
                    # Close entire short position
                    pos = self.portfolio.positions.get(order.symbol, 0.0)
                    qty = max(0.0, -pos)
                    if qty <= 1e-9:
                        continue
                    order = OrderEvent(symbol=order.symbol, action=order.action, quantity=qty)

            # ── Fractional share guard ────────────────────────────────────────
            if not self.allow_fractional:
                floored = math.floor(order.quantity)
                if floored < 1:
                    continue   # less than 1 whole unit – skip
                if floored != order.quantity:
                    order = OrderEvent(
                        symbol=order.symbol,
                        action=order.action,
                        quantity=float(floored),
                    )

            filled_qty, fill_price, unfilled_qty, warnings = self.fill_model.compute_fill(
                order=order,
                tick=tick,
                use_open=True,
            )
            self._fill_warnings.extend(warnings)

            # ── Commission ────────────────────────────────────────────────────
            commission = 0.0
            if filled_qty > 0:
                if self.commission_mode == "pct":
                    commission = filled_qty * fill_price * (self.commission_value / 100.0)
                elif self.commission_mode == "flat":
                    commission = self.commission_value

            if filled_qty > 0:
                fill = FillEvent(
                    symbol=order.symbol,
                    action=order.action,
                    quantity=filled_qty,
                    price=fill_price,
                    commission=commission,
                    time=tick.time,
                )
                self._handle_fill(fill)
                self._dbg(
                    f"[TRADE]  {tick.time.isoformat()[:10]} | {order.symbol} "
                    f"{order.action.upper()} {filled_qty:.4f} @ {fill_price:.4f}"
                    + (f"  commission=${commission:.2f}" if commission else "")
                )

            if unfilled_qty > 0:
                self._fill_warnings.append(
                    f"Order for {order.symbol} ({order.action} {order.quantity}) "
                    f"was only partially filled: {filled_qty:.4f} filled, "
                    f"{unfilled_qty:.4f} unfilled (insufficient liquidity)."
                )

    # ── equity curve ─────────────────────────────────────────────────────────

    def _record_equity(self, tick: TickData) -> None:
        self._equity_curve.append({
            "t":           tick.time.isoformat(),
            "equity":      round(self.portfolio.total_value(), 4),
            "cash":        round(self.portfolio.cash, 4),
            "asset_value": round(self.portfolio.asset_value, 4),
            "price":       round(tick.bid, 4),
        })
