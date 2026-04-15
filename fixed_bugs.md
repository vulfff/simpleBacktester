# Fixed Bugs

All bugs from `recorded_bugs.md` — fixed in group order (C → A → B → D → F → I → E → H → G → J).

---

## Group C — `strategy_rules.py`

| # | Fix |
|---|-----|
| B18 | `time_of_day` exit compared hours against minutes. Changed to `tick.time.hour * 60 + tick.time.minute`. |
| B19 | Bollinger std dev divided by `period` (population). Changed to `period - 1` (sample). |
| B20 | ATR used a simple mean of true ranges. Replaced with Wilder's smoothing (seed SMA, then RMA). |
| B21 | EMA recomputed from full buffer O(n) each tick. Added `_ema_state`/`_ema_last_tick` dicts for incremental O(1) updates. |
| B22 | `time_of_day` missing from `OPERAND_SCHEMA` so it wasn't selectable in the UI. Added entry with empty `params`. |
| B23 | `_SnapShot` didn't copy `_macd_last_tick`, `_tick_count`, `_ema_state`, or `_ema_last_tick` — MACD/EMA state lost on snapshot restore. Added all four to the copy. |

---

## Group A — `metrics.py` + `api.py` + `Analytics.jsx`

| # | Fix |
|---|-----|
| B2 | `compute_metrics` always used `bars_per_year=252`. Added `_BARS_PER_YEAR` dict and `_bars_per_year(timeframe)` helper in `api.py`; passed correct value per timeframe. |
| B10 | Round-trip P&L ignored commission. `_match_round_trips` now tracks commission per queue entry and subtracts prorated entry + exit commissions from each round-trip P&L. |
| B11 | CAGR returned `0%` on total loss. Added `last_eq <= 0` branch returning `-100.0`. |
| B12 | Max drawdown measured from pre-warmup cash peak. Rewrote to gate on `asset_value != 0`; resets peak on each new position entry. |
| B13 | Sharpe/Sortino used population variance (÷N). Changed to sample variance (÷(N-1)). |
| B14 | `profit_factor=Infinity` in live API response → invalid JSON. Changed to `None` directly in `compute_metrics` instead of relying on DB sanitisation. |
| F2 | `buildDrawdown` in `Analytics.jsx` didn't match backend gating logic. Rewrote with `hasAv` check; gates on `asset_value > 0`, resets peak at each new position. |

---

## Group B — `engine.py` + `portfolio.py` + `fill_model.py`

| # | Fix |
|---|-----|
| B8 | Multi-symbol: all pending orders filled against one tick's prices. `_fill_pending_at_open` now filters `orders_to_process` to only orders matching `tick.name`; unmatched orders stay queued. |
| B9 | Equity curve recorded `tick.bid` instead of mid-price. Changed to `(tick.bid + tick.ask) / 2 if tick.ask else tick.bid`. |
| B17 | Asymmetric slippage: buys could get favourable slip, sells always `abs()`. Changed buy fill to `base + impact + abs(slippage)`. |
| B24 | Trade log recorded the requested order quantity, not the actual executed quantity for partial fills. `sell` path sets `quantity = sold`; `cover` path sets `quantity = cover_qty` before appending to trade log. |

---

## Group D — `csvparser.py` + `api.py`

| # | Fix |
|---|-----|
| B15 | Unparseable timestamps silently got `datetime.utcnow()`, corrupting the time series. Changed to `skipped += 1; continue`. |
| B16 | Non-UTF8 CSV files crashed with unhandled `UnicodeDecodeError`. Added encoding fallback loop: tries `utf-8-sig`, then `cp1252`, then `latin-1`. |
| B7 | Yahoo Finance returned empty results with no error. Added check for empty `results` list; raises `HTTPException(404)`. |

---

## Group F — `api.py` (endpoints)

