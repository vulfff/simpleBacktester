"""
ai_indicator_builder.py – AI-powered indicator generation

Converts natural language indicator descriptions into expression tree JSON
that can be composed with existing operands.

Supports all standard technical indicators and mathematical operations:
- SMA, EMA, RSI, MACD, Bollinger Bands
- Custom expressions with +, -, *, /, **, sqrt, abs, log
- Conditions and clamps

Usage:
    from ai_indicator_builder import build_indicator_from_prompt
    
    indicator = build_indicator_from_prompt(
        user_prompt="RSI oversold: RSI(14) when it drops below 30"
    )
    print(indicator)  # Valid indicator expression JSON
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

INDICATOR_SYSTEM_PROMPT = """You are an expert technical analysis specialist. Your task is to convert natural language descriptions of trading indicators into valid JSON expression tree structures.

## Available Building Blocks

### Basic Operands (leaf nodes)
- `price`: Current OHLCV price (fields: bid, ask, mid, high, low, volume)
- `lookback`: Price from N bars ago (field, period)
- `sma`: Simple moving average (fields: mid/bid/ask/high/low/volume, period)
- `ema`: Exponential moving average (fields: mid/bid/ask/high/low/volume, period)
- `rsi`: Relative strength index (fields: mid/bid/ask/high/low/volume, period)
- `macd`: MACD indicator (fast, slow, signal periods, component: macd/signal/hist)
- `bollinger`: Bollinger bands (field, period, std_dev, component: upper/middle/lower/width/pct_b)
- `highest_high`: Rolling maximum of a field over N bars (field: high/low/mid/…, period). Use for Donchian channels, Williams %R, Stochastics.
- `lowest_low`: Rolling minimum of a field over N bars (field: high/low/mid/…, period). Use for Donchian channels, Williams %R, Stochastics.
- `atr`: Average True Range over N bars (period). TR = max(H-L, |H-prev_close|, |L-prev_close|). No field param.
- `typical_price`: (High + Low + Close) / 3. No parameters. Useful as CCI price basis.

### Operand JSON Structure
All operands follow this pattern in the expression tree:
```json
{ "node": "operand", "operand": { "type": "sma", "field": "close", "period": 20 } }
{ "node": "operand", "operand": { "type": "highest_high", "field": "high", "period": 14 } }
{ "node": "operand", "operand": { "type": "atr", "period": 14 } }
{ "node": "operand", "operand": { "type": "typical_price" } }
```

Constant values:
```json
{ "node": "const", "value": 30 }
```

### Mathematical Operations

**Binary Operations** (addition, subtraction, multiplication, etc.):
```json
{
  "node": "binop",
  "op": "+",
  "left": { "node": "operand", "operand": { "type": "sma", "field": "close", "period": 20 } },
  "right": { "node": "const", "value": 100 }
}
```

Available operators: `+`, `-`, `*`, `/`, `**` (power), `%` (modulo)

**Unary Operations** (negation, absolute value, square root, logarithm):
```json
{
  "node": "unop",
  "op": "abs",
  "operand": { "node": "operand", "operand": { "type": "rsi", "field": "close", "period": 14 } }
}
```

Available unary ops: `neg` (negate), `abs` (absolute), `sqrt` (square root), `log` (natural log)

**Clamping** (constrain value within bounds):
```json
{
  "node": "clamp",
  "value": { "node": "operand", "operand": { "type": "rsi", "field": "close", "period": 14 } },
  "lo": { "node": "const", "value": 0 },
  "hi": { "node": "const", "value": 100 }
}
```

**Conditional** (if-then-else):
```json
{
  "node": "ifelse",
  "cond_left": { "node": "operand", "operand": { "type": "rsi", "field": "close", "period": 14 } },
  "cond_op": ">",
  "cond_right": { "node": "const", "value": 70 },
  "then": { "node": "const", "value": 1 },
  "else_": { "node": "const", "value": 0 }
}
```

Available condition operators: `>`, `<`, `>=`, `<=`, `==`, `!=`

