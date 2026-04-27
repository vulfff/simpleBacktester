"""routes_ai.py — AI strategy/indicator builder and analyzer endpoints."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import get_active_model_key, get_strategy, get_indicator, get_run, _infer_provider

router = APIRouter()


# ── Language directive ────────────────────────────────────────────────────────

_LANGUAGE_DIRECTIVES = {
    "et": (
        "\n\nIMPORTANT: The end user speaks Estonian. All prose in your reply "
        "(explanations, reasoning, commentary, field values such as "
        "'name' and 'description') MUST be written in natural Estonian. "
        "Technical identifiers (JSON keys, operator symbols, indicator type names, "
        "rule_set schema tokens) stay in English."
    ),
}

def _language_directive(lang: Optional[str]) -> str:
    """Return a system-prompt suffix instructing the model to respond in the user's language."""
    if not lang:
        return ""
    return _LANGUAGE_DIRECTIVES.get(lang.lower(), "")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _decode_key_import():
    """Late import to avoid circular dependency with api.py module-level code."""
    from api import _decode_key
    return _decode_key


def get_ai_provider_with_password(password: Optional[str]):
    """Helper to get AI provider using the active model key from the multi-key store."""
    from ai_strategy_builder import AnthropicProvider, OpenAIProvider, GrokProvider, GeminiProvider

    key_rec = get_active_model_key()
    if not key_rec:
        raise ValueError("No AI model configured. Add one in Key Manager.")

    model_name    = key_rec["model_name"]
    provider_name = key_rec["provider"] or _infer_provider(model_name)

    _decode_key = _decode_key_import()
    try:
        api_key = _decode_key(key_rec, password=password, table="model")
    except ValueError as exc:
        raise ValueError(str(exc))

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


def _get_custom_indicator_context() -> str:
    """Build a system-prompt section listing user custom indicators with their editable params."""
    from indicator_registry import extract_editable_params
    from db import get_db_conn
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT name, expression FROM indicators WHERE is_builtin = 0 OR is_builtin IS NULL")
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return ""

    lines = []
    for r in rows:
        raw  = r["expression"] if isinstance(r, dict) else r[1]
        name = r["name"]       if isinstance(r, dict) else r[0]
        try:
            expr_data = json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError):
            expr_data = {}
        desc       = (expr_data.get("description") or "").strip()
        expr_tree  = expr_data.get("expr")
        params     = extract_editable_params(expr_tree) if expr_tree else []
        param_str  = ""
        if params:
            param_str = " | params: " + ", ".join(
                f'{p["path"]}={p["default_value"]}' for p in params
            )
        if desc or params:
            lines.append(f'- "{name}": {desc}{param_str}')

    if not lines:
        return ""

    return (
        "\n\n## User's Custom Indicators\n"
        'Reference with {"type": "custom", "name": "IndicatorName"}.\n'
        'To override parameter values, add an "overrides" dict keyed by the param path shown above:\n'
        '  {"type": "custom", "name": "RSI Oversold", "overrides": {"cond_right": 25, "cond_left.operand.period": 10}}\n'
        'If the user specifies custom values in their message, use them as overrides. '
        'If unspecified, omit overrides (defaults will be used).\n\n'
        + "\n".join(lines)
    )


def _auto_populate_overrides(strategy: dict) -> None:
    """For any custom indicator operand with no overrides, fill in the indicator's defaults."""
    from indicator_registry import INDICATOR_REGISTRY
    for rule in strategy.get("rules", []):
        for cond in rule.get("conditions", []):
            if cond.get("kind") == "exit_condition":
                continue
            for side in ("left", "right"):
                op = cond.get(side)
                if not op or op.get("type") != "custom":
                    continue
                ind_name = op.get("name", "")
                if not ind_name:
                    continue
                defn = INDICATOR_REGISTRY.get(ind_name)
                if not defn:
                    continue
                existing = op.get("overrides") or {}
                defaults = {p["path"]: p["default_value"] for p in defn.editable_params}
                merged = {**defaults, **existing}
                if merged:
                    op["overrides"] = merged


def _match_round_trips_from_dicts(fills: list) -> list:
    """Match buy->sell and short->cover fill dicts into round-trip trades with PnL."""
    from metrics import match_round_trips_from_dicts
    return match_round_trips_from_dicts(fills)


# ── Request / Response Models ─────────────────────────────────────────────────

class AIStrategyRequest(BaseModel):
    prompt: str = Field(..., description="Natural language description of the trading strategy.")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    password: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default="en", description="UI language code (e.g. 'en', 'et'). AI responds in this language.")


class AIStrategyResponse(BaseModel):
    name: str
    rules: List[Dict[str, Any]]
    warnings: List[str] = Field(default_factory=list)


class AIIndicatorRequest(BaseModel):
    prompt: str = Field(..., description="Natural language description of the indicator.")
    password: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default="en", description="UI language code (e.g. 'en', 'et'). AI responds in this language.")


class AIIndicatorResponse(BaseModel):
    name: str
    description: str
    expr: Dict[str, Any]
    color: str = "#3b82f6"


