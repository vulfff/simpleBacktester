"""
ai_strategy_builder.py – AI-powered strategy generation with multi-provider support

Supports multiple AI providers:
- Anthropic (Claude)
- OpenAI (GPT-4, GPT-4o, etc.)
- xAI Grok
- Google Gemini

Configuration stored in database model_api_keys table:
- provider: "anthropic", "openai", "grok", or "gemini"
- model_name: specific model (e.g., "claude-sonnet-4-6", "gpt-4o", "grok-3")
- key_data: base64-encoded or Fernet-encrypted API key

Usage:
    from ai_strategy_builder import get_ai_provider

    provider = get_ai_provider()  # Reads from database
    strategy = provider.build_from_prompt(
        user_prompt="Buy when EMA crosses above SMA"
    )
    print(strategy)  # Valid rule_set strategy JSON
"""

from __future__ import annotations

import json
import re
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class StrategySchema:
    """Defines the expected strategy JSON structure for AI generation."""

    # Available operand types
    OPERAND_TYPES = [
        "price",          # Current price (close, high, low, volume)
        "lookback",       # Price N bars ago
        "sma",            # Simple moving average
        "ema",            # Exponential moving average
        "rsi",            # Relative strength index
        "macd",           # MACD indicator
        "bollinger",      # Bollinger bands
        "highest_high",   # Rolling max of a field over N bars (field, period)
        "lowest_low",     # Rolling min of a field over N bars (field, period)
        "atr",            # Average True Range (period)
        "typical_price",  # (High + Low + Close) / 3, no params
        "time_of_day",    # Current bar time as minutes since midnight (0-1439)
        "constant"        # Fixed number
    ]

    # Available operators for conditions
    OPERATORS = [
        ">",            # Greater than
        "<",            # Less than
        ">=",           # Greater than or equal
        "<=",           # Less than or equal
        "==",           # Equals
        "!=",           # Not equals
        "cross_above",  # Crosses above (for indicators)
        "cross_below"   # Crosses below (for indicators)
    ]

    # Rule roles
    RULE_ROLES = [
        "entry_long",   # Buy signal
        "exit_long",    # Sell signal (close long)
        "entry_short",  # Short signal
        "exit_short"    # Cover signal (close short)
    ]

    # Price fields
    PRICE_FIELDS = ["close", "high", "low", "volume"]

    # Exit condition types
    EXIT_CONDITION_TYPES = [
        "take_profit_pct",   # Exit at +X% profit
        "stop_loss_pct",     # Exit at -X% loss
        "take_profit_abs",   # Exit at +$X profit
        "stop_loss_abs",     # Exit at -$X loss
        "bars_held",         # Exit after N bars
        "time_of_day",       # Exit at specific hour
        "day_of_week"        # Exit on specific day
    ]

    # Timing modes
    TIMING_MODES = ["every_tick", "on_change"]


# ─────────────────────────────────────────────────────────────────────────────
# DSL Parser Utilities
# ─────────────────────────────────────────────────────────────────────────────

_EXIT_CONDITION_KEYS = {
    "stop_loss_pct", "take_profit_pct", "stop_loss_abs", "take_profit_abs",
    "bars_held", "time_of_day", "day_of_week",
}

_TIMING_VALUES = {"on_change", "every_tick"}

_OPERATORS = ["cross_above", "cross_below", ">=", "<=", "!=", "==", ">", "<"]

_ROLE_LABELS = {
    "entry_long":  "Entry Long",
    "exit_long":   "Exit Long",
    "entry_short": "Entry Short",
    "exit_short":  "Exit Short",
}


def _split_by_comma_respecting_quotes(s: str) -> list:
    """Split by comma but not inside quoted strings or parentheses."""
    items: list = []
    depth = 0
    in_quote = False
    quote_char = ""
    current: list = []
    for ch in s:
        if in_quote:
            current.append(ch)
            if ch == quote_char:
                in_quote = False
        elif ch in ('"', "'"):
            in_quote = True
            quote_char = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                items.append(token)
            current = []
        else:
            current.append(ch)
    token = "".join(current).strip()
    if token:
        items.append(token)
    return items


