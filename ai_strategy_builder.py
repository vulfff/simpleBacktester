"""
ai_strategy_builder.py – AI-powered strategy generation with multi-provider support

Supports multiple AI providers:
- Anthropic (Claude)
- OpenAI (GPT-4, GPT-4o, etc.)
- xAI Grok
- Google Gemini

Configuration stored in database api_keys table:
- service: "anthropic", "openai", "grok", or "gemini"
- model_name: specific model (e.g., "claude-3-5-sonnet", "gpt-4", "grok-2")
- model_key: API key for that provider

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
        "price",        # Current price (bid, ask, mid, volume)
        "lookback",     # Price N bars ago
        "sma",          # Simple moving average
        "ema",          # Exponential moving average
        "rsi",          # Relative strength index
        "macd",         # MACD indicator
        "bollinger",    # Bollinger bands
        "constant"      # Fixed number
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
    PRICE_FIELDS = ["bid", "ask", "mid", "volume"]
    
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


SYSTEM_PROMPT = """You are an expert trading strategy designer with deep knowledge of technical analysis and price action. Your task is to convert natural language trading strategy descriptions into valid JSON structures.

## Available Components

### Price Operands
- `price`: Current price (fields: bid, ask, mid, volume)
- `constant`: Fixed number values
- `lookback`: Price or field value from N bars ago
- `sma`: Simple moving average (configurable period)
- `ema`: Exponential moving average (configurable period)
- `rsi`: Relative strength index 0-100 (configurable period, default 14)
- `macd`: MACD indicator (configurable fast/slow/signal periods)
- `bollinger`: Bollinger bands (configurable period, std_dev, components: upper/middle/lower)

### Operators
- `>`, `<`, `>=`, `<=`, `==`, `!=`: For numeric comparisons
- `cross_above`: When left operand crosses above right (for moving average crossovers)
- `cross_below`: When left operand crosses below right (for moving average crossovers)

### Rule Roles
- `entry_long`: Buy signal (long position entry)
- `exit_long`: Sell signal (long position exit)
- `entry_short`: Short entry signal
- `exit_short`: Short exit/cover signal

### Exit Conditions (Optional)
Exit conditions are placed in the conditions array with `kind: "exit_condition"`:
- `take_profit_pct`: Exit when position profit reaches X%
- `stop_loss_pct`: Exit when position loss reaches X%
- `take_profit_abs`: Exit when absolute profit reaches $X
- `stop_loss_abs`: Exit when absolute loss reaches $X
- `bars_held`: Exit after holding for N bars/candles
- `time_of_day`: Exit at specific hour (0-23)
- `day_of_week`: Exit on specific day (0=Sunday to 6=Saturday)

### Price Fields
bid, ask, mid, volume

## JSON Structure

```json
{
  "name": "Strategy Name",
  "rules": [
    {
      "name": "Rule Name",
      "role": "entry_long|exit_long|entry_short|exit_short",
      "timing": "every_tick|on_change",
      "quantity": 1.0,
      "conditions": [
        {
          "kind": "signal",
          "left": { "type": "operand_type", ...operand_params },
          "operator": "comparison_operator",
          "right": { "type": "operand_type", ...operand_params },
          "combiner": "and|or"
        },
        {
          "kind": "exit_condition",
          "exitType": "take_profit_pct|stop_loss_pct|bars_held|...",
          "value": numeric_value,
          "combiner": "and|or"
        }
      ]
    }
  ]
}
```

## Detailed Operand Examples

**Constant:**
```json
{ "type": "constant", "value": 50 }
```

**Current Price:**
```json
{ "type": "price", "field": "mid" }
```

**Price from N bars ago:**
```json
{ "type": "lookback", "field": "mid", "period": 5 }
```

**Simple Moving Average:**
```json
{ "type": "sma", "field": "mid", "period": 20 }
```

**Exponential Moving Average:**
```json
{ "type": "ema", "field": "mid", "period": 9 }
```

**RSI (Relative Strength Index):**
```json
{ "type": "rsi", "field": "mid", "period": 14 }
```

**MACD (all three lines must match):**
```json
{ "type": "macd", "fast": 12, "slow": 26, "signal": 9, "component": "macd|signal|histogram" }
```

**Bollinger Bands:**
```json
{ "type": "bollinger", "field": "mid", "period": 20, "std_dev": 2, "component": "upper|middle|lower" }
```

## Common Pattern Examples

### Golden Cross Strategy
Entry: Fast SMA (50) crosses above Slow SMA (200)
Exit: Fast SMA crosses below Slow SMA

```json
{
  "name": "Golden Cross",
  "rules": [
    {
      "name": "Buy on Golden Cross",
      "role": "entry_long",
      "timing": "on_change",
      "quantity": 1.0,
      "conditions": [
        {
          "kind": "signal",
          "left": { "type": "sma", "field": "mid", "period": 50 },
          "operator": "cross_above",
          "right": { "type": "sma", "field": "mid", "period": 200 },
          "combiner": "and"
        }
      ]
    },
    {
      "name": "Sell on Death Cross",
      "role": "exit_long",
      "timing": "on_change",
      "quantity": 1.0,
      "conditions": [
        {
          "kind": "signal",
          "left": { "type": "sma", "field": "mid", "period": 50 },
          "operator": "cross_below",
          "right": { "type": "sma", "field": "mid", "period": 200 },
          "combiner": "and"
        }
      ]
    }
  ]
}
```

### RSI Oversold/Overbought Strategy
Entry: Buy when RSI drops below 30 (oversold)
Exit: Sell when RSI rises above 70 (overbought) OR after 10 bars

