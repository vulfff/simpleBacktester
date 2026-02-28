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
- `price`: Current OHLCV price (fields: bid, ask, mid, volume)
- `sma`: Simple moving average (fields: mid/bid/ask/volume, period)
- `ema`: Exponential moving average (fields: mid/bid/ask/volume, period)
- `rsi`: Relative strength index (fields: mid/bid/ask/volume, period)
- `macd`: MACD indicator (fast, slow, signal periods, component: macd/signal/histogram)
- `bollinger`: Bollinger bands (field, period, std_dev, component: upper/middle/lower)

### Operand JSON Structure
All operands follow this pattern in the expression tree:
```json
{
  "node": "operand",
  "operand": { "type": "sma", "field": "mid", "period": 20 }
}
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
  "left": { "node": "operand", "operand": { "type": "sma", "field": "mid", "period": 20 } },
  "right": { "node": "const", "value": 100 }
}
```

Available operators: `+`, `-`, `*`, `/`, `**` (power), `%` (modulo)

**Unary Operations** (negation, absolute value, square root, logarithm):
```json
{
  "node": "unop",
  "op": "abs",
  "operand": { "node": "operand", "operand": { "type": "rsi", "field": "mid", "period": 14 } }
}
```

Available unary ops: `neg` (negate), `abs` (absolute), `sqrt` (square root), `log` (natural log)

**Clamping** (constrain value within bounds):
```json
{
  "node": "clamp",
  "value": { "node": "operand", "operand": { "type": "rsi", "field": "mid", "period": 14 } },
  "lo": { "node": "const", "value": 0 },
  "hi": { "node": "const", "value": 100 }
}
```

**Conditional** (if-then-else):
```json
{
  "node": "ifelse",
  "cond_left": { "node": "operand", "operand": { "type": "rsi", "field": "mid", "period": 14 } },
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
    "cond_left": { "node": "operand", "operand": { "type": "rsi", "field": "mid", "period": 14 } },
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
        "left": { "node": "operand", "operand": { "type": "price", "field": "mid" } },
        "right": { "node": "operand", "operand": { "type": "sma", "field": "mid", "period": 20 } }
      },
      "right": { "node": "operand", "operand": { "type": "sma", "field": "mid", "period": 20 } }
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
    "left": { "node": "operand", "operand": { "type": "rsi", "field": "mid", "period": 14 } },
    "right": { "node": "const", "value": 100 }
  },
  "color": "#ec4899"
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
        "left": { "node": "operand", "operand": { "type": "price", "field": "mid" } },
        "right": { "node": "operand", "operand": { "type": "lookback", "field": "mid", "period": 5 } }
      },
      "right": { "node": "operand", "operand": { "type": "lookback", "field": "mid", "period": 5 } }
    },
    "right": { "node": "const", "value": 100 }
  },
  "color": "#10b981"
}
```

## Important Rules

1. **Always return valid JSON** - no markdown, no explanations
2. **Use correct node types**: "operand", "const", "binop", "unop", "clamp", "ifelse"
3. **Every operand must be wrapped** in `{"node": "operand", "operand": {...}}`
4. **Constants use** `{"node": "const", "value": number}`
5. **Binary operations require both left and right**
6. **Unary operations require operand**
7. **Avoid division by zero** - test logic carefully
8. **Color should be hex** format like "#3b82f6"
9. **Name and description should be user-friendly**
10. **Expression node structure must be recursive and well-formed**

## Your Task
1. Analyze the user's natural language description
2. Identify the indicators/operands needed
3. Identify mathematical operations and logic
4. Build the correct nested expression tree
5. Provide a meaningful name and description
6. Return ONLY valid JSON (no markdown code blocks, no explanations)

The JSON structure must include:
- `name`: Short indicator name
- `description`: What this indicator does
- `expr`: The expression tree (required)
- `color`: Hex color for UI display (optional, defaults to blue)
"""


def build_indicator_from_prompt(user_prompt: str, provider=None) -> Dict[str, Any]:
    """
    Build an indicator expression from natural language using configured AI provider.

    Args:
        user_prompt: Natural language indicator description
        provider: Optional pre-configured provider. If None, reads from database.

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
            system_prompt=INDICATOR_SYSTEM_PROMPT,
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
