"""
tests/test_indicators.py
========================
Phase 3 tests: expression tree nodes, IndicatorDef, IndicatorRegistry,
and CustomIndicatorOperand.
"""
from __future__ import annotations

import math
import sys
import os
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from indicator_registry import (
    _eval_node,
    IndicatorDef,
    INDICATOR_REGISTRY,
)
from strategy_rules import PriceSeries, _OPERAND_REGISTRY, Operand
from tickdata import TickData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tick(i: int, close: float = 100.0, high: float = None,
          low: float = None, open_: float = None) -> TickData:
    c = close
    h = high if high is not None else c * 1.001
    l = low  if low  is not None else c * 0.999
    o = open_ if open_ is not None else c
    return TickData(
        name="X", close=c, open=o, high=h, low=l, volume=1000,
        time=datetime(2024, 1, 1) + timedelta(days=i),
    )


def _make_series(n: int = 20, close: float = 100.0) -> PriceSeries:
    series = PriceSeries()
    for i in range(n):
        series.push(_tick(i, close))
    return series


def _const(v: float) -> dict:
    return {"node": "const", "value": v}


def _binop(op: str, left: dict, right: dict) -> dict:
    return {"node": "binop", "op": op, "left": left, "right": right}


def _unop(op: str, operand: dict) -> dict:
    return {"node": "unop", "op": op, "operand": operand}


def _clamp(value: dict, lo: dict, hi: dict) -> dict:
    return {"node": "clamp", "value": value, "lo": lo, "hi": hi}


def _ifelse(cond_left: dict, cond_op: str, cond_right: dict,
            then: dict, else_: dict) -> dict:
    return {
        "node": "ifelse",
        "cond_left": cond_left,
        "cond_op": cond_op,
        "cond_right": cond_right,
        "then": then,
        "else_": else_,
    }


_NAN = _const(float("nan"))

# Shared series (read-only, reused across node tests)
_SERIES = _make_series(20)


# ---------------------------------------------------------------------------
# TestExprNodeConst
# ---------------------------------------------------------------------------

class TestExprNodeConst:
    def test_const_returns_value(self):
        assert _eval_node(_const(7.5), _SERIES, {}, "") == 7.5

    def test_const_override(self):
        result = _eval_node(_const(1.0), _SERIES, {"value": 99.0}, "")
        assert result == 99.0

    def test_const_zero(self):
        assert _eval_node(_const(0.0), _SERIES, {}, "") == 0.0


# ---------------------------------------------------------------------------
# TestExprNodeBinop
# ---------------------------------------------------------------------------

class TestExprNodeBinop:
    def test_add(self):
        assert _eval_node(_binop("+", _const(3), _const(4)), _SERIES, {}, "") == 7.0

    def test_sub(self):
        assert _eval_node(_binop("-", _const(10), _const(3)), _SERIES, {}, "") == 7.0

    def test_mul(self):
        assert _eval_node(_binop("*", _const(3), _const(4)), _SERIES, {}, "") == 12.0

    def test_div(self):
        assert _eval_node(_binop("/", _const(10), _const(4)), _SERIES, {}, "") == 2.5

    def test_pow(self):
        assert _eval_node(_binop("**", _const(2), _const(3)), _SERIES, {}, "") == 8.0

    def test_mod(self):
        assert _eval_node(_binop("%", _const(10), _const(3)), _SERIES, {}, "") == 1.0

    def test_div_by_zero_nan(self):
        result = _eval_node(_binop("/", _const(5), _const(0)), _SERIES, {}, "")
        assert math.isnan(result)

    def test_mod_by_zero_nan(self):
        result = _eval_node(_binop("%", _const(5), _const(0)), _SERIES, {}, "")
        assert math.isnan(result)

    def test_nan_left_propagates(self):
        result = _eval_node(_binop("+", _NAN, _const(3)), _SERIES, {}, "")
        assert math.isnan(result)

    def test_nan_right_propagates(self):
        result = _eval_node(_binop("+", _const(3), _NAN), _SERIES, {}, "")
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# TestExprNodeUnop
# ---------------------------------------------------------------------------

