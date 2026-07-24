"""routes_data.py — Data provider fetch and ticker search endpoints."""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from db import get_active_data_key

router = APIRouter()


def _decode_key_import():
    from api import _decode_key
    return _decode_key


# ── Data fetch proxy ──────────────────────────────────────────────────────────

@router.post("/data/fetch")
async def data_fetch(request: Request) -> Dict[str, Any]:
    body = await request.json()
    ticker     = body.get("ticker", "").upper().strip()
    start_date = body.get("start_date", "")
    end_date   = body.get("end_date", "")
    timeframe  = body.get("timeframe", "1d")

    if not ticker:
        raise HTTPException(400, "ticker is required.")
    if not start_date or not end_date:
        raise HTTPException(400, "start_date and end_date are required.")

    key_rec = get_active_data_key()
    if not key_rec:
        service, api_key = "yahoo-finance", ""
    else:
        service  = key_rec["service"] or ""
        password = body.get("password", "") if key_rec.get("protected") else None
        _decode_key = _decode_key_import()
        try:
            api_key = _decode_key(key_rec, password=password, table="data")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        if not api_key and service != "yahoo-finance":
            raise HTTPException(400, "Data API key is empty. Update it in Key Manager.")

    try:
        data = await _fetch_from_provider(service, api_key, ticker, start_date, end_date, timeframe)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Data provider error: {exc}") from exc

    return {"rows": data, "count": len(data)}


async def _fetch_from_provider(service, api_key, ticker, start_date, end_date, timeframe) -> List[Dict[str, Any]]:
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
        elif service == "massive":
            return await _massive_fetch(client, api_key, ticker, start_date, end_date, timeframe)
        else:
            raise HTTPException(400, f"Unknown data service: {service!r}. Update Key Manager.")


# ── Provider implementations ──────────────────────────────────────────────────

def _reject_unsupported_tf(service: str, timeframe: str, supported) -> None:
    if timeframe not in supported:
        raise HTTPException(400, f"Timeframe {timeframe!r} is not supported by {service}. "
                                 f"Supported: {', '.join(supported)}.")


def _av_error_check(j: dict) -> None:
    """Alpha Vantage returns HTTP 200 with an error/info message instead of data."""
    msg = j.get("Error Message") or j.get("Information") or j.get("Note")
    if msg:
        raise HTTPException(502, f"Alpha Vantage: {msg}")


async def _av_fetch(client, api_key, ticker, timeframe):
    TF_MAP = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "60min"}
    _reject_unsupported_tf("alpha-vantage", timeframe, [*TF_MAP, "1d", "1w", "1M"])
    av_tf = TF_MAP.get(timeframe)
    if av_tf is None:
        # TIME_SERIES_DAILY_ADJUSTED is premium-only; free keys get an "Information"
        # message and no data, so use the free unadjusted endpoints.
        FN = {"1d": ("TIME_SERIES_DAILY", "Time Series (Daily)"),
              "1w": ("TIME_SERIES_WEEKLY", "Weekly Time Series"),
              "1M": ("TIME_SERIES_MONTHLY", "Monthly Time Series")}
        fn, series_key = FN[timeframe]
        params = {"function": fn, "symbol": ticker, "outputsize": "full", "apikey": api_key}
        r = await client.get("https://www.alphavantage.co/query", params=params)
        r.raise_for_status()
        j = r.json()
        _av_error_check(j)
        series = j.get(series_key, {})
        rows = []
        for dt, vals in sorted(series.items()):
            close = float(vals.get("4. close", 0))
            rows.append({"timestamp": dt, "open": float(vals.get("1. open", close)), "high": float(vals.get("2. high", close)),
                          "low": float(vals.get("3. low", close)), "close": close,
                          "volume": float(vals.get("5. volume", 0)), "symbol": ticker})
        return rows
    else:
        params = {"function": "TIME_SERIES_INTRADAY", "symbol": ticker, "interval": av_tf, "outputsize": "full", "apikey": api_key}
        r = await client.get("https://www.alphavantage.co/query", params=params)
        r.raise_for_status()
        j = r.json()
        _av_error_check(j)
        series = j.get(f"Time Series ({av_tf})", {})
        rows = []
        for dt, vals in sorted(series.items()):
            close = float(vals.get("4. close", 0))
            rows.append({"timestamp": dt, "open": float(vals.get("1. open", close)), "high": float(vals.get("2. high", close)),
                          "low": float(vals.get("3. low", close)), "close": close,
                          "volume": float(vals.get("5. volume", 0)), "symbol": ticker})
        return rows


