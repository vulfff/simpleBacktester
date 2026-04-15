# Backtester — Project Documentation

> Single-file, self-contained algorithmic trading backtester with a React UI.
> Backend: FastAPI + SQLite. Frontend: React 19 + Vite.

---

## Table of Contents
1. [Overview](#overview)
2. [Running the App](#running-the-app)
3. [Architecture](#architecture)
4. [Backend — Key Modules](#backend--key-modules)
5. [API Endpoints](#api-endpoints)
6. [Frontend — Components](#frontend--components)
7. [Design System](#design-system)
8. [Database Schema](#database-schema)
9. [Execution Model](#execution-model)
10. [Data Providers](#data-providers)
11. [AI Features](#ai-features)
12. [Key Manager (API Keys)](#key-manager-api-keys)
13. [Analytics & Run History](#analytics--run-history)
14. [Known Bugs & Fixes Applied](#known-bugs--fixes-applied)

---

## Overview

A backtesting app that lets you:
- Fetch OHLCV data from multiple providers (Alpha Vantage, Polygon, Massive, Yahoo Finance, Finnhub, IEX Cloud)
- Define rule-based trading strategies via a visual builder or AI chat
- Run backtests with realistic fill simulation
- Store and compare historical runs via an analytics dashboard
- Build custom technical indicators via expression trees or AI chat

---

## Running the App

```bash
# Backend (from repo root)
cd c:\backtester
pip install -r requirements.txt   # first time only
uvicorn api:app --reload

# Frontend (separate terminal)
cd c:\backtester\frontend
npm install   # first time only
npm run dev
```

Default URLs:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

---

## Architecture

```
c:\backtester\
├── api.py                  # FastAPI app — setup, startup, backtest endpoint
├── routes_ai.py            # AI builder/analyzer endpoints (/ai/*)
├── routes_data.py          # Data fetch & ticker search (/data/*)
├── routes_db.py            # DB CRUD endpoints (/db/*)
├── engine.py               # Backtest engine (event loop, order queue)
├── fill_model.py           # Realistic fill simulation
├── metrics.py              # Quantitative performance analytics
├── strategy_rules.py       # Rule-based strategy execution
├── strategy.py             # Strategy factory (create_strategy / list_strategies)
├── portfolio.py            # Portfolio state management
├── tickdata.py             # TickData dataclass
├── csvparser.py            # CSV → TickData parsing
├── db.py                   # SQLite helpers (all DB access centralised here)
├── ai_strategy_builder.py  # LLM-powered strategy generation; multi-turn _call_api_multi
├── ai_indicator_builder.py # LLM-powered indicator expression tree generation
├── strategy_analyzer.py    # Multi-turn AI chat analyst for strategies
├── indicator_analyzer.py   # Multi-turn AI chat analyst for indicators
├── run_analyzer.py         # Multi-turn AI chat analyst for backtest runs
├── indicator_registry.py   # Custom indicator store
├── actionmanager.py        # Action/order management
├── seed_prebuilts.py       # Idempotent seed — 5 strategies + 13 indicators
├── backtester.db           # SQLite database (auto-created)
├── tests/                  # pytest test suite (metrics, fill_model, csvparser, engine)
└── frontend/
    ├── src/
    │   ├── App.jsx              # Root — tab navigation
    │   ├── App.css              # Global design system (CSS variables + classes)
    │   ├── Backtest.jsx         # Main backtest page (fetch data, run, results)
    │   ├── Analytics.jsx        # Run history, equity charts, comparison mode
    │   ├── StrategyBuilder.jsx  # Visual rule builder + AI strategy chat
    │   ├── IndicatorBuilder.jsx # Expression tree builder + AI indicator chat
    │   ├── KeyManager.jsx       # Multi-key API key manager
    │   ├── AIStrategyChat.jsx   # Chat UI for AI strategy generation
    │   ├── AIIndicatorChat.jsx  # Chat UI for AI indicator generation
    │   └── Analyzer.jsx         # Strategy/indicator/run AI analysis chat
    └── package.json
```

---

## Backend — Key Modules

### `engine.py`
Event-driven backtest engine. Iterates bars in chronological order.
- **Next-bar-open execution**: signal fires at bar close → order queued → fills at NEXT bar's open price (realistic, no lookahead)
- Tracks equity curve at every bar
- Pending order queue; orders expire after 1 bar if unfilled

### `fill_model.py` — `FillModel`
Realistic fill simulation applied to every order.
```
FillModel(participation_rate=0.25, price_impact_factor=0.001, slippage_sigma=0.0003)
```
- Liquidity check: order size vs volume (participation rate)
- Price impact: shifts fill price proportionally to order size
- Stochastic slippage: Gaussian noise on fill price (sigma = 0.03%)

### `metrics.py` — `compute_metrics(equity_curve, trade_log, starting_cash)`
Returns a dict of quantitative metrics:
| Metric | Description |
|---|---|
| `total_return_pct` | (final − initial) / initial × 100 |
| `cagr_pct` | Compound annual growth rate |
| `max_drawdown_pct` | Maximum peak-to-trough drawdown |
| `sharpe_ratio` | Annualised Sharpe (risk-free = 0) |
| `sortino_ratio` | Downside deviation variant of Sharpe |
| `calmar_ratio` | CAGR / |max drawdown| (0 when no drawdown) |
| `win_rate_pct` | % trades closed in profit |
| `profit_factor` | Gross profit / gross loss (null if no losing trades) |
| `total_trades` | Number of round-trip trades |
| `avg_trade_pct` | Average return per trade |
| `avg_bars_held` | Average bars per trade |

> **Note:** NaN/Infinity floats (e.g. `profit_factor` with zero losing trades) are sanitised to `null` before storage to keep responses RFC-compliant JSON.

### `strategy_rules.py` — `RuleSetStrategy`
Executes rule-based strategies. Each rule has:
- **role**: `entry_long` | `exit_long` | `entry_short` | `exit_short`
- **conditions**: list of signal conditions or exit conditions (T/P, stop-loss, bars held)
- **timing**: `on_change` (fires only when signal flips) | `every_tick` (fires every bar while true)
- **quantity**: units to trade

`RuleSetStrategy.warmup_bars` — returns the max indicator lookback across all conditions so the engine skips early bars.

### `indicator_registry.py`
Custom indicator store and expression tree evaluator.
- `INDICATOR_REGISTRY` — singleton; loaded from DB at startup via `_reload_indicator_registry()` in `api.py`
- `IndicatorDef` — stores `name`, `expr` (expression tree), `description`, `color`
  - `evaluate(series, overrides=None)` — evaluates the expression tree, substituting any override values
  - `editable_params` property — returns `[{path, label, default_value, param_type}]` for every tweakable leaf
- `extract_editable_params(expr, path="")` — walks an expression tree and returns a flat list of editable numeric fields; used by the AI context builder and the StrategyBuilder frontend
- `_eval_node(node, series, overrides, path)` — recursive evaluator; `const` nodes check `overrides[path]`; `operand` nodes apply overrides to `period`/`std_dev`/`fast`/`slow`/`signal`
- `CustomIndicatorOperand` — registered as `type: "custom"` in the operand registry
  - Stores `name: str` and `overrides: Dict[str, float]`
  - Serializes as `{"type": "custom", "name": "X", "overrides": {...}}` (omits `overrides` key when empty)
  - Calls `defn.evaluate(series, overrides=self.overrides)` at runtime

### Operand warmup requirements
| Operand | `min_bars` |
|---|---|
| SMA(n) | n |
| EMA(n) | n × 2 (stabilisation) |
| RSI(n) | n + 1 |
| Bollinger(n) | n |
| MACD(fast, slow, signal) | slow + signal |
| Lookback(n) | n + 1 |
| HighestHigh(n) | n |
| LowestLow(n) | n |
| ATR(n) | n + 1 |
| TypicalPrice | 1 |

### `db.py`
All SQLite access is centralised here. Never import `sqlite3` directly elsewhere.
- `db_conn(commit=False)` — context manager that guarantees connection close; auto-commits on clean exit when `commit=True`
- `create_tables()` — idempotent schema setup (called at startup)
- `_sanitize_floats(obj)` — recursively replaces NaN/Inf with None for JSON safety

### `strategy.py`
Strategy base class, registry (`STRATEGY_REGISTRY`), and `create_strategy()` factory. Only `rule_set` is registered (by `strategy_rules.py`); legacy MA cross / price change strategies have been removed.

### Route Modules
- **`routes_ai.py`** — AI builder/analyzer endpoints. Uses late import `_decode_key_import()` to avoid circular deps with `api.py`.
- **`routes_data.py`** — Data fetch proxy (`/data/fetch`) and ticker search (`/data/search-tickers`). All 6 provider implementations.
- **`routes_db.py`** — CRUD for runs, strategies, indicators, data-keys, model-keys. Uses `_keyring_refs()` late import for keyring access.

---

## API Endpoints

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok"}` |

### Backtest
| Method | Path | Description |
|---|---|---|
| POST | `/backtest/upload` | Run a backtest from CSV upload or pre-fetched JSON data |
| POST | `/data/fetch` | Fetch OHLCV data from a configured data provider |
| GET | `/data/search-tickers?q=` | Search ticker symbols via the active data provider |

### AI
| Method | Path | Description |
|---|---|---|
| POST | `/ai/build-strategy` | Generate strategy rules from a natural language prompt |
| POST | `/ai/build-indicator` | Generate an indicator expression tree from a prompt |
| POST | `/ai/analyze` | Multi-turn AI chat about a saved strategy or indicator (body: `{subject_type, subject_id, messages, temperature}`) |
| POST | `/ai/list-models` | Fetch live model list from a provider's API (body: `{provider, api_key}`) |
| GET | `/ai/schema` | Strategy schema + supported providers/models |
| GET | `/ai/indicator-schema` | Indicator expression tree schema |

### Database — Strategies & Indicators
| Method | Path | Description |
|---|---|---|
| GET | `/db/strategies` | List all saved strategies (includes `is_builtin` flag) |
| POST | `/db/strategies` | Save / upsert strategies |
| DELETE | `/db/strategies/{id}` | Delete a strategy (403 if built-in) |
| GET | `/db/indicators` | List all saved indicators (includes `is_builtin` flag) |
| POST | `/db/indicators` | Save / upsert indicators |
| DELETE | `/db/indicators/{id}` | Delete an indicator (403 if built-in) |

### Database — Run History
| Method | Path | Description |
|---|---|---|
| GET | `/db/runs` | List all backtest runs (metadata + metrics, no equity curve) |
| GET | `/db/runs/{id}` | Get a full run (includes equity curve + trade log) |
| DELETE | `/db/runs/{id}` | Delete a run |
| DELETE | `/db/runs` | Delete all runs |
| POST | `/db/runs/batch-delete` | Delete multiple runs by id (body: `{"ids": [1,2,3]}`) |

### API Keys — Data Providers
| Method | Path | Description |
|---|---|---|
| GET | `/db/data-keys` | List all saved data provider keys |
| POST | `/db/data-keys` | Save a new data provider key |
| POST | `/db/data-keys/{id}/activate` | Set a key as the active data provider |
| DELETE | `/db/data-keys/{id}` | Delete a key |

### API Keys — AI Models
| Method | Path | Description |
|---|---|---|
| GET | `/db/model-keys` | List all saved AI model keys |
| POST | `/db/model-keys` | Save a new AI model key |
| POST | `/db/model-keys/{id}/activate` | Set a key as the active AI model |
| DELETE | `/db/model-keys/{id}` | Delete a key |

### Encryption
| Method | Path | Description |
|---|---|---|
| POST | `/keys/encrypt` | Encrypt a key with a user password (PBKDF2 + Fernet) |
| POST | `/keys/decrypt` | Decrypt a previously encrypted key |

---

## Frontend — Components

### `App.jsx`
Root component. Renders a tab strip with 6 tabs:
1. **Backtest** — main workflow
2. **Analytics** — historical runs
3. **Strategy Builder** — rule editor
4. **Indicator Builder** — expression tree editor
5. **Analyzer** — AI chat for strategy/indicator assessment
6. **Key Manager** — API key management

### `Backtest.jsx`
Main page. Two data source modes:
- **Upload CSV** — parse and backtest a local CSV file
- **Fetch from API** — fetch OHLCV from the configured data provider

Features:
- **TickerSearch combobox** — debounced live search via `/data/search-tickers` (min 2 chars, 300ms debounce)
- **Session data cache** — module-level `Map` keyed by `ticker|start|end|timeframe`; avoids repeated API calls, shows cache badge + "Re-fetch" button
- Strategy selector (from saved strategies)
- Starting cash input
- Results panel: equity curve summary, trade count, metrics grid

### `Analytics.jsx`
- Left sidebar: scrollable list of past runs
- Main area: equity curve chart (Recharts `LineChart`) + drawdown overlay
- **Compare mode** — overlay up to 5 runs on the same chart (colours from `RUN_COLORS`)
- Metrics grid: all `compute_metrics` fields displayed as stat cards
- **AI Analysis tab** — 4th tab in the run detail panel; inline multi-turn chat about the selected run via `POST /ai/analyze` with `subject_type: "run"`; 8 quick-prompt chips; chat resets on run change

### `StrategyBuilder.jsx`
Two modes (tab strip):
- **Manual Builder** — visual rule editor
- **AI Strategy** — chat with an LLM to generate rules

Manual builder:
- Rule roles: Entry Long / Exit Long / Entry Short / Exit Short (pill nav)
- Each rule: name, role selector, timing (on_change / every_tick), quantity
- Conditions: Signal conditions (price, SMA, EMA, RSI, MACD, Bollinger, Volume) or Exit conditions (T/P %, Stop-loss %, bars held, time of day, day of week)
- Condition picker is inline (not a dropdown) — expands below the add buttons within the rule card
- AND/OR combiners between conditions
- Load / Save to DB
- JSON preview toggle

**Custom indicator conditions**: when a condition's left operand is `type: "custom"`, the expanded condition card renders a `CustomOperandPanel` instead of the generic `OperandEditor`. This panel shows the indicator name and inline number inputs for every editable parameter (extracted via `getEditableParams(ind.expr.expr)`). Edited values are stored as `left.overrides: {path: value}` and serialized into the strategy JSON. The condition summary shows `🔷 IndicatorName (N overrides)` when any overrides are set.

### `IndicatorBuilder.jsx`
Expression tree editor for custom indicators. Supports:
- `const`, `operand` (price/SMA/EMA/RSI/MACD/Bollinger), `binop` (+−×÷^%), `unop` (neg/abs/sqrt/log), `clamp`, `ifelse`
- AI chat tab to generate expression trees from natural language

**Parameter overridability**: all `const` node values and operand numeric params (`period`, `std_dev`, `fast`, `slow`, `signal`) stored in an indicator's expression tree are overridable per strategy use — no rebuild needed. The AI indicator builder is instructed to place tunable values in explicit `const` nodes and always include `period` params so they appear as override inputs in StrategyBuilder.

### `KeyManager.jsx`
Multi-key manager. Two panels:

**Data Providers** (service → `data_api_keys` table):
- Alpha Vantage, Polygon.io, Massive (rebranded Polygon), Yahoo Finance (no key), Finnhub, IEX Cloud
- Each key shows: label, service, active indicator, "Use this" button (for inactive keys), delete

**AI Models** (model → `model_api_keys` table):
- Anthropic: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`
- OpenAI: `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini`
- xAI: `grok-3`, `grok-3-mini`, `grok-2`
- Google: `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash`

**Provider auto-detection from API key format:** `sk-ant-*` → Anthropic, `xai-*` → xAI, `AIza*` → Google, `sk-*` → OpenAI.

**Fetch available models:** "Fetch available models" button in KeyManager calls `POST /ai/list-models` with the raw key; returns live model list from provider's API.

**No SDK dependencies:** All four providers call REST APIs directly via `httpx`. No `anthropic`, `openai`, or `google-generativeai` packages required.

Key storage: raw base64 OR encrypted (PBKDF2 + Fernet) if user enables password protection.

---

## Design System

`App.css` defines CSS variables and reusable classes.

**CSS Variables:**
```css
--bg       /* page background */
--surface  /* card surface */
--panel    /* panel background */
--panel2   /* secondary panel */
--border   /* border color */
--accent   /* primary accent (blue) */
--green    /* profit/positive */
--red      /* loss/negative */
```

**Utility Classes:**
```
.btn            base button
.btn-primary    accent-coloured CTA
.btn-danger     red destructive action
.btn-sm         compact button
.btn-pill       rounded pill button
.card           padded bordered card
.stat-card      metric display card
.tab-strip      horizontal tab container
.tab-btn        individual tab button (add .active for selected state)
.alert          info alert box
.alert-warn     amber warning alert
.alert-error    red error alert
.view           page container (padding + max-width)
.spinner        loading spinner (CSS animation)
```

---

## Database Schema

```sql
-- Rule-based strategies
CREATE TABLE strategies (
    id INTEGER PRIMARY KEY,
    name TEXT,
    logic TEXT,          -- "rule_based"
    config TEXT,         -- JSON: { rule_set: { name, rules: [...] } }
    is_builtin INTEGER DEFAULT 0  -- 1 = pre-seeded; deletion blocked
);

-- Custom indicators
CREATE TABLE indicators (
    id INTEGER PRIMARY KEY,
    name TEXT,
    expression TEXT,     -- JSON expression tree
    is_builtin INTEGER DEFAULT 0  -- 1 = pre-seeded; deletion blocked
);

-- Data provider API keys (multi-key, one active at a time)
CREATE TABLE data_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,          -- "alpha-vantage" | "polygon" | "massive" | ...
    key_data TEXT DEFAULT '',       -- raw base64 or encrypted ciphertext
    protected INTEGER DEFAULT 0,   -- 1 = encrypted with user password
    active INTEGER DEFAULT 0,      -- 1 = currently active
    label TEXT DEFAULT ''
);

-- AI model API keys (multi-key, one active at a time)
CREATE TABLE model_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,       -- e.g. "claude-sonnet-4-6"
    provider TEXT NOT NULL DEFAULT '', -- "anthropic" | "openai" | "grok" | "gemini"
    key_data TEXT DEFAULT '',
    protected INTEGER DEFAULT 0,
    active INTEGER DEFAULT 0,
    label TEXT DEFAULT ''
);

-- Backtest run history
CREATE TABLE backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT,
    strategy_hash TEXT UNIQUE,      -- SHA-256 for deduplication
    ticker TEXT,
    timeframe TEXT,
    start_date TEXT,
    end_date TEXT,
    starting_cash REAL,
    run_at TEXT,                    -- ISO UTC timestamp
    params_json TEXT,               -- full params dict
    metrics_json TEXT,              -- compute_metrics output
    equity_curve_json TEXT,         -- [{timestamp, value}, ...]
    trade_log_json TEXT,            -- [{entry, exit, pnl, ...}, ...]
    signal_log_json TEXT            -- [{t, symbol, action, blocked}, ...]
);
```

**Deduplication**: `strategy_hash` is SHA-256 of strategy config + ticker + dates + cash + `run_at` timestamp. Since `run_at` is always unique, every run creates a new row (no dedup suppression).

---

## Execution Model

```
Bar N close  →  evaluate conditions  →  queue order
Bar N+1 open →  fill at open price   →  update portfolio
```

1. For each bar, `engine.py` evaluates all strategy conditions against the current bar's indicators
2. If a rule fires, an order is queued (not immediately filled)
3. The next bar's `open` price is used for fill (prevents lookahead bias)
4. `FillModel` applies liquidity constraints, price impact, and slippage to the fill price
5. Portfolio state is updated; equity is recorded at bar close

**Warmup period**: the engine skips the first N bars where N = `strategy.warmup_bars` (max lookback across all indicators). No orders fire during warmup.

### Advanced Execution Options (set in Backtest → Advanced Settings)

| Option | Default | Description |
|---|---|---|
| `sizing_mode` | `"fixed"` | `"fixed"` uses the quantity from the strategy rule; `"all_in"` computes qty as `cash × leverage / open_price` at fill time |
| `leverage` | `1.0` | Multiplier on available cash for `all_in` mode (e.g. `2.0` = 2× leveraged position) |
| `commission_mode` | `"none"` | `"none"` = no commission; `"pct"` = `filled_qty × price × (value/100)`; `"flat"` = fixed `$value` per fill |
| `commission_value` | `0.0` | Numeric value for `commission_mode` (percentage or flat dollar amount) |
| `allow_fractional` | `false` | `false` = whole units only (stocks/futures): qty is `math.floor`-ed; orders < 1 unit are skipped. `true` = fractional units allowed (crypto). |

These options are passed through the API form fields, applied in `engine.py`, and saved in `params_json` of the run record so they appear in the Analytics detail view.

**Duplicate-fill guard (all_in mode)**: when multiple rules fire entry signals on the same bar, `_handle_signal` blocks any entry where `portfolio.cash <= 0`. Additionally, `_fill_pending_at_open` re-checks the current position before processing each entry order in the batch — if a previous order in the same batch already opened a position, subsequent entry orders for the same symbol are skipped. This prevents phantom fills from floating-point cash residuals.

---

## Data Providers

All providers return rows shaped as:
```python
{"timestamp": str, "open": float, "high": float, "low": float, "close": float, "volume": float, "symbol": str}
```

| Provider ID | Notes | Search API |
|---|---|---|
| `alpha-vantage` | `SYMBOL_SEARCH` function | Yes |
| `polygon` | `/v3/reference/tickers` | Yes |
| `massive` | Same API as Polygon, base URL: `api.massive.com` | Yes |
| `yahoo-finance` | No key required; unofficial API | Yes (`/v1/finance/search`) |
| `finnhub` | Candle endpoint, `/api/v1/search` for tickers | Yes |
| `iex-cloud` | Chart endpoint, `/stable/search/{q}` | Yes |

Ticker search endpoint: `GET /data/search-tickers?q=QUERY` → `{"results": [{"symbol": str, "name": str}]}`

**Key handling**: unprotected keys migrated to OS keychain (`keyring` library) at startup; DB stores `"keychain"` sentinel. Legacy base64 and password-encrypted keys also supported. On decode, `.strip()` is applied to remove accidental whitespace (common copy-paste issue).

---

## AI Features

### AI Strategy Builder
Endpoint: `POST /ai/build-strategy`
- Accepts: `{prompt: str, temperature: float}`
- Reads active model key from `model_api_keys` table
- Supports: Anthropic, OpenAI, Grok, Google Gemini
- Returns: `{name, rules, warnings}` matching the rule-set format
- AI-generated rules are loaded directly into the Manual Builder on "Edit in Manual Builder"

**Custom indicator context**: `_get_custom_indicator_context()` in `api.py` appends a section to the system prompt listing every user-created indicator with its description and editable parameter paths + defaults (e.g. `params: cond_right=30, cond_left.operand.period=14`). The AI is instructed to set `overrides` when the user specifies custom values, and to omit `overrides` otherwise.

**Auto-populate overrides**: `_auto_populate_overrides(strategy)` in `api.py` is called after AI generation and validation. It walks all conditions and, for any `custom` operand with no `overrides`, fills in the indicator's default param values from the registry. This makes every generated strategy self-documenting. Existing AI-set overrides take priority.

**`AIStrategyChat.jsx`**: loads custom indicators on mount and appends their names + parameter hint to the welcome message. Model name badge now correctly fetches from `GET /db/model-keys`.

### AI Indicator Builder
Endpoint: `POST /ai/build-indicator`
- Accepts: `{prompt: str}`
- Returns: `{name, description, expr, color}` — an expression tree
- Expression tree nodes: `const`, `operand`, `binop`, `unop`, `clamp`, `ifelse`
- System prompt includes "Parameter Overridability" section: instructs AI to put thresholds/multipliers in `const` nodes and always include explicit `period` params, maximising per-use overridability

Both chat UIs display the active model name as a pill badge in the header. Shows "No AI model configured" if no model key is saved.

### AI Analyzer
Endpoint: `POST /ai/analyze`
- Accepts: `{subject_type: "strategy"|"indicator"|"run", subject_id: int, messages: [{role, content},...], temperature: float, password: str|null}`
- Fetches the full strategy/indicator definition or run report from DB and injects it into the system prompt
- Returns: `{reply: str}` — plain-text AI response for the current turn
- Temperature fixed at **0.2** (frontend constant) for objective, analytical output
- Multi-turn: the full `messages` history is sent each request; AI maintains context without re-loading the definition

**`strategy_analyzer.py`**: `STRATEGY_ANALYST_PROMPT` instructs the AI to be factual and balanced — identify both strengths and weaknesses equally, flag structural problems (missing exits, unbounded risk, overfitting risk, parameter sensitivity). Function: `analyze_strategy_chat(strategy_data, messages, provider, temperature)`.

**`indicator_analyzer.py`**: `INDICATOR_ANALYST_PROMPT` instructs the AI to derive all conclusions from the expression tree, state output value ranges precisely, and flag edge cases (warmup, divide-by-zero, clamp saturation). Function: `analyze_indicator_chat(indicator_data, messages, provider, temperature)`.

**`run_analyzer.py`**: `RUN_ANALYST_PROMPT` instructs the AI to be objective and factual — flag poor risk-adjusted returns, high drawdown, insufficient trade count, compare to buy-and-hold, note execution impacts. Injects a summarized run report (all metrics, full trade log, equity summary stats, signal counts) — raw `equity_curve` array is excluded and replaced with `equity_summary` to keep prompt size manageable. Function: `analyze_run_chat(run_data, messages, provider, temperature)`.

**`Analyzer.jsx`**: Left panel (Strategies | Indicators tabs + scrollable list) + right chat panel. Built-in quick-prompt chips appear above the input box — 8 strategy-specific and 8 indicator-specific prompts. No creativity slider (temperature is hardcoded to 0.2). Amber accent color (`#f59e0b`). Prompts fire directly without appearing in the textarea.

**`Analytics.jsx` AI Analysis tab**: Within the run detail panel, a 4th tab "✦ AI Analysis" appears alongside Equity Curve / Drawdown / Asset Price. Contains an inline multi-turn chat against the selected run (`subject_type: "run"`). 8 quick-prompt chips shown when chat is empty. Chat resets when switching runs. Shows a "No AI model configured" notice if no active model key is saved.

---

## Key Manager (API Keys)

Keys are stored in two separate tables (`data_api_keys`, `model_api_keys`).
Only one key per table can be `active=1` at a time.

**Storage format**:
- Unprotected: `base64(raw_key)`
- Protected: `base64(salt) + ":" + fernet_token` (PBKDF2HMAC-SHA256, 100k iterations)

**Encryption endpoints**: `/keys/encrypt`, `/keys/decrypt` — used by the frontend before saving/after loading protected keys.

**Legacy migration**: if the old `api_keys` table has data and the new tables are empty, the old key is migrated on first startup.

---

## Analytics & Run History

- All backtest runs are persisted automatically after a successful run (`db.save_run`)
- Every run is always inserted fresh — `run_at` (UTC ISO timestamp) is included in the dedup hash so re-running the same strategy always creates a new record
- Advanced execution settings (`sizing_mode`, `leverage`, `commission_mode`, `commission_value`, `allow_fractional`) are stored in `params_json` and shown as badges in the Analytics detail view
- Pre-built strategies & indicators are auto-seeded on server startup (idempotent — skips names that already exist)

**API endpoints for runs**:

| Method | Path | Description |
|---|---|---|
| `GET` | `/db/runs` | List all runs (metadata + metrics, no equity curve) |
| `GET` | `/db/runs/{id}` | Full run with equity curve, trade log, and params |
| `DELETE` | `/db/runs/{id}` | Delete a single run |
| `DELETE` | `/db/runs` | Delete **all** runs |
| `POST` | `/db/runs/batch-delete` | Delete multiple runs by id — body: `{"ids": [1,2,3]}` |

**Analytics UI features**:
- Sidebar search: filter runs by strategy name or ticker (client-side, instant)
- **Select** checkbox on each card: marks runs for batch deletion
- **Delete selected (N)** button appears when any runs are selected
- **Delete all runs** button at sidebar bottom (with confirmation dialog)
- Compare mode unchanged: up to 5 runs, equity curves overlaid on one chart
- Run detail header shows: ticker, timeframe, date range, capital, `run_at`, execution setting badges, and warmup bar count

---

## Testing

```bash
python -m pytest tests/ -v
```

| Module | Tests | Coverage |
|---|---|---|
| `test_metrics.py` | `compute_metrics` (return, drawdown, win rate, round-trip count), `match_round_trips_from_dicts` (long/short, partial fills, multi-symbol) |
| `test_fill_model.py` | Adverse pricing, liquidity limits, zero-volume fallback, open-price fills, seed determinism |
| `test_csvparser.py` | OHLCV parsing, column aliases, custom maps, missing column errors, bad-row skipping |
| `test_engine.py` | Equity curve generation, trade execution, tick counting, all-in sizing, signal log |

---

## Known Bugs & Fixes Applied

| Bug | Fix |
|---|---|
| `profit_factor = Infinity` caused `GET /db/runs` to return 500 (FastAPI strict JSON) | `_sanitize_floats()` in `db.py` replaces NaN/Inf with `None` |
| API key with leading `\t` (tab) sent as `%09` in URLs → 401 from providers | `.strip()` applied after all base64 decode / decryption calls in `api.py` |
| StrategyBuilder picker dropdown clipped by `overflow: hidden` on rule card | Picker converted from `position: absolute` to inline block rendering |
| StrategyBuilder rule card `maxHeight` cut off signal/T&P panels | `maxHeight` removed; card grows naturally with content |
| JSX error (siblings in ternary without fragment) in Backtest.jsx cache badge | Wrapped siblings in `<>...</>` fragment |
| Re-running the same strategy did not create a new Analytics entry (dedup collision) | `run_at` timestamp added to hash params; every run now inserts a unique row |
| Pre-built strategies disappeared when another session or agent modified the DB | `seed_prebuilts.seed()` now called at every server startup (idempotent) |
| Analytics sidebar showed no capital, timeframe, or execution settings for saved runs | Capital + timeframe added to `RunCard`; execution params shown as badges in detail header via `params` field |
| `POST /db/strategies` wiped ALL strategies on every save (DELETE + INSERT of only 1) | Changed to upsert logic — update by id/name, never delete existing rows |
| `Backtest.jsx` called non-existent `GET /db/api_keys` → ticker search always disabled | Changed to `GET /db/data-keys`, checks `d.keys?.some(k => k.active)` |
| Blocked signals never logged in `_signal_log` (append inside `if not blocked:`) | Moved `_signal_log.append` outside the guard; blocked signals now recorded with `blocked: true` |
| Switching operand type to Bollinger in StrategyBuilder → `KeyError` crash (missing `component`) | Backend: `d.get("component", "upper")` default. Frontend: type-change sets `component: "upper"`, `std_dev: 2` |
| `day_of_week` exit condition: frontend sent 0-6 (Sunday=0), backend used ISO 1-7 (Sunday=7) | Frontend DOW array aligned to ISO weekday (1=Mon..7=Sun); AI system prompt updated |
| `take_profit_abs` / `stop_loss_abs` used `starting_cash` instead of `entry_equity` as baseline | Changed to use `entry_equity` (with fallback to `starting_cash` if None) |
| `_bars_in_trade` counter counted bars since last rule fire, not bars since trade entry | Fixed: increments while position held, resets when flat (for exit rules) |
| AI validator rejected exit-condition-only rules (empty `conditions` array) | Allow empty `conditions` if rule has exit conditions |
| StrategyBuilder save pushed `{name}` without `config` → load from dropdown failed | Optimistic update now includes full strategy object with config |
| MACD deque skipped append when consecutive ticks had identical MACD values | Track tick index per MACD key; append exactly once per tick regardless of value |
| All 6 data providers omitted `high`/`low` from fetched rows → `highest_high`/`lowest_low`/ATR/Williams %R all used `close` for both, producing NaN or constant values | All providers now extract `high`/`low` from API responses and include them in row dicts |
| StrategyBuilder page went blank when all rules were deleted (`useState(rules[0]._id)` crashed when `rules=[]`) | Lazy initialiser `useState(() => rules[0]?._id ?? null)` + `useEffect` auto-corrects `selectedRole` when its role becomes empty |
| No way to delete a saved strategy; deleting all rules to "clear" a strategy caused a blank page crash | Added `DELETE /db/strategies/{id}` endpoint; frontend: `loadedStrategyId` tracks the loaded record; toolbar "Delete Strategy" button deletes from DB; saving with 0 rules and a loaded strategy also deletes it |
| Deleting an indicator gave no warning when strategies referenced it | IndicatorBuilder fetches all strategies on mount; shows a `confirm()` listing affected strategy names before allowing delete |
| Built-in strategies and indicators could be deleted | `is_builtin INTEGER DEFAULT 0` column added to both tables; `DELETE` endpoints return 403 for built-in rows; `seed_prebuilts.seed()` sets `is_builtin=1`; frontend hides "Delete" / "Delete Strategy" buttons for built-in records |
| `AIStrategyChat.jsx` model name badge never showed (called non-existent `GET /db/api_keys`) | Changed to `GET /db/model-keys`; finds the key with `active: true` to display its `model_name` |
| Custom indicator conditions in StrategyBuilder had no UI for adjusting internal values | Added `CustomOperandPanel` + `getEditableParams()` in StrategyBuilder; `overrides` dict on `CustomIndicatorOperand`; `_eval_node` applies overrides at runtime; AI strategy builder context includes param paths and auto-populates defaults |
| `time_of_day` exit compared the value (minutes 0-1439) against `tick.time.hour` (0-23) — never matched | Changed to `tick.time.hour * 60 + tick.time.minute` |
| Bollinger Bands and Sharpe/Sortino used population variance (÷N) | Changed to sample variance (÷(N-1)) |
| ATR used a simple mean of true ranges instead of Wilder's smoothing | Replaced with seed-SMA + RMA: `atr = (prev*(period-1)+TR)/period` |
| EMA recomputed from the full price buffer O(n) on every tick | Added `_ema_state`/`_ema_last_tick` dicts for O(1) incremental updates; state included in `_SnapShot` |
| `time_of_day` missing from `OPERAND_SCHEMA` — not selectable as a condition in the UI | Added entry `"time_of_day": {"params": []}` |
| `_SnapShot` omitted `_macd_last_tick`, `_tick_count`, `_ema_state`, `_ema_last_tick` — MACD/EMA state lost on snapshot restore | All four dicts now copied in `_SnapShot.__init__` |
| `compute_metrics` always used `bars_per_year=252` regardless of timeframe — weekly/hourly Sharpe/CAGR wrong | Added `_BARS_PER_YEAR` dict and `_bars_per_year(timeframe)` helper in `api.py` |
| Round-trip P&L ignored commission — overstated `profit_factor`/`win_rate` | `_match_round_trips` now prorates entry + exit commission per matched lot |
| CAGR returned `0%` on total-loss scenarios | Added `last_eq <= 0` branch returning `-100.0` |
| Max drawdown included warmup bars and pre-trade cash drift | Gated on `asset_value != 0`; peak resets at each new position entry (in both `metrics.py` and `Analytics.jsx buildDrawdown`) |
| `profit_factor=Infinity` in live `/backtest/upload` response → invalid JSON | Set to `None` directly in `compute_metrics` (not just on DB save) |
| Multi-symbol backtest: all pending orders filled against one tick's prices | `_fill_pending_at_open` filters to orders matching `tick.name`; others remain queued |
| Equity curve recorded `tick.bid` instead of mid-price | Changed to `(tick.bid + tick.ask) / 2 if tick.ask else tick.bid` |
| Asymmetric slippage: buys could receive favourable slip, sells always `abs()` | Buy fill price changed to `base + impact + abs(slippage)` |
| Trade log recorded full order quantity, not actual executed quantity for partial fills | `portfolio.py` sets `quantity = sold` / `quantity = cover_qty` before appending to trade log |
| Unparseable CSV timestamps silently replaced with `datetime.utcnow()`, corrupting time series | Changed to `skipped += 1; continue` |
| Non-UTF8 CSV files crashed with unhandled `UnicodeDecodeError` | Added encoding fallback loop: `utf-8-sig` → `cp1252` → `latin-1` |
| Yahoo Finance empty result returned silently with no error | Added check for empty `results`; raises `HTTPException(404)` |
| `allow_credentials=True` + wildcard `allow_origins=["*"]` — browsers reject per spec | Changed to `allow_credentials=bool(_RAW_ORIGINS)` |
| `POST /db/indicators` deleted all indicators before re-insert with no transaction — data loss on failure | Wrapped in `try/except/rollback/finally` |
| `POST /db/strategies` UPDATE path could overwrite built-in strategies | Added `is_builtin` check; built-in rows skipped with `continue` |
| Batch delete dropped JS float-encoded IDs (e.g. `"3.0"`) via `str(i).isdigit()` check | Changed to `int(float(i))` |
| `_rows_to_csv` crashed when rows had inconsistent keys | Collects all keys via union; uses `extrasaction="ignore"` on `DictWriter` |
| `AIIndicatorChat` called `/db/api_keys` (wrong endpoint) + wrong response shape | Changed to `GET /db/model-keys`; extracts `active?.model_name` from `d.keys` |
| No validation that selected model matched key provider — silent failure | `ModelKeyPanel.save()` checks provider mismatch and shows descriptive error |
| `activate`/`remove` in `KeyManager` had no error handling | Wrapped in `try/catch` with `r.ok` checks |
| DB connections leaked on exception — no `try/finally` for `conn.close()` | Added `try/finally: conn.close()` to `create_tables`, `list_runs`, `get_run` |
| `equity_curve`/`trade_log` defaulted to `{}` (dict) when NULL in DB | Changed default to `[]` for list fields |
| ALTER TABLE migration failures silently swallowed with bare `except: pass` | Only ignores `OperationalError` with "duplicate column"; re-raises others |
| `useEffect` in `StrategyBuilder` missing `selectedRole` dependency | Added `selectedRole` to the dependency array |
| Save optimistic update missing server `id` — newly saved strategy couldn't be deleted without refresh | Changed to re-fetch strategies after save to obtain real `id` |
| Right-side operand in `StrategyBuilder` ignored `custom` indicator type | Added `type === 'custom'` check; renders `CustomOperandPanel` for right side |
| `aiGeneratedIndicator` not cleared after adding — double-add possible | Added `setAiGeneratedIndicator(null)` in `addAiIndicator` |
| Empty indicators (no blocks) saved to DB with `expr: null` | Added `.filter(ind => ind.blocks?.length > 0)` before save payload mapping |
| Trade timestamp not shown in Analytics trade log table | Added Time column rendering `String(t.t).slice(0, 19)` |
| Delete operations cleared UI state optimistically even on server failure | `deleteRun`, `deleteBatch`, `deleteAll` now check `r.ok` and throw before mutating state |
| `toggleCompare` race condition: rapid clicks caused duplicate fetches via stale closure | Added `_compareFetching = useRef(new Set())` in-flight guard; functional `setCompareData` update |
| `column_map` sent to `/backtest/upload` missing `open`/`high`/`low` — ATR/highest_high/lowest_low received `NaN` | Added `open:'open', high:'high', low:'low'` to the column map |
| `AIStrategyChat` errors shown twice (chat bubble + bottom error box) | Removed `setError` call from catch block; errors appear only as chat bubbles |