def _parse_operand(token: str) -> dict:
    """Parse a DSL operand token into a strategy JSON operand dict."""
    token = token.strip()

    # Bare number → constant
    try:
        val = float(token)
    except ValueError:
        pass
    else:
        import math
        if not math.isfinite(val):
            raise ValueError(f"Non-finite constant not allowed: {token!r}")
        return {"type": "constant", "value": val}

    # Function call: name(args...)
    m = re.match(r"^(\w+)\((.*)\)$", token, re.DOTALL)
    if not m:
        raise ValueError(f"Cannot parse operand: {token!r}")

    func = m.group(1).lower()
    args_str = m.group(2).strip()

    if func == "custom":
        name_m = re.match(r'^["\']([^"\']+)["\'](.*)$', args_str)
        if not name_m:
            raise ValueError(f"custom() requires a quoted indicator name: {token!r}")
        name = name_m.group(1)
        rest = name_m.group(2).strip().lstrip(",").strip()
        overrides: dict = {}
        if rest:
            for kv in _split_by_comma_respecting_quotes(rest):
                kv = kv.strip()
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    try:
                        overrides[k.strip()] = float(v.strip())
                    except ValueError:
                        overrides[k.strip()] = v.strip()
        result: dict = {"type": "custom", "name": name}
        if overrides:
            result["overrides"] = overrides
        return result

    args = [a.strip() for a in args_str.split(",") if a.strip()]

    if func in ("sma", "ema", "highest_high", "lowest_low"):
        if len(args) != 2:
            raise ValueError(f"{func}() requires (field, period): {token!r}")
        return {"type": func, "field": args[0], "period": int(args[1])}

    if func == "lookback":
        if len(args) != 2:
            raise ValueError(f"lookback() requires (field, period): {token!r}")
        return {"type": "lookback", "field": args[0], "period": int(args[1])}

    if func == "rsi":
        if len(args) == 1:
            return {"type": "rsi", "field": "close", "period": int(args[0])}
        if len(args) == 2:
            return {"type": "rsi", "field": args[0], "period": int(args[1])}
        raise ValueError(f"rsi() requires 1 or 2 args: {token!r}")

    if func == "macd":
        if len(args) != 4:
            raise ValueError(f"macd() requires (fast, slow, signal, component): {token!r}")
        valid_components = {"macd", "signal", "hist"}
        if args[3] not in valid_components:
            raise ValueError(f"macd() component must be one of {sorted(valid_components)}: {token!r}")
        return {"type": "macd", "fast": int(args[0]), "slow": int(args[1]),
                "signal": int(args[2]), "component": args[3]}

    if func == "bollinger":
        if len(args) != 4:
            raise ValueError(f"bollinger() requires (field, period, stddev, component): {token!r}")
        valid_components = {"upper", "middle", "lower", "width", "pct_b"}
        if args[3] not in valid_components:
            raise ValueError(f"bollinger() component must be one of {sorted(valid_components)}: {token!r}")
        return {"type": "bollinger", "field": args[0], "period": int(args[1]),
                "std_dev": float(args[2]), "component": args[3]}

    if func == "atr":
        if len(args) != 1:
            raise ValueError(f"atr() requires (period): {token!r}")
        return {"type": "atr", "period": int(args[0])}

    if func == "typical_price":
        if args_str.strip():
            raise ValueError(f"typical_price() takes no arguments: {token!r}")
        return {"type": "typical_price"}

    if func == "price":
        if len(args) != 1:
            raise ValueError(f"price() requires (field): {token!r}")
        return {"type": "price", "field": args[0]}

    if func == "time_of_day":
        if args_str.strip():
            raise ValueError(f"time_of_day() takes no arguments: {token!r}")
        return {"type": "time_of_day"}

    if func == "constant":
        if len(args) != 1:
            raise ValueError(f"constant() requires (value): {token!r}")
        return {"type": "constant", "value": float(args[0])}

    raise ValueError(f"Unknown operand type: {func!r}")


