"""
test_custom_indicators_and_strategies.py — Full pipeline tests:
define custom indicators via INDICATOR_REGISTRY, wire into strategies, run backtests.
"""
import json
import math
import pytest

from strategy_rules import PriceSeries, _OPERAND_REGISTRY
from indicator_registry import INDICATOR_REGISTRY, IndicatorDef
from tickdata import TickData
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Node-building helpers
# ---------------------------------------------------------------------------

def _const(v):
    return {"node": "const", "value": float(v)}

def _binop(op, l, r):
    return {"node": "binop", "op": op, "left": l, "right": r}

def _unop(op, x):
    return {"node": "unop", "op": op, "operand": x}

def _clamp(v, lo, hi):
    return {"node": "clamp", "value": v, "lo": _const(lo), "hi": _const(hi)}

def _ifelse(cl, cop, cr, then, else_):
    return {"node": "ifelse", "cond_left": cl, "cond_op": cop,
            "cond_right": cr, "then": then, "else_": else_}

def _operand(type_, **kwargs):
    return {"node": "operand", "operand": {"type": type_, **kwargs}}


CIO = _OPERAND_REGISTRY["custom"]


# ---------------------------------------------------------------------------
# Strategy config helpers
# ---------------------------------------------------------------------------

def _simple_strategy(entry_left, entry_op, entry_right,
                     exit_left, exit_op, exit_right,
                     name="Test", qty=10):
    return {
        "name": name,
        "rules": [
            {
                "name": "Buy", "role": "entry_long",
                "conditions": [{"left": entry_left, "operator": entry_op,
                                 "right": entry_right, "combiner": "and"}],
                "timing": "on_change", "quantity": qty,
            },
            {
                "name": "Sell", "role": "exit_long",
                "conditions": [{"left": exit_left, "operator": exit_op,
                                 "right": exit_right, "combiner": "and"}],
                "timing": "on_change", "quantity": qty,
            },
        ],
    }


def _custom_ref(name):
    return {"type": "custom", "name": name}

def _const_ref(v):
    return {"type": "constant", "value": v}