class TestExprNodeUnop:
    def test_neg(self):
        assert _eval_node(_unop("neg", _const(5)), _SERIES, {}, "") == -5.0

    def test_abs_positive(self):
        assert _eval_node(_unop("abs", _const(5)), _SERIES, {}, "") == 5.0

    def test_abs_negative(self):
        assert _eval_node(_unop("abs", _const(-5)), _SERIES, {}, "") == 5.0

    def test_sqrt_positive(self):
        assert _eval_node(_unop("sqrt", _const(4)), _SERIES, {}, "") == 2.0

    def test_sqrt_negative_nan(self):
        result = _eval_node(_unop("sqrt", _const(-1)), _SERIES, {}, "")
        assert math.isnan(result)

    def test_log_positive(self):
        result = _eval_node(_unop("log", _const(math.e)), _SERIES, {}, "")
        assert abs(result - 1.0) < 1e-9

    def test_log_zero_nan(self):
        result = _eval_node(_unop("log", _const(0)), _SERIES, {}, "")
        assert math.isnan(result)

    def test_log_negative_nan(self):
        result = _eval_node(_unop("log", _const(-1)), _SERIES, {}, "")
        assert math.isnan(result)

    def test_nan_propagates(self):
        result = _eval_node(_unop("neg", _NAN), _SERIES, {}, "")
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# TestExprNodeClamp
# ---------------------------------------------------------------------------

class TestExprNodeClamp:
    def test_below_lo(self):
        result = _eval_node(_clamp(_const(5), _const(10), _const(20)), _SERIES, {}, "")
        assert result == 10.0

    def test_above_hi(self):
        result = _eval_node(_clamp(_const(25), _const(10), _const(20)), _SERIES, {}, "")
        assert result == 20.0

    def test_within_range(self):
        result = _eval_node(_clamp(_const(15), _const(10), _const(20)), _SERIES, {}, "")
        assert result == 15.0

    def test_lo_greater_than_hi(self):
        # max(lo, min(hi, v)) = max(20, min(10, 15)) = max(20, 10) = 20
        result = _eval_node(_clamp(_const(15), _const(20), _const(10)), _SERIES, {}, "")
        assert result == 20.0

    def test_nan_value_propagates(self):
        result = _eval_node(_clamp(_NAN, _const(0), _const(1)), _SERIES, {}, "")
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# TestExprNodeIfelse
# ---------------------------------------------------------------------------

class TestExprNodeIfelse:
    def _ie(self, cl, op, cr, t, e):
        return _ifelse(_const(cl), op, _const(cr), _const(t), _const(e))

    def test_gt_true_branch(self):
        result = _eval_node(self._ie(5, ">", 3, 1, 0), _SERIES, {}, "")
        assert result == 1.0

    def test_gt_false_branch(self):
        result = _eval_node(self._ie(1, ">", 3, 1, 0), _SERIES, {}, "")
        assert result == 0.0

    def test_lt_operator(self):
        result = _eval_node(self._ie(1, "<", 3, 1, 0), _SERIES, {}, "")
        assert result == 1.0

    def test_gte_operator(self):
        result = _eval_node(self._ie(3, ">=", 3, 1, 0), _SERIES, {}, "")
        assert result == 1.0

    def test_lte_operator(self):
        result = _eval_node(self._ie(3, "<=", 3, 1, 0), _SERIES, {}, "")
        assert result == 1.0

    def test_eq_operator(self):
        result = _eval_node(self._ie(5.0, "==", 5.0, 1, 0), _SERIES, {}, "")
        assert result == 1.0

    def test_neq_operator(self):
        result = _eval_node(self._ie(5.0, "!=", 3.0, 1, 0), _SERIES, {}, "")
        assert result == 1.0

    def test_nan_in_cond_left_returns_nan(self):
        node = _ifelse(_NAN, ">", _const(1), _const(1), _const(0))
        result = _eval_node(node, _SERIES, {}, "")
        assert math.isnan(result)

    def test_nan_in_cond_right_returns_nan(self):
        node = _ifelse(_const(1), ">", _NAN, _const(1), _const(0))
        result = _eval_node(node, _SERIES, {}, "")
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# TestIndicatorDef
# ---------------------------------------------------------------------------

class TestIndicatorDef:
    def test_evaluate_const(self, fresh_registry):
        defn = IndicatorDef("x", _const(42.0))
        series = _make_series(5)
        assert defn.evaluate(series) == 42.0

    def test_evaluate_sma_node(self, fresh_registry):
        # SMA(3) on 5 flat bars at 100 → 100.0
        series = _make_series(5, close=100.0)
        sma_node = {"node": "operand", "operand": {"type": "sma", "period": 3, "field": "close"}}
        defn = IndicatorDef("sma3", sma_node)
        result = defn.evaluate(series)
        assert not math.isnan(result)
        assert abs(result - 100.0) < 1e-6

    def test_editable_params_const(self, fresh_registry):
        defn = IndicatorDef("x", _const(5.0))
        params = defn.editable_params
        assert len(params) == 1
        assert params[0]["path"] == "value"

    def test_editable_params_operand(self, fresh_registry):
        sma_node = {"node": "operand", "operand": {"type": "sma", "period": 5, "field": "close"}}
        defn = IndicatorDef("x", sma_node)
        params = defn.editable_params
        paths = [p["path"] for p in params]
        assert any("period" in path for path in paths)

    def test_round_trip(self, fresh_registry):
        sma_node = {"node": "operand", "operand": {"type": "sma", "period": 3, "field": "close"}}
        defn = IndicatorDef("rt", sma_node, description="test", color="#ff0000")
        series = _make_series(10)
        original = defn.evaluate(series)
        restored = IndicatorDef.from_dict(defn.to_dict()).evaluate(series)
        assert abs(original - restored) < 1e-9