def _split_condition(expr: str) -> tuple:
    """Split 'LEFT OP RIGHT' into (left_token, op, right_token). Tries longest operators first."""
    expr = expr.strip()
    # Normalize spaces around symbolic operators so "rsi(14)>30" and "rsi(14) > 30" both work.
    expr = re.sub(r"\s*([><=!]+)\s*", r" \1 ", expr).strip()
    for op in _OPERATORS:
        pattern = rf"^(.+?)\s+{re.escape(op)}\s+(.+)$"
        m = re.match(pattern, expr)
        if m:
            return m.group(1).strip(), op, m.group(2).strip()
    raise ValueError(f"No operator found in condition: {expr!r}")


def _split_by_and_respecting_quotes(s: str) -> list:
    """Split by ' and ' (case-insensitive) but not inside quoted strings or parentheses."""
    parts: list = []
    depth = 0
    in_quote = False
    quote_char = ""
    current: list = []
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quote:
            current.append(ch)
            if ch == quote_char:
                in_quote = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_quote = True
            quote_char = ch
            current.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            current.append(ch)
            i += 1
            continue
        if depth == 0 and s[i:i+5].lower() == " and " and not in_quote:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
            i += 5
            continue
        current.append(ch)
        i += 1
    token = "".join(current).strip()
    if token:
        parts.append(token)
    return parts


def parse_dsl_to_strategy(text: str) -> dict:
    """
    Parse compact DSL text into a full strategy JSON dict.

    DSL format (one line per role):
        name: Strategy Name
        entry_long: sma(close,50) cross_above sma(close,200), timing=every_tick
        exit_long: rsi(14) > 70, stop_loss_pct=3, bars_held=20
    """
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]

    name = "AI Strategy"
    role_lines: list = []

    for line in lines:
        lower = line.lower()
        if lower.startswith("name:"):
            name = line[5:].strip()
        else:
            for role in _ROLE_LABELS:
                if lower.startswith(role + ":"):
                    rest = line[len(role) + 1:].strip()
                    role_lines.append((role, rest))
                    break

    rules: list = []
    role_counters: dict = {}

    for role, rest in role_lines:
        items = _split_by_comma_respecting_quotes(rest)
        timing = "on_change"
        signal_items: list = []
        exit_items: list = []

        for item in items:
            item = item.strip()
            if not item:
                continue
            # Timing override
            if item.lower().startswith("timing="):
                val = item.split("=", 1)[1].strip().lower()
                if val not in _TIMING_VALUES:
                    raise ValueError(
                        f"Invalid timing value {val!r}. Must be one of: {sorted(_TIMING_VALUES)}"
                    )
                timing = val
                continue
            # Exit condition (key=value with known key)
            kv = re.match(r"^(\w+)=(.+)$", item)
            if kv and kv.group(1) in _EXIT_CONDITION_KEYS:
                exit_items.append((kv.group(1), kv.group(2).strip()))
                continue
            # Signal expression
            signal_items.append(item)

        label = _ROLE_LABELS[role]

        for sig_expr in signal_items:
            role_counters[role] = role_counters.get(role, 0) + 1
            n = role_counters[role]
            conditions: list = []
            for cond_expr in _split_by_and_respecting_quotes(sig_expr):
                left_tok, op, right_tok = _split_condition(cond_expr.strip())
                conditions.append({
                    "kind": "signal",
                    "left": _parse_operand(left_tok),
                    "operator": op,
                    "right": _parse_operand(right_tok),
                    "combiner": "and",
                })
            rules.append({
                "name": f"{label} {n}",
                "role": role,
                "timing": timing,
                "quantity": 1.0,
                "conditions": conditions,
            })

        for exit_key, exit_val_str in exit_items:
            role_counters[role] = role_counters.get(role, 0) + 1
            n = role_counters[role]
            try:
                exit_val = float(exit_val_str)
            except ValueError:
                raise ValueError(
                    f"Exit condition value must be numeric: {exit_key}={exit_val_str!r}"
                )
            if exit_val <= 0 and exit_key not in ("time_of_day", "day_of_week"):
                raise ValueError(
                    f"Exit condition value must be positive: {exit_key}={exit_val_str!r}"
                )
            rules.append({
                "name": f"{label} {n}",
                "role": role,
                "timing": timing,
                "quantity": 1.0,
                "conditions": [{
                    "kind": "exit_condition",
                    "exitType": exit_key,
                    "value": exit_val,
                    "combiner": "and",
                }],
            })

    return {"name": name, "rules": rules}


