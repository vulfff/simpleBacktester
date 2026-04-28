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