# ---------------------------------------------------------------------------
# TestFullPipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_momentum_strategy_buys_on_trend(self, price_series_factory, run_backtest, fresh_registry):
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "momentum",
            _binop("-", _operand("price", field="close"), _operand("lookback", field="close", period=5))
        ))
        ticks = price_series_factory("trending_up", 100)
        cfg = _simple_strategy(
            _custom_ref("momentum"), ">", _const_ref(0),
            _custom_ref("momentum"), "<", _const_ref(0),
        )
        eng, port = run_backtest(ticks, cfg)
        assert len(port.trade_log) >= 1

    def test_normalized_rsi_value_range(self, price_series_factory, fresh_registry):
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "norm_rsi",
            _binop("/", _binop("-", _operand("rsi", field="close", period=14), _const(50)), _const(50))
        ))
        ticks = price_series_factory("volatile", 200, seed=42)
        series = PriceSeries()
        for tick in ticks:
            series.push(tick)
            val = INDICATOR_REGISTRY.get("norm_rsi").evaluate(series)
            if not math.isnan(val):
                assert -1.2 <= val <= 1.2, f"norm_rsi={val} out of range"

    def test_band_pos_matches_pct_b(self, price_series_factory, fresh_registry):
        from strategy_rules import BollingerOperand, BollingerComponent, PriceField
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "band_pos",
            _binop("/",
                _binop("-", _operand("price", field="close"),
                            _operand("bollinger", field="close", period=20, std_dev=2.0, component="lower")),
                _binop("-", _operand("bollinger", field="close", period=20, std_dev=2.0, component="upper"),
                            _operand("bollinger", field="close", period=20, std_dev=2.0, component="lower"))
            )
        ))
        pct_b_op = BollingerOperand(field=PriceField.CLOSE, period=20, std_dev=2.0, component=BollingerComponent.PCT_B)
        ticks = price_series_factory("volatile", 60, seed=7)
        series = PriceSeries()
        compared = 0
        for tick in ticks:
            series.push(tick)
            custom_val = INDICATOR_REGISTRY.get("band_pos").evaluate(series)
            native_val = pct_b_op.value(series)
            if not math.isnan(custom_val) and not math.isnan(native_val):
                assert math.isclose(custom_val, native_val, rel_tol=1e-6), \
                    f"band_pos={custom_val} != pct_b={native_val}"
                compared += 1
        assert compared > 0, "No non-NaN bars to compare"

    def test_ifelse_signal_entry(self, price_series_factory, run_backtest, fresh_registry):
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "rsi_signal",
            _ifelse(_operand("rsi", field="close", period=14), ">", _const(70), _const(1), _const(0))
        ))
        ticks = price_series_factory("volatile", 100, seed=42)
        cfg = _simple_strategy(
            _custom_ref("rsi_signal"), "==", _const_ref(1),
            _custom_ref("rsi_signal"), "==", _const_ref(0),
        )
        eng, port = run_backtest(ticks, cfg)
        # Just verify no crash and engine completed
        assert eng._tick_count == 100

    def test_clamped_indicator_in_range(self, price_series_factory, fresh_registry):
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "clamped_rsi",
            _clamp(_operand("rsi", field="close", period=14), 0, 100)
        ))
        ticks = price_series_factory("volatile", 200, seed=42)
        series = PriceSeries()
        for tick in ticks:
            series.push(tick)
            val = INDICATOR_REGISTRY.get("clamped_rsi").evaluate(series)
            if not math.isnan(val):
                assert 0 <= val <= 100, f"clamped_rsi={val} out of [0,100]"

    def test_deeply_nested_no_recursion_error(self, price_series_factory, fresh_registry):
        # Build 6-level nested binop: ((((((close + 1) + 1) + 1) + 1) + 1) + 1)
        expr = _operand("price", field="close")
        for _ in range(6):
            expr = _binop("+", expr, _const(1))
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef("deep_nest", expr))
        ticks = price_series_factory("flat", 10)
        series = PriceSeries()
        for tick in ticks:
            series.push(tick)
        val = INDICATOR_REGISTRY.get("deep_nest").evaluate(series)
        # flat=100, +1 six times = 106
        assert math.isclose(val, 106.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# TestRegistryStateIsolation
# ---------------------------------------------------------------------------

class TestRegistryStateIsolation:

    def test_indicator_visible_within_test(self, fresh_registry):
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef("isolation_test_A", _const(1)))
        assert "isolation_test_A" in INDICATOR_REGISTRY.names()

    def test_indicator_not_visible_from_prior_test(self, fresh_registry):
        # fresh_registry resets between tests — "isolation_test_A" must not be here
        assert "isolation_test_A" not in INDICATOR_REGISTRY.names()

    def test_empty_registry_strategy_runs_zero_trades(self, price_series_factory, run_backtest, fresh_registry):
        # Registry is empty — custom indicator returns nan → condition never fires
        ticks = price_series_factory("trending_up", 50)
        cfg = _simple_strategy(
            _custom_ref("missing_indicator"), ">", _const_ref(0),
            _custom_ref("missing_indicator"), "<", _const_ref(0),
        )
        eng, port = run_backtest(ticks, cfg)
        assert len(port.trade_log) == 0

    def test_add_or_replace_mid_session(self, price_series_factory, run_backtest, fresh_registry):
        # First run: momentum with period=1 (always positive on trending up)
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "dyn_indicator",
            _binop("-", _operand("price", field="close"), _operand("lookback", field="close", period=1))
        ))
        ticks = price_series_factory("trending_up", 50)
        cfg = _simple_strategy(
            _custom_ref("dyn_indicator"), ">", _const_ref(0),
            _custom_ref("dyn_indicator"), "<", _const_ref(0),
        )
        _, port1 = run_backtest(ticks, cfg)

        # Replace indicator with one that never fires (always negative expression)
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "dyn_indicator",
            _const(-999)  # always -999, so > 0 condition never fires
        ))
        _, port2 = run_backtest(ticks, cfg)
        assert len(port2.trade_log) == 0, "Replaced indicator should produce no trades"


# ---------------------------------------------------------------------------
# TestMultiIndicatorStrategies
# ---------------------------------------------------------------------------

