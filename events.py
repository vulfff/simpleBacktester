from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from tickdata import TickData


class Event:
    """Base event type."""


@dataclass(frozen=True)
class TickEvent(Event):
    tick: TickData


@dataclass(frozen=True)
class SignalEvent(Event):
    symbol: str
    action: str  # "buy" or "sell"
    quantity: float = 1.0


@dataclass(frozen=True)
class OrderEvent(Event):
    symbol: str
    action: str  # "buy" or "sell"
    quantity: float


@dataclass(frozen=True)
class FillEvent(Event):
    symbol: str
    action: str  # "buy" or "sell"
    quantity: float
    price: float
    commission: float = 0.0
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
