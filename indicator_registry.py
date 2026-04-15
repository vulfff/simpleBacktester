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

def _pfx(path: str, key: str) -> str:
    """Extend a dot-separated path key."""
    return f"{path}.{key}" if path else key


def _eval_node(node: Dict[str, Any], series, overrides: Optional[Dict[str, float]] = None, path: str = "") -> float:
    """Recursively evaluate an expression tree node against a PriceSeries."""
    kind = node.get("node")
    ov = overrides or {}

    if kind == "const":
        k = path or "value"
        return float(ov.get(k, node["value"]))

    if kind == "operand":
        # Lazy import to avoid circular dependency
        from strategy_rules import Operand
        op = dict(node["operand"])  # shallow copy so we don't mutate the stored tree
        op_type = op.get("type", "")
        for param in ("period", "fast", "slow", "signal"):
            k = _pfx(path, f"operand.{param}")
            if k in ov:
                op[param] = max(1, int(round(ov[k])))
        k_std = _pfx(path, "operand.std_dev")
        if k_std in ov:
            op["std_dev"] = max(0.01, float(ov[k_std]))
        return Operand.from_dict(op).value(series)

    if kind == "binop":
        left  = _eval_node(node["left"],  series, ov, _pfx(path, "left"))
        right = _eval_node(node["right"], series, ov, _pfx(path, "right"))
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
        v = _eval_node(node["operand"], series, ov, _pfx(path, "operand"))
        if math.isnan(v):
            return math.nan
        op = node["op"]
        if op == "neg":  return -v
        if op == "abs":  return abs(v)
        if op == "sqrt": return math.sqrt(v) if v >= 0 else math.nan
        if op == "log":  return math.log(v)  if v > 0  else math.nan
        return math.nan

    if kind == "clamp":
        v  = _eval_node(node["value"], series, ov, _pfx(path, "value"))
        lo = _eval_node(node["lo"],    series, ov, _pfx(path, "lo"))
        hi = _eval_node(node["hi"],    series, ov, _pfx(path, "hi"))
        if any(math.isnan(x) for x in (v, lo, hi)):
            return math.nan
        return max(lo, min(hi, v))

    if kind == "ifelse":
        cl = _eval_node(node["cond_left"],  series, ov, _pfx(path, "cond_left"))
        cr = _eval_node(node["cond_right"], series, ov, _pfx(path, "cond_right"))
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
        branch = "then" if result else "else_"
        return _eval_node(node[branch], series, ov, _pfx(path, branch))

    return math.nan


# ---------------------------------------------------------------------------
# extract_editable_params  (returns a flat list of tweakable fields)
# ---------------------------------------------------------------------------

_PATH_LABELS: Dict[str, str] = {
    "cond_right": "Threshold",
    "cond_left":  "Left value",
    "then":       "True value",
    "else_":      "False value",
    "lo":         "Min",
    "hi":         "Max",
    "value":      "Value",
    "left":       "Left operand",
    "right":      "Right operand",
}

_OPERAND_NUMERIC_PARAMS = ("period", "fast", "slow", "signal", "std_dev")


def _label_from_path(path: str) -> str:
    if not path:
        return "Value"
    last = path.split(".")[-1]
    return _PATH_LABELS.get(last, last.replace("_", " ").title())


def extract_editable_params(expr: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
    """
    Walk an expression tree and return a flat list of editable numeric fields:
      [{path, label, default_value, param_type}]
    'path' uniquely identifies each field for use as an override key.
    """
    kind = expr.get("node")
    results: List[Dict[str, Any]] = []

    if kind == "const":
        k = path or "value"
        results.append({
            "path":          k,
            "label":         _label_from_path(path),
            "default_value": float(expr["value"]),
            "param_type":    "float",
        })

    elif kind == "operand":
        op = expr.get("operand", {})
        op_type = op.get("type", "operand").upper()
        for param in _OPERAND_NUMERIC_PARAMS:
            if param in op:
                k = _pfx(path, f"operand.{param}")
                label = f"{op_type} {param.replace('_', ' ')}"
                results.append({
                    "path":          k,
                    "label":         label,
                    "default_value": float(op[param]),
                    "param_type":    "float" if param == "std_dev" else "int",
                })

    elif kind == "binop":
        results.extend(extract_editable_params(expr["left"],  _pfx(path, "left")))
        results.extend(extract_editable_params(expr["right"], _pfx(path, "right")))

    elif kind == "unop":
        results.extend(extract_editable_params(expr["operand"], _pfx(path, "operand")))

    elif kind == "clamp":
        results.extend(extract_editable_params(expr["value"], _pfx(path, "value")))
        results.extend(extract_editable_params(expr["lo"],    _pfx(path, "lo")))
        results.extend(extract_editable_params(expr["hi"],    _pfx(path, "hi")))

    elif kind == "ifelse":
        results.extend(extract_editable_params(expr["cond_left"],  _pfx(path, "cond_left")))
        results.extend(extract_editable_params(expr["cond_right"], _pfx(path, "cond_right")))
        results.extend(extract_editable_params(expr["then"],       _pfx(path, "then")))
        results.extend(extract_editable_params(expr["else_"],      _pfx(path, "else_")))

    return results


# ---------------------------------------------------------------------------
# IndicatorDef  (the stored definition)
# ---------------------------------------------------------------------------

@dataclass
class IndicatorDef:
    name:        str
    expr:        Dict[str, Any]          # expression tree root node
    description: str = ""
    color:       str = "#22d3ee"         # display colour hint for the UI

    def evaluate(self, series, overrides: Optional[Dict[str, float]] = None) -> float:
        return _eval_node(self.expr, series, overrides or {}, "")

    @property
    def editable_params(self) -> List[Dict[str, Any]]:
        return extract_editable_params(self.expr)

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
        overrides: Dict[str, float] = field(default_factory=dict)

        def value(self, series) -> float:
            defn = INDICATOR_REGISTRY.get(self.name)
            if defn is None:
                return math.nan
            return defn.evaluate(series, overrides=self.overrides)

        def to_dict(self) -> Dict[str, Any]:
            d: Dict[str, Any] = {"type": "custom", "name": self.name}
            if self.overrides:
                d["overrides"] = self.overrides
            return d

        @classmethod
        def _from_dict(cls, d: Dict[str, Any]) -> "CustomIndicatorOperand":
            return cls(name=d["name"], overrides=d.get("overrides", {}))

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
    # Example: Momentum = close - close[5]
    from strategy_rules import PriceSeries, TickData  # type: ignore

    INDICATOR_REGISTRY.load([{
        "name": "momentum_5",
        "description": "Price change over last 5 bars",
        "color": "#34d399",
        "expr": node_binop(
            "-",
            node_operand({"type": "price", "field": "close"}),
            node_operand({"type": "lookback", "field": "close", "period": 5}),
        ),
    }])

    print("Registered indicators:", INDICATOR_REGISTRY.names())