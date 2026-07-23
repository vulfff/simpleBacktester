from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from events import SignalEvent
from tickdata import TickData


class Strategy:
    def on_tick(self, tick: TickData) -> List[SignalEvent]:
        return []


class StrategyConfig(BaseModel):
    pass


def list_strategies() -> List[Dict[str, Any]]:
    from strategy_rules import RuleSetStrategyConfig

    return [
        {
            "name": "rule_set",
            "config_schema": RuleSetStrategyConfig.model_json_schema(),
        }
    ]


def create_strategy(name: str, config: Optional[Dict[str, Any]] = None) -> Strategy:
    if name != "rule_set":
        raise KeyError(f"Unknown strategy: {name}")

    from strategy_rules import RuleSet, RuleSetStrategy, RuleSetStrategyConfig

    cfg = RuleSetStrategyConfig.model_validate(config or {})
    return RuleSetStrategy(RuleSet.from_dict(cfg.rule_set))