class ListModelsRequest(BaseModel):
    provider: str = Field(..., description="Provider: anthropic, openai, grok, or gemini")
    api_key: str  = Field(..., description="Plain (unencrypted) API key")


class AIAnalyzeRequest(BaseModel):
    subject_type: str
    subject_id: int
    messages: List[Dict[str, Any]]
    temperature: float = 0.7
    password: Optional[str] = None
    language: Optional[str] = "en"


class AIAnalyzeResponse(BaseModel):
    reply: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ai/build-strategy", response_model=AIStrategyResponse)
def ai_build_strategy(request: AIStrategyRequest) -> AIStrategyResponse:
    try:
        provider = get_ai_provider_with_password(request.password)
        extra_ctx = _get_custom_indicator_context() + _language_directive(request.language)
        strategy = provider.build_from_prompt(
            user_prompt=request.prompt,
            temperature=request.temperature,
            extra_system_context=extra_ctx,
        )
        is_valid, warnings = provider.validate_strategy(strategy)
        if not is_valid:
            raise HTTPException(422, f"AI generated invalid strategy: {warnings[0] if warnings else 'Unknown error'}")
        _auto_populate_overrides(strategy)
        return AIStrategyResponse(
            name=strategy.get("name", "AI-Generated Strategy"),
            rules=strategy.get("rules", []),
            warnings=warnings,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as exc:
        raise HTTPException(500, f"Failed to generate strategy: {str(exc)}") from exc


@router.post("/ai/list-models")
async def ai_list_models(request: ListModelsRequest) -> Dict[str, Any]:
    import httpx

    provider = request.provider.lower().strip()
    key = request.api_key.strip()
    if not key:
        raise HTTPException(400, "api_key is required")

    try:
        if provider == "anthropic":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.anthropic.com/v1/models",
                                        headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"Anthropic error: {resp.text}")
            models = [m["id"] for m in resp.json().get("data", [])]

        elif provider == "openai":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.openai.com/v1/models",
                                        headers={"Authorization": f"Bearer {key}"})
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"OpenAI error: {resp.text}")
            all_ids = [m["id"] for m in resp.json().get("data", [])]
            prefixes = ("gpt-", "o1", "o3", "o4")
            models = sorted([mid for mid in all_ids if any(mid.startswith(p) for p in prefixes)])

        elif provider == "grok":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.x.ai/v1/models",
                                        headers={"Authorization": f"Bearer {key}"})
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, f"xAI error: {resp.text}")
            all_ids = [m["id"] for m in resp.json().get("data", [])]
            models = sorted([mid for mid in all_ids if mid.startswith("grok")])

        elif provider == "gemini":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                        params={"key": key})
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
    except Exception as exc:
        raise HTTPException(500, f"Failed to fetch models: {str(exc)}") from exc