class TestMultiIndicatorStrategies:

    def test_and_condition_requires_both(self, price_series_factory, run_backtest, fresh_registry):
        # ind_A: close - 100 (positive on trending_up starting at 100)
        # ind_B: always negative constant
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef("ind_A", _binop("-", _operand("price", field="close"), _const(100))))
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef("ind_B", _const(-1)))  # always negative
        ticks = price_series_factory("trending_up", 60)
        cfg = {
            "name": "AND test",
            "rules": [
                {
                    "name": "Buy", "role": "entry_long",
                    "conditions": [
                        {"left": _custom_ref("ind_A"), "operator": ">", "right": _const_ref(0), "combiner": "and"},
                        {"left": _custom_ref("ind_B"), "operator": ">", "right": _const_ref(0), "combiner": "and"},
                    ],
                    "timing": "on_change", "quantity": 10,
                },
                {
                    "name": "Sell", "role": "exit_long",
                    "conditions": [{"left": _custom_ref("ind_A"), "operator": "<", "right": _const_ref(0), "combiner": "and"}],
                    "timing": "on_change", "quantity": 10,
                },
            ],
        }
        _, port = run_backtest(ticks, cfg)
        # ind_B is always -1, never > 0, so AND condition never fires
        assert len(port.trade_log) == 0

    def test_atr_based_indicator_not_nan(self, price_series_factory, fresh_registry):
        # Regression guard: ATR operand uses high/low — must return non-NaN after warmup
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef("atr5", _operand("atr", period=5)))
        ticks = price_series_factory("trending_up", 50)
        series = PriceSeries()
        found_non_nan = False
        for tick in ticks:
            series.push(tick)
            val = INDICATOR_REGISTRY.get("atr5").evaluate(series)
            if not math.isnan(val):
                found_non_nan = True
                assert val >= 0, f"ATR must be non-negative, got {val}"
        assert found_non_nan, "ATR indicator never returned a non-NaN value — OHLC regression!"


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_sqrt_of_negative_no_crash(self, price_series_factory, run_backtest, fresh_registry):
        # sqrt(close - 200) on data where close < 200 → nan, condition False → no trades
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "sqrt_ind",
            _unop("sqrt", _binop("-", _operand("price", field="close"), _const(200)))
        ))
        ticks = price_series_factory("flat", 30, price=100.0)
        cfg = _simple_strategy(
            _custom_ref("sqrt_ind"), ">", _const_ref(0),
            _custom_ref("sqrt_ind"), "<", _const_ref(0),
        )
        eng, port = run_backtest(ticks, cfg)
        assert eng._tick_count == 30

    def test_division_by_nan_during_warmup_no_crash(self, price_series_factory, run_backtest, fresh_registry):
        # close / sma(20) — before 20 bars SMA is nan → nan result → no trades
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "close_div_sma",
            _binop("/", _operand("price", field="close"), _operand("sma", field="close", period=20))
        ))
        ticks = price_series_factory("trending_up", 10)
        cfg = _simple_strategy(
            _custom_ref("close_div_sma"), ">", _const_ref(1.01),
            _custom_ref("close_div_sma"), "<", _const_ref(0.99),
        )
        eng, port = run_backtest(ticks, cfg)
        assert eng._tick_count == 10
        assert len(port.trade_log) == 0  # SMA not warmed up yet

    def test_log_of_negative_no_crash(self, price_series_factory, run_backtest, fresh_registry):
        # log(close - 200) where close < 200 → nan → no crash
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "log_ind",
            _unop("log", _binop("-", _operand("price", field="close"), _const(200)))
        ))
        ticks = price_series_factory("flat", 20, price=100.0)
        cfg = _simple_strategy(
            _custom_ref("log_ind"), ">", _const_ref(0),
            _custom_ref("log_ind"), "<", _const_ref(0),
        )
        eng, port = run_backtest(ticks, cfg)
        assert eng._tick_count == 20


# ---------------------------------------------------------------------------
# TestSerialisationRoundTrips
# ---------------------------------------------------------------------------

class TestSerialisationRoundTrips:

    def test_json_round_trip_same_trade_count(self, price_series_factory, run_backtest, fresh_registry):
        INDICATOR_REGISTRY.add_or_replace(IndicatorDef(
            "momentum_rt",
            _binop("-", _operand("price", field="close"), _operand("lookback", field="close", period=3))
        ))
        ticks = price_series_factory("trending_up", 60)
        cfg = _simple_strategy(
            _custom_ref("momentum_rt"), ">", _const_ref(0),
            _custom_ref("momentum_rt"), "<", _const_ref(0),
        )
        cfg_rt = json.loads(json.dumps(cfg))
        _, port1 = run_backtest(ticks, cfg)
        # Re-register (run_backtest creates a new strategy object each time)
        _, port2 = run_backtest(ticks, cfg_rt)
        assert len(port1.trade_log) == len(port2.trade_log)

    def test_to_dict_omits_empty_overrides(self, fresh_registry):
        op = CIO(name="x", overrides={})
        d = op.to_dict()
        assert "overrides" not in d

    def test_to_dict_includes_nonempty_overrides(self, fresh_registry):
        op = CIO(name="x", overrides={"period": 5})
        d = op.to_dict()
        assert "overrides" in d
        assert d["overrides"]["period"] == 5
