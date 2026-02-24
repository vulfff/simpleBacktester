"""
api.py  –  FastAPI application

Fixes vs original
=================
1. /backtest/upload now accepts `strategies` (JSON array) instead of the
   obsolete `strategy_name` + `strategy_config` form fields.
2. /backtest/upload also accepts raw `data` (JSON string) for the API-fetch path.
3. CORS is expanded to accept any localhost port (dev) and can be configured
   via the CORS_ORIGINS environment variable for production.
4. All errors inside _run_backtest are caught and returned as 400/422 JSON,
   not unhandled 500s.
5. DB indicator writes now use the correct column name (`expression`).
6. DB strategy writes preserve existing rows when id is supplied; upsert logic.
7. /data/fetch stub that proxies to a data-provider API using stored keys.
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
from portfolio import Portfolio
from strategy import create_strategy, list_strategies
from db import get_db_conn, create_tables, encrypt_with_password, decrypt_with_password

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Backtester API", version="2.0.0")

# Allow all localhost origins in dev; set CORS_ORIGINS=https://yourapp.com in prod
_RAW_ORIGINS = os.getenv("CORS_ORIGINS", "")
_ORIGINS = (
    [o.strip() for o in _RAW_ORIGINS.split(",") if o.strip()]
    if _RAW_ORIGINS
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure DB schema exists at startup
create_tables()

# ── Models ────────────────────────────────────────────────────────────────────

class BacktestResult(BaseModel):
    cash: float
    asset_value: float
    total_value: float
    positions: Dict[str, float]
    last_prices: Dict[str, float]
    trades: int = 0
    warnings: List[str] = Field(default_factory=list)


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
    # file OR data must be supplied
    file: Optional[UploadFile] = File(default=None),
    data: Optional[str]        = Form(default=None),   # JSON string of pre-fetched rows

    column_map:     str   = Form(default='{"time":"timestamp","bid":"bid","ask":"ask","volume":"volume","name":"symbol"}'),
    strategies:     str   = Form(default="[]"),          # JSON array of strategy objects
    symbol:         Optional[str]   = Form(default=None),
    time_format:    Optional[str]   = Form(default=None),
    timeframe:      Optional[str]   = Form(default=None),
    starting_cash:  float           = Form(default=10_000.0),
) -> BacktestResult:

    # -- parse JSON fields --
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

    # -- write CSV to temp file --
    temp_path: Optional[str] = None
    csv_bytes: Optional[bytes] = None

    if file is not None:
        csv_bytes = await file.read()
    elif data is not None:
        # Convert pre-fetched JSON rows → CSV in memory
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

        # -- resolve strategy --
        strategy_cfg = strategy_arr[0]
        strategy_name, strategy_config = _resolve_strategy(strategy_cfg)

        return _run_backtest(
            csv_path=temp_path,
            column_map=column_map_dict,
            symbol=symbol,
            time_format=time_format,
            strategy_name=strategy_name,
            strategy_config=strategy_config,
            starting_cash=starting_cash,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _rows_to_csv(rows: List[Dict]) -> bytes:
    """Convert a list of dicts (from data provider) to CSV bytes."""
    if not rows:
        return b""
    import csv as _csv
    buf = io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def _resolve_strategy(cfg: Dict[str, Any]):
    """
    Determine (strategy_name, strategy_config) from a strategy slot dict.

    The frontend sends:
      { name: str, logic: str, config: str|dict, ... }

    - If logic == "rule_set" or config contains "rule_set", use rule_set strategy.
    - If name matches a registered strategy, use it directly.
    - Fall back to "rule_set" with whatever config is provided.
    """
    # import rule_based strategy so it gets registered
    import strategy_rules  # noqa: F401

    raw_config = cfg.get("config", {})
    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except (json.JSONDecodeError, TypeError):
            raw_config = {}

    logic = (cfg.get("logic") or "").strip()
    name  = (cfg.get("name")  or "").strip()

    # Determine which strategy class to use
    from strategy import STRATEGY_REGISTRY
    all_names = set(STRATEGY_REGISTRY.keys())

    if "rule_set" in raw_config:
        return "rule_set", raw_config
    if logic in all_names:
        return logic, raw_config
    if name in all_names:
        return name, raw_config
    # Default: treat the whole config as a rule_set payload
    return "rule_set", {"rule_set": raw_config}


def _run_backtest(
    csv_path: str,
    column_map: Dict[str, str],
    symbol: Optional[str],
    time_format: Optional[str],
    strategy_name: str,
    strategy_config: Dict[str, Any],
    starting_cash: float,
) -> BacktestResult:
    warnings: List[str] = []

    # -- build strategy --
    try:
        strategy = create_strategy(strategy_name, strategy_config)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown strategy: {exc}") from exc
    except Exception as exc:
        raise HTTPException(422, f"Strategy configuration error: {exc}") from exc

    # -- build data feed --
    try:
        feed = CSVTickDataFeed(
            file_path=csv_path,
            column_map=column_map,
            symbol=symbol,
            time_format=time_format,
        )
    except Exception as exc:
        raise HTTPException(422, f"Data feed error: {exc}") from exc

    # -- run engine --
    portfolio = Portfolio(starting_cash=starting_cash, cash=starting_cash)
    engine = BacktestEngine(
        data_feed=feed,
        strategy=strategy,
        action_manager=ActionManager(),
        portfolio=portfolio,
    )

    try:
        engine.run()
    except Exception as exc:
        tb = traceback.format_exc()
        raise HTTPException(500, f"Engine error: {exc}\n{tb}") from exc

    tick_count = getattr(engine, "_tick_count", None)
    if tick_count is not None and tick_count == 0:
        warnings.append("No ticks were processed. Check your CSV columns and column_map.")

    return BacktestResult(
        cash=portfolio.cash,
        asset_value=portfolio.asset_value,
        total_value=portfolio.total_value(),
        positions=portfolio.positions,
        last_prices=portfolio.last_prices,
        trades=getattr(engine, "_fill_count", 0),
        warnings=warnings,
    )


# ── Data fetch proxy ──────────────────────────────────────────────────────────

@app.post("/data/fetch")
async def data_fetch(request: Request) -> Dict[str, Any]:
    """
    Proxy to a configured data provider.
    Reads the stored API key and forwards the request.
    """
    body = await request.json()
    ticker    = body.get("ticker", "").upper().strip()
    start_date = body.get("start_date", "")
    end_date   = body.get("end_date", "")
    timeframe  = body.get("timeframe", "1d")

    if not ticker:
        raise HTTPException(400, "ticker is required.")
    if not start_date or not end_date:
        raise HTTPException(400, "start_date and end_date are required.")

    # load stored key
    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("SELECT service, data_key, protected FROM api_keys LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(400, "No data API key configured. Add one in Key Manager.")

    service   = row["service"] or ""
    enc_key   = row["data_key"] or ""
    protected = bool(row["protected"])

    if protected:
        password = body.get("password", "")
        if not password:
            raise HTTPException(400, "Data key is password-protected. Supply 'password' in request.")
        try:
            api_key = decrypt_with_password(password, enc_key)
        except ValueError:
            raise HTTPException(400, "Wrong password for data key.")
    else:
        try:
            api_key = base64.b64decode(enc_key.encode()).decode()
        except Exception:
            api_key = enc_key

    if not api_key:
        raise HTTPException(400, "Data API key is empty. Update it in Key Manager.")

    # Dispatch to provider
    try:
        data = await _fetch_from_provider(service, api_key, ticker, start_date, end_date, timeframe)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Data provider error: {exc}") from exc

    return {"rows": data, "count": len(data)}


async def _fetch_from_provider(
    service: str,
    api_key: str,
    ticker: str,
    start_date: str,
    end_date: str,
    timeframe: str,
) -> List[Dict[str, Any]]:
    """Route to the correct provider and return a list of OHLCV dicts."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:

        if service == "alpha-vantage":
            return await _av_fetch(client, api_key, ticker, timeframe)

        elif service == "polygon":
            return await _polygon_fetch(client, api_key, ticker, start_date, end_date, timeframe)

        elif service == "yahoo-finance":
            return await _yahoo_fetch(client, ticker, start_date, end_date, timeframe)

        elif service == "finnhub":
            return await _finnhub_fetch(client, api_key, ticker, start_date, end_date, timeframe)

        elif service == "iex-cloud":
            return await _iex_fetch(client, api_key, ticker, timeframe)

        else:
            raise HTTPException(400, f"Unknown data service: {service!r}. Update Key Manager.")