## Common Indicator Examples

### Simple RSI (Oversold Indicator)
Description: "RSI-based oversold indicator that returns 1 when oversold, 0 otherwise"
```json
{
  "name": "RSI Oversold",
  "description": "Returns 1 when RSI(14) is below 30 (oversold signal)",
  "expr": {
    "node": "ifelse",
    "cond_left": { "node": "operand", "operand": { "type": "rsi", "field": "close", "period": 14 } },
    "cond_op": "<",
    "cond_right": { "node": "const", "value": 30 },
    "then": { "node": "const", "value": 1 },
    "else_": { "node": "const", "value": 0 }
  },
  "color": "#3b82f6"
}
```

### Moving Average Stretched (Deviation)
Description: "How far is price from its 20-period moving average, as a percentage"
```json
{
  "name": "MA Deviation %",
  "description": "Percentage distance from 20-period SMA",
  "expr": {
    "node": "binop",
    "op": "*",
    "left": {
      "node": "binop",
      "op": "/",
      "left": {
        "node": "binop",
        "op": "-",
        "left": { "node": "operand", "operand": { "type": "price", "field": "close" } },
        "right": { "node": "operand", "operand": { "type": "sma", "field": "close", "period": 20 } }
      },
      "right": { "node": "operand", "operand": { "type": "sma", "field": "close", "period": 20 } }
    },
    "right": { "node": "const", "value": 100 }
  },
  "color": "#8b5cf6"
}
```

### RSI Normalized (0-1)
Description: "RSI scaled from 0-100 range to 0-1 range"
```json
{
  "name": "RSI Normalized",
  "description": "RSI(14) divided by 100 to get 0-1 range",
  "expr": {
    "node": "binop",
    "op": "/",
    "left": { "node": "operand", "operand": { "type": "rsi", "field": "close", "period": 14 } },
    "right": { "node": "const", "value": 100 }
  },
  "color": "#ec4899"
}
```

### Williams %R
Description: "Williams Percent Range — measures overbought/oversold on a -100 to 0 scale"
```json
{
  "name": "Williams %R",
  "description": "Momentum oscillator ranging from -100 to 0. Near 0 = overbought, near -100 = oversold.",
  "expr": {
    "node": "binop", "op": "*",
    "left": {
      "node": "binop", "op": "/",
      "left": {
        "node": "binop", "op": "-",
        "left":  { "node": "operand", "operand": { "type": "highest_high", "field": "high", "period": 14 } },
        "right": { "node": "operand", "operand": { "type": "price", "field": "close" } }
      },
      "right": {
        "node": "binop", "op": "-",
        "left":  { "node": "operand", "operand": { "type": "highest_high", "field": "high", "period": 14 } },
        "right": { "node": "operand", "operand": { "type": "lowest_low",   "field": "low",  "period": 14 } }
      }
    },
    "right": { "node": "const", "value": -100 }
  },
  "color": "#f59e0b"
}
```

### ATR-Based Volatility Filter
Description: "Raw ATR(14) — useful as a stop-distance or volatility filter"
```json
{
  "name": "ATR(14)",
  "description": "Average True Range over 14 bars — measures market volatility",
  "expr": { "node": "operand", "operand": { "type": "atr", "period": 14 } },
  "color": "#f472b6"
}
```

### Momentum (Price Change)
Description: "Price change from N bars ago as percentage"
```json
{
  "name": "Momentum %",
  "description": "Percentage change in price over last 5 bars",
  "expr": {
    "node": "binop",
    "op": "*",
    "left": {
      "node": "binop",
      "op": "/",
      "left": {
        "node": "binop",
        "op": "-",
        "left": { "node": "operand", "operand": { "type": "price", "field": "close" } },
        "right": { "node": "operand", "operand": { "type": "lookback", "field": "close", "period": 5 } }
      },
      "right": { "node": "operand", "operand": { "type": "lookback", "field": "close", "period": 5 } }
    },
    "right": { "node": "const", "value": 100 }
  },
  "color": "#10b981"
}
```