```json
{
  "name": "RSI Extremes",
  "rules": [
    {
      "name": "Buy on Oversold",
      "role": "entry_long",
      "timing": "on_change",
      "quantity": 1.0,
      "conditions": [
        {
          "kind": "signal",
          "left": { "type": "rsi", "field": "mid", "period": 14 },
          "operator": "<",
          "right": { "type": "constant", "value": 30 },
          "combiner": "and"
        }
      ]
    },
    {
      "name": "Sell on Overbought",
      "role": "exit_long",
      "timing": "on_change",
      "quantity": 1.0,
      "conditions": [
        {
          "kind": "signal",
          "left": { "type": "rsi", "field": "mid", "period": 14 },
          "operator": ">",
          "right": { "type": "constant", "value": 70 },
          "combiner": "and"
        },
        {
          "kind": "exit_condition",
          "exitType": "bars_held",
          "value": 10,
          "combiner": "or"
        }
      ]
    }
  ]
}
```

## Important Rules

1. **Every entry rule should have a corresponding exit rule** (entry_long needs exit_long, entry_short needs exit_short)
2. **All conditions array is valid** - the first condition is always the primary signal
3. **Use combiner: "and"** between most conditions (both must be true)
4. **Use combiner: "or"** when providing alternative exit conditions
5. **Period values should be realistic**: SMA/EMA typically 5-200, RSI period 14, Bollinger period 20
6. **Quantity should be positive float** (usually 1.0)
7. **timing**: Use "on_change" for most indicators (triggers once when condition changes), "every_tick" runs every bar
8. **Validate all JSON** - ensure it's properly formatted and contains no syntax errors

## Your Task
1. Analyze the user's natural language description
2. Identify the trading signals and exit conditions
3. Map them to the available operands and operators
4. Generate valid, well-formed JSON
5. Ensure every entry rule has a corresponding exit rule
6. Return ONLY the JSON (no explanation, no markdown code blocks)

Remember: Generate clean, parseable JSON that adheres to this exact format. The strategy will be directly parsed and executed.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Base Provider Class
# ─────────────────────────────────────────────────────────────────────────────

class AIProvider(ABC):
    """Abstract base class for AI providers."""
    
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name
    
    @abstractmethod
    def build_from_prompt(self, user_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """Convert natural language to strategy JSON."""
        pass
    
    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Helper to parse and validate JSON response."""
        # Remove markdown code blocks if present
        text = re.sub(r'^```(?:json)?\n', '', text)
        text = re.sub(r'\n```$', '', text)
        
        try:
            strategy = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Response is not valid JSON: {e}")
        
        # Validate structure
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
            if not isinstance(rule["conditions"], list) or not rule["conditions"]:
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
# Anthropic Provider (Claude)
# ─────────────────────────────────────────────────────────────────────────────

class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""
    
    def build_from_prompt(self, user_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """Build strategy using Anthropic Claude API."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package required. Install: pip install anthropic")
        
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=self.model_name,
                max_tokens=2048,
                temperature=temperature,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Create a trading strategy from this description:\n\n{user_prompt}"
                    }
                ]
            )
            response_text = message.content[0].text.strip()
            return self._parse_response(response_text)
        except Exception as e:
            raise ValueError(f"Anthropic API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Provider (GPT-4, etc.)
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIProvider(AIProvider):
    """OpenAI GPT API provider."""
    
    def build_from_prompt(self, user_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """Build strategy using OpenAI API."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required. Install: pip install openai")
        
        try:
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model_name,
                max_tokens=2048,
                temperature=temperature,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Create a trading strategy from this description:\n\n{user_prompt}"
                    }
                ]
            )
            response_text = response.choices[0].message.content.strip()
            return self._parse_response(response_text)
        except Exception as e:
            raise ValueError(f"OpenAI API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Grok Provider (xAI, OpenAI-compatible)
# ─────────────────────────────────────────────────────────────────────────────

class GrokProvider(AIProvider):
    """xAI Grok API provider (OpenAI-compatible endpoint)."""
    
    def build_from_prompt(self, user_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """Build strategy using xAI Grok API."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required. Install: pip install openai")
        
        try:
            # Grok uses OpenAI-compatible API but with different base URL
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.x.ai/v1"
            )
            response = client.chat.completions.create(
                model=self.model_name,
                max_tokens=2048,
                temperature=temperature,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Create a trading strategy from this description:\n\n{user_prompt}"
                    }
                ]
            )
            response_text = response.choices[0].message.content.strip()
            return self._parse_response(response_text)
        except Exception as e:
            raise ValueError(f"Grok API error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Google Gemini Provider
# ─────────────────────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    """Google Gemini API provider."""
    
    def build_from_prompt(self, user_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """Build strategy using Google Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("google-generativeai package required. Install: pip install google-generativeai")
        
        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=2048
                )
            )
            response = model.generate_content(
                f"Create a trading strategy from this description:\n\n{user_prompt}"
            )
            response_text = response.text.strip()
            return self._parse_response(response_text)
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
        from db import get_db_conn, decrypt_with_password
        
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT service, model_name, model_key, protected FROM api_keys LIMIT 1")
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise ValueError(
                "No AI provider configured in database. "
                "Use the Key Manager frontend to set up an LLM provider."
            )
        
        provider = provider or row["service"]
        model_name = model_name or row["model_name"]
        
        # Decrypt API key if needed
        enc_key = row["model_key"]
        is_protected = bool(row["protected"])
        
        if is_protected:
            # For protected keys, we need the password - this should be provided by frontend
            # For now, return an error directing user to decrypt
            raise ValueError(
                "LLM API key is encrypted. "
                "Please provide decryption in the Key Manager."
            )
        else:
            import base64
            try:
                api_key = base64.b64decode(enc_key).decode()
            except Exception:
                api_key = enc_key  # Fallback if not base64 encoded
    
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

