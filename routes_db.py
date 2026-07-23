"""routes_db.py — Database CRUD endpoints for runs, strategies, indicators, and keys."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from db import (
    db_conn, encrypt_with_password,
    list_runs, get_run, delete_run, delete_all_runs, delete_runs_batch,
    list_data_keys, save_data_key, activate_data_key, delete_data_key,
    get_data_key_by_id, update_data_key_data,
    list_model_keys, save_model_key, activate_model_key, delete_model_key,
    get_model_key_by_id, update_model_key_data,
    _infer_provider,
)
from indicator_registry import extract_editable_params

router = APIRouter()


def _keyring_refs():
    """Late import keyring refs from api module."""
    from api import _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX
    return _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX


# ── Backtest Run History ──────────────────────────────────────────────────────

@router.get("/db/runs")
def db_get_runs():
    return {"runs": list_runs()}


@router.get("/db/runs/{run_id}")
def db_get_run(run_id: int):
    run = get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return run


@router.delete("/db/runs/{run_id}")
def db_delete_run(run_id: int):
    if not delete_run(run_id):
        raise HTTPException(404, f"Run {run_id} not found.")
    return {"status": "ok"}


@router.delete("/db/runs")
def db_delete_all_runs():
    count = delete_all_runs()
    return {"status": "ok", "deleted": count}


@router.post("/db/runs/batch-delete")
async def db_delete_runs_batch(request: Request):
    body = await request.json()
    ids = []
    for i in body.get("ids", []):
        try:
            ids.append(int(float(i)))
        except (TypeError, ValueError):
            pass
    count = delete_runs_batch(ids)
    return {"status": "ok", "deleted": count}


# ── Strategy DB ───────────────────────────────────────────────────────────────

@router.get("/db/strategies")
def db_get_strategies():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, logic, config, is_builtin FROM strategies ORDER BY id")
        return {"strategies": [dict(r) for r in cur.fetchall()]}


@router.post("/db/strategies")
def db_post_strategies(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get("strategies", [])
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        for s in arr:
            config_val = s.get("config")
            if isinstance(config_val, dict):
                config_val = json.dumps(config_val)
            elif config_val is None:
                config_val = "{}"
            name = s.get("name", "")
            logic = s.get("logic", "")
            sid = s.get("id")
            if sid:
                cur.execute("SELECT is_builtin FROM strategies WHERE id=?", (sid,))
                existing_row = cur.fetchone()
                if existing_row and existing_row["is_builtin"]:
                    continue
                cur.execute("UPDATE strategies SET name=?, logic=?, config=? WHERE id=? AND (is_builtin = 0 OR is_builtin IS NULL)",
                            (name, logic, config_val, sid))
                if cur.rowcount == 0 and not existing_row:
                    cur.execute("INSERT INTO strategies (id, name, logic, config) VALUES (?, ?, ?, ?)",
                                (sid, name, logic, config_val))
            else:
                cur.execute("SELECT id, is_builtin FROM strategies WHERE name=?", (name,))
                existing = cur.fetchone()
                if existing:
                    if existing["is_builtin"]:
                        continue
                    cur.execute("UPDATE strategies SET logic=?, config=? WHERE id=?", (logic, config_val, existing["id"]))
                else:
                    cur.execute("INSERT INTO strategies (name, logic, config) VALUES (?, ?, ?)", (name, logic, config_val))
    return {"status": "ok", "count": len(arr)}


@router.delete("/db/strategies/{strategy_id}")
def db_delete_strategy(strategy_id: int):
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT is_builtin FROM strategies WHERE id = ?", (strategy_id,))
        row = cur.fetchone()
        if row and row["is_builtin"]:
            raise HTTPException(403, "Cannot delete a built-in strategy")
        cur.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    return {"status": "ok"}


# ── Indicator DB ──────────────────────────────────────────────────────────────

@router.get("/db/indicators")
def db_get_indicators():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, expression, is_builtin FROM indicators ORDER BY id")
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            raw_expr = d.pop("expression", None)
            try:
                d["expr"] = json.loads(raw_expr) if raw_expr else None
            except (json.JSONDecodeError, TypeError):
                d["expr"] = None
            d["is_builtin"] = bool(d.get("is_builtin", 0))
            # d["expr"] is the stored wrapper {"expr": <tree>, "description": ..., "color": ...};
            # extract_editable_params needs the actual tree, not the wrapper.
            tree = d["expr"].get("expr") if isinstance(d["expr"], dict) else None
            try:
                d["editable_params"] = extract_editable_params(tree) if isinstance(tree, dict) else []
            except (KeyError, TypeError, AttributeError):
                d["editable_params"] = []
            rows.append(d)
    return {"indicators": rows}


@router.post("/db/indicators")
def db_post_indicators(payload: Dict[str, List[Dict[str, Any]]]):
    arr = payload.get("indicators", [])
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM indicators WHERE is_builtin = 0 OR is_builtin IS NULL")
        for ind in arr:
            if ind.get("is_builtin"):
                continue
            expr = ind.get("expr") or ind.get("expression")
            cur.execute(
                "INSERT INTO indicators (id, name, expression) VALUES (?, ?, ?)",
                (ind.get("id"), ind.get("name", ""),
                 json.dumps({"expr": expr, "description": ind.get("description", ""), "color": ind.get("color", "#22d3ee")})),
            )
    # Reload indicator registry after save
    try:
        from api import _reload_indicator_registry
        _reload_indicator_registry()
    except Exception:
        pass
    return {"status": "ok", "count": len(arr)}


# ── Multi-key CRUD endpoints ──────────────────────────────────────────────────
# Shared implementations for the data-keys/model-keys pairs below. `kind` is
# always the internal literal "data" or "model" — never user input.

_KEY_KIND: Dict[str, Dict[str, Any]] = {
    "data": {
        "label": "Data key", "list": list_data_keys, "save": save_data_key,
        "activate": activate_data_key, "delete": delete_data_key,
        "get": get_data_key_by_id, "update": update_data_key_data,
    },
    "model": {
        "label": "Model key", "list": list_model_keys, "save": save_model_key,
        "activate": activate_model_key, "delete": delete_model_key,
        "get": get_model_key_by_id, "update": update_model_key_data,
    },
}


def _list_keys(kind: str):
    return {"keys": _KEY_KIND[kind]["list"]()}


async def _post_key(kind: str, request: Request):
    _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX = _keyring_refs()
    prefix = _KC_DATA_PREFIX if kind == "data" else _KC_MODEL_PREFIX
    spec = _KEY_KIND[kind]

    payload   = await request.json()
    raw_key   = payload.get("key", "").strip()
    protected = bool(payload.get("protected", False))
    password  = payload.get("password", "")
    label     = payload.get("label", "").strip()
    activate  = bool(payload.get("activate", True))

    if kind == "data":
        name_values = (payload.get("service", "").strip(),)
        if not name_values[0]:
            raise HTTPException(400, "service is required")
    else:
        model_name = payload.get("model_name", "").strip()
        if not model_name:
            raise HTTPException(400, "model_name is required")
        name_values = (model_name, payload.get("provider", "").strip() or _infer_provider(model_name))

    if protected:
        if not password:
            raise HTTPException(400, "password required for encryption")
        key_data = encrypt_with_password(password, raw_key)
        key_id = spec["save"](*name_values, key_data, protected, label, activate)
    else:
        key_id = spec["save"](*name_values, "keychain", False, label, activate)
        if _KEYRING_AVAILABLE and _keyring is not None:
            try:
                _keyring.set_password(_KC_SERVICE, f"{prefix}{key_id}", raw_key)
            except Exception as exc:
                raise HTTPException(500, f"Failed to store key in OS keychain: {exc}")
        else:
            spec["update"](key_id, base64.b64encode(raw_key.encode()).decode())

    return {"id": key_id, "status": "ok"}


def _activate_key(kind: str, key_id: int):
    if not _KEY_KIND[kind]["activate"](key_id):
        raise HTTPException(404, f"{_KEY_KIND[kind]['label']} {key_id} not found")
    return {"status": "ok"}


def _delete_key(kind: str, key_id: int):
    _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX = _keyring_refs()
    prefix = _KC_DATA_PREFIX if kind == "data" else _KC_MODEL_PREFIX
    spec = _KEY_KIND[kind]
    rec = spec["get"](key_id)
    if not rec:
        raise HTTPException(404, f"{spec['label']} {key_id} not found")
    if not rec["protected"] and rec["key_data"] == "keychain" and _KEYRING_AVAILABLE and _keyring is not None:
        try:
            _keyring.delete_password(_KC_SERVICE, f"{prefix}{key_id}")
        except Exception:
            pass
    spec["delete"](key_id)
    return {"status": "ok"}


@router.get("/db/data-keys")
def db_get_data_keys():
    return _list_keys("data")


@router.post("/db/data-keys")
async def db_post_data_key(request: Request):
    return await _post_key("data", request)


@router.post("/db/data-keys/{key_id}/activate")
def db_activate_data_key(key_id: int):
    return _activate_key("data", key_id)


@router.delete("/db/data-keys/{key_id}")
def db_delete_data_key(key_id: int):
    return _delete_key("data", key_id)


@router.get("/db/model-keys")
def db_get_model_keys():
    return _list_keys("model")


@router.post("/db/model-keys")
async def db_post_model_key(request: Request):
    return await _post_key("model", request)


@router.post("/db/model-keys/{key_id}/activate")
def db_activate_model_key(key_id: int):
    return _activate_key("model", key_id)


@router.delete("/db/model-keys/{key_id}")
def db_delete_model_key(key_id: int):
    return _delete_key("model", key_id)
