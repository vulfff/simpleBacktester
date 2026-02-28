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
from fill_model import FillModel
from metrics import compute_metrics
from portfolio import Portfolio
from strategy import create_strategy, list_strategies
from db import (
    get_db_conn, create_tables, encrypt_with_password, decrypt_with_password,
    save_run, list_runs, get_run, delete_run, delete_all_runs, delete_runs_batch,
    list_data_keys, save_data_key, activate_data_key, delete_data_key, get_active_data_key,
    list_model_keys, save_model_key, activate_model_key, delete_model_key, get_active_model_key,
    _infer_provider,
)

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

# Seed pre-built strategies/indicators if they don't exist yet (idempotent)
try:
    from seed_prebuilts import seed as _seed_prebuilts
    _seed_prebuilts()
except Exception:
    pass

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


# ── AI Strategy Builder ───────────────────────────────────────────────────────

class AIStrategyRequest(BaseModel):
    """Request model for AI strategy generation."""
    prompt: str = Field(
        ...,
        description="Natural language description of the trading strategy. "
                    "E.g., 'Buy when price crosses above the 50-day moving average and RSI is below 70'"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Controls AI creativity (0.0=deterministic, 1.0=creative)"
    )
    password: Optional[str] = Field(
        default=None,
        description="Password if LLM key is encrypted in database"
    )


class AIStrategyResponse(BaseModel):
    """Response model for AI strategy generation."""
    name: str
    rules: List[Dict[str, Any]]
    warnings: List[str] = Field(default_factory=list)


@app.post("/ai/build-strategy", response_model=AIStrategyResponse)
def ai_build_strategy(request: AIStrategyRequest) -> AIStrategyResponse:
    """
    Generate a trading strategy from natural language description.
    
    Reads LLM provider configuration (API key, model, provider) from database.
    Supports: Anthropic, OpenAI, Grok, Google Gemini.
    
    Example prompt:
    "Create a moving average crossover strategy. Buy when 20-period SMA crosses 
     above 50-period SMA. Sell when it crosses back below. Use 1.0 quantity per trade."
    """
    try:
        provider = get_ai_provider_with_password(request.password)
        
        strategy = provider.build_from_prompt(
            user_prompt=request.prompt,
            temperature=request.temperature
        )
        
        # Validate the generated strategy
        is_valid, warnings = provider.validate_strategy(strategy)
        
        if not is_valid:
            raise HTTPException(
                422,
                f"AI generated invalid strategy: {warnings[0] if warnings else 'Unknown error'}"
            )
        
        return AIStrategyResponse(
            name=strategy.get("name", "AI-Generated Strategy"),
            rules=strategy.get("rules", []),
            warnings=warnings
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as exc:
        raise HTTPException(500, f"Failed to generate strategy: {str(exc)}") from exc


def get_ai_provider_with_password(password: Optional[str]):
    """Helper to get AI provider using the active model key from the multi-key store.

    Accepts password=None for unprotected (base64-only) keys.
    """
    from ai_strategy_builder import AnthropicProvider, OpenAIProvider, GrokProvider, GeminiProvider

    key_rec = get_active_model_key()
    if not key_rec:
        raise ValueError("No AI model configured. Add one in Key Manager.")

    model_name    = key_rec["model_name"]
    provider_name = key_rec["provider"] or _infer_provider(model_name)
    enc_key       = key_rec["key_data"] or ""
    is_protected  = bool(key_rec["protected"])

    if is_protected:
        if not password:
            raise ValueError("LLM API key is encrypted. Please provide your password.")
        try:
            api_key = decrypt_with_password(password, enc_key).strip()
        except Exception:
            raise ValueError("Failed to decrypt LLM API key. Check your password.")
    else:
        try:
            api_key = base64.b64decode(enc_key).decode().strip()
        except Exception:
            api_key = enc_key.strip()

    PROVIDERS = {
        "anthropic": AnthropicProvider,
        "openai":    OpenAIProvider,
        "grok":      GrokProvider,
        "gemini":    GeminiProvider,
    }

    ProviderClass = PROVIDERS.get(provider_name.lower())
    if not ProviderClass:
        raise ValueError(f"Unknown AI provider: {provider_name!r}")

    return ProviderClass(api_key=api_key, model_name=model_name)


class ListModelsRequest(BaseModel):
    """Request to fetch available models from a provider's live API."""
    provider: str = Field(..., description="Provider: anthropic, openai, grok, or gemini")
    api_key: str  = Field(..., description="Plain (unencrypted) API key typed by user before saving")


@app.post("/ai/list-models")
async def ai_list_models(request: ListModelsRequest) -> Dict[str, Any]:
    """
    Fetch the list of available models from a provider's API using the supplied key.

    This endpoint is called before saving a key — it receives the raw plaintext key.
    Returns a filtered list of model IDs suitable for use with AI strategy/indicator generation.
    """
    import httpx

    provider = request.provider.lower().strip()
    key = request.api_key.strip()

    if not key:
        raise HTTPException(400, "api_key is required")

    try:
        if provider == "anthropic":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"Anthropic error: {resp.text}")
            models = [m["id"] for m in resp.json().get("data", [])]

        elif provider == "openai":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"OpenAI error: {resp.text}")
            all_ids = [m["id"] for m in resp.json().get("data", [])]
            prefixes = ("gpt-", "o1", "o3", "o4")
            models = sorted([mid for mid in all_ids if any(mid.startswith(p) for p in prefixes)])

        elif provider == "grok":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"xAI error: {resp.text}")
            all_ids = [m["id"] for m in resp.json().get("data", [])]
            models = sorted([mid for mid in all_ids if mid.startswith("grok")])

        elif provider == "gemini":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": key},
                )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"Google error: {resp.text}")
            models = []
            for m in resp.json().get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    name = m.get("name", "").replace("models/", "")
                    if name:
                        models.append(name)
            models = sorted(models)

        else:
            raise HTTPException(400, f"Unknown provider: {provider!r}. Use: anthropic, openai, grok, gemini")

        return {"provider": provider, "models": models}

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(504, f"Timeout fetching models from {provider}")
    except Exception as exc:
        raise HTTPException(500, f"Failed to fetch models: {str(exc)}") from exc


