# AI Strategy Builder API Documentation

## Overview

The AI Strategy Builder allows you to create trading strategies using natural language. Simply describe your trading idea (e.g., "Buy when price crosses above the 50-day moving average"), and the AI generates a valid strategy JSON that the backtester can execute immediately.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs the Anthropic SDK needed for Claude API integration.

### 2. Set Your API Key

Get your Anthropic API key from https://console.anthropic.com/account/keys and set it as an environment variable:

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "sk-..."
python -m uvicorn api:app --reload
```

**Windows (Command Prompt):**
```cmd
set ANTHROPIC_API_KEY=sk-...
python -m uvicorn api:app --reload
```

**Linux/Mac:**
```bash
export ANTHROPIC_API_KEY="sk-..."
python -m uvicorn api:app --reload
```

## API Endpoints

### POST /ai/build-strategy

Convert a natural language description into a trading strategy JSON.

**Request:**
```json
{
  "prompt": "Buy when 20-period EMA crosses above 50-period SMA. Sell when RSI exceeds 70.",
  "temperature": 0.7
}
```

**Parameters:**
- `prompt` (string, required): Natural language description of your strategy
- `temperature` (float, optional, 0.0-1.0): Controls AI creativity
  - 0.0 = Deterministic, same output every time
  - 0.7 = Default, balanced
  - 1.0 = Maximum creativity/variation

**Response (Success):**
```json
{
  "name": "EMA-SMA Crossover with RSI",
  "rules": [
    {
      "name": "Buy on EMA-SMA Cross",
      "role": "entry_long",
      "timing": "on_change",
      "quantity": 1.0,
      "conditions": [
        {
          "kind": "signal",
          "left": { "type": "ema", "field": "mid", "period": 20 },
          "operator": "cross_above",
          "right": { "type": "sma", "field": "mid", "period": 50 },
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
        }
      ]
    }
  ],
  "warnings": [
    "⚠️ No exit_long rule found - long positions will never close!"
  ]
}
```

**Response (Error):**
```json
{
  "detail": "Failed to generate strategy: ANTHROPIC_API_KEY not set"
}
```

### GET /ai/schema

Retrieve the schema/documentation of available strategy components.

**Response:**
```json
{
  "operand_types": [
    "price",
    "lookback",
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "constant"
  ],
  "operators": [
    ">",
    "<",
    ">=",
    "<=",
    "==",
    "!=",
    "cross_above",
    "cross_below"
  ],
  "rule_roles": [
    "entry_long",
    "exit_long",
    "entry_short",
    "exit_short"
  ],
  "price_fields": ["bid", "ask", "mid", "volume"],
  "exit_condition_types": [
    "take_profit_pct",
    "stop_loss_pct",
    "take_profit_abs",
    "stop_loss_abs",
    "bars_held",
    "time_of_day",
    "day_of_week"
  ],
  "timing_modes": ["every_tick", "on_change"]
}
```

## Usage Examples

### Example 1: Simple Moving Average Crossover

**Prompt:**
```
Build a golden cross strategy. Buy when the 50-day SMA crosses above the 200-day SMA. 
Sell when the 50-day SMA crosses back below the 200-day SMA.
```

**What the AI generates:**
- Entry rule: Fast SMA (50) crosses above Slow SMA (200)
- Exit rule: Fast SMA (50) crosses below Slow SMA (200)
- Quantity: 1.0 per trade

### Example 2: RSI-Based Range Trading

**Prompt:**
```
Create an RSI oversold/overbought strategy. Buy when RSI drops below 30 (oversold).
Take profit at +5% or when RSI rises above 70. Stop loss at -2%.
```

**What the AI generates:**
- Entry rule: RSI < 30
- Exit rules:
  - Take profit at +5% (profit condition)
  - Stop loss at -2% (loss condition)
  - Exit when RSI > 70 (overbought)

### Example 3: Multi-Timeframe Strategy

**Prompt:**
```
Buy when price is above the 20-period EMA AND the 50-period SMA is above the 200-period SMA
(both bullish). Take profit at +3% or after 10 bars. Stop loss at -1.5%.
```

**What the AI generates:**
- Entry rule: Price > 20-EMA AND 50-SMA > 200-SMA
- Exit rules:
  - Take profit at +3%
  - Stop loss at -1.5%
  - Exit after 10 bars held

### Example 4: MACD Strategy with Time-Based Exit

**Prompt:**
```
Buy when MACD crosses above the signal line. Sell at end of day (16:00 UTC) or 
when MACD crosses below signal line.
```

**What the AI generates:**
- Entry rule: MACD line crosses above signal line
- Exit rules:
  - Exit at 16:00 UTC (time_of_day=16)
  - Exit when MACD crosses below signal line

## Python Integration

Use the AI builder directly in your Python code:

```python
from ai_strategy_builder import AIStrategyBuilder
import json
import os

# Initialize the builder
api_key = os.getenv("ANTHROPIC_API_KEY")
builder = AIStrategyBuilder(api_key=api_key)

# Generate a strategy
strategy = builder.build_from_prompt(
    user_prompt="Buy on RSI oversold below 30, sell above 70"
)

# Validate it
is_valid, warnings = builder.validate_strategy(strategy)
if is_valid:
    print("✓ Strategy is valid!")
    if warnings:
        print(f"⚠️ Warnings: {warnings}")
    
    # Use with the backtest API
    print(json.dumps(strategy, indent=2))
else:
    print(f"✗ Invalid strategy: {warnings}")
