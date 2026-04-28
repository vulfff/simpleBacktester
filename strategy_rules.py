"""
strategy_rules.py  –  Rule-based strategy framework

Changes vs original
====================
1. Rule.evaluate() now respects per-condition `combiner` fields (AND/OR between
   each adjacent pair), matching what the frontend serialises.
2. PriceSeries.macd() now computes the signal line and histogram properly using
   an incremental EMA buffer instead of returning math.nan.
3. Condition.from_dict() gracefully skips / wraps exit_condition dicts
   (take_profit_pct, stop_loss_pct, bars_held, time_of_day, day_of_week …)
   that are stored in the conditions list by the frontend.
4. ExitCondition is a new Condition subclass that is evaluated by the engine
   via portfolio state rather than price operands.
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
    ENTRY_LONG   = "entry_long"
    EXIT_LONG    = "exit_long"
    ENTRY_SHORT  = "entry_short"
    EXIT_SHORT   = "exit_short"


# ---------------------------------------------------------------------------
# 2. Timing filter
# ---------------------------------------------------------------------------

class TimingMode(str, Enum):
    EVERY_TICK = "every_tick"
    ON_CHANGE  = "on_change"


# ---------------------------------------------------------------------------
# 3. Operands  (value producers)
# ---------------------------------------------------------------------------

class Operand(ABC):
    @abstractmethod
    def value(self, series: "PriceSeries") -> float: ...
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]: ...

    @property
    def min_bars(self) -> int:
        """Minimum bars of history required before this operand returns a valid value."""
        return 1

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Operand":
        t = d["type"]
        cls = _OPERAND_REGISTRY.get(t)
        if cls is None:
            raise KeyError(f"Unknown operand type: {t!r}")
        return cls._from_dict(d)

    @classmethod
    @abstractmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "Operand": ...


_OPERAND_REGISTRY: Dict[str, type] = {}


def _reg(cls):
    _OPERAND_REGISTRY[cls._type_tag] = cls
    return cls


# ── Constant ─────────────────────────────────────────────────────────────────

@_reg
@dataclass
class ConstantOperand(Operand):
    _type_tag = "constant"
    value_: float

    def value(self, series: "PriceSeries") -> float:
        return self.value_

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "constant", "value": self.value_}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "ConstantOperand":
        return cls(value_=float(d["value"]))


# ── Price field ───────────────────────────────────────────────────────────────

class PriceField(str, Enum):
    CLOSE  = "close"
    HIGH   = "high"
    LOW    = "low"
    VOLUME = "volume"


def _parse_price_field(val: str) -> PriceField:
    """Parse a PriceField value with backward-compat fallback.
    Old saved strategies may reference 'bid', 'ask', or 'mid' — all map to CLOSE."""
    try:
        return PriceField(val)
    except ValueError:
        return PriceField.CLOSE


@_reg
@dataclass
class PriceOperand(Operand):
    _type_tag = "price"
    field: PriceField = PriceField.CLOSE

    def value(self, series: "PriceSeries") -> float:
        return series.current(self.field)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "price", "field": self.field.value}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "PriceOperand":
        return cls(field=_parse_price_field(d["field"]))


# ── Lookback ──────────────────────────────────────────────────────────────────

@_reg
@dataclass
class LookbackOperand(Operand):
    _type_tag = "lookback"
    field: PriceField = PriceField.CLOSE
    period: int = 1

    @property
    def min_bars(self) -> int:
        return self.period + 1

    def value(self, series: "PriceSeries") -> float:
        return series.ago(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "lookback", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "LookbackOperand":
        return cls(field=_parse_price_field(d["field"]), period=int(d["period"]))


# ── SMA ───────────────────────────────────────────────────────────────────────

@_reg
@dataclass
class SMAOperand(Operand):
    _type_tag = "sma"
    field: PriceField = PriceField.CLOSE
    period: int = 20

    @property
    def min_bars(self) -> int:
        return self.period

    def value(self, series: "PriceSeries") -> float:
        buf = series.buffer(self.field, self.period)
        if len(buf) < self.period:
            return math.nan
        return sum(buf) / self.period

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "sma", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "SMAOperand":
        return cls(field=_parse_price_field(d["field"]), period=int(d["period"]))


# ── EMA ───────────────────────────────────────────────────────────────────────

@_reg
@dataclass
class EMAOperand(Operand):
    _type_tag = "ema"
    field: PriceField = PriceField.CLOSE
    period: int = 20

    @property
    def min_bars(self) -> int:
        return self.period * 2  # extra runway to stabilise EMA

    def value(self, series: "PriceSeries") -> float:
        return series.ema(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "ema", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "EMAOperand":
        return cls(field=_parse_price_field(d["field"]), period=int(d["period"]))


# ── RSI ───────────────────────────────────────────────────────────────────────

@_reg
@dataclass
class RSIOperand(Operand):
    _type_tag = "rsi"
    field: PriceField = PriceField.CLOSE
    period: int = 14

    @property
    def min_bars(self) -> int:
        return self.period + 1

    def value(self, series: "PriceSeries") -> float:
        return series.rsi(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "rsi", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "RSIOperand":
        return cls(field=_parse_price_field(d["field"]), period=int(d["period"]))


# ── Bollinger ─────────────────────────────────────────────────────────────────

class BollingerComponent(str, Enum):
    UPPER  = "upper"
    MIDDLE = "middle"
    LOWER  = "lower"
    WIDTH  = "width"
    PCT_B  = "pct_b"


@_reg
@dataclass
class BollingerOperand(Operand):
    _type_tag = "bollinger"
    field: PriceField = PriceField.CLOSE
    period: int = 20
    std_dev: float = 2.0
    component: BollingerComponent = BollingerComponent.UPPER

    @property
    def min_bars(self) -> int:
        return self.period

    def value(self, series: "PriceSeries") -> float:
        return series.bollinger(self.field, self.period, self.std_dev, self.component)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "bollinger", "field": self.field.value, "period": self.period,
                "std_dev": self.std_dev, "component": self.component.value}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "BollingerOperand":
        return cls(
            field=_parse_price_field(d["field"]),
            period=int(d["period"]),
            std_dev=float(d.get("std_dev", 2.0)),
            component=BollingerComponent(d.get("component", "upper")),
        )


# ── MACD ──────────────────────────────────────────────────────────────────────

class MACDComponent(str, Enum):
    MACD   = "macd"
    SIGNAL = "signal"
    HIST   = "hist"


@_reg
@dataclass
class MACDOperand(Operand):
    _type_tag = "macd"
    fast: int = 12
    slow: int = 26
    signal: int = 9
    component: MACDComponent = MACDComponent.MACD

    @property
    def min_bars(self) -> int:
        return self.slow + self.signal

    def value(self, series: "PriceSeries") -> float:
        return series.macd(self.fast, self.slow, self.signal, self.component)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "macd", "fast": self.fast, "slow": self.slow,
                "signal": self.signal, "component": self.component.value}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "MACDOperand":
        return cls(
            fast=int(d.get("fast", 12)),
            slow=int(d.get("slow", 26)),
            signal=int(d.get("signal", 9)),
            component=MACDComponent(d.get("component", "macd")),
        )


# ── Highest High ─────────────────────────────────────────────────────────────

@_reg
@dataclass
class HighestHighOperand(Operand):
    _type_tag = "highest_high"
    field: PriceField = PriceField.HIGH
    period: int = 14

    @property
    def min_bars(self) -> int:
        return self.period

    def value(self, series: "PriceSeries") -> float:
        return series.highest(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "highest_high", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "HighestHighOperand":
        return cls(field=PriceField(d.get("field", "high")), period=int(d["period"]))


# ── Lowest Low ────────────────────────────────────────────────────────────────

@_reg
@dataclass
class LowestLowOperand(Operand):
    _type_tag = "lowest_low"
    field: PriceField = PriceField.LOW
    period: int = 14

    @property
    def min_bars(self) -> int:
        return self.period

    def value(self, series: "PriceSeries") -> float:
        return series.lowest(self.field, self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "lowest_low", "field": self.field.value, "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "LowestLowOperand":
        return cls(field=PriceField(d.get("field", "low")), period=int(d["period"]))


# ── ATR ───────────────────────────────────────────────────────────────────────

@_reg
@dataclass
class ATROperand(Operand):
    _type_tag = "atr"
    period: int = 14

    @property
    def min_bars(self) -> int:
        return self.period + 1

    def value(self, series: "PriceSeries") -> float:
        return series.atr(self.period)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "atr", "period": self.period}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "ATROperand":
        return cls(period=int(d.get("period", 14)))


# ── Typical Price ─────────────────────────────────────────────────────────────

@_reg
@dataclass
class TypicalPriceOperand(Operand):
    _type_tag = "typical_price"

    def value(self, series: "PriceSeries") -> float:
        return series.typical_price()

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "typical_price"}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "TypicalPriceOperand":
        return cls()


# ── Time of Day ───────────────────────────────────────────────────────────────

@_reg
@dataclass
class TimeOfDayOperand(Operand):
    """Returns current bar time as minutes since midnight (0–1439).

    Allows time-filtered signal conditions, e.g.:
      time_of_day >= 570  →  at or after 09:30
      time_of_day <  960  →  before 16:00
    """
    _type_tag = "time_of_day"

    @property
    def min_bars(self) -> int:
        return 1

    def value(self, series: "PriceSeries") -> float:
        t = getattr(series, "_current_time", None)
        if t is None:
            return math.nan
        return float(t.hour * 60 + t.minute)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "time_of_day"}

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "TimeOfDayOperand":
        return cls()


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
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"


@dataclass
class Condition:
    """Evaluates left_operand operator right_operand."""
    left:     Operand
    operator: Operator
    right:    Operand
    # combiner tells Rule how to join this condition with the NEXT one
    combiner: str = "and"   # "and" | "or"

    def evaluate(self, series: "PriceSeries") -> bool:
        lv = self.left.value(series)
        rv = self.right.value(series)

        if math.isnan(lv) or math.isnan(rv):
            return False

        if self.operator == Operator.GT:  return lv >  rv
        if self.operator == Operator.GTE: return lv >= rv
        if self.operator == Operator.LT:  return lv <  rv
        if self.operator == Operator.LTE: return lv <= rv
        if self.operator == Operator.EQ:  return math.isclose(lv, rv)
        if self.operator == Operator.NEQ: return not math.isclose(lv, rv)

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
        return {"left": self.left.to_dict(), "operator": self.operator.value,
                "right": self.right.to_dict(), "combiner": self.combiner}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> Optional["Condition"]:
        """Return None for exit_condition dicts (handled separately)."""
        if d.get("kind") == "exit_condition":
            return None  # skipped – ExitCondition handled by engine
        return Condition(
            left=Operand.from_dict(d["left"]),
            operator=Operator(d["operator"]),
            right=Operand.from_dict(d["right"]),
            combiner=d.get("combiner", "and"),
        )


# ── ExitCondition ─────────────────────────────────────────────────────────────

@dataclass
class ExitCondition:
    """
    Portfolio-state based exit condition (P&L / time).
    Evaluated by the engine with access to portfolio, not just price series.
    """
    exit_type: str   # take_profit_pct | stop_loss_pct | take_profit_abs |
                     # stop_loss_abs | bars_held | time_of_day | day_of_week
    value: float
    combiner: str = "and"

    def evaluate_portfolio(self, portfolio: Any, tick: Any, bars_in_trade: int,
                           entry_equity: float = None) -> bool:
        t = self.exit_type
        if t == "take_profit_pct":
            pnl_pct = _portfolio_pnl_pct(portfolio, entry_equity)
            return pnl_pct is not None and pnl_pct >= self.value
        if t == "stop_loss_pct":
            pnl_pct = _portfolio_pnl_pct(portfolio, entry_equity)
            return pnl_pct is not None and pnl_pct <= -self.value
        if t == "take_profit_abs":
            baseline = entry_equity if entry_equity is not None else portfolio.starting_cash
            pnl = portfolio.total_value() - baseline
            return pnl >= self.value
        if t == "stop_loss_abs":
            baseline = entry_equity if entry_equity is not None else portfolio.starting_cash
            pnl = portfolio.total_value() - baseline
            return pnl <= -self.value
        if t == "bars_held":
            return bars_in_trade >= int(self.value)
        if t == "time_of_day":
            minutes = tick.time.hour * 60 + tick.time.minute
            return minutes == int(self.value)
        if t == "day_of_week":
            # value uses ISO weekday convention: 1=Monday … 5=Friday … 7=Sunday
            return tick.time.isoweekday() == int(self.value)
        return False

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ExitCondition":
        return ExitCondition(
            exit_type=d["exitType"],
            value=float(d.get("value", 0)),
            combiner=d.get("combiner", "and"),
        )


def _portfolio_pnl_pct(portfolio: Any, entry_equity: float = None) -> Optional[float]:
    """
    Return P&L as a percentage.
    When entry_equity is provided (portfolio total_value captured at trade entry)
    the return is relative to that entry baseline — accurate for TP/SL checks.
    Falls back to the all-time starting_cash baseline when entry_equity is None.
    """
    start = entry_equity if (entry_equity is not None and entry_equity > 0) \
            else portfolio.starting_cash
    if start == 0:
        return None
    current = portfolio.total_value()
    return (current - start) / abs(start) * 100


# ---------------------------------------------------------------------------
# 5. Rule  – per-condition AND/OR combiner
# ---------------------------------------------------------------------------

class RuleCombiner(str, Enum):
    AND = "and"
    OR  = "or"


@dataclass
class Rule:
    """
    A named set of conditions attached to a role.

    Condition list evaluation
    ─────────────────────────
    Each condition (after the first) carries a `combiner` field ("and"/"or")
    that defines how it joins with the accumulated result so far:

        result = cond[0]
        for cond[i] (i > 0):
            if cond[i].combiner == "and":  result = result AND cond[i]
            else:                           result = result OR  cond[i]

    This matches exactly what the frontend serialises.
    """
    name:            str
    role:            RuleRole
    conditions:      List[Condition]        # signal conditions
    exit_conditions: List[ExitCondition] = field(default_factory=list)
    combiner:        RuleCombiner = RuleCombiner.AND   # fallback / legacy
    timing:          TimingMode   = TimingMode.ON_CHANGE
    quantity:        float        = 1.0

    _prev_result:    bool = field(default=False, init=False, repr=False, compare=False)
    _bars_in_trade:  int  = field(default=0,     init=False, repr=False, compare=False)

    def evaluate(self, series: "PriceSeries", portfolio: Any = None, tick: Any = None,
                 entry_equity: float = None) -> bool:
        # ── position guard for exit rules ──────────────────────────────────
        # Return False *without* updating _prev_result so the exit fires fresh
        # on the first bar where a position is actually held.
        if portfolio is not None and tick is not None:
            pos = portfolio.positions.get(tick.name, 0.0)
            if self.role == RuleRole.EXIT_LONG and pos <= 1e-9:
                self._prev_result = False  # reset so on_change fires fresh on next entry
                return False
            if self.role == RuleRole.EXIT_SHORT and pos >= -1e-9:
                self._prev_result = False
                return False

        # ── signal conditions ──────────────────────────────────────────────
        if self.conditions:
            result = self.conditions[0].evaluate(series)
            for cond in self.conditions[1:]:
                result = result and cond.evaluate(series)
        else:
            result = True  # no signal conditions = always pass (rely on exit conds)

        # ── exit conditions (portfolio-based) ──────────────────────────────
        if self.exit_conditions and portfolio is not None and tick is not None:
            exit_result = self.exit_conditions[0].evaluate_portfolio(
                portfolio, tick, self._bars_in_trade, entry_equity)
            for ec in self.exit_conditions[1:]:
                exit_result = exit_result and ec.evaluate_portfolio(
                    portfolio, tick, self._bars_in_trade, entry_equity)
            result = result and exit_result

        # ── timing filter ──────────────────────────────────────────────────
        if self.timing == TimingMode.EVERY_TICK:
            fire = result
        else:
            fire = result and not self._prev_result

        self._prev_result = result

        # Track bars in trade for exit conditions (bars_held).
        # For exit rules: increment each bar while position is held, reset when flat.
        # For entry rules: the counter is unused, just keep incrementing.
        if portfolio is not None and tick is not None:
            pos = portfolio.positions.get(tick.name, 0.0)
            if self.role in (RuleRole.EXIT_LONG, RuleRole.EXIT_SHORT):
                if abs(pos) > 1e-9:
                    self._bars_in_trade += 1
                else:
                    self._bars_in_trade = 0
            else:
                self._bars_in_trade += 1
        else:
            self._bars_in_trade += 1

        if fire:
            self._bars_in_trade = 0
        return fire

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":            self.name,
            "role":            self.role.value,
            "conditions":      [c.to_dict() for c in self.conditions],
            "exit_conditions": [{"kind": "exit_condition", "exitType": ec.exit_type,
                                  "value": ec.value, "combiner": ec.combiner}
                                 for ec in self.exit_conditions],
            "combiner":        self.combiner.value,
            "timing":          self.timing.value,
            "quantity":        self.quantity,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Rule":
        raw_conds = d.get("conditions", [])
        signal_conds:  List[Condition]     = []
        exit_conds:    List[ExitCondition] = []

        for c in raw_conds:
            if c.get("kind") == "exit_condition":
                try:
                    exit_conds.append(ExitCondition.from_dict(c))
                except Exception:
                    pass
            else:
                try:
                    cond = Condition.from_dict(c)
                    if cond is not None:
                        signal_conds.append(cond)
                except Exception:
                    pass

        return Rule(
            name=d.get("name", "Rule"),
            role=RuleRole(d["role"]),
            conditions=signal_conds,
            exit_conditions=exit_conds,
            combiner=RuleCombiner(d.get("combiner", "and")),
            timing=TimingMode(d.get("timing", "on_change")),
            quantity=float(d.get("quantity", 1.0)),
        )


# ---------------------------------------------------------------------------
# 6. RuleSet
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
            name=d.get("name", "RuleSet"),
            rules=[Rule.from_dict(r) for r in d.get("rules", [])],
        )


# ---------------------------------------------------------------------------
# 7. PriceSeries  – with working MACD signal & histogram
# ---------------------------------------------------------------------------

class PriceSeries:
    """
    Rolling price buffers + on-demand indicator computation.

    MACD fix
    ────────
    The original implementation returned math.nan for signal and hist because
    it tried to compute a secondary EMA without a history of MACD line values.
    We now maintain a dedicated deque of MACD line values per (fast,slow,signal)
    key so that the signal EMA is computed correctly after enough bars.
    """

    _MAX_BUF = 1000

    def __init__(self) -> None:
        self._bufs:           Dict[str, Deque[float]] = {}
        self._cache:          Dict[Any, float]         = {}
        self._macd_hist:      Dict[Tuple, Deque[float]]= {}  # history of MACD line values
        self._tick_count:     int                       = 0
        self._macd_last_tick: Dict[Tuple, int]          = {}  # last tick index per MACD key
        self._ema_state:      Dict[Tuple, float]        = {}  # running EMA values (persistent)
        self._ema_last_tick:  Dict[Tuple, int]          = {}  # tick when EMA was last updated
        self.prev_snapshot: "PriceSeries" = _NullSeries()
        self._current_time = None  # datetime of the most recent tick

    def push(self, tick: TickData) -> None:
        self.prev_snapshot = _SnapShot(self)
        self._current_time = tick.time

        bar_high = getattr(tick, "high", 0.0) or tick.close
        bar_low  = getattr(tick, "low",  0.0) or tick.close
        for fname, val in [
            ("close",  tick.close),
            ("high",   bar_high),
            ("low",    bar_low),
            ("volume", getattr(tick, "volume", 0.0) or 0.0),
        ]:
            buf = self._bufs.setdefault(fname, deque(maxlen=self._MAX_BUF))
            buf.append(val)

        # Invalidate per-tick cache
        self._cache.clear()
        self._tick_count += 1

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

    def ema(self, field: PriceField, period: int) -> float:
        key = ("ema", field.value, period)
        if key in self._cache:
            return self._cache[key]
        buf = self._bufs.get(field.value)
        if not buf or len(buf) < period:
            self._cache[key] = math.nan
            return math.nan
        k = 2.0 / (period + 1)
        state_key = ("ema_state", field.value, period)
        last_tick = self._ema_last_tick.get(state_key, -1)
        if last_tick == self._tick_count - 1 and state_key in self._ema_state:
            # Incremental update: one new bar since last compute
            ema_val = buf[-1] * k + self._ema_state[state_key] * (1 - k)
        else:
            # Full recompute from buffer (first call or gap)
            buf_list = list(buf)
            ema_val = sum(buf_list[:period]) / period
            for price in buf_list[period:]:
                ema_val = price * k + ema_val * (1 - k)
        self._ema_state[state_key] = ema_val
        self._ema_last_tick[state_key] = self._tick_count
        self._cache[key] = ema_val
        return ema_val

    def rsi(self, field: PriceField, period: int) -> float:
        key = ("rsi", field.value, period)
        if key in self._cache:
            return self._cache[key]
        buf = self.buffer(field, period + 1)
        if len(buf) < period + 1:
            self._cache[key] = math.nan
            return math.nan
        gains, losses = [], []
        for i in range(1, len(buf)):
            d = buf[i] - buf[i - 1]
            (gains if d >= 0 else losses).append(abs(d))
        ag = sum(gains) / period if gains else 0.0
        al = sum(losses) / period if losses else 0.0
        v = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
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
            self._cache[key] = math.nan
            return math.nan
        mean     = sum(buf) / period
        variance = sum((x - mean) ** 2 for x in buf) / (period - 1) if period > 1 else 0.0
        sd       = math.sqrt(variance) * std_dev
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

        fast_ema = self.ema(PriceField.CLOSE, fast)
        slow_ema = self.ema(PriceField.CLOSE, slow)

        if math.isnan(fast_ema) or math.isnan(slow_ema):
            self._cache[key] = math.nan
            return math.nan

        macd_line = fast_ema - slow_ema

        if component == MACDComponent.MACD:
            self._cache[key] = macd_line
            return macd_line

        # ── Signal & Histogram: need a history of MACD line values ────────
        hist_key = ("macd_hist", fast, slow)
        macd_deque = self._macd_hist.setdefault(hist_key, deque(maxlen=self._MAX_BUF))
        # Append exactly once per tick (tracked via _tick_count)
        if self._macd_last_tick.get(hist_key) != self._tick_count:
            macd_deque.append(macd_line)
            self._macd_last_tick[hist_key] = self._tick_count

        if len(macd_deque) < signal_period:
            self._cache[key] = math.nan
            return math.nan

        # Signal = EMA(macd_line, signal_period)
        buf = list(macd_deque)
        k   = 2.0 / (signal_period + 1)
        sig = sum(buf[:signal_period]) / signal_period
        for v in buf[signal_period:]:
            sig = v * k + sig * (1 - k)

        if component == MACDComponent.SIGNAL:
            self._cache[key] = sig
            return sig

        # Histogram
        hist = macd_line - sig
        self._cache[key] = hist
        return hist


    def highest(self, field: PriceField, period: int) -> float:
        buf = self.buffer(field, period)
        if len(buf) < period:
            return math.nan
        return max(buf)

    def lowest(self, field: PriceField, period: int) -> float:
        buf = self.buffer(field, period)
        if len(buf) < period:
            return math.nan
        return min(buf)

    def atr(self, period: int) -> float:
        """Average True Range using Wilder's smoothing (RMA).
        Seed = SMA of first `period` true ranges; then RMA: (prev*(period-1)+TR)/period.
        TR = max(high-low, |high-prev_close|, |low-prev_close|)
        """
        key = ("atr", period)
        if key in self._cache:
            return self._cache[key]
        highs  = list(self._bufs.get("high",  deque()))
        lows   = list(self._bufs.get("low",   deque()))
        closes = list(self._bufs.get("close", deque()))
        n = min(len(highs), len(lows), len(closes))
        if n < period + 1:
            self._cache[key] = math.nan
            return math.nan
        trs = []
        for i in range(1, n):
            h, l, pc = highs[i], lows[i], closes[i - 1]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if len(trs) < period:
            self._cache[key] = math.nan
            return math.nan
        # Seed with SMA of first `period` TRs, then Wilder's smoothing
        atr_val = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr_val = (atr_val * (period - 1) + tr) / period
        self._cache[key] = atr_val
        return atr_val

    def typical_price(self) -> float:
        """(High + Low + Close) / 3"""
        h = self.current(PriceField.HIGH)
        l = self.current(PriceField.LOW)
        c = self.current(PriceField.CLOSE)
        if math.isnan(h) or math.isnan(l) or math.isnan(c):
            return math.nan
        return (h + l + c) / 3


class _NullSeries(PriceSeries):
    """Stub returned as prev_snapshot before the first tick."""
    def __init__(self) -> None:
        # Don't call super().__init__() — we override everything
        self._bufs      = {}
        self._cache     = {}
        self._macd_hist = {}
        self.prev_snapshot = self   # circular — but never queried deeper
        self._current_time = None

    def current(self, *_):    return math.nan
    def ago(self, *_):        return math.nan
    def buffer(self, *_):     return []
    def ema(self, *_):        return math.nan
    def rsi(self, *_):        return math.nan
    def bollinger(self, *_):  return math.nan
    def macd(self, *_):       return math.nan
    def push(self, *_):       pass


class _SnapShot(PriceSeries):
    """Lightweight copy of PriceSeries state for crossover detection (prev tick)."""
    def __init__(self, src: PriceSeries) -> None:
        self._bufs            = {k: deque(v) for k, v in src._bufs.items()}
        self._cache           = dict(src._cache)
        self._macd_hist       = {k: deque(v) for k, v in src._macd_hist.items()}
        self._tick_count      = src._tick_count
        self._macd_last_tick  = dict(src._macd_last_tick)
        self._ema_state       = dict(src._ema_state)
        self._ema_last_tick   = dict(src._ema_last_tick)
        self.prev_snapshot    = src.prev_snapshot   # chain doesn't need to go deeper
        self._current_time    = src._current_time

    def push(self, *_):
        raise RuntimeError("Cannot push to a snapshot")


# ---------------------------------------------------------------------------
# 8. RuleSetStrategy  (wraps RuleSet into the Strategy interface)
# ---------------------------------------------------------------------------

from strategy import Strategy  # noqa: E402


class RuleSetStrategy(Strategy):
    _ROLE_TO_ACTION: Dict[RuleRole, str] = {
        RuleRole.ENTRY_LONG:  "buy",
        RuleRole.EXIT_LONG:   "sell",
        RuleRole.ENTRY_SHORT: "short",
        RuleRole.EXIT_SHORT:  "cover",
    }

    def __init__(self, rule_set: RuleSet) -> None:
        self.rule_set = rule_set
        self._series: Dict[str, PriceSeries] = {}
        self._bar_count: int = 0
        # portfolio.total_value() captured at trade entry, per symbol.
        # Used to compute TP/SL % relative to the entry baseline, not starting_cash.
        self._entry_equity: Dict[str, float] = {}

    @property
    def warmup_bars(self) -> int:
        """
        Minimum bars needed before any indicator in this strategy is reliable.
        During warmup no signals are generated (lookahead-bias prevention).
        """
        max_bars = 1
        for rule in self.rule_set.rules:
            for cond in rule.conditions:
                for operand in (cond.left, cond.right):
                    max_bars = max(max_bars, operand.min_bars)
        return max_bars

    def on_tick(self, tick: TickData) -> List[SignalEvent]:
        series = self._series.setdefault(tick.name, PriceSeries())
        series.push(tick)
        self._bar_count += 1

        # Suppress all signals during the warmup period
        if self._bar_count <= self.warmup_bars:
            return []

        # Maintain entry equity snapshot for accurate TP/SL % calculation.
        # Captured on the first bar where a position exists (after fill).
        portfolio = getattr(self, "_portfolio", None)
        if portfolio is not None:
            pos = portfolio.positions.get(tick.name, 0.0)
            if abs(pos) > 1e-9:
                if tick.name not in self._entry_equity:
                    self._entry_equity[tick.name] = portfolio.total_value()
            else:
                self._entry_equity.pop(tick.name, None)

        signals: List[SignalEvent] = []
        for rule in self.rule_set.rules:
            entry_eq = self._entry_equity.get(tick.name)
            if rule.evaluate(series, portfolio=portfolio, tick=tick, entry_equity=entry_eq):
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
# 10. Schema introspection helpers
# ---------------------------------------------------------------------------

OPERAND_SCHEMA = {
    "constant":  {"params": [{"name": "value",      "type": "number",  "label": "Value"}]},
    "price":     {"params": [{"name": "field",      "type": "select",  "label": "Field",
                               "options": [f.value for f in PriceField]}]},
    "lookback":  {"params": [{"name": "field",      "type": "select",  "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",    "type": "integer", "label": "Bars ago", "min": 1}]},
    "sma":       {"params": [{"name": "field",      "type": "select",  "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",    "type": "integer", "label": "Period",   "min": 2}]},
    "ema":       {"params": [{"name": "field",      "type": "select",  "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",    "type": "integer", "label": "Period",   "min": 2}]},
    "rsi":       {"params": [{"name": "field",      "type": "select",  "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",    "type": "integer", "label": "Period",   "min": 2}]},
    "bollinger": {"params": [{"name": "field",      "type": "select",  "label": "Field",
                               "options": [f.value for f in PriceField]},
                              {"name": "period",    "type": "integer", "label": "Period",   "min": 2},
                              {"name": "std_dev",   "type": "number",  "label": "Std Dev"},
                              {"name": "component", "type": "select",  "label": "Component",
                               "options": [c.value for c in BollingerComponent]}]},
    "macd":      {"params": [{"name": "fast",       "type": "integer", "label": "Fast",    "min": 1},
                              {"name": "slow",       "type": "integer", "label": "Slow",    "min": 1},
                              {"name": "signal",     "type": "integer", "label": "Signal",  "min": 1},
                              {"name": "component",  "type": "select",  "label": "Component",
                               "options": [c.value for c in MACDComponent]}]},
    "highest_high": {"params": [{"name": "field",   "type": "select",  "label": "Field",
                                  "options": [f.value for f in PriceField]},
                                 {"name": "period",  "type": "integer", "label": "Period",  "min": 1}]},
    "lowest_low":   {"params": [{"name": "field",   "type": "select",  "label": "Field",
                                  "options": [f.value for f in PriceField]},
                                 {"name": "period",  "type": "integer", "label": "Period",  "min": 1}]},
    "atr":          {"params": [{"name": "period",  "type": "integer", "label": "Period",  "min": 1}]},
    "typical_price": {"params": []},
    "time_of_day":   {"params": []},
}

OPERATOR_OPTIONS = [op.value for op in Operator]
ROLE_OPTIONS     = [r.value for r in RuleRole]