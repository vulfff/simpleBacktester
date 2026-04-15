"""
api.py  –  FastAPI application

Core app setup, shared helpers, and the backtest endpoint.
Route modules: routes_ai, routes_data, routes_db.
"""

from __future__ import annotations

import json
import os
import base64
import io
import tempfile
import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from actionmanager import ActionManager
from csvparser import CSVTickDataFeed
from engine import BacktestEngine
from fill_model import FillModel
from metrics import compute_metrics

# Timeframe → approximate trading bars per calendar year
_BARS_PER_YEAR: Dict[str, int] = {
    "1m":  98280,   # 252 * 390 (US equities)
    "5m":  19656,   # 252 * 78
    "15m":  6552,   # 252 * 26
    "30m":  3276,   # 252 * 13
    "1h":   1638,   # 252 * 6.5
    "1d":    252,
    "1w":     52,
    "1M":     12,
}

def _bars_per_year(timeframe: Optional[str]) -> int:
    return _BARS_PER_YEAR.get(timeframe or "1d", 252)

from portfolio import Portfolio
from strategy import create_strategy, list_strategies
from db import (
    get_db_conn, create_tables, encrypt_with_password, decrypt_with_password,
    save_run, list_runs, get_run, delete_run, delete_all_runs, delete_runs_batch,
    list_data_keys, save_data_key, activate_data_key, delete_data_key, get_active_data_key,
    get_data_key_by_id, update_data_key_data, list_all_data_keys_full,
    list_model_keys, save_model_key, activate_model_key, delete_model_key, get_active_model_key,
    get_model_key_by_id, update_model_key_data, list_all_model_keys_full,
    get_strategy, get_indicator,
    _infer_provider,
)

try:
    import keyring as _keyring
    _KEYRING_AVAILABLE = True
except Exception:
    _keyring = None  # type: ignore
    _KEYRING_AVAILABLE = False

_KC_SERVICE      = "backtester"
_KC_DATA_PREFIX  = "data_"
_KC_MODEL_PREFIX = "model_"


def _decode_key(key_rec: dict, password: Optional[str] = None, table: str = "data") -> str:
    """Decode/decrypt a key record from the DB."""
    protected = bool(key_rec.get("protected"))
    key_data  = key_rec.get("key_data", "")
    key_id    = key_rec.get("id")
    prefix    = _KC_DATA_PREFIX if table == "data" else _KC_MODEL_PREFIX

    if protected:
        if not password:
            raise ValueError("Key is password-protected. Please provide your password.")
        try:
            return decrypt_with_password(password, key_data).strip()
        except Exception:
            raise ValueError("Wrong password for key decryption.")

    if key_data == "keychain":
        if not _KEYRING_AVAILABLE or _keyring is None:
            raise ValueError("OS keychain unavailable. Reinstall with 'pip install keyring'.")
        raw = _keyring.get_password(_KC_SERVICE, f"{prefix}{key_id}")
        if raw is None:
            raise ValueError("Key not found in system keychain — it may have been removed externally.")
        return raw.strip()

    # Legacy base64 fallback
    try:
        return base64.b64decode(key_data.encode()).decode().strip()
    except Exception:
        return key_data.strip()


def _migrate_legacy_keys() -> None:
    """One-time migration: move unprotected base64 keys into the OS keychain."""
    if not _KEYRING_AVAILABLE or _keyring is None:
        print("[keychain] keyring not available — skipping legacy key migration.")
        return
    for row in list_all_data_keys_full():
        if row["protected"] or row["key_data"] == "keychain":
            continue
        try:
            raw = base64.b64decode(row["key_data"].encode()).decode().strip()
        except Exception:
            continue
        try:
            _keyring.set_password(_KC_SERVICE, f"{_KC_DATA_PREFIX}{row['id']}", raw)
            update_data_key_data(row["id"], "keychain")
        except Exception as exc:
            print(f"[keychain] Failed to migrate data key {row['id']}: {exc}")
    for row in list_all_model_keys_full():
        if row["protected"] or row["key_data"] == "keychain":
            continue
        try:
            raw = base64.b64decode(row["key_data"].encode()).decode().strip()
        except Exception:
            continue
        try:
            _keyring.set_password(_KC_SERVICE, f"{_KC_MODEL_PREFIX}{row['id']}", raw)
            update_model_key_data(row["id"], "keychain")
        except Exception as exc:
            print(f"[keychain] Failed to migrate model key {row['id']}: {exc}")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Backtester API", version="2.0.0")