STRATEGY_DSL_PROMPT = """You are a trading strategy designer. Output strategies using this compact DSL — NOT JSON, no markdown, no explanations.

## Format

name: Strategy Name
entry_long: CONDITION [and CONDITION ...] [, CONDITION ...] [, exit_key=value ...] [, timing=every_tick]
exit_long: ...
entry_short: ...
exit_short: ...

Rules:
- Always provide a matching exit for every entry (entry_long needs exit_long, entry_short needs exit_short)

## `and` vs Comma — most important rule

**`and`** combines conditions into ONE rule. ALL joined conditions must be true at the same time.
    entry_long: rsi(14) < 30 and price(close) > sma(close,200)
    → buys only when BOTH: RSI is oversold AND price is above the 200 SMA simultaneously

**Comma `,`** between signal expressions creates SEPARATE, independent rules for the same role.
Each separate rule fires on its own — whichever triggers first.
    entry_long: rsi(14) < 30, price(close) cross_above sma(close,200)
    → two independent entry rules: fires when EITHER RSI drops below 30 OR price crosses above 200 SMA

You can mix both:
    entry_long: rsi(14) < 30 and price(close) > sma(close,200), macd(12,26,9,macd) cross_above 0
    → fires when (RSI<30 AND above SMA) OR when MACD crosses above zero — two separate rules

Comma also separates exit_key=value items and timing — these are always independent additions:
    exit_long: rsi(14) > 70, stop_loss_pct=3, bars_held=20
    → three independent exit triggers: RSI signal rule, stop-loss rule, max-bars rule

## Operands

sma(field,period)              Simple moving average. field: close/high/low/volume
ema(field,period)              Exponential moving average
rsi(period)                    RSI on close. Or: rsi(field,period)
macd(fast,slow,signal,comp)    comp: macd / signal / hist
bollinger(field,period,sd,comp) comp: upper / middle / lower / width / pct_b
atr(period)                    Average True Range — no field
highest_high(field,period)     Rolling max. Use field: high for standard Donchian
lowest_low(field,period)       Rolling min. Use field: low for standard Donchian
typical_price()                (High+Low+Close)/3 — no args
price(field)                   Raw price field
lookback(field,period)         Price N bars ago
time_of_day()                  Minutes since midnight (570=09:30, 960=16:00)
42                             Bare number = constant
custom("Name")                 Reference a custom indicator by name
custom("Name", key=val, ...)   Custom indicator with parameter overrides

## Operators

cross_above   cross_below   >   <   >=   <=   ==   !=

## Exit Condition Keys (key=value items, each becomes its own rule)

stop_loss_pct=N     take_profit_pct=N    stop_loss_abs=N    take_profit_abs=N
bars_held=N         time_of_day=N        day_of_week=N (1=Mon .. 7=Sun)

## Timing (optional, per role line)

Default: on_change (fires once when condition flips true).
Override: add `timing=every_tick` to fire every bar while condition holds.

## Examples

name: Golden Cross
entry_long: sma(close,50) cross_above sma(close,200)
exit_long: sma(close,50) cross_below sma(close,200), stop_loss_pct=5

name: RSI Extremes
entry_long: rsi(14) < 30 and time_of_day() >= 570 and time_of_day() < 960
exit_long: rsi(14) > 70, bars_held=20, stop_loss_pct=3, take_profit_pct=8

name: Donchian Breakout
entry_long: price(close) cross_above highest_high(high,20)
exit_long: price(close) cross_below lowest_low(low,10), stop_loss_pct=4
entry_short: price(close) cross_below lowest_low(low,20)
exit_short: price(close) cross_above highest_high(high,10), stop_loss_pct=4

Output ONLY the DSL text. No JSON, no markdown, no explanation.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Base Provider Class
# ─────────────────────────────────────────────────────────────────────────────

class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    # ── Abstract: each subclass implements the raw HTTP call ─────────────────

    @abstractmethod
    def _call_api(self, user_prompt: str, system_prompt: str, temperature: float) -> str:
        """Make API call and return raw text response."""
        pass

    @abstractmethod
    def _call_api_multi(self, messages: list, system_prompt: str, temperature: float) -> str:
        """Multi-turn chat: accepts full message history and returns plain-text reply.

        Args:
            messages: List of {"role": "user"|"assistant", "content": str}
            system_prompt: System/context prompt (prepended to conversation)
            temperature: Creativity (0.0–1.0)
        """
        pass

    # ── Public: strategy builder convenience ─────────────────────────────────

    def build_from_prompt(self, user_prompt: str, temperature: float = 0.7, extra_system_context: str = "") -> Dict[str, Any]:
        """Convert natural language to strategy JSON via compact DSL."""
        text = self._call_api(
            user_prompt=f"Create a trading strategy from this description:\n\n{user_prompt}",
            system_prompt=STRATEGY_DSL_PROMPT + extra_system_context,
            temperature=temperature,
        )
        return parse_dsl_to_strategy(text)

    # ── JSON extraction (shared with indicator builder) ───────────────────────

    def _extract_json(self, text: str) -> Any:
        """
        Robustly extract a JSON object from AI response text.

        Handles:
        - Markdown code fences (```json ... ``` or ``` ... ```)
        - Trailing explanation text after the JSON object
        - Leading explanation text before the JSON object
        - Literal (unescaped) newlines inside JSON string values
        - Trailing commas before } or ]
        """
        text = text.strip()

        # Strip markdown code fence markers only at boundaries to avoid
        # mangling backtick content inside string values.
        # Handle: ```json\n, ```\n at start; \n``` at end.
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        text = text.strip()

        # Find the start of the first JSON object
        start = text.find('{')
        if start == -1:
            raise ValueError("No JSON object found in response")

        # First attempt: parse as-is (handles trailing text via raw_decode)
        try:
            obj, _ = json.JSONDecoder().raw_decode(text, idx=start)
            return obj
        except json.JSONDecodeError:
            pass

        # Second attempt: sanitize common AI output issues then retry.
        sanitized = self._sanitize_json_text(text[start:])
        try:
            obj, _ = json.JSONDecoder().raw_decode(sanitized)
            return obj
        except json.JSONDecodeError as e:
            loc = e.pos
            snippet = sanitized[max(0, loc - 60): loc + 60]
            tail = sanitized[-120:]  # last 120 chars — shows whether response is cut off
            raise ValueError(
                f"Response is not valid JSON: {e}\n"
                f"  ...around char {loc}: {snippet!r}\n"
                f"  Response tail (last 120 chars): {tail!r}"
            )

    @staticmethod
    def _sanitize_json_text(text: str) -> str:
        """
        Attempt to repair common JSON malformations produced by LLMs:
        1. Literal (unescaped) newlines inside string values → \\n
        2. Trailing commas before } or ]
        """
        # Fix literal newlines inside strings.
        # Strategy: walk character by character tracking whether we're inside a
        # string.  When inside a string, replace bare \n / \r with \\n / \\r.
        result = []
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                result.append(ch)
                escape_next = False
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string and ch == '\n':
                result.append('\\n')
                continue
            if in_string and ch == '\r':
                result.append('\\r')
                continue
            result.append(ch)
        text = ''.join(result)

        # Fix trailing commas: , followed by optional whitespace then } or ]
        text = re.sub(r',\s*([}\]])', r'\1', text)

        return text

    # ── Strategy-specific response parsing ───────────────────────────────────

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse and validate a strategy JSON response."""
        strategy = self._extract_json(text)

        if not isinstance(strategy, dict):
            raise ValueError("Response must be a JSON object")
        if "name" not in strategy or "rules" not in strategy:
            raise ValueError("Strategy must contain 'name' and 'rules' fields")
        if not isinstance(strategy["rules"], list):
            raise ValueError("'rules' must be a list")

        return strategy

    def validate_strategy(self, strategy: Dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate strategy structure and return warnings."""
        warnings = []

        if not isinstance(strategy, dict):
            return False, ["Strategy must be a dictionary"]
        if "name" not in strategy:
            return False, ["Missing 'name' field"]
        if "rules" not in strategy or not isinstance(strategy["rules"], list):
            return False, ["'rules' must be a list"]
        if not strategy["rules"]:
            return False, ["Strategy must have at least one rule"]

        role_counts = {}
        for rule in strategy["rules"]:
            if not isinstance(rule, dict):
                return False, ["Each rule must be a dictionary"]
            for field in ["name", "role", "conditions", "timing", "quantity"]:
                if field not in rule:
                    return False, [f"Rule missing required field: {field}"]
            role = rule.get("role")
            role_counts[role] = role_counts.get(role, 0) + 1
            if not isinstance(rule["conditions"], list):
                return False, [f"Rule '{rule['name']}' conditions must be a list"]
            # Allow empty conditions if the rule has exit conditions
            has_exit_conds = any(
                isinstance(c, dict) and c.get("kind") == "exit_condition"
                for c in rule["conditions"]
            )
            if not rule["conditions"] and not has_exit_conds:
                return False, [f"Rule '{rule['name']}' must have at least one condition"]

        # Warnings for missing exit rules
        if role_counts.get("entry_long") and not role_counts.get("exit_long"):
            warnings.append("⚠️ No exit_long rule - long positions will never close!")
        if role_counts.get("entry_short") and not role_counts.get("exit_short"):
            warnings.append("⚠️ No exit_short rule - short positions will never close!")
        if role_counts.get("exit_long") and not role_counts.get("entry_long"):
            warnings.append("⚠️ Exit long exists but no entry_long rule!")
        if role_counts.get("exit_short") and not role_counts.get("entry_short"):
            warnings.append("⚠️ Exit short exists but no entry_short rule!")

        return True, warnings


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic Provider (Claude) — pure REST, no SDK required
# ─────────────────────────────────────────────────────────────────────────────

class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider (REST)."""

    BASE_URL = "https://api.anthropic.com/v1/messages"

    def _call_api(self, user_prompt: str, system_prompt: str, temperature: float) -> str:
        """Call Anthropic Messages API and return raw text."""
        import httpx

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    self.BASE_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if data.get("stop_reason") == "max_tokens":
                raise ValueError(
                    "AI response was truncated (max_tokens reached). "
                    "Try a shorter/simpler description."
                )
            return data["content"][0]["text"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Anthropic API error: {e}")

    def _call_api_multi(self, messages: list, system_prompt: str, temperature: float) -> str:
        import httpx
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": temperature,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    self.BASE_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["content"][0]["text"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Anthropic API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Provider — pure REST, no SDK required
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIProvider(AIProvider):
    """OpenAI Chat Completions API provider (REST)."""

    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def _call_api(self, user_prompt: str, system_prompt: str, temperature: float) -> str:
        """Call OpenAI Chat Completions API and return raw text."""
        import httpx

        # o1/o3/o4 reasoning models don't accept temperature or a system role message
        is_reasoning = self.model_name.startswith(("o1", "o3", "o4"))

        messages = []
        if not is_reasoning:
            messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
        else:
            # Embed system instructions in the user turn for reasoning models
            messages.append({"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_completion_tokens": 4096,
            "messages": messages,
        }
        if not is_reasoning:
            payload["temperature"] = temperature

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if data["choices"][0].get("finish_reason") == "length":
                raise ValueError(
                    "AI response was truncated (max_tokens reached). "
                    "Try a shorter/simpler description."
                )
            return data["choices"][0]["message"]["content"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"OpenAI API error: {e}")

    def _call_api_multi(self, messages: list, system_prompt: str, temperature: float) -> str:
        import httpx
        is_reasoning = self.model_name.startswith(("o1", "o3", "o4"))
        full_msgs: list = []
        if not is_reasoning:
            full_msgs.append({"role": "system", "content": system_prompt})
        full_msgs += [{"role": m["role"], "content": m["content"]} for m in messages]
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_completion_tokens": 4096,
            "messages": full_msgs,
        }
        if not is_reasoning:
            payload["temperature"] = temperature
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"OpenAI API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Grok Provider (xAI) — OpenAI-compatible REST endpoint
# ─────────────────────────────────────────────────────────────────────────────

class GrokProvider(AIProvider):
    """xAI Grok API provider (OpenAI-compatible REST)."""

    BASE_URL = "https://api.x.ai/v1/chat/completions"

    def _call_api(self, user_prompt: str, system_prompt: str, temperature: float) -> str:
        """Call xAI Grok API and return raw text."""
        import httpx

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if data["choices"][0].get("finish_reason") == "length":
                raise ValueError(
                    "AI response was truncated (max_tokens reached). "
                    "Try a shorter/simpler description."
                )
            return data["choices"][0]["message"]["content"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Grok API error: {e}")

    def _call_api_multi(self, messages: list, system_prompt: str, temperature: float) -> str:
        import httpx
        full_msgs = [{"role": "system", "content": system_prompt}]
        full_msgs += [{"role": m["role"], "content": m["content"]} for m in messages]
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": full_msgs,
            "temperature": temperature,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Grok API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Google Gemini Provider — pure REST, no SDK required
# ─────────────────────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    """Google Gemini generateContent API provider (REST)."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def _call_api(self, user_prompt: str, system_prompt: str, temperature: float) -> str:
        """Call Google Gemini generateContent API and return raw text."""
        import httpx

        url = self.BASE_URL.format(model=self.model_name)
        payload: Dict[str, Any] = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096,
            },
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    url,
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if data["candidates"][0].get("finishReason") == "MAX_TOKENS":
                raise ValueError(
                    "AI response was truncated (max_tokens reached). "
                    "Try a shorter/simpler description."
                )
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Gemini API error: {e}")

    def _call_api_multi(self, messages: list, system_prompt: str, temperature: float) -> str:
        import httpx
        url = self.BASE_URL.format(model=self.model_name)
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]
        payload: Dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096,
            },
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Gemini API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Factory Function
# ─────────────────────────────────────────────────────────────────────────────

