from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from actionmanager import ActionManager
from eventqueue import EventQueue
from events import Event, FillEvent, OrderEvent, SignalEvent, TickEvent
from portfolio import Portfolio
from strategy import Strategy
from tickdata import TickData


@dataclass
class BacktestEngine:
    data_feed:      Iterable[TickData]
    strategy:       Strategy
    action_manager: ActionManager
    portfolio:      Portfolio

    def __post_init__(self) -> None:
        self.events      = EventQueue()
        self._last_tick: dict[str, TickData] = {}
        self._tick_count = 0
        self._fill_count = 0

        # Give the strategy a reference to the portfolio so that
        # exit conditions (P&L-based, time-based) can query it.
        if hasattr(self.strategy, "_portfolio"):
            self.strategy._portfolio = self.portfolio

    def run(self) -> None:
        for tick in self.data_feed:
            self.events.put(TickEvent(tick=tick))
            self._drain_events()
            self._tick_count += 1

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

    def _handle_tick(self, event: TickEvent) -> None:
        tick = event.tick
        self._last_tick[tick.name] = tick
        mid = (tick.bid + tick.ask) / 2 if tick.ask else tick.bid
        self.portfolio.update_market_price(tick.name, mid)

        for signal in self.strategy.on_tick(tick):
            self.events.put(signal)

    def _handle_signal(self, event: SignalEvent) -> None:
        for order in self.action_manager.on_signal(event):
            self.events.put(order)

    def _handle_order(self, event: OrderEvent) -> None:
        tick = self._last_tick.get(event.symbol)
        if tick is None:
            return
        # Use ask for buys/covers, bid for sells/shorts
        price = tick.ask if event.action in ("buy", "cover") else tick.bid
        fill = FillEvent(
            symbol=event.symbol,
            action=event.action,
            quantity=event.quantity,
            price=price,
        )
        self.events.put(fill)

    def _handle_fill(self, event: FillEvent) -> None:
        self.portfolio.apply_fill(
            name=event.symbol,
            action=event.action,
            quantity=event.quantity,
            price=event.price,
            commission=event.commission,
        )
        self._fill_count += 1