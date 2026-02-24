# AI Strategy & Indicator Builder

Complete natural language to trading strategy and indicator generation system with multi-LLM support.

## Features

### 🤖 AI Strategy Builder
- Convert natural language descriptions into valid trading rules
- Full rule-based strategy generation with entry/exit conditions
- Support for all technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, etc.)
- Automatic validation and warning generation
- Live preview with JSON visualization

### 📊 AI Indicator Builder
- Create custom technical indicators from natural language descriptions
- Expression tree generation with mathematical operations
- Support for complex indicator logic (if-else, clamping, operations, etc.)
- Reusable indicators across multiple strategies

### 🔄 Multi-LLM Provider Support
- **Anthropic** - Claude 3.5 Sonnet, Claude 3 Opus, etc.
- **OpenAI** - GPT-4, GPT-4o, GPT-3.5-turbo
- **xAI Grok** - Via OpenAI-compatible API
- **Google Gemini** - Gemini 2.0 Flash, 1.5 Pro, 1.5 Flash

All providers configured and toggled via the Key Manager (database-driven).

## Setup

### 1. Backend Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `anthropic>=0.7.0` - Anthropic API
- `openai>=1.0.0` - OpenAI + Grok support
- `google-generativeai>=0.3.0` - Google Gemini
- `fastapi>=0.110`
- `uvicorn[standard]>=0.27`

### 2. Configure LLM Provider

Use the **Key Manager** UI (KeyManager.jsx) to:

1. Select your preferred AI provider (Anthropic, OpenAI, Grok, or Gemini)
2. Choose a specific model
3. Enter your API key
4. Optionally encrypt with a password

**Database Schema:**
```
api_keys table:
- service: "anthropic", "openai", "grok", or "gemini"
- model_name: Specific model (e.g., "gpt-4-turbo", "claude-3-5-sonnet-20241022")
- model_key: Your API key (stored encrypted or base64-encoded)
- protected: Boolean (whether key is password-encrypted)
```

### 3. Start Backend & Frontend

```bash
# Terminal 1: Backend
python -m uvicorn api:app --reload --port 8000

# Terminal 2: Frontend (if not running)
cd frontend
npm run dev
```

## Usage

### Strategy Builder UI

1. **Go to Strategy Builder** page
2. Click **"🤖 AI Strategy"** tab
3. Describe your strategy in plain English

**Example prompts:**
- "Buy when 20-day EMA crosses above 50-day EMA. Sell when RSI exceeds 70."
- "Golden cross strategy: Buy on 50-200 SMA cross above, sell on cross below."
- "Buy when price breaks above Bollinger Band upper. Sell after 10 bars or at 5% profit."
- "RSI oversold strategy: Buy when RSI drops below 30, sell when it exceeds 70."

4. View generated strategy in the right panel
5. Click **"Edit in Manual Builder"** to adjust rules manually
6. Save your strategy

### Indicator Builder UI

1. Click **"📊 AI Indicator"** tab
2. Describe your indicator

**Example prompts:**
- "RSI oversold signal: Returns 1 when RSI(14) is below 30"
- "Moving average distance as a percentage: (price - SMA(20)) / SMA(20) * 100"
- "Volume ratio: Current volume divided by 20-period average volume"
- "Momentum: Percentage price change over last 5 bars"

3. View expression tree on the right
4. Save indicator to use in strategies

## API Endpoints

### Strategy Generation

**POST** `/ai/build-strategy`

Request:
```json
{
  "prompt": "Buy when EMA crosses SMA. Sell when RSI > 70.",
  "temperature": 0.7,
  "password": "optional_if_encrypted"
}
```

Response:
```json
{
  "name": "Strategy Name",
  "rules": [...],
  "warnings": [
    "⚠️ No exit_long rule - long positions will never close!"
  ]
}
```

### Indicator Generation

**POST** `/ai/build-indicator`

Request:
```json
{
  "prompt": "RSI oversold: returns 1 when RSI(14) < 30",
  "password": "optional_if_encrypted"
}
```

Response:
```json
{
  "name": "RSI Oversold",
  "description": "Returns 1 when RSI(14) drops below 30 (oversold signal)",
  "expr": { "node": "ifelse", ... },
  "color": "#3b82f6"
}
```

### Schema Documentation

**GET** `/ai/schema` - View strategy schema, operators, providers, and models

**GET** `/ai/indicator-schema` - View indicator expression tree types and examples

## Strategy Schema

### Available Operands
- `price` - Current price (bid, ask, mid, volume)
- `lookback` - Price N bars ago
- `sma` - Simple moving average
- `ema` - Exponential moving average
- `rsi` - Relative strength index
- `macd` - MACD indicator
- `bollinger` - Bollinger bands
- `constant` - Fixed numbers

### Available Operators
- Comparisons: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Crossovers: `cross_above`, `cross_below`

### Rule Roles
- `entry_long` - Buy signal
- `exit_long` - Sell signal
- `entry_short` - Short entry
- `exit_short` - Short cover

