from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

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