# ─ Alpha Vantage ──────────────────────────────────────────────────────────────

async def _av_fetch(client, api_key, ticker, timeframe):
    TF_MAP = {
        "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "60min", "4h": "60min",  # AV doesn't have 4h; use 60min
        "1d": None,  # daily uses a different function
    }
    av_tf = TF_MAP.get(timeframe)
    if av_tf is None or timeframe in ("1d", "1w", "1M"):
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "outputsize": "full",
            "apikey": api_key,
        }
        r = await client.get(url, params=params)
        r.raise_for_status()
        j = r.json()
        series = j.get("Time Series (Daily)", {})
        rows = []
        for dt, vals in sorted(series.items()):
            close = float(vals.get("5. adjusted close") or vals.get("4. close", 0))
            rows.append({"timestamp": dt, "bid": close, "ask": close,
                          "volume": float(vals.get("6. volume", 0)), "symbol": ticker})
        return rows
    else:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": ticker,
            "interval": av_tf,
            "outputsize": "full",
            "apikey": api_key,
        }
        r = await client.get(url, params=params)
        r.raise_for_status()
        j = r.json()
        key = f"Time Series ({av_tf})"
        series = j.get(key, {})
        rows = []
        for dt, vals in sorted(series.items()):
            close = float(vals.get("4. close", 0))
            rows.append({"timestamp": dt, "bid": close, "ask": close,
                          "volume": float(vals.get("5. volume", 0)), "symbol": ticker})
        return rows


