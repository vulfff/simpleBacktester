# tests/test_strategy_dsl.py
"""Tests for DSL parser utility functions in ai_strategy_builder."""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import will fail until Task 2 adds these — that's expected.
from ai_strategy_builder import (
    _split_by_comma_respecting_quotes,
    _parse_operand,
    _split_condition,
)


# ── _split_by_comma_respecting_quotes ────────────────────────────────────────

def test_split_simple():
    assert _split_by_comma_respecting_quotes("a, b, c") == ["a", "b", "c"]

def test_split_quoted_name_not_split():
    # Comma inside quoted string must not split
    result = _split_by_comma_respecting_quotes('custom("RSI, Vol"), stop_loss_pct=2')
    assert result == ['custom("RSI, Vol")', "stop_loss_pct=2"]

def test_split_parens_not_split():
    # Comma inside parens must not split
    result = _split_by_comma_respecting_quotes("sma(close,50) cross_above sma(close,200), bars_held=10")
    assert result == ["sma(close,50) cross_above sma(close,200)", "bars_held=10"]

def test_split_empty_items_ignored():
    assert _split_by_comma_respecting_quotes("a,,b") == ["a", "b"]


# ── _parse_operand ────────────────────────────────────────────────────────────

def test_parse_bare_integer():
    assert _parse_operand("30") == {"type": "constant", "value": 30.0}

def test_parse_bare_float():
    assert _parse_operand("1.5") == {"type": "constant", "value": 1.5}

def test_parse_negative_number():
    assert _parse_operand("-100") == {"type": "constant", "value": -100.0}

def test_parse_sma():
    assert _parse_operand("sma(close,50)") == {"type": "sma", "field": "close", "period": 50}

def test_parse_ema():
    assert _parse_operand("ema(high,20)") == {"type": "ema", "field": "high", "period": 20}

def test_parse_rsi_short():
    assert _parse_operand("rsi(14)") == {"type": "rsi", "field": "close", "period": 14}

def test_parse_rsi_with_field():
    assert _parse_operand("rsi(high,14)") == {"type": "rsi", "field": "high", "period": 14}

def test_parse_macd():
    result = _parse_operand("macd(12,26,9,hist)")
    assert result == {"type": "macd", "fast": 12, "slow": 26, "signal": 9, "component": "hist"}

def test_parse_bollinger():
    result = _parse_operand("bollinger(close,20,2,upper)")
    assert result == {"type": "bollinger", "field": "close", "period": 20, "std_dev": 2.0, "component": "upper"}

def test_parse_atr():
    assert _parse_operand("atr(14)") == {"type": "atr", "period": 14}

def test_parse_highest_high():
    assert _parse_operand("highest_high(high,20)") == {"type": "highest_high", "field": "high", "period": 20}

def test_parse_lowest_low():
    assert _parse_operand("lowest_low(low,10)") == {"type": "lowest_low", "field": "low", "period": 10}

def test_parse_typical_price():
    assert _parse_operand("typical_price()") == {"type": "typical_price"}

def test_parse_price():
    assert _parse_operand("price(close)") == {"type": "price", "field": "close"}

def test_parse_lookback():
    assert _parse_operand("lookback(close,5)") == {"type": "lookback", "field": "close", "period": 5}

def test_parse_time_of_day():
    assert _parse_operand("time_of_day()") == {"type": "time_of_day"}

def test_parse_custom_no_overrides():
    assert _parse_operand('custom("RSI Oversold")') == {"type": "custom", "name": "RSI Oversold"}

def test_parse_custom_with_overrides():
    result = _parse_operand('custom("RSI Oversold", period=10, threshold=25)')
    assert result == {
        "type": "custom",
        "name": "RSI Oversold",
        "overrides": {"period": 10.0, "threshold": 25.0},
    }

def test_parse_unknown_operand_raises():
    with pytest.raises(ValueError, match="Unknown operand type"):
        _parse_operand("mystery(close,5)")


# ── _split_condition ──────────────────────────────────────────────────────────

def test_split_gt():
    left, op, right = _split_condition("rsi(14) > 30")
    assert left == "rsi(14)" and op == ">" and right == "30"

def test_split_cross_above():
    left, op, right = _split_condition("sma(close,50) cross_above sma(close,200)")
    assert left == "sma(close,50)" and op == "cross_above" and right == "sma(close,200)"

def test_split_cross_below():
    left, op, right = _split_condition("price(close) cross_below lowest_low(low,10)")
    assert left == "price(close)" and op == "cross_below" and right == "lowest_low(low,10)"

def test_split_gte():
    left, op, right = _split_condition("time_of_day() >= 570")
    assert left == "time_of_day()" and op == ">=" and right == "570"

def test_split_no_operator_raises():
    with pytest.raises(ValueError, match="No operator"):
        _split_condition("rsi(14) something weird")


# ── parse_dsl_to_strategy ─────────────────────────────────────────────────────

from ai_strategy_builder import parse_dsl_to_strategy


def test_golden_cross_basic():
    dsl = """
name: Golden Cross
entry_long: sma(close,50) cross_above sma(close,200)
exit_long: sma(close,50) cross_below sma(close,200)
"""
    result = parse_dsl_to_strategy(dsl)
    assert result["name"] == "Golden Cross"
    assert len(result["rules"]) == 2

    entry = result["rules"][0]
    assert entry["role"] == "entry_long"
    assert entry["name"] == "Entry Long 1"
    assert entry["timing"] == "on_change"
    assert entry["quantity"] == 1.0
    assert len(entry["conditions"]) == 1
    c = entry["conditions"][0]
    assert c["kind"] == "signal"
    assert c["left"] == {"type": "sma", "field": "close", "period": 50}
    assert c["operator"] == "cross_above"
    assert c["right"] == {"type": "sma", "field": "close", "period": 200}
    assert c["combiner"] == "and"

    ex = result["rules"][1]
    assert ex["role"] == "exit_long"
    assert ex["name"] == "Exit Long 1"


