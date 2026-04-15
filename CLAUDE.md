# Backtester — Agent Guide

Algorithmic trading backtester. Backend: FastAPI + SQLite (`api.py`). Frontend: React 19 + Vite (`frontend/`).

## Running

```bash
# Backend (repo root)
uvicorn api:app --reload

# Frontend
cd frontend && npm run dev
```

Backend: `http://localhost:8000` · Frontend: `http://localhost:5173`

## Key Files

| File | Purpose |
|---|---|
| `api.py` | App setup, startup, backtest endpoint; includes route modules |
| `routes_ai.py` | AI builder/analyzer endpoints (`/ai/*`) |
| `routes_data.py` | Data fetch & ticker search endpoints (`/data/*`) |
| `routes_db.py` | DB CRUD for runs, strategies, indicators, keys (`/db/*`) |
| `engine.py` | Event-driven backtest loop; next-bar-open execution, equity curve, signal log |
| `strategy_rules.py` | `RuleSetStrategy` — executes rule-based strategies |
| `fill_model.py` | Realistic fill simulation (liquidity, price impact, slippage) |
| `metrics.py` | Quantitative analytics (Sharpe, CAGR, drawdown, win rate…) |
| `db.py` | **All** SQLite access — never import `sqlite3` elsewhere |
| `portfolio.py` | Portfolio state; `Trade` dataclass with `time` field |
| `indicator_registry.py` | Custom indicator store; expression tree evaluator |
| `ai_strategy_builder.py` | LLM strategy generation; `AIProvider` abstract class with `_call_api` (single-turn) and `_call_api_multi` (multi-turn chat) |
| `ai_indicator_builder.py` | LLM indicator (expression tree) generation |
| `strategy_analyzer.py` | Multi-turn AI chat about a strategy; injects full strategy JSON into system prompt |
| `indicator_analyzer.py` | Multi-turn AI chat about an indicator; injects full expression tree into system prompt |
| `run_analyzer.py` | Multi-turn AI chat about a backtest run; injects summarized run report (metrics, trades, equity summary) into system prompt |
| `seed_prebuilts.py` | Idempotent seed — 5 strategies + 13 indicators; called at startup |
| `tickdata.py` | `TickData` dataclass (`close`, `open`, `high`, `low`, `volume`) |
| `strategy.py` | Strategy base class, registry, `create_strategy()` |

## Architecture Notes

- **Execution model**: signal at bar close → order queued → fills at *next* bar's open (no lookahead)
- **Warmup**: engine skips first N bars where N = `strategy.warmup_bars` (max indicator lookback)
- **Route modules**: `routes_ai.py`, `routes_data.py`, `routes_db.py` — mounted via `APIRouter`; use late imports (`_decode_key_import()`, `_keyring_refs()`) to avoid circular deps
- **DB layer**: `db.py` owns all SQLite; `db_conn` context manager guarantees close; `_sanitize_floats()` replaces NaN/Inf → `None` for JSON safety
- **AI providers**: Anthropic, OpenAI, Grok, Gemini — all via direct `httpx` REST calls, **no SDKs**
  - Anthropic: `POST api.anthropic.com/v1/messages`, header `x-api-key` + `anthropic-version: 2023-06-01`
  - OpenAI / Grok: `POST .../v1/chat/completions`, header `Authorization: Bearer`; use `max_completion_tokens` (not `max_tokens`) for o1/o3/o4 models
  - Gemini: `POST generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=…`
  - Key auto-detect: `sk-ant-*`→anthropic, `xai-*`→grok, `AIza*`→gemini, `sk-*`→openai
- **`_call_api_multi(messages, system_prompt, temperature)`**: added to `AIProvider` + all 4 concrete providers for multi-turn chat; Gemini maps `"assistant"` → `"model"`; OpenAI o1/o3/o4 skip system role
- **Analyzer**: `POST /ai/analyze` endpoint; supports `subject_type: "strategy" | "indicator" | "run"`; each module injects full definition/report into system prompt; temperature fixed at 0.2 for objective output. Run analysis uses summarized equity stats (not raw curve array) + full trade log.
- **`_extract_json(text)`**: strips ``` fences, uses `json.JSONDecoder.raw_decode` from first `{`
- **Indicator overrides**: `const` node values and operand params (`period`, `std_dev`, `fast`, `slow`, `signal`) are overridable per-strategy-use via `overrides` dict on `CustomIndicatorOperand`
- **Strategies table**: use upsert by id/name — never DELETE + re-INSERT all rows
- **Run dedup**: `run_at` timestamp is included in the SHA-256 hash so every run creates a unique row
- **`is_builtin` column**: both `strategies` and `indicators` tables have this; `DELETE` endpoints return 403 for built-in rows
- **Metrics**: includes `calmar_ratio` (CAGR / |max_drawdown|) in addition to Sharpe/Sortino
- **OS keychain**: unprotected API keys are migrated to OS keychain via `keyring` library at startup; DB stores `"keychain"` sentinel instead of raw base64

## Data Provider Row Shape

```python
{"timestamp": str, "open": float, "high": float, "low": float,
 "close": float, "volume": float, "symbol": str}
```

All 6 providers (Alpha Vantage, Polygon, Massive, Yahoo Finance, Finnhub, IEX Cloud) must populate `high` and `low`; omitting them breaks ATR / Williams %R / highest_high / lowest_low operands.

## Frontend Conventions

- Design system in `App.css` — use CSS variables (`--bg`, `--surface`, `--accent`, `--green`, `--red`) and utility classes (`.btn`, `.btn-primary`, `.btn-danger`, `.card`, `.stat-card`, `.tab-strip`, `.tab-btn`, `.alert`)
- No external state management — local `useState`/`useEffect` only
- StrategyBuilder condition picker is **inline** (not absolutely positioned) to avoid overflow clipping
- Analytics equity chart: Y-axis is % return normalised to starting cash; trade markers on equity line; Brush for zoom

## Testing

```bash
python -m pytest tests/ -v
```

Tests cover: metrics (compute_metrics, round-trip matching), fill model (liquidity, slippage, determinism), CSV parser (OHLCV, aliases, error handling), engine (equity curve, trade execution, all-in sizing, signal log).

## Full Documentation

See [PROJECT.md](PROJECT.md) for complete API reference, DB schema, component docs, and the full bug log.