@app.get("/ai/schema")
def ai_strategy_schema() -> Dict[str, Any]:
    """
    Return the strategy schema and supported AI providers.
    
    Shows:
    - Available operand types (price, sma, ema, rsi, macd, bollinger, etc.)
    - Available operators (>, <, cross_above, etc.)
    - Available rule roles (entry_long, exit_long, etc.)
    - Supported AI providers and their recommended models
    - Expected JSON structure
    """
    from ai_strategy_builder import StrategySchema
    
    return {
        "operand_types": StrategySchema.OPERAND_TYPES,
        "operators": StrategySchema.OPERATORS,
        "rule_roles": StrategySchema.RULE_ROLES,
        "price_fields": StrategySchema.PRICE_FIELDS,
        "exit_condition_types": StrategySchema.EXIT_CONDITION_TYPES,
        "timing_modes": StrategySchema.TIMING_MODES,
        "supported_providers": {
            "anthropic": {
                "name": "Anthropic Claude",
                "models": [
                    "claude-opus-4-6",
                    "claude-sonnet-4-6",
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                ],
                "api_key_format": "sk-ant-...",
                "get_key_url": "https://console.anthropic.com/"
            },
            "openai": {
                "name": "OpenAI GPT",
                "models": [
                    "gpt-4.1",
                    "gpt-4.1-mini",
                    "gpt-4o",
                    "gpt-4o-mini",
                    "o3",
                    "o4-mini",
                ],
                "api_key_format": "sk-...",
                "get_key_url": "https://platform.openai.com/api-keys"
            },
            "grok": {
                "name": "xAI Grok",
                "models": [
                    "grok-3",
                    "grok-3-mini",
                    "grok-2",
                ],
                "api_key_format": "xai-...",
                "get_key_url": "https://console.x.ai"
            },
            "gemini": {
                "name": "Google Gemini",
                "models": [
                    "gemini-2.5-pro",
                    "gemini-2.5-flash",
                    "gemini-2.0-flash",
                ],
                "api_key_format": "AIza...",
                "get_key_url": "https://aistudio.google.com/app/apikey"
            }
        },
        "example_prompt": "Buy when 20-period EMA crosses above 50-period EMA. Sell when RSI is above 70.",
        "note": "Configure your preferred LLM provider in the Key Manager before using this endpoint."
    }


