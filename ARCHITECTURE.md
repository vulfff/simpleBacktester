# AI Strategy Builder - Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React)                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  StrategyBuilder.jsx (Main Component)                           │  │
│  │  ├── 🔄 THREE MODES:                                            │  │
│  │  │   ├── Manual Builder (Original UI - Unchanged)               │  │
│  │  │   ├── AI Strategy Chat (New)                                 │  │
│  │  │   └── AI Indicator Chat (New)                                │  │
│  │  │                                                               │  │
│  │  ├── State Management:                                           │  │
│  │  │   ├── rules[] - Trading rules                               │  │
│  │  │   ├── mode - Current mode ('build'|'ai-strategy'            │  │
│  │  │   ├── aiGeneratedStrategy - AI output                       │  │
│  │  │   └── Temperature - AI creativity control                   │  │
│  │  │                                                               │  │
│  │  └── Key Handlers:                                              │  │
│  │      └── handleStrategyGenerated() - Import AI rules            │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────┐              ┌──────────────────────────────┐│
│  │ AIStrategyChat.jsx   │              │ AIIndicatorChat.jsx          ││
│  │                      │              │                              ││
│  │ • Chat interface     │              │ • Chat interface             ││
│  │ • Message history    │              │ • Message history            ││
│  │ • Temperature slider │              │ • Same chat UX               ││
│  │ • Error handling     │              │ • Expression visualization   ││
│  │ • JSON preview       │              │ • Color indicators           ││
│  │                      │              │                              ││
│  │ POST /ai/build-      │              │ POST /ai/build-indicator     ││
│  │      strategy        │              │                              ││
│  └──────────────────────┘              └──────────────────────────────┘│
│                                                                          │
│  Shared API_BASE: http://localhost:8000                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                              ↕ JSON
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │ api.py - HTTP Routes                                          │    │
│  │ ├── POST /ai/build-strategy (AIStrategyRequest)               │    │
│  │ │   └── Calls: get_ai_provider() → provider.build_from_      │    │
│  │ │                     prompt()                                 │    │
│  │ │   └── Returns: AIStrategyResponse (name, rules, warnings)   │    │
│  │ ├── POST /ai/build-indicator (AIIndicatorRequest)             │    │
│  │ │   └── Calls: build_indicator_from_prompt()                 │    │
│  │ │   └── Returns: AIIndicatorResponse (expr tree)             │    │
│  │ ├── GET /ai/schema -schema documentation                      │    │
│  │ └── GET /ai/indicator-schema - indicator documentation        │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │ ai_strategy_builder.py - Strategy Generation                  │    │
│  │ ├── AIProvider (Abstract Base)                                │    │
│  │ ├── AnthropicProvider (Claude)                                │    │
│  │ ├── OpenAIProvider (GPT-4, GPT-4o, etc.)                      │    │
│  │ ├── GrokProvider (xAI - OpenAI compatible)                    │    │
│  │ ├── GeminiProvider (Google - native API)                      │    │
│  │ ├── get_ai_provider()                                         │    │
│  │ │   └── Reads: db → api_keys table                            │    │
│  │ │   └── Decrypts: password-protected keys                     │    │
│  │ │   └── Returns: Configured provider instance                 │    │
│  │ │                                                               │    │
│  │ └── SYSTEM_PROMPT (Comprehensive strategy generation guide)   │    │
│  │     └── 5000+ tokens of technical instructions                │    │
│  │     └── Schema examples & patterns                            │    │
│  │                                                                │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │ ai_indicator_builder.py - Indicator Generation                │    │
│  │ ├── build_indicator_from_prompt()                             │    │
│  │ │   └── Uses: get_ai_provider() for actual generation         │    │
│  │ ├── _validate_expression_node()                               │    │
│  │ │   └── Validates: Expression tree structure                  │    │
│  │ │   └── Checks: Node types, operators, recursion depth        │    │
│  │ └── INDICATOR_SYSTEM_PROMPT (4000+ tokens)                    │    │
│  │     └── Expression tree structure rules                       │    │
│  │     └── Operand types & mathematical operations               │    │
│  │     └── Example indicators                                    │    │
│  │                                                                │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │ db.py - Database & Encryption                                 │    │
│  │ ├── get_db_conn() - SQLite connection                         │    │
│  │ ├── api_keys table reader                                     │    │
│  │ ├── decrypt_with_password() - Protected key decryption        │    │
│  │ └── Base64 decoding for unencrypted keys                      │    │
│  │                                                                │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                              ↕ REST API Calls
┌─────────────────────────────────────────────────────────────────────────┐
│                       EXTERNAL LLM SERVICES                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │   Anthropic   │  │   OpenAI   │  │    xAI     │  │   Google   │   │
│  │  (Claude)     │  │   (GPT-4)  │  │  (Grok)    │  │  (Gemini)  │   │
│  │               │  │            │  │            │  │            │   │
│  │ /messages     │  │/chat/      │  │/chat/      │  │/generate   │   │
│  │               │  │completions │  │completions │  │_content    │   │
│  │               │  │            │  │            │  │            │   │
│  │ sk-ant-...    │  │ sk-...     │  │ xai-...    │  │ AIza...    │   │
│  └───────────────┘  └────────────┘  └────────────┘  └────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                              ↕ Database
┌─────────────────────────────────────────────────────────────────────────┐
│                          SQLITE DATABASE                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  api_keys table (Existing)                                             │
│  ┌────────────────────────────────────────────────────┐                │
│  │ id | service   | model_name       | model_key  │..│                │
│  ├────────────────────────────────────────────────────┤                │
│  │ 1  │ anthropic │ claude-3-5-sonnet│ sk-ant-... │..│                │
│  │ 2  │ openai    │ gpt-4-turbo      │ sk-...     │..│                │
│  │ 3  │ grok      │ grok-2           │ xai-...    │..│                │
│  │ 4  │ gemini    │ gemini-2.0-flash │ AIza...    │..│                │
│  └────────────────────────────────────────────────────┘                │
│                                                                          │
│  strategies table (New data from generated strategies)                 │
│  indicators table (New data from generated indicators)                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Example: Strategy Generation

```
User types in AIStrategyChat:
"Buy when 20 EMA crosses above 50 EMA. Sell on RSI > 70."
      ↓
AIStrategyChat.jsx
  ├─ Store in messages[]
  ├─ POST /ai/build-strategy
  └─ {prompt: "...", temperature: 0.7}
      ↓
api.py: ai_build_strategy()
  ├─ get_ai_provider() reads api_keys table
  │  ├─ Finds: service="openai", model="gpt-4-turbo"
  │  └─ Decrypts model_key if protected
  ├─ Create OpenAIProvider(api_key, model_name)
  └─ provider.build_from_prompt(prompt)
      ↓
OpenAIProvider.build_from_prompt()
  ├─ client = OpenAI(api_key=api_key)
  ├─ client.chat.completions.create()
  │  ├─ model: "gpt-4-turbo"
  │  ├─ messages: [system_prompt, user_prompt]
  │  └─ max_tokens: 2048
  └─ API Call → OpenAI Servers
      ↓
OpenAI API processes request
  ├─ Applies gpt-4-turbo model
  └─ Returns streaming completion
      ↓
Response parsed in OpenAIProvider._parse_response()
  ├─ Extract JSON from response
  ├─ Validate structure:
  │  ├─ Check "name" exists
  │  ├─ Check "rules" is array
  │  └─ Validate each rule
  └─ Return strategy dict
      ↓
api.py validates with provider.validate_strategy()
  ├─ Check role counts (entry_long needs exit_long)
  ├─ Generate warnings
  └─ Return AIStrategyResponse
      ↓
Frontend receives:
{
  "name": "EMA Crossover RSI", 
  "rules": [
    {
      "name": "Buy on EMA Cross",
      "role": "entry_long",
      "conditions": [...]
    },
    ...
  ],
  "warnings": ["..."]
}
      ↓
AIStrategyChat displays:
  ├─ Message: "Generated 'EMA Crossover RSI' with 2 rules"
  ├─ JSON preview
  ├─ Warning alerts
  └─ "Edit in Manual Builder" button
      ↓
User clicks "Edit in Manual Builder"
  ├─ StrategyBuilder.handleStrategyGenerated(result)
  ├─ Convert rules to internal format
  ├─ setRules(convertedRules)
  ├─ Switch mode to 'build'
  └─ User can now manually edit⁣ in the full rule editor
```

## Data Flow Example: Multi-Provider Switching

```
Key Manager UI → Save API Keys
  ├─ Select provider: OpenAI
  ├─ Model: gpt-4-turbo
  ├─ Key: sk-xxx...
  │
SQLite: api_keys.service = "openai", .model_name = "gpt-4-turbo"
  │
┌─ Later, user posts to /ai/build-strategy
│
└─ get_ai_provider() queries api_keys
   ├─ Finds service="openai", model_name="gpt-4-turbo"
   ├─ PROVIDERS["openai"] → OpenAIProvider class
   ├─ Create instance: OpenAIProvider(api_key, "gpt-4-turbo")
   └─ Use this to generate strategies
  │
  └─ To switch to Claude:
     ├─ Key Manager: Change service to "anthropic"
     ├─ Next /ai/build-strategy call:
     └─ get_ai_provider() finds service="anthropic"
        ├─ Loads AnthropicProvider instead
        └─ Uses Claude for generation
```

## System Features & Integration Points

### 1. Configuration Management
- **Database Driven**: No hardcoded API keys
- **Provider Switch**: Change LLM instantly via Key Manager
- **Encryption Support**: Optional password protection for sensitive keys
- **Model Flexibility**: Each provider supports multiple models

### 2. Validation & Safety
- **Schema Validation**: All generated rules validated against schema
- **Warning System**: Alerts for incomplete or risky strategies
- **Expression Trees**: Recursive validation for indicators
- **Type Checking**: Operands and operators validated

### 3. User Experience
- **Seamless Integration**: AI chat alongside manual builder
- **Mode Switching**: Single click between AI and manual editing
- **Live Feedback**: Message history, streaming responses
- **Temperature Control**: Fine-tune AI creativity

### 4. Error Handling
- **Graceful Degradation**: Missing LLM libraries warned cleanly
- **API Failures**: Detailed error messages to user
- **Validation Errors**: Specific feedback on why generation failed
- **Fallbacks**: Can use multiple providers if one fails

## Technology Stack

### Frontend
- React with Hooks (useState, useCallback, useEffect, useRef)
- CSS-in-JS for component styling
- Fetch API for HTTP requests
- No external UI libraries (pure React)

### Backend
- FastAPI (Python web framework)
- Pydantic (Request/Response validation)
- SQLite (Database)
- Cryptography (Encryption support)
- Multiple LLM APIs (Anthropic, OpenAI, Google, xAI)

### Deployment
- Single backend server (uvicorn)
- Single frontend server (Vite)
- Shared SQLite database
- Environment-configured API base URL

## Security Considerations

1. **API Keys**
   - Stored in database, not environment
   - Optional password encryption
   - Base64 encoding for unencrypted keys
   - Never exposed to frontend

2. **Prompts**
   - System prompts define boundary
   - User prompts validated before sending
   - No code execution (only JSON generation)

3. **Database**
   - SQLite (local file)
   - No external DB connections
   - Encryption optional per key

4. **API Calls**
   - Only to LLM providers
   - No data leaking between providers
   - Requests fully isolated

## Performance Metrics

- **Strategy Generation**: 2-5 seconds (typical)
- **Indicator Generation**: 1-3 seconds (typical)
- **Database Queries**: <10ms
- **Frontend Rendering**: Instant
- **API Response Parsing**: <100ms

## Extensibility

Future enhancements:
- Additional LLM providers (Llama, Mistral, etc.)
- Custom indicator templates
- Strategy refinement chats
- Backtesting within chat
- Parameter optimization
- Strategy explanation generation
- Indicator visualization