### SMA Crossover Spread (normalised by ATR)
Description: "Difference between a fast and slow SMA, normalised by ATR so scale is comparable across assets"
```json
{
  "name": "SMA Cross / ATR",
  "description": "(SMA20 - SMA50) divided by ATR(14) — normalised trend signal",
  "expr": {
    "node": "binop", "op": "/",
    "left": {
      "node": "binop", "op": "-",
      "left":  { "node": "operand", "operand": { "type": "sma", "field": "close", "period": 20 } },
      "right": { "node": "operand", "operand": { "type": "sma", "field": "close", "period": 50 } }
    },
    "right": { "node": "operand", "operand": { "type": "atr", "period": 14 } }
  },
  "color": "#22d3ee"
}
```

## Parameter Overridability

When users reference a custom indicator in a strategy, they can **override** any `const` value or operand parameter (period, std_dev, fast/slow/signal) without rebuilding the indicator. This means:

- **Put thresholds and multipliers in `const` nodes** — e.g. `{"node": "const", "value": 30}` for an RSI threshold — so users can change the threshold per strategy use.
- **Use explicit `period` parameters** in all operands (never omit them) — users can override periods per use.
- **Avoid computing values that belong as constants** — don't write `{"node": "binop", "op": "+", "left": {"node": "const", "value": 29}, "right": {"node": "const", "value": 1}}` when you mean `{"node": "const", "value": 30}`.

This design means a single "RSI Oversold" indicator can be used in many strategies with different thresholds and periods, each set independently via overrides.

## Important Rules

1. **Always return valid JSON** — no markdown, no explanations, no code fences.
2. **Use correct node types**: `"operand"`, `"const"`, `"binop"`, `"unop"`, `"clamp"`, `"ifelse"`.
3. **Every operand must be wrapped** in `{"node": "operand", "operand": {...}}`.
4. **Constants use** `{"node": "const", "value": number}` — must be a real number, not a placeholder.
5. **All operand parameters must be explicit and correct** — never omit any field:
   - `sma`, `ema`, `rsi`, `lookback`, `highest_high`, `lowest_low`: always include both `"field"` and `"period"`.
   - `bollinger`: always include `"field"`, `"period"`, `"std_dev"`, and `"component"`.
   - `macd`: always include `"fast"`, `"slow"`, `"signal"`, and `"component"`.
   - `atr`: always include `"period"` (no field).
   - `price`: always include `"field"`.
   - `typical_price`: no parameters needed.
6. **Period values must match the user's intent** — if the user says "20-bar SMA", use `"period": 20`. Never default to 1 or 0.
7. **`const` values must be intentional** — use `0` only when zero is literally the correct value (e.g., a lower bound). Scale factors, multipliers, and thresholds must be real, meaningful numbers.
8. **Binary operations require both `left` and `right`**; unary operations require `"operand"`.
9. **Operator precedence is enforced by nesting, not by order.** If you need `(A + B) / C`, the `+` binop must be the `left` child of the `/` binop. Never assume sibling nodes are parenthesised automatically — nest explicitly.
10. **Avoid division by zero** — guard with a clamp or ifelse when the denominator might be zero.
11. **Color must be hex** like `"#3b82f6"`.
12. **Name and description must be user-friendly** — short name, one-sentence description.
13. **Expression must be recursive and well-formed** — validate every branch before returning.

## Your Task
1. Analyse the user's natural language description.
2. Identify all indicators/operands needed and their correct parameters (periods, fields, components).
3. Identify all mathematical operations and logic.
4. Build the correct nested expression tree with every parameter explicit.
5. Return ONLY valid JSON — no markdown code blocks, no explanations.