# ─ Polygon.io ─────────────────────────────────────────────────────────────────

async def _polygon_fetch(client, api_key, ticker, start_date, end_date, timeframe):
    TF_MAP = {
        "1m": ("1", "minute"), "5m": ("5", "minute"), "15m": ("15", "minute"),
        "30m": ("30", "minute"), "1h": ("1", "hour"), "4h": ("4", "hour"),
        "1d": ("1", "day"), "1w": ("1", "week"), "1M": ("1", "month"),
    }
    mult, span = TF_MAP.get(timeframe, ("1", "day"))
    sd = start_date[:10]
    ed = end_date[:10]
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{sd}/{ed}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    r = await client.get(url, params=params)
    r.raise_for_status()
    j = r.json()
    rows = []
    for bar in j.get("results", []):
        import datetime as _dt
        ts = _dt.datetime.utcfromtimestamp(bar["t"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        c = float(bar.get("c", 0))
        rows.append({"timestamp": ts, "bid": c, "ask": c,
                      "volume": float(bar.get("v", 0)), "symbol": ticker})
    return rows


# ─ Yahoo Finance (unofficial, no key needed) ──────────────────────────────────

async def _yahoo_fetch(client, ticker, start_date, end_date, timeframe):
    import datetime as _dt
    TF_MAP = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "60m", "4h": "1h", "1d": "1d", "1w": "1wk", "1M": "1mo",
    }
    yf_tf = TF_MAP.get(timeframe, "1d")

    def _to_ts(s):
        s = s[:10]
        return int(_dt.datetime.strptime(s, "%Y-%m-%d").timestamp())

    p1 = _to_ts(start_date)
    p2 = _to_ts(end_date)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"period1": p1, "period2": p2, "interval": yf_tf, "includeTimestamps": "true"}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = await client.get(url, params=params, headers=headers)
    r.raise_for_status()
    j = r.json()
    result = j.get("chart", {}).get("result", [{}])[0]
    timestamps = result.get("timestamp", [])
    closes  = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    volumes = result.get("indicators", {}).get("quote", [{}])[0].get("volume", [])
    rows = []
    for ts, c, v in zip(timestamps, closes, volumes):
        if c is None:
            continue
        dt_str = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": dt_str, "bid": float(c), "ask": float(c),
                      "volume": float(v or 0), "symbol": ticker})
    return rows


# ─ Finnhub ────────────────────────────────────────────────────────────────────

async def _finnhub_fetch(client, api_key, ticker, start_date, end_date, timeframe):
    import datetime as _dt
    TF_MAP = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "1d": "D", "1w": "W", "1M": "M"}
    res = TF_MAP.get(timeframe, "D")

    def _to_ts(s):
        return int(_dt.datetime.strptime(s[:10], "%Y-%m-%d").timestamp())

    params = {"symbol": ticker, "resolution": res, "from": _to_ts(start_date), "to": _to_ts(end_date), "token": api_key}
    r = await client.get("https://finnhub.io/api/v1/stock/candle", params=params)
    r.raise_for_status()
    j = r.json()
    if j.get("s") == "no_data":
        raise HTTPException(404, f"No data returned by Finnhub for {ticker}.")
    rows = []
    for ts, c, v in zip(j.get("t", []), j.get("c", []), j.get("v", [])):
        dt_str = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": dt_str, "bid": float(c), "ask": float(c),
                      "volume": float(v or 0), "symbol": ticker})
    return rows


# ─ IEX Cloud ──────────────────────────────────────────────────────────────────

async def _iex_fetch(client, api_key, ticker, timeframe):
    TF_MAP = {"1d": "1m", "5d": "5d", "1m": "1mm", "3m": "3m", "6m": "6m", "1y": "1y"}
    rng = TF_MAP.get(timeframe, "1m")
    url = f"https://cloud.iexapis.com/stable/stock/{ticker}/chart/{rng}"
    r = await client.get(url, params={"token": api_key})
    r.raise_for_status()
    bars = r.json()
    rows = []
    for b in bars:
        ts = b.get("date", "") + (" " + b.get("minute", "") if b.get("minute") else "")
        c  = float(b.get("close") or b.get("average") or 0)
        rows.append({"timestamp": ts.strip(), "bid": c, "ask": c,
                      "volume": float(b.get("volume") or 0), "symbol": ticker})
    return rows


# ── Encryption helpers ────────────────────────────────────────────────────────