| # | Fix |
|---|-----|
| B1 | `allow_credentials=True` + wildcard `allow_origins=["*"]` — browsers reject per spec. Changed to `allow_credentials=bool(_RAW_ORIGINS)` so credentials are only set when explicit origins are configured. |
| B3 | `POST /db/indicators` deleted all indicators before re-inserting with no rollback on failure. Wrapped in `try/except/rollback/finally`. |
| B4 | `POST /db/strategies` UPDATE path could overwrite built-in strategies. Added `is_builtin` check; built-in rows are skipped with `continue`. |
| B5 | Batch delete used `str(i).isdigit()` to validate IDs, which dropped JS float-encoded IDs like `"3.0"`. Changed to `int(float(i))`. |
| B6 | `_rows_to_csv` crashed on rows with inconsistent keys. Now collects all keys via union across all rows; uses `extrasaction="ignore"` on the `DictWriter`. |

---

## Group I — `AIIndicatorChat.jsx` + `KeyManager.jsx`

| # | Fix |
|---|-----|
| F1 | `AIIndicatorChat` called `/db/api_keys` (doesn't exist) and used the wrong response shape. Changed to `GET /db/model-keys`; extracts `active?.model_name` from `d.keys` array. |
| F11 | No validation that the selected model matched the key's provider — e.g. GPT-4o key + Anthropic model = silent failure. `save()` in `ModelKeyPanel` now checks provider mismatch and shows a descriptive error. |
| F12 | `activate`/`remove` in both panels had no error handling. Wrapped in `try/catch` with `r.ok` checks; shows alert on failure. |

---

## Group E — `db.py`

| # | Fix |
|---|-----|
| D1 | No `try/finally` for `conn.close()` — connections leaked on exceptions. Added `try/finally: conn.close()` to `create_tables`, `list_runs`, and `get_run`. |
| D2 | `equity_curve`/`trade_log` defaulted to `{}` (dict) when NULL in DB. Changed default to `[]` for those two list fields. |
| D3 | ALTER TABLE migration failures silently swallowed with bare `except: pass`. Changed to only ignore `sqlite3.OperationalError` where the message contains "duplicate column"; re-raises other errors. |

---

## Group H — `StrategyBuilder.jsx` + `IndicatorBuilder.jsx`

| # | Fix |
|---|-----|
| F6 | `useEffect` in `StrategyBuilder` was missing `selectedRole` in its dependency array. Added it. |
| F7 | Save optimistic update didn't include the server-assigned `id`, so a newly saved strategy couldn't be deleted without a page refresh. Changed to re-fetch strategies after save to get the real `id`. |
| F8 | Right-side operand in `ConditionCard` didn't handle `type: "custom"` — broken for AI-generated strategies using custom indicators. Added check for `cond.right?.type === 'custom'`; renders `CustomOperandPanel` for the right side. |
| F9 | `aiGeneratedIndicator` wasn't cleared after adding it in `IndicatorBuilder`, making a double-add possible. Added `setAiGeneratedIndicator(null)` after adding. |
| F10 | Empty indicators (no blocks) were saved to the DB with `expr: null`. Added `.filter(ind => ind.blocks?.length > 0)` before mapping to the save payload. |

---

## Group G — `Analytics.jsx`

| # | Fix |
|---|-----|
| F5 | Trade timestamp (`t`) not shown in the trade log table. Added a Time column rendering `String(t.t).slice(0, 19)`. |
| F3 | Delete operations (`deleteRun`, `deleteBatch`, `deleteAll`) cleared state optimistically even on server failure. All three now check `r.ok` and throw before mutating state. |
| F4 | `toggleCompare` race condition: rapid clicks saw stale `compareData` (closure capture) and triggered duplicate fetches. Added `_compareFetching = useRef(new Set())` to track in-flight requests; `setCompareData` now uses a functional update to avoid stale closure. |

---

## Group J — `Backtest.jsx` + `AIStrategyChat.jsx`

| # | Fix |
|---|-----|
| F13 | `column_map` sent to `/backtest/upload` was missing `open`, `high`, `low` keys. ATR/highest_high/lowest_low operands received `NaN`. Added the three missing mappings. |
| F14 | On error, both `setError(errorMsg)` (bottom box) and `setMessages(... isError: true)` (chat bubble) fired — error shown twice. Removed `setError` call; errors now appear only as chat bubbles. |