def get_ai_provider(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> AIProvider:
    """
    Get an AI provider instance.

    Reads from database if no arguments provided.

    Args:
        provider: "anthropic", "openai", "grok", or "gemini"
        api_key: API key for the provider
        model_name: Model name to use

    Returns:
        Configured AIProvider instance
    """
    # If not provided, read from database
    if provider is None or api_key is None:
        import base64
        from db import get_active_model_key, _infer_provider

        key_rec = get_active_model_key()
        if not key_rec:
            raise ValueError(
                "No AI provider configured in database. "
                "Use the Key Manager frontend to set up an LLM provider."
            )

        model_name   = model_name or key_rec["model_name"]
        provider     = provider or key_rec.get("provider") or _infer_provider(model_name)
        enc_key      = key_rec["key_data"] or ""
        is_protected = bool(key_rec["protected"])

        if is_protected:
            raise ValueError(
                "LLM API key is encrypted. "
                "Please provide the password via the AI chat interface."
            )
        else:
            try:
                api_key = base64.b64decode(enc_key).decode().strip()
            except Exception:
                api_key = enc_key.strip()

    # Validate inputs
    if not provider or not api_key or not model_name:
        raise ValueError("provider, api_key, and model_name are required")

    provider = provider.lower().strip()

    # Provider mapping
    PROVIDERS = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "grok": GrokProvider,
        "gemini": GeminiProvider,
    }

    ProviderClass = PROVIDERS.get(provider)
    if not ProviderClass:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported: {', '.join(PROVIDERS.keys())}"
        )

    return ProviderClass(api_key=api_key, model_name=model_name)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────

def build_strategy_from_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Build a strategy from a prompt using configured provider.

    Reads provider config from database.

    Args:
        user_prompt: Natural language strategy description

    Returns:
        Strategy JSON dictionary
    """
    provider = get_ai_provider()
    return provider.build_from_prompt(user_prompt)