The JSON must include:
- `name`: Short indicator name
- `description`: What this indicator does (one sentence)
- `expr`: The expression tree (required)
- `color`: Hex color for UI display (optional, defaults to blue)
"""


def build_indicator_from_prompt(user_prompt: str, provider=None, language_directive: str = "") -> Dict[str, Any]:
    """
    Build an indicator expression from natural language using configured AI provider.

    Args:
        user_prompt: Natural language indicator description
        provider: Optional pre-configured provider. If None, reads from database.
        language_directive: Optional suffix appended to the system prompt instructing
            the model which natural language to respond in (for name/description prose).

    Returns:
        Dictionary with name, description, expr, and color
    """
    if provider is None:
        from ai_strategy_builder import get_ai_provider
        provider = get_ai_provider()

    try:
        # Call the API with the indicator-specific system prompt.
        # Uses _call_api directly so we get raw text without strategy validation.
        raw_text = provider._call_api(
            user_prompt=f"Create an indicator from this description:\n\n{user_prompt}",
            system_prompt=INDICATOR_SYSTEM_PROMPT + language_directive,
            temperature=0.5,
        )

        # Extract JSON (handles markdown fences and trailing text)
        response_json = provider._extract_json(raw_text)

        # Check if AI accidentally returned a strategy format instead
        if "rules" in response_json:
            raise ValueError("AI generated a strategy instead of an indicator. Try a simpler description.")

        # Validate required indicator fields
        for field in ("name", "expr"):
            if field not in response_json:
                raise ValueError(f"Generated indicator missing required field: {field}")

        response_json.setdefault("description", "")
        response_json.setdefault("color", "#3b82f6")

        # Validate expression tree structure
        _validate_expression_node(response_json["expr"])

        return response_json

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to generate indicator: {e}")


def _validate_expression_node(node: Any, depth: int = 0) -> None:
    """Recursively validate expression tree structure."""
    if depth > 50:
        raise ValueError("Expression tree too deeply nested (max 50 levels)")
    
    if not isinstance(node, dict):
        raise ValueError("Expression node must be a dictionary")
    
    node_type = node.get("node")
    
    if node_type == "const":
        if "value" not in node or not isinstance(node["value"], (int, float)):
            raise ValueError("const node must have numeric 'value'")
    
    elif node_type == "operand":
        if "operand" not in node or not isinstance(node["operand"], dict):
            raise ValueError("operand node must have 'operand' dict")
        operand = node["operand"]
        if "type" not in operand:
            raise ValueError("operand must have 'type' field")
    
    elif node_type == "binop":
        if "op" not in node or node["op"] not in ["+", "-", "*", "/", "**", "%"]:
            raise ValueError(f"Invalid binary operator: {node.get('op')}")
        if "left" not in node or "right" not in node:
            raise ValueError("binop must have 'left' and 'right'")
        _validate_expression_node(node["left"], depth + 1)
        _validate_expression_node(node["right"], depth + 1)
    
    elif node_type == "unop":
        if "op" not in node or node["op"] not in ["neg", "abs", "sqrt", "log"]:
            raise ValueError(f"Invalid unary operator: {node.get('op')}")
        if "operand" not in node:
            raise ValueError("unop must have 'operand'")
        _validate_expression_node(node["operand"], depth + 1)
    
    elif node_type == "clamp":
        for field in ["value", "lo", "hi"]:
            if field not in node:
                raise ValueError(f"clamp must have '{field}'")
        _validate_expression_node(node["value"], depth + 1)
        _validate_expression_node(node["lo"], depth + 1)
        _validate_expression_node(node["hi"], depth + 1)
    
    elif node_type == "ifelse":
        for field in ["cond_left", "cond_op", "cond_right", "then", "else_"]:
            if field not in node:
                raise ValueError(f"ifelse must have '{field}'")
        if node["cond_op"] not in [">", "<", ">=", "<=", "==", "!="]:
            raise ValueError(f"Invalid condition operator: {node.get('cond_op')}")
        _validate_expression_node(node["cond_left"], depth + 1)
        _validate_expression_node(node["cond_right"], depth + 1)
        _validate_expression_node(node["then"], depth + 1)
        _validate_expression_node(node["else_"], depth + 1)
    
    else:
        raise ValueError(f"Unknown node type: {node_type}")
