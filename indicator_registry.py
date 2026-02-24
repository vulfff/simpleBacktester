"""
indicator_registry.py
=====================

Custom composite indicators built as expression trees over existing Operands.

Architecture
------------
IndicatorDef   – a named, serialisable expression tree (stored in DB as JSON)
IndicatorRegistry – singleton that holds all loaded IndicatorDefs
CustomIndicatorOperand – an Operand that looks up a name in the registry
                         and evaluates it; plugs straight into the existing
                         Operand/Condition/Rule pipeline in strategy_rules.py

Expression nodes
----------------
Every node is a dict with a "node" key:

  {"node": "operand", "operand": <operand-dict>}       -- any Operand
  {"node": "const",   "value":   <float>}              -- literal (shorthand)
  {"node": "binop",   "op": "+"|"-"|"*"|"/"|"**"|"%",
                      "left": <node>, "right": <node>}
  {"node": "unop",    "op": "neg"|"abs"|"sqrt"|"log",
                      "operand": <node>}
  {"node": "clamp",   "value": <node>,
                      "lo": <node>, "hi": <node>}
  {"node": "ifelse",  "cond_left":  <node>,
                      "cond_op":    ">"|"<"|">="|"<="|"=="|"!=",
                      "cond_right": <node>,
                      "then":  <node>, "else_": <node>}

This keeps evaluation safe (no eval/exec) while still being very expressive.

Usage
-----
    from indicator_registry import INDICATOR_REGISTRY, IndicatorDef

    # Load saved indicators from the DB at startup:
    INDICATOR_REGISTRY.load([
        {"name": "price_momentum", "expr": {...}, "description": "..."},
        ...
    ])

    # The CustomIndicatorOperand is auto-registered in strategy_rules;
    # just reference it by name in a condition:
    #   {"type": "custom", "name": "price_momentum"}
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Expression tree evaluator
# ---------------------------------------------------------------------------

def _eval_node(node: Dict[str, Any], series) -> float:
    """Recursively evaluate an expression tree node against a PriceSeries."""
    kind = node.get("node")

    if kind == "const":
        return float(node["value"])

    if kind == "operand":
        # Lazy import to avoid circular dependency
        from strategy_rules import Operand
        return Operand.from_dict(node["operand"]).value(series)

    if kind == "binop":
        left  = _eval_node(node["left"],  series)
        right = _eval_node(node["right"], series)
        if math.isnan(left) or math.isnan(right):
            return math.nan
        op = node["op"]
        if op == "+":  return left + right
        if op == "-":  return left - right
        if op == "*":  return left * right
        if op == "/":  return left / right if right != 0 else math.nan
        if op == "**": return left ** right
        if op == "%":  return math.fmod(left, right) if right != 0 else math.nan
        return math.nan

    if kind == "unop":
        v  = _eval_node(node["operand"], series)
        if math.isnan(v):
            return math.nan
        op = node["op"]
        if op == "neg":  return -v
        if op == "abs":  return abs(v)
        if op == "sqrt": return math.sqrt(v) if v >= 0 else math.nan
        if op == "log":  return math.log(v)  if v > 0  else math.nan
        return math.nan

    if kind == "clamp":
        v  = _eval_node(node["value"], series)
        lo = _eval_node(node["lo"],    series)
        hi = _eval_node(node["hi"],    series)
        if any(math.isnan(x) for x in (v, lo, hi)):
            return math.nan
        return max(lo, min(hi, v))

    if kind == "ifelse":
        cl = _eval_node(node["cond_left"],  series)
        cr = _eval_node(node["cond_right"], series)
        if math.isnan(cl) or math.isnan(cr):
            return math.nan
        cond_op = node["cond_op"]
        result = (
            cl >  cr if cond_op == ">"  else
            cl <  cr if cond_op == "<"  else
            cl >= cr if cond_op == ">=" else
            cl <= cr if cond_op == "<=" else
            math.isclose(cl, cr) if cond_op == "==" else
            not math.isclose(cl, cr)
        )
        return _eval_node(node["then"] if result else node["else_"], series)

    return math.nan


# ---------------------------------------------------------------------------
# IndicatorDef  (the stored definition)
# ---------------------------------------------------------------------------

@dataclass
class IndicatorDef:
    name:        str
    expr:        Dict[str, Any]          # expression tree root node
    description: str = ""
    color:       str = "#22d3ee"         # display colour hint for the UI

    def evaluate(self, series) -> float:
        return _eval_node(self.expr, series)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":        self.name,
            "expr":        self.expr,
            "description": self.description,
            "color":       self.color,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "IndicatorDef":
        return IndicatorDef(
            name=d["name"],
            expr=d["expr"],
            description=d.get("description", ""),
            color=d.get("color", "#22d3ee"),
        )


# ---------------------------------------------------------------------------
# IndicatorRegistry  (singleton, loaded once at startup)
# ---------------------------------------------------------------------------

class _IndicatorRegistry:
    def __init__(self) -> None:
        self._indicators: Dict[str, IndicatorDef] = {}

    def load(self, defs: List[Dict[str, Any]]) -> None:
        """Replace all indicators from a list of dicts (called at startup / after save)."""
        self._indicators = {d["name"]: IndicatorDef.from_dict(d) for d in defs}

    def get(self, name: str) -> Optional[IndicatorDef]:
        return self._indicators.get(name)

    def all(self) -> List[IndicatorDef]:
        return list(self._indicators.values())

    def names(self) -> List[str]:
        return list(self._indicators.keys())

    def add_or_replace(self, defn: IndicatorDef) -> None:
        self._indicators[defn.name] = defn

    def remove(self, name: str) -> None:
        self._indicators.pop(name, None)

    def to_list(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._indicators.values()]


INDICATOR_REGISTRY = _IndicatorRegistry()


# ---------------------------------------------------------------------------
# CustomIndicatorOperand  – plug into strategy_rules Operand registry
# ---------------------------------------------------------------------------

def _register_custom_operand() -> None:
    """
    Call once after importing this module to register the 'custom' operand
    type into strategy_rules._OPERAND_REGISTRY.
    """
    from strategy_rules import Operand, _OPERAND_REGISTRY

    from dataclasses import dataclass as _dc

    @_dc
    class CustomIndicatorOperand(Operand):
        _type_tag = "custom"
        name: str = ""

        def value(self, series) -> float:
            defn = INDICATOR_REGISTRY.get(self.name)
            if defn is None:
                return math.nan
            return defn.evaluate(series)

        def to_dict(self) -> Dict[str, Any]:
            return {"type": "custom", "name": self.name}

        @classmethod
        def _from_dict(cls, d: Dict[str, Any]) -> "CustomIndicatorOperand":
            return cls(name=d["name"])

    _OPERAND_REGISTRY["custom"] = CustomIndicatorOperand


_register_custom_operand()


# ---------------------------------------------------------------------------
# Node builder helpers  (used by the API / tests to construct expression trees)
# ---------------------------------------------------------------------------

def node_const(value: float) -> Dict[str, Any]:
    return {"node": "const", "value": value}

def node_operand(operand_dict: Dict[str, Any]) -> Dict[str, Any]:
    return {"node": "operand", "operand": operand_dict}

def node_binop(op: str, left: Dict, right: Dict) -> Dict[str, Any]:
    return {"node": "binop", "op": op, "left": left, "right": right}

def node_unop(op: str, operand: Dict) -> Dict[str, Any]:
    return {"node": "unop", "op": op, "operand": operand}

def node_clamp(value: Dict, lo: Dict, hi: Dict) -> Dict[str, Any]:
    return {"node": "clamp", "value": value, "lo": lo, "hi": hi}

def node_ifelse(cond_left: Dict, cond_op: str, cond_right: Dict,
                then: Dict, else_: Dict) -> Dict[str, Any]:
    return {"node": "ifelse", "cond_left": cond_left, "cond_op": cond_op,
            "cond_right": cond_right, "then": then, "else_": else_}


# ---------------------------------------------------------------------------
# Example / validation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Example: Momentum = mid - mid[5]
    from strategy_rules import PriceSeries, TickData  # type: ignore

    INDICATOR_REGISTRY.load([{
        "name": "momentum_5",
        "description": "Price change over last 5 bars",
        "color": "#34d399",
        "expr": node_binop(
            "-",
            node_operand({"type": "price", "field": "mid"}),
            node_operand({"type": "lookback", "field": "mid", "period": 5}),
        ),
    }])

    print("Registered indicators:", INDICATOR_REGISTRY.names())