async def _polygon_fetch(client, api_key, ticker, start_date, end_date, timeframe):
    TF_MAP = {"1m": ("1", "minute"), "5m": ("5", "minute"), "15m": ("15", "minute"),
              "30m": ("30", "minute"), "1h": ("1", "hour"), "4h": ("4", "hour"),
              "1d": ("1", "day"), "1w": ("1", "week"), "1M": ("1", "month")}
    mult, span = TF_MAP.get(timeframe, ("1", "day"))
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{start_date[:10]}/{end_date[:10]}"
    r = await client.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key})
    r.raise_for_status()
    rows = []
    for bar in r.json().get("results", []):
        ts = _dt.datetime.fromtimestamp(bar["t"] / 1000, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        c = float(bar.get("c", 0))
        rows.append({"timestamp": ts, "open": float(bar.get("o", c)), "high": float(bar.get("h", c)),
                      "low": float(bar.get("l", c)), "close": c,
                      "volume": float(bar.get("v", 0)), "symbol": ticker})
    return rows


async def _yahoo_fetch(client, ticker, start_date, end_date, timeframe):
    TF_MAP = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d", "1w": "1wk", "1M": "1mo"}
    _reject_unsupported_tf("yahoo-finance", timeframe, list(TF_MAP))
    yf_tf = TF_MAP[timeframe]
    def _to_ts(s): return int(_dt.datetime.strptime(s[:10], "%Y-%m-%d").timestamp())
    params = {"period1": _to_ts(start_date), "period2": _to_ts(end_date), "interval": yf_tf}
    r = await client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                         params=params, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    chart = r.json().get("chart", {})
    if chart.get("error"):
        raise HTTPException(404, f"Yahoo Finance error for {ticker}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise HTTPException(404, f"No data returned by Yahoo Finance for {ticker}.")
    result = results[0]
    timestamps = result.get("timestamp", [])
    if not timestamps:
        raise HTTPException(404, f"No data returned by Yahoo Finance for {ticker}.")
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes, opens, highs, lows, volumes = quote.get("close", []), quote.get("open", []), quote.get("high", []), quote.get("low", []), quote.get("volume", [])
    rows = []
    for i, (ts, c, v) in enumerate(zip(timestamps, closes, volumes)):
        if c is None: continue
        o = opens[i] if i < len(opens) and opens[i] is not None else c
        h = highs[i] if i < len(highs) and highs[i] is not None else c
        l = lows[i] if i < len(lows) and lows[i] is not None else c
        dt_str = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": dt_str, "open": float(o), "high": float(h), "low": float(l),
                      "close": float(c), "volume": float(v or 0), "symbol": ticker})
    return rows


async def _finnhub_fetch(client, api_key, ticker, start_date, end_date, timeframe):
    TF_MAP = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "1d": "D", "1w": "W", "1M": "M"}
    _reject_unsupported_tf("finnhub", timeframe, list(TF_MAP))
    def _to_ts(s): return int(_dt.datetime.strptime(s[:10], "%Y-%m-%d").timestamp())
    params = {"symbol": ticker, "resolution": TF_MAP[timeframe], "from": _to_ts(start_date), "to": _to_ts(end_date), "token": api_key}
    r = await client.get("https://finnhub.io/api/v1/stock/candle", params=params)
    if r.status_code == 403:
        raise HTTPException(400, "Finnhub stock candles require a paid plan (free tier no longer has access). "
                                 "Use another data provider or upgrade the Finnhub key.")
    r.raise_for_status()
    j = r.json()
    if j.get("s") == "no_data":
        raise HTTPException(404, f"No data returned by Finnhub for {ticker}.")
    opens, highs, lows = j.get("o", []), j.get("h", []), j.get("l", [])
    rows = []
    for i, (ts, c, v) in enumerate(zip(j.get("t", []), j.get("c", []), j.get("v", []))):
        dt_str = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": dt_str, "open": float(opens[i] if i < len(opens) else c),
                      "high": float(highs[i] if i < len(highs) else c), "low": float(lows[i] if i < len(lows) else c),
                      "close": float(c), "volume": float(v or 0), "symbol": ticker})
    return rows