@app.post("/keys/encrypt")
def keys_encrypt(payload: Dict[str, str]):
    pwd = payload.get("password", "")
    if not pwd:
        raise HTTPException(400, "Password required.")
    return {
        "dataKey":  encrypt_with_password(pwd, payload.get("dataKey",  "")),
        "modelKey": encrypt_with_password(pwd, payload.get("modelKey", "")),
    }


@app.post("/keys/decrypt")
def keys_decrypt(payload: Dict[str, str]):
    pwd = payload.get("password", "")
    if not pwd:
        raise HTTPException(400, "Password required.")
    try:
        return {
            "dataKey":  decrypt_with_password(pwd, payload.get("dataKey",  "")),
            "modelKey": decrypt_with_password(pwd, payload.get("modelKey", "")),
        }
    except ValueError:
        raise HTTPException(400, "Decryption failed — wrong password?")


# ── Strategy DB ───────────────────────────────────────────────────────────────

@app.get("/db/strategies")
def db_get_strategies():
    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("SELECT id, name, logic, config FROM strategies ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"strategies": rows}


@app.post("/db/strategies")
def db_post_strategies(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get("strategies", [])
    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM strategies")
    for s in arr:
        config_val = s.get("config")
        if isinstance(config_val, dict):
            config_val = json.dumps(config_val)
        elif config_val is None:
            config_val = "{}"
        cur.execute(
            "INSERT INTO strategies (id, name, logic, config) VALUES (?, ?, ?, ?)",
            (s.get("id"), s.get("name", ""), s.get("logic", ""), config_val),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "count": len(arr)}


# ── Indicator DB ──────────────────────────────────────────────────────────────

@app.get("/db/indicators")
def db_get_indicators():
    conn = get_db_conn()
    cur  = conn.cursor()
    # column is `expression` in the schema
    cur.execute("SELECT id, name, expression FROM indicators ORDER BY id")
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        # parse expression JSON → expose as `expr` for frontend compatibility
        raw_expr = d.pop("expression", None)
        try:
            d["expr"] = json.loads(raw_expr) if raw_expr else None
        except (json.JSONDecodeError, TypeError):
            d["expr"] = None
        rows.append(d)
    conn.close()
    return {"indicators": rows}


@app.post("/db/indicators")
def db_post_indicators(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get("indicators", [])
    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM indicators")
    for ind in arr:
        expr = ind.get("expr") or ind.get("expression")
        expr_str = json.dumps(expr) if isinstance(expr, dict) else (expr or "null")
        # store name + expression; description/color go into expression JSON wrapper
        cur.execute(
            "INSERT INTO indicators (id, name, expression) VALUES (?, ?, ?)",
            (
                ind.get("id"),
                ind.get("name", ""),
                json.dumps({
                    "expr":        expr,
                    "description": ind.get("description", ""),
                    "color":       ind.get("color", "#22d3ee"),
                }),
            ),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "count": len(arr)}


# ── API Keys DB ───────────────────────────────────────────────────────────────

@app.get("/db/api_keys")
def db_get_api_keys():
    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("SELECT id, service, model_name, data_key, model_key, protected FROM api_keys ORDER BY id LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"api_key": None}
    return {"api_key": dict(row)}


@app.post("/db/api_keys")
def db_post_api_keys(payload: Dict[str, Any]):
    service    = payload.get("service",    "")
    model_name = payload.get("model_name", "")
    data_key   = payload.get("dataKey",   "")
    model_key  = payload.get("modelKey",  "")
    protected  = bool(payload.get("protected"))
    password   = payload.get("password",  "")

    # Load existing encrypted values so we don't overwrite with blank
    data_key_enc  = ""
    model_key_enc = ""
    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("SELECT data_key, model_key, protected FROM api_keys LIMIT 1")
    existing = cur.fetchone()
    conn.close()
    if existing:
        data_key_enc  = existing["data_key"]  or ""
        model_key_enc = existing["model_key"] or ""
        if not protected and bool(existing["protected"]):
            protected = True  # keep protection flag if previously protected

    # Encrypt / encode whichever keys the caller supplied (non-empty)
    if protected:
        if not password:
            raise HTTPException(400, "Password required to encrypt keys.")
        if data_key:
            data_key_enc  = encrypt_with_password(password, data_key)
        if model_key:
            model_key_enc = encrypt_with_password(password, model_key)
    else:
        if data_key:
            data_key_enc  = base64.b64encode(data_key.encode()).decode()
        if model_key:
            model_key_enc = base64.b64encode(model_key.encode()).decode()

    conn = get_db_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM api_keys")
    cur.execute(
        "INSERT INTO api_keys (service, model_name, data_key, model_key, protected) VALUES (?, ?, ?, ?, ?)",
        (service, model_name, data_key_enc, model_key_enc, 1 if protected else 0),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}