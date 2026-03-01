# RECORDED BUGS!

## Backend

| # | File | Severity | Description |
|---|------|----------|-------------|
| B1 | `api.py:59` | Medium | CORS `allow_credentials=True` with wildcard `allow_origins=["*"]` — browsers reject this per spec |
| B2 | `api.py:807` | **High** | `compute_metrics` always uses `bars_per_year=252` regardless of timeframe — weekly/hourly Sharpe/CAGR are wrong |
| B3 | `api.py:1435` | **High** | `POST /db/indicators` deletes all user indicators before re-insert with no transaction rollback — data loss risk |
| B4 | `api.py:1361` | Medium | `POST /db/strategies` UPDATE path doesn't check `is_builtin` — prebuilt strategies can be overwritten |
| B5 | `api.py:1303` | Medium | Batch delete `str(i).isdigit()` drops float-encoded IDs from JS |
| B6 | `api.py:689` | Medium | `_rows_to_csv` crashes if rows have inconsistent keys (no `extrasaction='ignore'`) |
| B7 | `api.py:1074` | Low | Yahoo empty result silently returns no rows, no error raised |
| B8 | `engine.py:162-208` | **High** | Multi-symbol: ALL pending orders filled against single tick's prices (wrong symbol prices) |
| B9 | `engine.py:267` | Low | Equity curve logs `tick.bid` as price but portfolio uses mid-price for valuation |
| B10 | `metrics.py:180-188` | Medium | Round-trip P&L ignores commission — overstates profit_factor/win_rate |
| B11 | `metrics.py:68-70` | Medium | CAGR shows 0% for total-loss scenarios instead of -100% |
| B12 | `metrics.py:73-82` | Medium | Max drawdown uses all bars including warmup, doesn't gate on `asset_value` |
| B13 | `metrics.py:98-112` | Low | Sharpe/Sortino use population variance (N) instead of sample variance (N-1) |
| B14 | `metrics.py:119` | Medium | `profit_factor=Infinity` in live API response is invalid JSON (only sanitised on DB save) |
| B15 | `csvparser.py:191` | **High** | Unparseable timestamps get `datetime.utcnow()` instead of being skipped — corrupts time series |
| B16 | `csvparser.py:127` | Low | Non-UTF8 CSV files crash with unhandled `UnicodeDecodeError` |
| B17 | `fill_model.py:99-102` | Medium | Asymmetric slippage: sells always use `abs(slippage)`, buys can get favourable slippage |
| B18 | `strategy_rules.py:529` | **High** | `time_of_day` exit uses hours (0-23) but signal operand returns minutes (0-1439) — incompatible |
| B19 | `strategy_rules.py:838` | Low | Bollinger Bands use population std dev, not sample — narrower than industry standard |
| B20 | `strategy_rules.py:924` | Medium | ATR uses simple mean, not Wilder's smoothing — non-standard results |
| B21 | `strategy_rules.py:789` | Medium | EMA recomputed from full buffer O(n) every tick — performance bottleneck |
| B22 | `strategy_rules.py` | Low | `time_of_day` missing from `OPERAND_SCHEMA` — not selectable in UI |
| B23 | `strategy_rules.py` | Medium | `_SnapShot` doesn't copy `_macd_last_tick`/`_tick_count` — MACD crossover on snapshots may duplicate values |
| B24 | `portfolio.py:107` | **High** | Trade log records full order `quantity`, not actual executed qty for partial fills |

## Database

| # | File | Severity | Description |
|---|------|----------|-------------|
| D1 | `db.py` (all funcs) | Medium | No `try/finally` or context managers for `conn.close()` — connections leaked on exceptions |
| D2 | `db.py:430` | Medium | `equity_curve`/`trade_log` default to `{}` (dict) instead of `[]` (list) when NULL |
| D3 | `db.py:114-151` | Low | ALTER TABLE migration failures silently swallowed with bare `except: pass` |

## Frontend

| # | File | Severity | Description |
|---|------|----------|-------------|
| F1 | `AIIndicatorChat.jsx:16` | **High** | Wrong endpoint `/db/api_keys` (should be `/db/model-keys`) + wrong response shape — always shows "No AI model configured" |
| F2 | `Analytics.jsx:31` | Medium | `buildDrawdown` doesn't match backend logic (no `asset_value` gating) |
| F3 | `Analytics.jsx:407,423,442` | Medium | Delete operations don't check `r.ok` — optimistic clear even on failure |
| F4 | `Analytics.jsx:379` | Medium | `toggleCompare` race condition: stale `compareData` capture triggers duplicate fetches |
| F5 | `Analytics.jsx:173` | Low | Trade timestamp `t` not shown in trade log table |
| F6 | `StrategyBuilder.jsx:643` | Medium | `useEffect` missing `selectedRole` dependency |
| F7 | `StrategyBuilder.jsx:688,714` | Medium | Save optimistic update missing `id` — can't delete newly saved strategy without refresh |
| F8 | `StrategyBuilder.jsx:454` | Medium | Right-side operand ignores `custom` indicator type — broken for AI-generated strategies |
| F9 | `IndicatorBuilder.jsx:555` | Low | `aiGeneratedIndicator` not cleared after adding — double-add possible |
| F10 | `IndicatorBuilder.jsx:606` | Low | Empty indicators (no blocks) saved with `expr: null` |
| F11 | `KeyManager.jsx:287` | **High** | No validation that selected model matches key provider — e.g. GPT-4o + Anthropic key = silent failure |
| F12 | `KeyManager.jsx:151` | Medium | `activate`/`remove` have no error handling |
| F13 | `Backtest.jsx:200` | Medium | `column_map` missing `open`/`high`/`low` mappings |
| F14 | `AIStrategyChat.jsx:99` | Low | Errors displayed twice (message bubble + bottom box) |

## Cross-system / undefined

## Missing Prebuilt Indicators

### Can be added now (zero backend changes)

| Indicator | Expression |
|-----------|-----------|
| Williams %R | `(highest_high(14) - price) / (highest_high(14) - lowest_low(14)) * -100` |
| Stochastic %K | `(price - lowest_low(14)) / (highest_high(14) - lowest_low(14)) * 100` |
| Rate of Change (ROC) | `(price - lookback(mid, 12)) / lookback(mid, 12) * 100` |
| Keltner Channel Upper | `ema(mid, 20) + 2 * atr(14)` |
| Keltner Channel Lower | `ema(mid, 20) - 2 * atr(14)` |
| Donchian Midline | `(highest_high(20) + lowest_low(20)) / 2` |
| ATR(14) | `atr(14)` standalone |
| MACD Histogram | `macd(component=hist)` standalone |

### Would require new backend operands

- **Stochastic %D** — needs SMA/EMA of a computed expression output
- **VWAP** — cumulative stateful (volume-weighted running sum)
- **ADX** — Directional Movement (+DM/-DM) computation
- **OBV** — cumulative stateful (On-Balance Volume)
- **MFI** — cumulative stateful (Money Flow Index)
- **Parabolic SAR** — recursive/stateful formula
- **Ichimoku Cloud** — complex multi-component (Tenkan/Kijun/Senkou/Chikou)
- **TRIX / Hull MA / DEMA / TEMA** — EMA-of-EMA chaining (needs expression-output smoothing)