_RAW_ORIGINS = os.getenv("CORS_ORIGINS", "")
_ORIGINS = (
    [o.strip() for o in _RAW_ORIGINS.split(",") if o.strip()]
    if _RAW_ORIGINS
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_credentials=bool(_RAW_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure DB schema exists at startup
create_tables()

# Migrate unprotected base64 keys to OS keychain (one-time, idempotent)
try:
    _migrate_legacy_keys()
except Exception as _mig_exc:
    print(f"[keychain] Migration warning: {_mig_exc}")

# Seed pre-built strategies/indicators if they don't exist yet (idempotent)
try:
    from seed_prebuilts import seed as _seed_prebuilts
    _seed_prebuilts()
except Exception:
    pass


def _reload_indicator_registry() -> None:
    """Reload all indicators from DB into the runtime INDICATOR_REGISTRY."""
    try:
        from indicator_registry import INDICATOR_REGISTRY
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT name, expression FROM indicators")
        defs = []
        for r in cur.fetchall():
            try:
                expr_data = json.loads(r["expression"] or "{}")
                expr = expr_data.get("expr")
                if expr:
                    defs.append({
                        "name":        r["name"],
                        "expr":        expr,
                        "description": expr_data.get("description", ""),
                        "color":       expr_data.get("color", "#22d3ee"),
                    })
            except (json.JSONDecodeError, TypeError):
                pass
        conn.close()
        INDICATOR_REGISTRY.load(defs)
    except Exception:
        pass


_reload_indicator_registry()

# ── Include route modules ─────────────────────────────────────────────────────

from routes_ai import router as ai_router
from routes_data import router as data_router
from routes_db import router as db_router

app.include_router(ai_router)
app.include_router(data_router)
app.include_router(db_router)


# ── Models ────────────────────────────────────────────────────────────────────

class BacktestResult(BaseModel):
    cash: float
    asset_value: float
    total_value: float
    positions: Dict[str, float]
    last_prices: Dict[str, float]
    trades: int = 0
    warnings: List[str] = Field(default_factory=list)
    run_id: Optional[int] = None
    warmup_bars: int = 0
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    trade_log: List[Dict[str, Any]] = Field(default_factory=list)
    signal_log: List[Dict[str, Any]] = Field(default_factory=list)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/strategies")
def strategies_list() -> Dict[str, Any]:
    return {"strategies": list_strategies()}


# ── Backtest (upload or pre-fetched JSON data) ────────────────────────────────

@app.post("/backtest/upload", response_model=BacktestResult)
async def backtest_upload(
    file: Optional[UploadFile] = File(default=None),
    data: Optional[str]        = Form(default=None),
    column_map:     str   = Form(default='{"time":"timestamp","close":"close","volume":"volume","name":"symbol"}'),
    strategies:     str   = Form(default="[]"),
    symbol:         Optional[str]   = Form(default=None),
    time_format:    Optional[str]   = Form(default=None),
    timeframe:      Optional[str]   = Form(default=None),
    starting_cash:  float           = Form(default=10_000.0),
    sizing_mode:      str   = Form(default="fixed"),
    leverage:         float = Form(default=1.0),
    commission_mode:  str   = Form(default="none"),
    commission_value: float = Form(default=0.0),
    allow_fractional: bool  = Form(default=False),
) -> BacktestResult:

    try:
        column_map_dict: Dict[str, str] = json.loads(column_map)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"column_map is not valid JSON: {exc}") from exc

    try:
        strategy_arr: List[Dict[str, Any]] = json.loads(strategies)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"strategies is not valid JSON: {exc}") from exc

    if not strategy_arr:
        raise HTTPException(400, "No strategy provided.")

    temp_path: Optional[str] = None
    csv_bytes: Optional[bytes] = None

    if file is not None:
        csv_bytes = await file.read()
    elif data is not None:
        try:
            rows: List[Dict] = json.loads(data)
            if not rows:
                raise HTTPException(422, "Fetched data is empty.")
            csv_bytes = _rows_to_csv(rows)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"data is not valid JSON: {exc}") from exc
    else:
        raise HTTPException(400, "Either a CSV file or pre-fetched data must be supplied.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            temp_path = tmp.name
            tmp.write(csv_bytes)

        strategy_cfg = strategy_arr[0]
        engine_type, strategy_config = _resolve_strategy(strategy_cfg)
        display_name = (strategy_cfg.get("name") or "").strip() or engine_type

        return _run_backtest(
            csv_path=temp_path,
            column_map=column_map_dict,
            symbol=symbol,
            time_format=time_format,
            timeframe=timeframe,
            engine_type=engine_type,
            display_name=display_name,
            strategy_config=strategy_config,
            starting_cash=starting_cash,
            raw_strategy_cfg=strategy_arr[0],
            sizing_mode=sizing_mode,
            leverage=leverage,
            commission_mode=commission_mode,
            commission_value=commission_value,
            allow_fractional=allow_fractional,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _rows_to_csv(rows: List[Dict]) -> bytes:
    if not rows:
        return b""
    import csv as _csv
    all_keys: list = list(dict.fromkeys(k for row in rows for k in row))
    buf = io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def _resolve_strategy(cfg: Dict[str, Any]):
    import strategy_rules  # noqa: F401

    raw_config = cfg.get("config", {})
    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except (json.JSONDecodeError, TypeError):
            raw_config = {}

    logic = (cfg.get("logic") or "").strip()
    name  = (cfg.get("name")  or "").strip()

    from strategy import STRATEGY_REGISTRY
    all_names = set(STRATEGY_REGISTRY.keys())

    if "rule_set" in raw_config:
        return "rule_set", raw_config
    if logic in all_names:
        return logic, raw_config
    if name in all_names:
        return name, raw_config
    return "rule_set", {"rule_set": raw_config}


def _run_backtest(
    csv_path: str,
    column_map: Dict[str, str],
    symbol: Optional[str],
    time_format: Optional[str],
    engine_type: str,
    display_name: str,
    strategy_config: Dict[str, Any],
    starting_cash: float,
    timeframe: Optional[str] = None,
    raw_strategy_cfg: Optional[Dict[str, Any]] = None,
    sizing_mode: str = "fixed",
    leverage: float = 1.0,
    commission_mode: str = "none",
    commission_value: float = 0.0,
    allow_fractional: bool = False,
) -> BacktestResult:
    warnings: List[str] = []

    try:
        strategy = create_strategy(engine_type, strategy_config)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown strategy: {exc}") from exc
    except Exception as exc:
        raise HTTPException(422, f"Strategy configuration error: {exc}") from exc

    try:
        feed = CSVTickDataFeed(file_path=csv_path, column_map=column_map, symbol=symbol, time_format=time_format)
    except Exception as exc:
        raise HTTPException(422, f"Data feed error: {exc}") from exc

    portfolio = Portfolio(starting_cash=starting_cash, cash=starting_cash)
    engine = BacktestEngine(
        data_feed=feed, strategy=strategy, action_manager=ActionManager(),
        portfolio=portfolio, fill_model=FillModel(),
        sizing_mode=sizing_mode, leverage=leverage,
        commission_mode=commission_mode, commission_value=commission_value,
        allow_fractional=allow_fractional,
    )

    try:
        engine.run()
    except Exception as exc:
        tb = traceback.format_exc()
        raise HTTPException(500, f"Engine error: {exc}\n{tb}") from exc

    tick_count = getattr(engine, "_tick_count", None)
    if tick_count is not None and tick_count == 0:
        warnings.append("No ticks were processed. Check your CSV columns and column_map.")
    warnings.extend(getattr(engine, "_fill_warnings", []))

    equity_curve = getattr(engine, "_equity_curve", [])
    trade_log_objs = portfolio.trade_log
    mets = compute_metrics(equity_curve, trade_log_objs, starting_cash,
                           bars_per_year=_bars_per_year(timeframe))

    trade_log_dicts = [
        {"t": t.time, "action": t.action, "symbol": t.symbol, "qty": t.quantity, "price": t.price}
        for t in trade_log_objs
    ]
    signal_log_dicts = getattr(engine, "_signal_log", [])
    warmup = getattr(strategy, "warmup_bars", 0)

    _last_ticks = getattr(engine, "_last_tick", {})
    ticker_key = symbol or (next(iter(_last_ticks), None)) or "ASSET"
    start_date = equity_curve[0]["t"][:10] if equity_curve else ""
    end_date   = equity_curve[-1]["t"][:10] if equity_curve else ""
    try:
        run_id = save_run(
            strategy_name=display_name, ticker=ticker_key,
            timeframe=timeframe or "unknown", start_date=start_date, end_date=end_date,
            starting_cash=starting_cash, strategy_config=raw_strategy_cfg or strategy_config,
            metrics=mets, equity_curve=equity_curve, trade_log=trade_log_dicts,
            signal_log=signal_log_dicts,
            extra_params={"sizing_mode": sizing_mode, "leverage": leverage,
                          "commission_mode": commission_mode, "commission_value": commission_value,
                          "allow_fractional": allow_fractional},
        )
    except Exception:
        run_id = None

    return BacktestResult(
        cash=portfolio.cash, asset_value=portfolio.asset_value, total_value=portfolio.total_value(),
        positions=portfolio.positions, last_prices=portfolio.last_prices,
        trades=getattr(engine, "_fill_count", 0), warnings=warnings,
        run_id=run_id, warmup_bars=warmup, equity_curve=equity_curve,
        metrics=mets, trade_log=trade_log_dicts, signal_log=signal_log_dicts,
    )