# ---------------------------------------------------------------------------
# TestIndicatorRegistry
# ---------------------------------------------------------------------------

class TestIndicatorRegistry:
    def test_load_empty_clears_all(self, fresh_registry):
        fresh_registry.load([{"name": "x", "expr": _const(1.0)}])
        fresh_registry.load([])
        assert fresh_registry.names() == []

    def test_load_replaces_all(self, fresh_registry):
        fresh_registry.load([
            {"name": "a", "expr": _const(1.0)},
            {"name": "b", "expr": _const(2.0)},
        ])
        fresh_registry.load([{"name": "c", "expr": _const(3.0)}])
        assert fresh_registry.names() == ["c"]

    def test_get_returns_correct_def(self, fresh_registry):
        fresh_registry.load([{"name": "myind", "expr": _const(7.0)}])
        defn = fresh_registry.get("myind")
        assert defn is not None
        assert defn.name == "myind"

    def test_get_nonexistent_returns_none(self, fresh_registry):
        assert fresh_registry.get("bogus") is None

    def test_add_or_replace_upserts(self, fresh_registry):
        fresh_registry.add_or_replace(IndicatorDef("x", _const(1.0)))
        fresh_registry.add_or_replace(IndicatorDef("x", _const(99.0)))
        series = _make_series(5)
        assert fresh_registry.get("x").evaluate(series) == 99.0

    def test_add_or_replace_no_affect_others(self, fresh_registry):
        fresh_registry.add_or_replace(IndicatorDef("a", _const(1.0)))
        fresh_registry.add_or_replace(IndicatorDef("b", _const(2.0)))
        fresh_registry.add_or_replace(IndicatorDef("a", _const(99.0)))
        assert "b" in fresh_registry.names()

    def test_remove_deletes(self, fresh_registry):
        fresh_registry.add_or_replace(IndicatorDef("x", _const(5.0)))
        fresh_registry.remove("x")
        assert fresh_registry.get("x") is None

    def test_names_and_all_reflect_state(self, fresh_registry):
        fresh_registry.load([
            {"name": "p", "expr": _const(1.0)},
            {"name": "q", "expr": _const(2.0)},
        ])
        names = fresh_registry.names()
        all_defs = fresh_registry.all()
        assert len(names) == 2
        assert set(names) == {"p", "q"}
        assert len(all_defs) == 2
        assert all(isinstance(d, IndicatorDef) for d in all_defs)


# ---------------------------------------------------------------------------
# TestCustomIndicatorOperand
# ---------------------------------------------------------------------------

class TestCustomIndicatorOperand:
    def _get_cio(self):
        return _OPERAND_REGISTRY["custom"]

    def test_unregistered_name_returns_nan(self, fresh_registry):
        CIO = self._get_cio()
        series = _make_series(5)
        result = CIO(name="missing").value(series)
        assert math.isnan(result)

    def test_registered_returns_correct_value(self, fresh_registry):
        CIO = self._get_cio()
        fresh_registry.add_or_replace(IndicatorDef("const42", _const(42.0)))
        series = _make_series(5)
        result = CIO(name="const42").value(series)
        assert result == 42.0

    def test_to_dict_omits_empty_overrides(self, fresh_registry):
        CIO = self._get_cio()
        d = CIO(name="x", overrides={}).to_dict()
        assert "overrides" not in d

    def test_to_dict_includes_nonempty_overrides(self, fresh_registry):
        CIO = self._get_cio()
        d = CIO(name="x", overrides={"period": 5}).to_dict()
        assert "overrides" in d
        assert d["overrides"] == {"period": 5}

    def test_from_dict_round_trip(self, fresh_registry):
        result = Operand.from_dict({"type": "custom", "name": "foo", "overrides": {"period": 10}})
        assert result.name == "foo"
        assert result.overrides == {"period": 10}

    def test_from_dict_no_overrides(self, fresh_registry):
        result = Operand.from_dict({"type": "custom", "name": "bar"})
        assert result.name == "bar"
        assert result.overrides == {}