```

## Available Indicators Explained

### Price-based
- **price**: Current bid/ask/mid/volume
- **lookback**: Price from N bars ago (e.g., 5 bars ago)
- **constant**: Fixed number for comparisons

### Trend Following
- **SMA** (Simple Moving Average): Smooths price, good for identifying trends
  - Periods: 5-200 (common: 20, 50, 200)
- **EMA** (Exponential Moving Average): Faster than SMA, reacts quicker
  - Periods: 5-200 (common: 9, 21, 50)

### Momentum
- **RSI** (Relative Strength Index): 0-100, shows overbought/oversold
  - Below 30 = oversold (potential bounce)
  - Above 70 = overbought (potential pullback)
  - Period: typically 14
- **MACD**: Trend + momentum (3 lines: MACD, signal, histogram)
  - Builtin periods: fast=12, slow=26, signal=9

### Volatility
- **Bollinger Bands**: Upper/middle/lower bands around price
  - Period: typically 20
  - Std Dev: typically 2
  - Price at upper band = overbought
  - Price at lower band = oversold

## Operators Guide

### Comparison Operators
- `>` : Greater than
- `<` : Less than
- `>=` : Greater than or equal
- `<=` : Less than or equal
- `==` : Equals
- `!=` : Not equals

### Indicator Crossovers
- `cross_above`: First line crosses above second
  - Example: "SMA 20 cross_above SMA 50" = golden cross
- `cross_below`: First line crosses below second
  - Example: "SMA 20 cross_below SMA 50" = death cross

## Writing Good Prompts

### ✓ Good Prompts (Specific & Clear)
- "Buy when EMA(9) crosses above EMA(21). Sell when it crosses below."
- "Buy when RSI < 30 AND price is above 50-SMA. Stop loss at -2%, take profit at +5%."
- "Golden cross: buy on SMA(50) > SMA(200), sell on SMA(50) < SMA(200)."

### ✗ Avoid (Vague & Ambiguous)
- "A momentum strategy" (too vague)
- "Buy when it looks good" (not technical)
- "Use indicators" (doesn't specify which)

### Tips
1. **Be specific about periods**: "20-day SMA", not "moving average"
2. **Include both entry AND exit**: AI needs both to create complete strategy
3. **Mention quantities if needed**: "Use 2.0 lot size", otherwise defaults to 1.0
4. **Include stop loss/take profit**: Makes strategies more robust

## Workflow

### Using with Frontend

1. User inputs strategy in natural language via frontend
2. Frontend calls `POST /ai/build-strategy`
3. API returns strategy JSON
4. Frontend can:
   - Preview the strategy rules visually
   - Show any warnings (e.g., missing exit rules)
   - Send to backtester via `POST /backtest/upload`

### Using via API Directly

```bash
curl -X POST http://localhost:8000/ai/build-strategy \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Buy when 20-EMA crosses above 50-SMA. Sell when it crosses below.",
    "temperature": 0.7
  }'
```

## Limitations & Best Practices

### What the AI Can Do
✓ Create valid, executable strategies
✓ Generate rule-based strategies (not ML models)
✓ Use all available technical indicators
✓ Handle multiple entry/exit conditions
✓ Add proper risk management (stops, profits)

### What the AI Cannot Do
✗ Create ML/neural network strategies
✗ Use data-driven optimization
✗ Generate custom indicators beyond the schema
✗ Backtest - it only generates the JSON structure

### Best Practices
1. **Always review generated strategies** - Check the JSON before backtesting
2. **Use warnings** - Watch for alerts like "no exit rule"
3. **Test thoroughly** - Backtest on historical data before trading live
4. **Keep it simple** - Fewer conditions = more robust
5. **Validate assumptions** - Does the logic match your market view?

## Troubleshooting

### Error: "ANTHROPIC_API_KEY not configured"
- Make sure you set the environment variable
- Restart the API server after setting it
- Check: `echo $ANTHROPIC_API_KEY` (Linux/Mac) or `echo %ANTHROPIC_API_KEY%` (Windows)

### Error: "AI generated invalid strategy"
- Try a more specific prompt
- Make sure to include both entry AND exit conditions
- Use standard indicator names (SMA, EMA, RSI, MACD, Bollinger)

### Strategy seems wrong
- Check the warnings in the response
- Review the generated JSON
- Try reprompting with more detail
- Reduce temperature to 0.3 for more deterministic output

## Integration with Backtester

Once you have a strategy from the AI endpoint, run it:

```bash
curl -X POST http://localhost:8000/backtest/upload \
  -F file=@data.csv \
  -F strategies='[{"logic":"rule_set","config":{"rule_set":YOUR_STRATEGY_JSON}}]'
```

Or use the frontend to:
1. Generate with AI
2. Review the rules
3. Click "Backtest" directly

## Pricing & Rate Limits

- Uses Anthropic Claude API
- Pricing: Check https://console.anthropic.com/account/billing/overview
- Rate limits: Depends on your account tier
- No rate limiting on the backend (add if needed)

## Examples of Edge Cases

### Bollinger Band Squeeze
```
Create a mean reversion strategy. Buy when price touches the lower Bollinger band.
Sell when it touches the upper band.
```

### Volume Confirmation
```
Buy when price crosses above 50-SMA with volume spike (volume > 20-SMA).
Sell when RSI exceeds 70.
```

### Multi-Signal Confirmation
```
Buy only when ALL: price > 20-EMA AND RSI < 50 AND MACD > 0.
Sell when RSI > 75 OR MACD crosses below signal line.
```

## Future Enhancements

Potential additions:
- Custom indicator composition
- Alerts on anomalies
- Strategy backtest integration
- Confidence scores
- Alternative AI models (GPT-4, Claude 3 Opus)
- Strategy refinement ("make it more aggressive")
- Multi-timeframe strategies