async def _massive_fetch(client, api_key, ticker, start_date, end_date, timeframe):
    TF_MAP = {"1m": ("1", "minute"), "5m": ("5", "minute"), "15m": ("15", "minute"),
              "30m": ("30", "minute"), "1h": ("1", "hour"), "4h": ("4", "hour"),
              "1d": ("1", "day"), "1w": ("1", "week"), "1M": ("1", "month")}
    mult, span = TF_MAP.get(timeframe, ("1", "day"))
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{start_date[:10]}/{end_date[:10]}"
    r = await client.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key})
    r.raise_for_status()
    rows = []
    for bar in r.json().get("results", []):
        ts = _dt.datetime.fromtimestamp(bar["t"] / 1000, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        c = float(bar.get("c", 0))
        rows.append({"timestamp": ts, "open": float(bar.get("o", c)), "high": float(bar.get("h", c)),
                      "low": float(bar.get("l", c)), "close": c, "volume": float(bar.get("v", 0)), "symbol": ticker})
    return rows


# ── Ticker search ─────────────────────────────────────────────────────────────

@router.get("/data/search-tickers")
async def data_search_tickers(q: str = "", password: str = "") -> Dict[str, Any]:
    if len(q) < 2:
        return {"results": []}

    key_rec = get_active_data_key()
    if not key_rec:
        service, api_key = "yahoo-finance", ""
    else:
        service = key_rec["service"] or ""
        pw = password if key_rec.get("protected") else None
        _decode_key = _decode_key_import()
        try:
            api_key = _decode_key(key_rec, password=pw, table="data")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            results = await _search_tickers(client, service, api_key, q)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Ticker search error: {exc}") from exc

    return {"results": results[:20]}


async def _search_tickers(client, service, api_key, q):
    if service == "alpha-vantage":
        r = await client.get("https://www.alphavantage.co/query",
                             params={"function": "SYMBOL_SEARCH", "keywords": q, "apikey": api_key})
        r.raise_for_status()
        return [{"symbol": m.get("1. symbol", ""), "name": m.get("2. name", "")} for m in r.json().get("bestMatches", [])]
    elif service in ("polygon", "massive"):
        base = "https://api.massive.com" if service == "massive" else "https://api.polygon.io"
        r = await client.get(f"{base}/v3/reference/tickers", params={"search": q, "active": "true", "limit": 20, "apiKey": api_key})
        r.raise_for_status()
        return [{"symbol": m.get("ticker", ""), "name": m.get("name", "")} for m in r.json().get("results", [])]
    elif service == "yahoo-finance":
        r = await client.get("https://query1.finance.yahoo.com/v1/finance/search",
                             params={"q": q, "newsCount": 0, "quotesCount": 20}, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return [{"symbol": m.get("symbol", ""), "name": m.get("shortname") or m.get("longname", "")}
                for m in r.json().get("quotes", []) if m.get("symbol")]
    elif service == "finnhub":
        r = await client.get("https://finnhub.io/api/v1/search", params={"q": q, "token": api_key})
        r.raise_for_status()
        return [{"symbol": m.get("symbol", ""), "name": m.get("description", "")} for m in r.json().get("result", [])]
    else:
        raise HTTPException(400, f"Ticker search not supported for provider: {service!r}")
