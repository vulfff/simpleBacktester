"""
Rule-based strategy framework.

Architecture
============

Operand  – anything that produces a numeric value at a point in time
           (price fields, indicators, constants, historical lookbacks)
Condition – compares two Operands using an operator (>, <, cross, etc.)
Rule      – a named Condition assigned a role (entry_long, exit_long, …)
RuleSet   – ordered list of Rules for a single strategy slot
Strategy  – evaluates a RuleSet against incoming ticks, emitting signals

Serialisation
=============
Every object can round-trip through a plain dict so it can be stored in
the DB as JSON and reconstructed without eval().
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

from events import SignalEvent
from tickdata import TickData


# ---------------------------------------------------------------------------
# 1. Roles
# ---------------------------------------------------------------------------

class RuleRole(str, Enum):
    ENTRY_LONG   = "entry_long"    # open / add to long position
    EXIT_LONG    = "exit_long"     # close / reduce long position
    ENTRY_SHORT  = "entry_short"   # open / add to short position
    EXIT_SHORT   = "exit_short"    # close / reduce short position


# ---------------------------------------------------------------------------
# 2. Timing filter
# ---------------------------------------------------------------------------

class TimingMode(str, Enum):
    EVERY_TICK = "every_tick"   # fire whenever condition is true
    ON_CHANGE  = "on_change"   # fire only on the tick the condition turns true


# ---------------------------------------------------------------------------
# 3. Operands  (value producers)
# ---------------------------------------------------------------------------

class Operand(ABC):
    """Returns a float (or NaN) given the current price series."""

    @abstractmethod
    def value(self, series: "PriceSeries") -> float:
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        ...

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Operand":
        t = d["type"]
        cls = _OPERAND_REGISTRY.get(t)
        if cls is None:
            raise KeyError(f"Unknown operand type: {t!r}")
        return cls._from_dict(d)

    @classmethod
    @abstractmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "Operand":
        ...


_OPERAND_REGISTRY: Dict[str, type] = {}


def _reg(cls):
    _OPERAND_REGISTRY[cls._type_tag] = cls
    return cls


# --- Constant ---------------------------------------------------------------

@_reg
@dataclass
class ConstantOperand(Operand):
    """A literal number."""
    _type_tag = "constant"
    value_: float

    def value(self, series: "PriceSeries") -> float:
        return self.value_

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "constant", "value": self.value_}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "ConstantOperand":
        return cls(value_=float(d["value"]))


# --- Price field ------------------------------------------------------------

class PriceField(str, Enum):
    BID    = "bid"
    ASK    = "ask"
    MID    = "mid"
    VOLUME = "volume"


@_reg
@dataclass
class PriceOperand(Operand):
    """Current bid / ask / mid / volume."""
    _type_tag = "price"
    field: PriceField = PriceField.MID

    def value(self, series: "PriceSeries") -> float:
        return series.current(self.field)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "price", "field": self.field.value}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "PriceOperand":
        return cls(field=PriceField(d["field"]))


# --- Historical lookback ----------------------------------------------------

@_reg
@dataclass
class LookbackOperand(Operand):
    """Price field N bars ago."""
    _type_tag = "lookback"
    field: PriceField = PriceField.MID
    period: int = 1

    def value(self, series: "PriceSeries") -> float:
        return series.ago(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "lookback", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "LookbackOperand":
        return cls(field=PriceField(d["field"]), period=int(d["period"]))


# --- Simple Moving Average --------------------------------------------------

@_reg
@dataclass
class SMAOperand(Operand):
    """Simple moving average of a price field."""
    _type_tag = "sma"
    field: PriceField = PriceField.MID
    period: int = 20

    def value(self, series: "PriceSeries") -> float:
        buf = series.buffer(self.field, self.period)
        if len(buf) < self.period:
            return math.nan
        return sum(buf) / self.period

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "sma", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "SMAOperand":
        return cls(field=PriceField(d["field"]), period=int(d["period"]))


# --- Exponential Moving Average ---------------------------------------------

@_reg
@dataclass
class EMAOperand(Operand):
    """EMA stored in the PriceSeries cache."""
    _type_tag = "ema"
    field: PriceField = PriceField.MID
    period: int = 20

    def value(self, series: "PriceSeries") -> float:
        return series.ema(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "ema", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "EMAOperand":
        return cls(field=PriceField(d["field"]), period=int(d["period"]))


# --- RSI --------------------------------------------------------------------

@_reg
@dataclass
class RSIOperand(Operand):
    """RSI(period) of a price field."""
    _type_tag = "rsi"
    field: PriceField = PriceField.MID
    period: int = 14

    def value(self, series: "PriceSeries") -> float:
        return series.rsi(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "rsi", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "RSIOperand":
        return cls(field=PriceField(d["field"]), period=int(d["period"]))


# --- Bollinger Band component -----------------------------------------------

class BollingerComponent(str, Enum):
    UPPER  = "upper"
    MIDDLE = "middle"
    LOWER  = "lower"
    WIDTH  = "width"
    PCT_B  = "pct_b"


@_reg
@dataclass
class BollingerOperand(Operand):
    """One component of a Bollinger Band."""
    _type_tag = "bollinger"
    field: PriceField = PriceField.MID
    period: int = 20
    std_dev: float = 2.0
    component: BollingerComponent = BollingerComponent.UPPER

    def value(self, series: "PriceSeries") -> float:
        return series.bollinger(self.field, self.period, self.std_dev, self.component)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "bollinger",
            "field": self.field.value,
            "period": self.period,
            "std_dev": self.std_dev,
            "component": self.component.value,
        }

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "BollingerOperand":
        return cls(
            field=PriceField(d["field"]),
            period=int(d["period"]),
            std_dev=float(d.get("std_dev", 2.0)),
            component=BollingerComponent(d["component"]),
        )


# --- MACD component ---------------------------------------------------------

class MACDComponent(str, Enum):
    MACD    = "macd"
    SIGNAL  = "signal"
    HIST    = "hist"


@_reg
@dataclass
class MACDOperand(Operand):
    _type_tag = "macd"
    fast: int = 12
    slow: int = 26
    signal: int = 9
    component: MACDComponent = MACDComponent.MACD

    def value(self, series: "PriceSeries") -> float:
        return series.macd(self.fast, self.slow, self.signal, self.component)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "macd",
            "fast": self.fast,
            "slow": self.slow,
            "signal": self.signal,
            "component": self.component.value,
        }

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "MACDOperand":
        return cls(
            fast=int(d.get("fast", 12)),
            slow=int(d.get("slow", 26)),
            signal=int(d.get("signal", 9)),
            component=MACDComponent(d.get("component", "macd")),
        )


# ---------------------------------------------------------------------------
# 4. Operators / Conditions
# ---------------------------------------------------------------------------

class Operator(str, Enum):
    GT          = ">"
    GTE         = ">="
    LT          = "<"
    LTE         = "<="
    EQ          = "=="
    NEQ         = "!="
    CROSS_ABOVE = "cross_above"   # left crossed above right on this tick
    CROSS_BELOW = "cross_below"   # left crossed below right on this tick


@dataclass
class Condition:
    """
    Evaluates  left_operand  operator  right_operand.

    Cross operators require the PriceSeries to expose a one-tick lag so they
    can check whether the relationship *changed* this tick.
    """
    left:     Operand
    operator: Operator
    right:    Operand

    def evaluate(self, series: "PriceSeries") -> bool:
        lv = self.left.value(series)
        rv = self.right.value(series)

        if math.isnan(lv) or math.isnan(rv):
            return False

        if self.operator == Operator.GT:          return lv >  rv
        if self.operator == Operator.GTE:         return lv >= rv
        if self.operator == Operator.LT:          return lv <  rv
        if self.operator == Operator.LTE:         return lv <= rv
        if self.operator == Operator.EQ:          return math.isclose(lv, rv)
        if self.operator == Operator.NEQ:         return not math.isclose(lv, rv)

        # Cross operators need previous values
        lv_prev = self.left.value(series.prev_snapshot)
        rv_prev = self.right.value(series.prev_snapshot)
        if math.isnan(lv_prev) or math.isnan(rv_prev):
            return False

        if self.operator == Operator.CROSS_ABOVE:
            return (lv_prev <= rv_prev) and (lv > rv)
        if self.operator == Operator.CROSS_BELOW:
            return (lv_prev >= rv_prev) and (lv < rv)

        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left":     self.left.to_dict(),
            "operator": self.operator.value,
            "right":    self.right.to_dict(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Condition":
        return Condition(
            left=Operand.from_dict(d["left"]),
            operator=Operator(d["operator"]),
            right=Operand.from_dict(d["right"]),
        )


# ---------------------------------------------------------------------------
# 5. Rule
# ---------------------------------------------------------------------------

class RuleCombiner(str, Enum):
    AND = "and"
    OR  = "or"


@dataclass
class Rule:
    """
    A named condition (or list of conditions) attached to a role.

    When multiple conditions are listed they are combined with AND or OR.
    """
    name:       str
    role:       RuleRole
    conditions: List[Condition]
    combiner:   RuleCombiner = RuleCombiner.AND
    timing:     TimingMode   = TimingMode.ON_CHANGE
    quantity:   float        = 1.0

    # runtime state – not serialised
    _prev_result: bool = field(default=False, init=False, repr=False, compare=False)

    def evaluate(self, series: "PriceSeries") -> bool:
        if self.combiner == RuleCombiner.AND:
            result = all(c.evaluate(series) for c in self.conditions)
        else:
            result = any(c.evaluate(series) for c in self.conditions)

        if self.timing == TimingMode.EVERY_TICK:
            fire = result
        else:  # ON_CHANGE
            fire = result and not self._prev_result

        self._prev_result = result
        return fire

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":       self.name,
            "role":       self.role.value,
            "conditions": [c.to_dict() for c in self.conditions],
            "combiner":   self.combiner.value,
            "timing":     self.timing.value,
            "quantity":   self.quantity,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Rule":
        return Rule(
            name=d["name"],
            role=RuleRole(d["role"]),
            conditions=[Condition.from_dict(c) for c in d["conditions"]],
            combiner=RuleCombiner(d.get("combiner", "and")),
            timing=TimingMode(d.get("timing", "on_change")),
            quantity=float(d.get("quantity", 1.0)),
        )


# ---------------------------------------------------------------------------
# 6. RuleSet  (a full strategy slot)
# ---------------------------------------------------------------------------

@dataclass
class RuleSet:
    name:  str
    rules: List[Rule] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "rules": [r.to_dict() for r in self.rules]}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RuleSet":
        return RuleSet(
            name=d["name"],
            rules=[Rule.from_dict(r) for r in d.get("rules", [])],
        )


# ---------------------------------------------------------------------------
# 7. PriceSeries  (rolling price + indicator cache)
# ---------------------------------------------------------------------------

class PriceSeries:
    """
    Maintains rolling buffers for every field and computes indicators
    lazily, caching them per-tick so each operand only computes once.
    """

    _MAX_BUF = 500

    def __init__(self) -> None:
        self._bufs: Dict[str, Deque[float]] = {}
        self._ema_state: Dict[Tuple, float] = {}
        self._cache: Dict[Any, float] = {}
        self.prev_snapshot: "PriceSeries" = _NullSeries()

    def push(self, tick: TickData) -> None:
        # capture a lightweight prev snapshot for crossover detection
        self.prev_snapshot = _SnapShot(self)

        mid = (tick.bid + tick.ask) / 2 if tick.ask else tick.bid
        for fname, val in [
            ("bid",    tick.bid),
            ("ask",    tick.ask or tick.bid),
            ("mid",    mid),
            ("volume", getattr(tick, "volume", 0.0) or 0.0),
        ]:
            buf = self._bufs.setdefault(fname, deque(maxlen=self._MAX_BUF))
            buf.append(val)

        # invalidate per-tick cache
        self._cache.clear()

    # -- value accessors -----------------------------------------------------

    def current(self, field: PriceField) -> float:
        buf = self._bufs.get(field.value)
        if not buf:
            return math.nan
        return buf[-1]

    def ago(self, field: PriceField, n: int) -> float:
        buf = self._bufs.get(field.value)
        if not buf or len(buf) < n + 1:
            return math.nan
        return buf[-(n + 1)]

    def buffer(self, field: PriceField, size: int) -> List[float]:
        buf = self._bufs.get(field.value, deque())
        return list(buf)[-size:]

    # -- indicators ----------------------------------------------------------

    def ema(self, field: PriceField, period: int) -> float:
        key = ("ema", field.value, period)
        if key in self._cache:
            return self._cache[key]
        buf = self.buffer(field, period * 3)
        if len(buf) < period:
            return math.nan
        k = 2 / (period + 1)
        ema_val = sum(buf[:period]) / period
        for price in buf[period:]:
            ema_val = price * k + ema_val * (1 - k)
        self._cache[key] = ema_val
        return ema_val

    def rsi(self, field: PriceField, period: int) -> float:
        key = ("rsi", field.value, period)
        if key in self._cache:
            return self._cache[key]
        buf = self.buffer(field, period + 1)
        if len(buf) < period + 1:
            return math.nan
        gains, losses = [], []
        for i in range(1, len(buf)):
            d = buf[i] - buf[i - 1]
            (gains if d >= 0 else losses).append(abs(d))
        ag = sum(gains) / period if gains else 0
        al = sum(losses) / period if losses else 0
        if al == 0:
            v = 100.0
        else:
            v = 100 - 100 / (1 + ag / al)
        self._cache[key] = v
        return v

    def bollinger(
        self,
        field: PriceField,
        period: int,
        std_dev: float,
        component: BollingerComponent,
    ) -> float:
        key = ("boll", field.value, period, std_dev, component.value)
        if key in self._cache:
            return self._cache[key]
        buf = self.buffer(field, period)
        if len(buf) < period:
            return math.nan
        mean = sum(buf) / period
        variance = sum((x - mean) ** 2 for x in buf) / period
        sd = math.sqrt(variance) * std_dev
        upper, lower = mean + sd, mean - sd
        mapping = {
            BollingerComponent.UPPER:  upper,
            BollingerComponent.MIDDLE: mean,
            BollingerComponent.LOWER:  lower,
            BollingerComponent.WIDTH:  upper - lower,
            BollingerComponent.PCT_B:  (buf[-1] - lower) / (upper - lower) if upper != lower else 0.5,
        }
        v = mapping[component]
        self._cache[key] = v
        return v

    def macd(
        self,
        fast: int,
        slow: int,
        signal_period: int,
        component: MACDComponent,
    ) -> float:
        key = ("macd", fast, slow, signal_period, component.value)
        if key in self._cache:
            return self._cache[key]
        macd_val = self.ema(PriceField.MID, fast) - self.ema(PriceField.MID, slow)
        if component == MACDComponent.MACD:
            self._cache[key] = macd_val
            return macd_val
        # signal / hist require a history of MACD values – simplified:
        # (a full implementation would maintain a secondary EMA buffer)
        self._cache[key] = math.nan
        return math.nan


class _NullSeries(PriceSeries):
    """Stub returned as prev_snapshot before the first tick."""
    def current(self, *_):        return math.nan
    def ago(self, *_):            return math.nan
    def buffer(self, *_):         return []
    def ema(self, *_):            return math.nan
    def rsi(self, *_):            return math.nan
    def bollinger(self, *_):      return math.nan
    def macd(self, *_):           return math.nan


class _SnapShot(PriceSeries):
    """Captures current state so crossover conditions can compare prev tick."""
    def __init__(self, src: PriceSeries) -> None:
        self._bufs       = {k: deque(v) for k, v in src._bufs.items()}
        self._cache      = dict(src._cache)
        self.prev_snapshot = src.prev_snapshot

    def push(self, *_):
        raise RuntimeError("Cannot push to a snapshot")


# ---------------------------------------------------------------------------
# 8. RuleSetStrategy  (wraps a RuleSet into the Strategy interface)
# ---------------------------------------------------------------------------

from strategy import Strategy  # noqa: E402  (import after dataclasses)


class RuleSetStrategy(Strategy):
    """
    Evaluates a RuleSet on every tick and emits SignalEvents.

    Role → action mapping
    ─────────────────────
    entry_long   → buy
    exit_long    → sell   (reduce/close long)
    entry_short  → short
    exit_short   → cover  (reduce/close short)
    """

    _ROLE_TO_ACTION: Dict[RuleRole, str] = {
        RuleRole.ENTRY_LONG:  "buy",
        RuleRole.EXIT_LONG:   "sell",
        RuleRole.ENTRY_SHORT: "short",
        RuleRole.EXIT_SHORT:  "cover",
    }

    def __init__(self, rule_set: RuleSet) -> None:
        self.rule_set = rule_set
        self._series: Dict[str, PriceSeries] = {}

    def on_tick(self, tick: TickData) -> List[SignalEvent]:
        series = self._series.setdefault(tick.name, PriceSeries())
        series.push(tick)

        signals: List[SignalEvent] = []
        for rule in self.rule_set.rules:
            if rule.evaluate(series):
                action = self._ROLE_TO_ACTION.get(rule.role)
                if action:
                    signals.append(SignalEvent(
                        symbol=tick.name,
                        action=action,
                        quantity=rule.quantity,
                    ))
        return signals


# ---------------------------------------------------------------------------
# 9. Register with existing registry
# ---------------------------------------------------------------------------

from strategy import StrategyConfig, register_strategy  # noqa: E402
from pydantic import Field as PField                     # noqa: E402
import json                                              # noqa: E402


class RuleSetStrategyConfig(StrategyConfig):
    rule_set: Dict[str, Any] = PField(default_factory=dict)


register_strategy(
    name="rule_set",
    config_model=RuleSetStrategyConfig,
    factory=lambda cfg: RuleSetStrategy(RuleSet.from_dict(cfg.rule_set)),
)


# ---------------------------------------------------------------------------
# 10. Schema introspection helpers  (used by the API)
# ---------------------------------------------------------------------------

OPERAND_SCHEMA = {
    "constant":  {"params": [{"name": "value",     "type": "number", "label": "Value"}]},
    "price":     {"params": [{"name": "field",     "type": "select", "label": "Field",
                               "options": [f.value for f in PriceField]}]},
    "lookback":  {"params": [{"name": "field",     "type": "select", "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",   "type": "integer", "label": "Bars ago", "min": 1}]},
    "sma":       {"params": [{"name": "field",     "type": "select", "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",   "type": "integer", "label": "Period", "min": 2}]},
    "ema":       {"params": [{"name": "field",     "type": "select", "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",   "type": "integer", "label": "Period", "min": 2}]},
    "rsi":       {"params": [{"name": "field",     "type": "select", "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",   "type": "integer", "label": "Period", "min": 2}]},
    "bollinger": {"params": [{"name": "field",     "type": "select", "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",   "type": "integer", "label": "Period", "min": 2},
                              {"name": "std_dev",  "type": "number",  "label": "Std Dev"},
                              {"name": "component","type": "select",  "label": "Component",
                               "options": [c.value for c in BollingerComponent]}]},
    "macd":      {"params": [{"name": "fast",      "type": "integer", "label": "Fast period", "min": 1},
                              {"name": "slow",      "type": "integer", "label": "Slow period", "min": 1},
                              {"name": "signal",    "type": "integer", "label": "Signal period", "min": 1},
                              {"name": "component", "type": "select",  "label": "Component",
                               "options": [c.value for c in MACDComponent]}]},
}

OPERATOR_OPTIONS = [op.value for op in Operator]

ROLE_OPTIONS     = [r.value for r in RuleRole]