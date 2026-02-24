from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from events import SignalEvent
from tickdata import TickData


class Strategy:
    def on_tick(self, tick: TickData) -> List[SignalEvent]:
        return []


class StrategyConfig(BaseModel):
    pass


@dataclass(frozen=True)
class StrategySpec:
    name: str
    config_model: Type[StrategyConfig]
    factory: Callable[[StrategyConfig], Strategy]


STRATEGY_REGISTRY: Dict[str, StrategySpec] = {}


def register_strategy(name: str, config_model: Type[StrategyConfig], factory: Callable[[StrategyConfig], Strategy]) -> None:
    STRATEGY_REGISTRY[name] = StrategySpec(name=name, config_model=config_model, factory=factory)


def list_strategies() -> List[Dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "config_schema": spec.config_model.model_json_schema(),
        }
        for spec in STRATEGY_REGISTRY.values()
    ]


def create_strategy(name: str, config: Optional[Dict[str, Any]] = None) -> Strategy:
    if name not in STRATEGY_REGISTRY:
        raise KeyError(f"Unknown strategy: {name}")
    spec = STRATEGY_REGISTRY[name]
    validated = spec.config_model.model_validate(config or {})
    return spec.factory(validated)


class MovingAverageCrossConfig(StrategyConfig):
    short_window: int = Field(default=5, ge=1)
    long_window: int = Field(default=20, ge=2)
    quantity: float = Field(default=1.0, gt=0)


@dataclass
class MovingAverageCrossStrategy(Strategy):
    short_window: int = 5
    long_window: int = 20
    quantity: float = 1.0
    _prices: List[float] = None

    def __post_init__(self) -> None:
        if self._prices is None:
            self._prices = []

    def on_tick(self, tick: TickData) -> List[SignalEvent]:
        self._prices.append(tick.bid)
        if len(self._prices) < self.long_window:
            return []

        short_avg = sum(self._prices[-self.short_window:]) / self.short_window
        long_avg = sum(self._prices[-self.long_window:]) / self.long_window

        if short_avg > long_avg:
            return [SignalEvent(symbol=tick.name, action="buy", quantity=self.quantity)]
        if short_avg < long_avg:
            return [SignalEvent(symbol=tick.name, action="sell", quantity=self.quantity)]

        return []


class PriceChangeConfig(StrategyConfig):
    quantity: float = Field(default=1.0, gt=0)


@dataclass
class SimplePriceChangeStrategy(Strategy):
    quantity: float = 1.0
    last_bid: Optional[float] = None

    def on_tick(self, tick: TickData) -> List[SignalEvent]:
        if self.last_bid is None:
            self.last_bid = tick.bid
            return []

        action = "buy" if tick.bid > self.last_bid else "sell"
        self.last_bid = tick.bid
        return [SignalEvent(symbol=tick.name, action=action, quantity=self.quantity)]


register_strategy(
    name="moving_average_cross",
    config_model=MovingAverageCrossConfig,
    factory=lambda cfg: MovingAverageCrossStrategy(
        short_window=cfg.short_window,
        long_window=cfg.long_window,
        quantity=cfg.quantity,
    ),
)

register_strategy(
    name="price_change",
    config_model=PriceChangeConfig,
    factory=lambda cfg: SimplePriceChangeStrategy(quantity=cfg.quantity),
)