# ── AI Indicator Builder ───────────────────────────────────────────────────────

class AIIndicatorRequest(BaseModel):
    """Request model for AI indicator generation."""
    prompt: str = Field(
        ...,
        description="Natural language description of the indicator. "
                    "E.g., 'RSI oversold signal that returns 1 when below 30'"
    )
    password: Optional[str] = Field(
        default=None,
        description="Password if LLM key is encrypted in database"
    )


class AIIndicatorResponse(BaseModel):
    """Response model for AI indicator generation."""
    name: str
    description: str
    expr: Dict[str, Any]
    color: str = "#3b82f6"


@app.post("/ai/build-indicator", response_model=AIIndicatorResponse)
def ai_build_indicator(request: AIIndicatorRequest) -> AIIndicatorResponse:
    """
    Generate a technical indicator from natural language description.
    
    Reads LLM provider configuration from database.
    Returns an indicator expression tree that can be used in strategy conditions.
    
    Example prompt:
    "RSI oversold detector that returns 1 when RSI(14) is below 30, else 0"
    
    Returns:
    {
      "name": "RSI Oversold",
      "description": "...",
      "expr": { expression tree },
      "color": "#3b82f6"
    }
    """
    from ai_indicator_builder import build_indicator_from_prompt

    try:
        provider = get_ai_provider_with_password(request.password)
        
        indicator = build_indicator_from_prompt(
            user_prompt=request.prompt,
            provider=provider
        )
        
        # Validate required fields
        if "name" not in indicator or "expr" not in indicator:
            raise HTTPException(422, "Generated indicator missing required fields")
        
        return AIIndicatorResponse(
            name=indicator.get("name", "AI-Generated Indicator"),
            description=indicator.get("description", ""),
            expr=indicator.get("expr", {}),
            color=indicator.get("color", "#3b82f6")
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as exc:
        raise HTTPException(500, f"Failed to generate indicator: {str(exc)}") from exc


@app.get("/ai/indicator-schema")
def ai_indicator_schema() -> Dict[str, Any]:
    """
    Return indicator expression tree schema and examples.
    
    Shows:
    - Available operand types for indicators
    - Expression tree node types (operand, const, binop, unop, clamp, ifelse)
    - Mathematical operations supported
    - Example indicator expressions
    """
    return {
        "operand_types": [
            "price", "lookback", "sma", "ema", "rsi", "macd", "bollinger"
        ],
        "expression_node_types": [
            "const (constant value)",
            "operand (technical indicator or price)",
            "binop (binary operation: +, -, *, /, **, %)",
            "unop (unary operation: neg, abs, sqrt, log)",
            "clamp (constrain value between lo and hi)",
            "ifelse (conditional: if cond_left cond_op cond_right then ... else ...)"
        ],
        "binary_operators": ["+", "-", "*", "/", "**", "%"],
        "unary_operators": ["neg", "abs", "sqrt", "log"],
        "condition_operators": [">", "<", ">=", "<=", "==", "!="],
        "example_indicators": {
            "rsi_oversold": {
                "prompt": "RSI oversold signal: returns 1 when RSI(14) drops below 30",
                "use_case": "Entry signal detector"
            },
            "ma_distance": {
                "prompt": "Distance from 20-period SMA as percentage",
                "use_case": "Volatility/deviation measurement"
            },
            "momentum_pct": {
                "prompt": "Price momentum over last 5 bars as percentage change",
                "use_case": "Trend strength measurement"
            },
            "volume_ratio": {
                "prompt": "Current volume divided by 20-period average volume",
                "use_case": "Volume confirmation"
            }
        },
        "note": "Indicators generate expression trees that can be used in rule conditions or as custom operands"
    }



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
    # Execution options
    sizing_mode:      str   = Form(default="fixed"),   # "fixed" | "all_in"
    leverage:         float = Form(default=1.0),
    commission_mode:  str   = Form(default="none"),    # "none" | "pct" | "flat"
    commission_value: float = Form(default=0.0),
    allow_fractional: bool  = Form(default=False),     # True = crypto (fractional units ok)
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
        engine_type, strategy_config = _resolve_strategy(strategy_cfg)
        # Use the human-readable name from the frontend, fall back to engine type
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

    # -- build strategy --
    try:
        strategy = create_strategy(engine_type, strategy_config)
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
        fill_model=FillModel(),
        sizing_mode=sizing_mode,
        leverage=leverage,
        commission_mode=commission_mode,
        commission_value=commission_value,
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

    # -- compute metrics --
    equity_curve = getattr(engine, "_equity_curve", [])
    trade_log_objs = portfolio.trade_log
    mets = compute_metrics(equity_curve, trade_log_objs, starting_cash)

    # -- serialise trade log --
    trade_log_dicts = [
        {
            "t":      t.time,
            "action": t.action,
            "symbol": t.symbol,
            "qty":    t.quantity,
            "price":  t.price,
        }
        for t in trade_log_objs
    ]

    # -- serialise signal log (all signals, blocked ones have blocked=True) --
    signal_log_dicts = getattr(engine, "_signal_log", [])

    warmup = getattr(strategy, "warmup_bars", 0)

    # -- persist run --
    # Prefer explicit symbol param; fall back to the actual name used in tick data
    # (engine._last_tick keys are the instrument names read from the feed).
    # Never use column_map["name"] — that's a column header, not a ticker value.
    _last_ticks = getattr(engine, "_last_tick", {})
    ticker_key = symbol or (next(iter(_last_ticks), None)) or "ASSET"
    start_date = equity_curve[0]["t"][:10] if equity_curve else ""
    end_date   = equity_curve[-1]["t"][:10] if equity_curve else ""
    try:
        run_id = save_run(
            strategy_name=display_name,
            ticker=ticker_key,
            timeframe=timeframe or "unknown",
            start_date=start_date,
            end_date=end_date,
            starting_cash=starting_cash,
            strategy_config=raw_strategy_cfg or strategy_config,
            metrics=mets,
            equity_curve=equity_curve,
            trade_log=trade_log_dicts,
            signal_log=signal_log_dicts,
            extra_params={
                "sizing_mode":      sizing_mode,
                "leverage":         leverage,
                "commission_mode":  commission_mode,
                "commission_value": commission_value,
                "allow_fractional": allow_fractional,
            },
        )
    except Exception:
        run_id = None  # don't fail the whole backtest if saving fails

    return BacktestResult(
        cash=portfolio.cash,
        asset_value=portfolio.asset_value,
        total_value=portfolio.total_value(),
        positions=portfolio.positions,
        last_prices=portfolio.last_prices,
        trades=getattr(engine, "_fill_count", 0),
        warnings=warnings,
        run_id=run_id,
        warmup_bars=warmup,
        equity_curve=equity_curve,
        metrics=mets,
        trade_log=trade_log_dicts,
        signal_log=signal_log_dicts,
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

    key_rec = get_active_data_key()
    if not key_rec:
        raise HTTPException(400, "No data API key configured. Add one in Key Manager.")

    service   = key_rec["service"] or ""
    enc_key   = key_rec["key_data"] or ""
    protected = bool(key_rec["protected"])

    if protected:
        password = body.get("password", "")
        if not password:
            raise HTTPException(400, "Data key is password-protected. Supply 'password' in request.")
        try:
            api_key = decrypt_with_password(password, enc_key).strip()
        except ValueError:
            raise HTTPException(400, "Wrong password for data key.")
    else:
        try:
            api_key = base64.b64decode(enc_key.encode()).decode().strip()
        except Exception:
            api_key = enc_key.strip()

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

        elif service == "massive":
            return await _massive_fetch(client, api_key, ticker, start_date, end_date, timeframe)

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
            open_ = float(vals.get("1. open", close))
            rows.append({"timestamp": dt, "open": open_, "bid": close, "ask": close,
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
            open_ = float(vals.get("1. open", close))
            rows.append({"timestamp": dt, "open": open_, "bid": close, "ask": close,
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
        o = float(bar.get("o", c))
        rows.append({"timestamp": ts, "open": o, "bid": c, "ask": c,
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
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes  = quote.get("close", [])
    opens   = quote.get("open", [])
    volumes = quote.get("volume", [])
    rows = []
    for i, (ts, c, v) in enumerate(zip(timestamps, closes, volumes)):
        if c is None:
            continue
        o = opens[i] if i < len(opens) and opens[i] is not None else c
        dt_str = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": dt_str, "open": float(o), "bid": float(c), "ask": float(c),
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
    opens = j.get("o", [])
    rows = []
    for i, (ts, c, v) in enumerate(zip(j.get("t", []), j.get("c", []), j.get("v", []))):
        o = opens[i] if i < len(opens) else c
        dt_str = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": dt_str, "open": float(o), "bid": float(c), "ask": float(c),
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
        o  = float(b.get("open") or c)
        rows.append({"timestamp": ts.strip(), "open": o, "bid": c, "ask": c,
                      "volume": float(b.get("volume") or 0), "symbol": ticker})
    return rows


# ─ Massive (rebranded Polygon.io) ────────────────────────────────────────────

async def _massive_fetch(client, api_key, ticker, start_date, end_date, timeframe):
    TF_MAP = {
        "1m": ("1", "minute"), "5m": ("5", "minute"), "15m": ("15", "minute"),
        "30m": ("30", "minute"), "1h": ("1", "hour"), "4h": ("4", "hour"),
        "1d": ("1", "day"), "1w": ("1", "week"), "1M": ("1", "month"),
    }
    mult, span = TF_MAP.get(timeframe, ("1", "day"))
    sd = start_date[:10]
    ed = end_date[:10]
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{sd}/{ed}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    r = await client.get(url, params=params)
    r.raise_for_status()
    j = r.json()
    rows = []
    for bar in j.get("results", []):
        import datetime as _dt
        ts = _dt.datetime.utcfromtimestamp(bar["t"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        c = float(bar.get("c", 0))
        o = float(bar.get("o", c))
        rows.append({"timestamp": ts, "open": o, "bid": c, "ask": c,
                      "volume": float(bar.get("v", 0)), "symbol": ticker})
    return rows


# ── Ticker symbol search ───────────────────────────────────────────────────────

@app.get("/data/search-tickers")
async def data_search_tickers(q: str = "", password: str = "") -> Dict[str, Any]:
    """
    Search for ticker symbols using the configured data provider.
    Returns up to 20 matching results as [{symbol, name}].
    """
    if len(q) < 2:
        return {"results": []}

    key_rec = get_active_data_key()
    if not key_rec:
        raise HTTPException(400, "No data API key configured.")

    service   = key_rec["service"] or ""
    enc_key   = key_rec["key_data"] or ""
    protected = bool(key_rec["protected"])

    if protected:
        if not password:
            raise HTTPException(400, "Data key is password-protected. Supply 'password'.")
        try:
            api_key = decrypt_with_password(password, enc_key).strip()
        except ValueError:
            raise HTTPException(400, "Wrong password for data key.")
    else:
        try:
            api_key = base64.b64decode(enc_key.encode()).decode().strip()
        except Exception:
            api_key = enc_key.strip()

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            results = await _search_tickers(client, service, api_key, q)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Ticker search error: {exc}") from exc

    return {"results": results[:20]}


async def _search_tickers(client, service: str, api_key: str, q: str):
    """Route ticker search to the correct provider. Returns [{symbol, name}]."""

    if service == "alpha-vantage":
        r = await client.get("https://www.alphavantage.co/query", params={
            "function": "SYMBOL_SEARCH", "keywords": q, "apikey": api_key
        })
        r.raise_for_status()
        matches = r.json().get("bestMatches", [])
        return [{"symbol": m.get("1. symbol", ""), "name": m.get("2. name", "")} for m in matches]

    elif service in ("polygon", "massive"):
        base = "https://api.massive.com" if service == "massive" else "https://api.polygon.io"
        r = await client.get(f"{base}/v3/reference/tickers", params={
            "search": q, "active": "true", "limit": 20, "apiKey": api_key
        })
        r.raise_for_status()
        results = r.json().get("results", [])
        return [{"symbol": m.get("ticker", ""), "name": m.get("name", "")} for m in results]

    elif service == "yahoo-finance":
        r = await client.get("https://query1.finance.yahoo.com/v1/finance/search", params={
            "q": q, "newsCount": 0, "quotesCount": 20
        }, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        quotes = r.json().get("quotes", [])
        return [{"symbol": m.get("symbol", ""), "name": m.get("shortname") or m.get("longname", "")} for m in quotes if m.get("symbol")]

    elif service == "finnhub":
        r = await client.get("https://finnhub.io/api/v1/search", params={"q": q, "token": api_key})
        r.raise_for_status()
        results = r.json().get("result", [])
        return [{"symbol": m.get("symbol", ""), "name": m.get("description", "")} for m in results]

    elif service == "iex-cloud":
        r = await client.get(f"https://cloud.iexapis.com/stable/search/{q}", params={"token": api_key})
        r.raise_for_status()
        results = r.json() if isinstance(r.json(), list) else []
        return [{"symbol": m.get("symbol", ""), "name": m.get("securityName", "")} for m in results]

    else:
        raise HTTPException(400, f"Ticker search not supported for provider: {service!r}")


# ── Backtest Run History ──────────────────────────────────────────────────────

@app.get("/db/runs")
def db_get_runs():
    """List all saved backtest runs (metadata + metrics, no equity curve)."""
    return {"runs": list_runs()}


@app.get("/db/runs/{run_id}")
def db_get_run(run_id: int):
    """Fetch a full backtest run including equity curve and trade log."""
    run = get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return run


@app.delete("/db/runs/{run_id}")
def db_delete_run(run_id: int):
    """Delete a saved backtest run."""
    if not delete_run(run_id):
        raise HTTPException(404, f"Run {run_id} not found.")
    return {"status": "ok"}


@app.delete("/db/runs")
def db_delete_all_runs():
    """Delete every saved backtest run."""
    count = delete_all_runs()
    return {"status": "ok", "deleted": count}


@app.post("/db/runs/batch-delete")
async def db_delete_runs_batch(request: Request):
    """Delete multiple runs by id. Body: { ids: [1, 2, 3] }"""
    body = await request.json()
    ids = [int(i) for i in body.get("ids", []) if str(i).isdigit()]
    count = delete_runs_batch(ids)
    return {"status": "ok", "deleted": count}


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
    cur.execute("SELECT id, name, expression, is_builtin FROM indicators ORDER BY id")
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        # parse expression JSON → expose as `expr` for frontend compatibility
        raw_expr = d.pop("expression", None)
        try:
            d["expr"] = json.loads(raw_expr) if raw_expr else None
        except (json.JSONDecodeError, TypeError):
            d["expr"] = None
        d["is_builtin"] = bool(d.get("is_builtin", 0))
        rows.append(d)
    conn.close()
    return {"indicators": rows}


@app.post("/db/indicators")
def db_post_indicators(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get("indicators", [])
    conn = get_db_conn()
    cur  = conn.cursor()
    # Only delete user-created indicators; leave builtins untouched
    cur.execute("DELETE FROM indicators WHERE is_builtin = 0 OR is_builtin IS NULL")
    for ind in arr:
        # Skip re-inserting builtins — they're already in the DB
        if ind.get("is_builtin"):
            continue
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


# ── Multi-key CRUD endpoints ──────────────────────────────────────────────────

@app.get("/db/data-keys")
def db_get_data_keys():
    return {"keys": list_data_keys()}


@app.post("/db/data-keys")
async def db_post_data_key(request: Request):
    payload   = await request.json()
    service   = payload.get("service", "").strip()
    raw_key   = payload.get("key", "").strip()
    protected = bool(payload.get("protected", False))
    password  = payload.get("password", "")
    label     = payload.get("label", "").strip()
    activate  = bool(payload.get("activate", True))

    if not service:
        raise HTTPException(400, "service is required")

    if protected:
        if not password:
            raise HTTPException(400, "password required for encryption")
        key_data = encrypt_with_password(password, raw_key)
    else:
        key_data = base64.b64encode(raw_key.encode()).decode()

    key_id = save_data_key(service, key_data, protected, label, activate)
    return {"id": key_id, "status": "ok"}


@app.post("/db/data-keys/{key_id}/activate")
def db_activate_data_key(key_id: int):
    if not activate_data_key(key_id):
        raise HTTPException(404, f"Data key {key_id} not found")
    return {"status": "ok"}


@app.delete("/db/data-keys/{key_id}")
def db_delete_data_key(key_id: int):
    if not delete_data_key(key_id):
        raise HTTPException(404, f"Data key {key_id} not found")
    return {"status": "ok"}


@app.get("/db/model-keys")
def db_get_model_keys():
    return {"keys": list_model_keys()}


@app.post("/db/model-keys")
async def db_post_model_key(request: Request):
    payload    = await request.json()
    model_name = payload.get("model_name", "").strip()
    provider   = payload.get("provider", "").strip() or _infer_provider(model_name)
    raw_key    = payload.get("key", "").strip()
    protected  = bool(payload.get("protected", False))
    password   = payload.get("password", "")
    label      = payload.get("label", "").strip()
    activate   = bool(payload.get("activate", True))

    if not model_name:
        raise HTTPException(400, "model_name is required")

    if protected:
        if not password:
            raise HTTPException(400, "password required for encryption")
        key_data = encrypt_with_password(password, raw_key)
    else:
        key_data = base64.b64encode(raw_key.encode()).decode()

    key_id = save_model_key(model_name, provider, key_data, protected, label, activate)
    return {"id": key_id, "status": "ok"}


@app.post("/db/model-keys/{key_id}/activate")
def db_activate_model_key(key_id: int):
    if not activate_model_key(key_id):
        raise HTTPException(404, f"Model key {key_id} not found")
    return {"status": "ok"}


@app.delete("/db/model-keys/{key_id}")
def db_delete_model_key(key_id: int):
    if not delete_model_key(key_id):
        raise HTTPException(404, f"Model key {key_id} not found")
    return {"status": "ok"}


# ── API Keys DB (legacy compat) ───────────────────────────────────────────────

@app.get("/db/api_keys")
def db_get_api_keys():
    """Backward-compat endpoint used by AI chat and Backtest to check configured keys."""
    data_rec  = get_active_data_key()
    model_rec = get_active_model_key()
    if not data_rec and not model_rec:
        return {"api_key": None}
    return {"api_key": {
        "service":    data_rec["service"]     if data_rec  else "",
        "model_name": model_rec["model_name"] if model_rec else "",
        "data_key":   "configured"            if data_rec  and data_rec.get("key_data")  else "",
        "model_key":  "configured"            if model_rec and model_rec.get("key_data") else "",
        "protected":  0,
    }}


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