### Exit Conditions
- `take_profit_pct` - Exit at +X% profit
- `stop_loss_pct` - Exit at -X% loss
- `take_profit_abs` - Exit at +$X profit
- `stop_loss_abs` - Exit at -$X loss
- `bars_held` - Exit after N bars
- `time_of_day` - Exit at specific hour
- `day_of_week` - Exit on specific day

## Indicator Expression Trees

Indicators are built from expression trees:

### Node Types
- `const` - Constant value
- `operand` - Price/indicator operand
- `binop` - Binary operation (+, -, *, /, **, %)
- `unop` - Unary operation (neg, abs, sqrt, log)
- `clamp` - Constrain value between min/max
- `ifelse` - Conditional (ternary)

### Example: RSI Oversold
```json
{
  "name": "RSI Oversold",
  "expr": {
    "node": "ifelse",
    "cond_left": { "node": "operand", "operand": { "type": "rsi", "period": 14 } },
    "cond_op": "<",
    "cond_right": { "node": "const", "value": 30 },
    "then": { "node": "const", "value": 1 },
    "else_": { "node": "const", "value": 0 }
  }
}
```

## Best Practices

### Writing Good Strategy Prompts

✅ **DO:**
- Be specific: "Buy when 20-period SMA crosses above 50-period SMA"
- Include exit conditions: "Sell when RSI exceeds 70"
- Mention quantities: "Use 1.0 quantity per trade"
- Specify timeframes: "5-bar lookback" or "14-period RSI"

❌ **DON'T:**
- Be vague: "Buy when trend is up"
- Miss exit rules: Only describing entry signals
- Use unsupported indicators: Stick to SMA, EMA, RSI, MACD, Bollinger Bands
- Ask for too much complexity in one rule

### Example Strong Prompts

**Golden Cross:**
```
Create a golden cross strategy. Buy when the 50-period SMA crosses above the 
200-period SMA. Sell when the 50-period SMA crosses below the 200-period SMA. 
Use standard 1.0 quantity per trade.
```

**Multi-Indicator:**
```
Build an RSI + Moving Average strategy. Buy when price is above its 20-period 
SMA AND RSI(14) is below 30 (oversold). Sell when RSI exceeds 70 (overbought) 
OR after holding for 10 bars, whichever comes first.
```

**Risk Management:**
```
Entry: Buy when 10-period EMA crosses above 30-period EMA.
Exit: Use 2% stop loss and 5% take profit.
Use 1.0 quantity.
```

## Temperature Settings

The `temperature` parameter controls AI creativity:

- **0.0** - Deterministic, precise, conservative
- **0.5** - Balanced (recommended for indicators)
- **0.7** - Default, slightly creative
- **1.0** - Maximum creativity, may be inconsistent

**Recommendation:**
- Strategies: 0.6-0.8 (need balance between creativity and consistency)
- Indicators: 0.3-0.5 (need reliable, reproducible expressions)

## Troubleshooting

### "No AI provider configured"
- Go to Key Manager
- Add an LLM provider (Anthropic, OpenAI, Grok, or Gemini)
- Select a model and enter your API key

### "Failed to generate strategy"
- Check your API key is valid
- Ensure you have sufficient API credits
- Try a simpler, more specific prompt
- Reduce temperature for more consistent generation

### "Generated invalid strategy"
- Check warnings in the response
- Ensure entry rules have matching exit rules
- Verify all conditions are properly specified
- Try rephrasing the prompt

### Strategy doesn't load after generation
- Check browser console for errors
- Verify backend is running (`http://localhost:8000/health`)
- Try switching to Manual Builder and adding rules manually

## Files Modified/Created

**Backend:**
- `ai_strategy_builder.py` - Multi-provider strategy generation
- `ai_indicator_builder.py` - Indicator expression tree generation
- `api.py` - New `/ai/build-strategy`, `/ai/build-indicator`, `/ai/schema` endpoints
- `db.py` - Uses existing `api_keys` table for provider config

**Frontend:**
- `AIStrategyChat.jsx` - Strategy chat interface component
- `AIIndicatorChat.jsx` - Indicator chat interface component
- `StrategyBuilder.jsx` - Integrated AI chat tabs

**Dependencies:**
- `requirements.txt` - Updated with anthropic, openai, google-generativeai

## API Provider Details

### Anthropic
- Models: claude-3-5-sonnet-20241022, claude-3-opus-20240229
- Key format: `sk-ant-...`
- Get key: https://console.anthropic.com

### OpenAI
- Models: gpt-4-turbo, gpt-4o, gpt-3.5-turbo
- Key format: `sk-...`
- Get key: https://platform.openai.com/api-keys

### xAI Grok
- Models: grok-2, grok-beta
- Key format: `xai-...`
- Get key: https://console.x.ai

### Google Gemini
- Models: gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash
- Key format: `AIza...`
- Get key: https://aistudio.google.com/app/apikey

## Performance Notes

- Strategy generation typically takes 2-5 seconds
- Indicator generation usually completes in 1-3 seconds
- Temperature values between 0.5-0.8 recommended for reliability
- Always validate generated strategies before backtesting
- Test on historical data first
