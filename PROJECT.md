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
├── api.py                  # FastAPI app — all HTTP endpoints
├── engine.py               # Backtest engine (event loop, order queue)
├── fill_model.py           # Realistic fill simulation
├── metrics.py              # Quantitative performance analytics
├── strategy_rules.py       # Rule-based strategy execution
├── strategy.py             # Strategy factory (create_strategy / list_strategies)
├── portfolio.py            # Portfolio state management
├── tickdata.py             # TickData dataclass
├── csvparser.py            # CSV → TickData parsing
├── db.py                   # SQLite helpers (all DB access centralised here)
├── ai_strategy_builder.py  # LLM-powered strategy generation
├── ai_indicator_builder.py # LLM-powered indicator expression tree generation
├── indicator_registry.py   # Custom indicator store
├── actionmanager.py        # Action/order management
├── backtester.db           # SQLite database (auto-created)
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
    │   └── AIIndicatorChat.jsx  # Chat UI for AI indicator generation
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

### Operand warmup requirements
| Operand | `min_bars` |
|---|---|
| SMA(n) | n |
| EMA(n) | n × 2 (stabilisation) |
| RSI(n) | n + 1 |
| Bollinger(n) | n |
| MACD(fast, slow, signal) | slow + signal |
| Lookback(n) | n + 1 |

### `db.py`
All SQLite access is centralised here. Never import `sqlite3` directly elsewhere.
- `ensure_db()` / `create_tables()` — idempotent schema setup (called at startup)
- `_sanitize_floats(obj)` — recursively replaces NaN/Inf with None for JSON safety

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
| POST | `/ai/list-models` | Fetch live model list from a provider's API (body: `{provider, api_key}`) |
| GET | `/ai/schema` | Strategy schema + supported providers/models |
| GET | `/ai/indicator-schema` | Indicator expression tree schema |

### Database — Strategies & Indicators
| Method | Path | Description |
|---|---|---|
| GET | `/db/strategies` | List all saved strategies |
| POST | `/db/strategies` | Save strategies |
| GET | `/db/indicators` | List all saved indicators |
| POST | `/db/indicators` | Save indicators |

### Database — Run History
| Method | Path | Description |
|---|---|---|
| GET | `/db/runs` | List all backtest runs (metadata + metrics, no equity curve) |
| GET | `/db/runs/{id}` | Get a full run (includes equity curve + trade log) |
| DELETE | `/db/runs/{id}` | Delete a run |

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
Root component. Renders a tab strip with 5 tabs:
1. **Backtest** — main workflow
2. **Analytics** — historical runs
3. **Strategy Builder** — rule editor
4. **Indicator Builder** — expression tree editor
5. **Key Manager** — API key management

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

### `IndicatorBuilder.jsx`
Expression tree editor for custom indicators. Supports:
- `const`, `operand` (price/SMA/EMA/RSI/MACD/Bollinger), `binop` (+−×÷^%), `unop` (neg/abs/sqrt/log), `clamp`, `ifelse`
- AI chat tab to generate expression trees from natural language

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
    config TEXT          -- JSON: { rule_set: { name, rules: [...] } }
);

-- Custom indicators
CREATE TABLE indicators (
    id INTEGER PRIMARY KEY,
    name TEXT,
    expression TEXT      -- JSON expression tree
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
    trade_log_json TEXT             -- [{entry, exit, pnl, ...}, ...]
);
```

**Deduplication**: runs with identical strategy config + ticker + dates + cash get the same `strategy_hash` (SHA-256). Duplicate runs return the existing `id` without re-inserting.

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
{"timestamp": str, "open": float, "bid": float, "ask": float, "volume": float, "symbol": str}
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

**Key handling**: keys stored as base64. On decode, `.strip()` is applied to remove accidental whitespace (common copy-paste issue).

---

## AI Features

### AI Strategy Builder
Endpoint: `POST /ai/build-strategy`
- Accepts: `{prompt: str, temperature: float}`
- Reads active model key from `model_api_keys` table
- Supports: Anthropic, OpenAI, Grok, Google Gemini
- Returns: `{name, rules, warnings}` matching the rule-set format
- AI-generated rules are loaded directly into the Manual Builder on "Edit in Manual Builder"

### AI Indicator Builder
Endpoint: `POST /ai/build-indicator`
- Accepts: `{prompt: str}`
- Returns: `{name, description, expr, color}` — an expression tree
- Expression tree nodes: `const`, `operand`, `binop`, `unop`, `clamp`, `ifelse`

Both chat UIs display the active model name as a pill badge in the header. Shows "No AI model configured" if no model key is saved.

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