@router.get("/ai/schema")
def ai_strategy_schema() -> Dict[str, Any]:
    from ai_strategy_builder import StrategySchema
    return {
        "operand_types": StrategySchema.OPERAND_TYPES,
        "operators": StrategySchema.OPERATORS,
        "rule_roles": StrategySchema.RULE_ROLES,
        "price_fields": StrategySchema.PRICE_FIELDS,
        "exit_condition_types": StrategySchema.EXIT_CONDITION_TYPES,
        "timing_modes": StrategySchema.TIMING_MODES,
        "supported_providers": {
            "anthropic": {"name": "Anthropic Claude", "models": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-6", "claude-sonnet-4-5-20250929"], "api_key_format": "sk-ant-...", "get_key_url": "https://console.anthropic.com/"},
            "openai": {"name": "OpenAI GPT", "models": ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "o4-mini", "o3", "o3-mini"], "api_key_format": "sk-...", "get_key_url": "https://platform.openai.com/api-keys"},
            "grok": {"name": "xAI Grok", "models": ["grok-4", "grok-4-1-fast-non-reasoning", "grok-4-1-fast-reasoning", "grok-3", "grok-3-mini"], "api_key_format": "xai-...", "get_key_url": "https://console.x.ai"},
            "gemini": {"name": "Google Gemini", "models": ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"], "api_key_format": "AIza...", "get_key_url": "https://aistudio.google.com/app/apikey"},
        },
        "example_prompt": "Buy when 20-period EMA crosses above 50-period EMA. Sell when RSI is above 70.",
        "note": "Configure your preferred LLM provider in the Key Manager before using this endpoint.",
    }


@router.post("/ai/build-indicator", response_model=AIIndicatorResponse)
def ai_build_indicator(request: AIIndicatorRequest) -> AIIndicatorResponse:
    from ai_indicator_builder import build_indicator_from_prompt
    try:
        provider = get_ai_provider_with_password(request.password)
        indicator = build_indicator_from_prompt(
            user_prompt=request.prompt,
            provider=provider,
            language_directive=_language_directive(request.language),
        )
        if "name" not in indicator or "expr" not in indicator:
            raise HTTPException(422, "Generated indicator missing required fields")
        return AIIndicatorResponse(
            name=indicator.get("name", "AI-Generated Indicator"),
            description=indicator.get("description", ""),
            expr=indicator.get("expr", {}),
            color=indicator.get("color", "#3b82f6"),
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as exc:
        raise HTTPException(500, f"Failed to generate indicator: {str(exc)}") from exc


@router.post("/ai/analyze", response_model=AIAnalyzeResponse)
def ai_analyze(request: AIAnalyzeRequest) -> AIAnalyzeResponse:
    from strategy_analyzer import analyze_strategy_chat
    from indicator_analyzer import analyze_indicator_chat
    from run_analyzer import analyze_run_chat

    if request.subject_type not in ("strategy", "indicator", "run"):
        raise HTTPException(400, "subject_type must be 'strategy', 'indicator', or 'run'")
    if not request.messages:
        raise HTTPException(400, "messages must not be empty")

    try:
        provider = get_ai_provider_with_password(request.password)
        lang_directive = _language_directive(request.language)

        if request.subject_type == "strategy":
            row = get_strategy(request.subject_id)
            if not row:
                raise HTTPException(404, f"Strategy {request.subject_id} not found")
            config_raw = row["config"]
            config = json.loads(config_raw) if isinstance(config_raw, str) else (config_raw or {})
            strategy_data = {"name": row["name"], **config}
            reply = analyze_strategy_chat(strategy_data, request.messages, provider, request.temperature, language_directive=lang_directive)

        elif request.subject_type == "indicator":
            row = get_indicator(request.subject_id)
            if not row:
                raise HTTPException(404, f"Indicator {request.subject_id} not found")
            expr_raw = row["expression"]
            expr = json.loads(expr_raw) if isinstance(expr_raw, str) else (expr_raw or {})
            indicator_data = {"name": row["name"], "expression": expr}
            reply = analyze_indicator_chat(indicator_data, request.messages, provider, request.temperature, language_directive=lang_directive)

        else:  # run
            row = get_run(request.subject_id)
            if not row:
                raise HTTPException(404, f"Run {request.subject_id} not found")
            equity = row.get("equity_curve", [])
            equities = [p["equity"] for p in equity if "equity" in p]
            prices = [p["price"] for p in equity if p.get("price")]
            signal_log = row.get("signal_log", [])
            raw_fills = row.get("trade_log", [])
            completed_trades = _match_round_trips_from_dicts(raw_fills)
            run_data = {
                "run_id": row["id"],
                "strategy_name": row["strategy_name"],
                "ticker": row["ticker"],
                "timeframe": row["timeframe"],
                "date_range": f"{row['start_date']} \u2192 {row['end_date']}",
                "starting_cash": row["starting_cash"],
                "run_at": row["run_at"],
                "execution": row.get("params", {}),
                "metrics": row.get("metrics", {}),
                "completed_trades": completed_trades,
                "equity_summary": {
                    "start_equity": equities[0] if equities else None,
                    "end_equity": equities[-1] if equities else None,
                    "peak_equity": max(equities) if equities else None,
                    "trough_equity": min(equities) if equities else None,
                    "total_bars": len(equity),
                    "price_start": prices[0] if prices else None,
                    "price_end": prices[-1] if prices else None,
                },
                "signal_summary": {
                    "total_signals": len(signal_log),
                    "blocked_signals": sum(1 for s in signal_log if s.get("blocked")),
                },
            }
            reply = analyze_run_chat(run_data, request.messages, provider, request.temperature, language_directive=lang_directive)

        return AIAnalyzeResponse(reply=reply)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as exc:
        raise HTTPException(500, f"Analysis failed: {str(exc)}") from exc


@router.get("/ai/indicator-schema")
def ai_indicator_schema() -> Dict[str, Any]:
    return {
        "operand_types": ["price", "lookback", "sma", "ema", "rsi", "macd", "bollinger"],
        "expression_node_types": [
            "const (constant value)", "operand (technical indicator or price)",
            "binop (binary operation: +, -, *, /, **, %)", "unop (unary operation: neg, abs, sqrt, log)",
            "clamp (constrain value between lo and hi)", "ifelse (conditional: if cond_left cond_op cond_right then ... else ...)",
        ],
        "binary_operators": ["+", "-", "*", "/", "**", "%"],
        "unary_operators": ["neg", "abs", "sqrt", "log"],
        "condition_operators": [">", "<", ">=", "<=", "==", "!="],
        "example_indicators": {
            "rsi_oversold": {"prompt": "RSI oversold signal: returns 1 when RSI(14) drops below 30", "use_case": "Entry signal detector"},
            "ma_distance": {"prompt": "Distance from 20-period SMA as percentage", "use_case": "Volatility/deviation measurement"},
            "momentum_pct": {"prompt": "Price momentum over last 5 bars as percentage change", "use_case": "Trend strength measurement"},
            "volume_ratio": {"prompt": "Current volume divided by 20-period average volume", "use_case": "Volume confirmation"},
        },
        "note": "Indicators generate expression trees that can be used in rule conditions or as custom operands",
    }