def test_and_within_rule():
    dsl = """
name: RSI + Trend
entry_long: rsi(14) < 30 and sma(close,50) > sma(close,200)
exit_long: rsi(14) > 70
"""
    result = parse_dsl_to_strategy(dsl)
    entry = result["rules"][0]
    assert len(entry["conditions"]) == 2
    assert entry["conditions"][0]["left"] == {"type": "rsi", "field": "close", "period": 14}
    assert entry["conditions"][0]["operator"] == "<"
    assert entry["conditions"][0]["right"] == {"type": "constant", "value": 30.0}
    assert entry["conditions"][1]["left"] == {"type": "sma", "field": "close", "period": 50}
    assert entry["conditions"][1]["operator"] == ">"


def test_comma_creates_separate_rules():
    dsl = """
name: OR Test
exit_long: rsi(14) > 70, bars_held=10
"""
    result = parse_dsl_to_strategy(dsl)
    assert len(result["rules"]) == 2
    assert result["rules"][0]["role"] == "exit_long"
    assert result["rules"][0]["name"] == "Exit Long 1"
    assert result["rules"][0]["conditions"][0]["kind"] == "signal"
    assert result["rules"][1]["role"] == "exit_long"
    assert result["rules"][1]["name"] == "Exit Long 2"
    assert result["rules"][1]["conditions"][0]["kind"] == "exit_condition"
    assert result["rules"][1]["conditions"][0]["exitType"] == "bars_held"
    assert result["rules"][1]["conditions"][0]["value"] == 10.0


def test_exit_condition_stop_and_profit():
    dsl = """
name: Exit Conds
entry_long: rsi(14) < 30
exit_long: stop_loss_pct=3, take_profit_pct=8
"""
    result = parse_dsl_to_strategy(dsl)
    exits = [r for r in result["rules"] if r["role"] == "exit_long"]
    assert len(exits) == 2
    types = {r["conditions"][0]["exitType"] for r in exits}
    assert types == {"stop_loss_pct", "take_profit_pct"}
    values = {r["conditions"][0]["exitType"]: r["conditions"][0]["value"] for r in exits}
    assert values["stop_loss_pct"] == 3.0
    assert values["take_profit_pct"] == 8.0


def test_timing_override():
    dsl = """
name: Timing Test
entry_long: rsi(14) < 30, timing=every_tick
exit_long: rsi(14) > 70
"""
    result = parse_dsl_to_strategy(dsl)
    entry = result["rules"][0]
    assert entry["timing"] == "every_tick"
    ex = result["rules"][1]
    assert ex["timing"] == "on_change"


def test_custom_indicator_no_overrides():
    dsl = """
name: Custom Test
entry_long: custom("RSI Oversold") > 0
exit_long: stop_loss_pct=3
"""
    result = parse_dsl_to_strategy(dsl)
    entry = result["rules"][0]
    assert entry["conditions"][0]["left"] == {"type": "custom", "name": "RSI Oversold"}


def test_custom_indicator_with_overrides():
    dsl = """
name: Custom Override
entry_long: custom("RSI Oversold", period=10, threshold=25) > 0
exit_long: stop_loss_pct=2
"""
    result = parse_dsl_to_strategy(dsl)
    left = result["rules"][0]["conditions"][0]["left"]
    assert left["type"] == "custom"
    assert left["name"] == "RSI Oversold"
    assert left["overrides"] == {"period": 10.0, "threshold": 25.0}


def test_short_strategy():
    dsl = """
name: Short Test
entry_short: rsi(14) > 70
exit_short: rsi(14) < 30, stop_loss_pct=2
"""
    result = parse_dsl_to_strategy(dsl)
    roles = [r["role"] for r in result["rules"]]
    assert "entry_short" in roles
    assert "exit_short" in roles
    assert len(result["rules"]) == 3  # 1 entry + 1 signal exit + 1 stop loss


def test_auto_naming_multiple_rules_same_role():
    dsl = """
name: Multi
entry_long: rsi(14) < 30, price(close) > sma(close,200)
exit_long: rsi(14) > 70
"""
    result = parse_dsl_to_strategy(dsl)
    entries = [r for r in result["rules"] if r["role"] == "entry_long"]
    assert entries[0]["name"] == "Entry Long 1"
    assert entries[1]["name"] == "Entry Long 2"


def test_default_name_when_missing():
    dsl = "entry_long: rsi(14) < 30\nexit_long: rsi(14) > 70"
    result = parse_dsl_to_strategy(dsl)
    assert result["name"] == "AI Strategy"


def test_time_of_day_operand():
    dsl = """
name: Time Filter
entry_long: rsi(14) < 30 and time_of_day() >= 570
exit_long: stop_loss_pct=2
"""
    result = parse_dsl_to_strategy(dsl)
    conds = result["rules"][0]["conditions"]
    assert conds[1]["left"] == {"type": "time_of_day"}
    assert conds[1]["operator"] == ">="
    assert conds[1]["right"] == {"type": "constant", "value": 570.0}
