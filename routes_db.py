"""routes_db.py — Database CRUD endpoints for runs, strategies, indicators, and keys."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from db import (
    get_db_conn, db_conn, encrypt_with_password, decrypt_with_password,
    save_run, list_runs, get_run, delete_run, delete_all_runs, delete_runs_batch,
    list_data_keys, save_data_key, activate_data_key, delete_data_key,
    get_active_data_key, get_data_key_by_id, update_data_key_data,
    list_model_keys, save_model_key, activate_model_key, delete_model_key,
    get_active_model_key, get_model_key_by_id, update_model_key_data,
    _infer_provider,
)

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


# ── Encryption helpers ────────────────────────────────────────────────────────

@router.post("/keys/encrypt")
def keys_encrypt(payload: Dict[str, str]):
    pwd = payload.get("password", "")
    if not pwd:
        raise HTTPException(400, "Password required.")
    return {
        "dataKey":  encrypt_with_password(pwd, payload.get("dataKey",  "")),
        "modelKey": encrypt_with_password(pwd, payload.get("modelKey", "")),
    }


@router.post("/keys/decrypt")
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

@router.get("/db/data-keys")
def db_get_data_keys():
    return {"keys": list_data_keys()}


@router.post("/db/data-keys")
async def db_post_data_key(request: Request):
    _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX = _keyring_refs()
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
        key_id = save_data_key(service, key_data, protected, label, activate)
    else:
        key_id = save_data_key(service, "keychain", False, label, activate)
        if _KEYRING_AVAILABLE and _keyring is not None:
            try:
                _keyring.set_password(_KC_SERVICE, f"{_KC_DATA_PREFIX}{key_id}", raw_key)
            except Exception as exc:
                raise HTTPException(500, f"Failed to store key in OS keychain: {exc}")
        else:
            update_data_key_data(key_id, base64.b64encode(raw_key.encode()).decode())

    return {"id": key_id, "status": "ok"}


@router.post("/db/data-keys/{key_id}/activate")
def db_activate_data_key(key_id: int):
    if not activate_data_key(key_id):
        raise HTTPException(404, f"Data key {key_id} not found")
    return {"status": "ok"}


@router.delete("/db/data-keys/{key_id}")
def db_delete_data_key(key_id: int):
    _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX = _keyring_refs()
    rec = get_data_key_by_id(key_id)
    if not rec:
        raise HTTPException(404, f"Data key {key_id} not found")
    if not rec["protected"] and rec["key_data"] == "keychain" and _KEYRING_AVAILABLE and _keyring is not None:
        try:
            _keyring.delete_password(_KC_SERVICE, f"{_KC_DATA_PREFIX}{key_id}")
        except Exception:
            pass
    delete_data_key(key_id)
    return {"status": "ok"}


@router.get("/db/model-keys")
def db_get_model_keys():
    return {"keys": list_model_keys()}


@router.post("/db/model-keys")
async def db_post_model_key(request: Request):
    _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX = _keyring_refs()
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
        key_id = save_model_key(model_name, provider, key_data, protected, label, activate)
    else:
        key_id = save_model_key(model_name, provider, "keychain", False, label, activate)
        if _KEYRING_AVAILABLE and _keyring is not None:
            try:
                _keyring.set_password(_KC_SERVICE, f"{_KC_MODEL_PREFIX}{key_id}", raw_key)
            except Exception as exc:
                raise HTTPException(500, f"Failed to store key in OS keychain: {exc}")
        else:
            update_model_key_data(key_id, base64.b64encode(raw_key.encode()).decode())

    return {"id": key_id, "status": "ok"}


@router.post("/db/model-keys/{key_id}/activate")
def db_activate_model_key(key_id: int):
    if not activate_model_key(key_id):
        raise HTTPException(404, f"Model key {key_id} not found")
    return {"status": "ok"}


@router.delete("/db/model-keys/{key_id}")
def db_delete_model_key(key_id: int):
    _keyring, _KEYRING_AVAILABLE, _KC_SERVICE, _KC_DATA_PREFIX, _KC_MODEL_PREFIX = _keyring_refs()
    rec = get_model_key_by_id(key_id)
    if not rec:
        raise HTTPException(404, f"Model key {key_id} not found")
    if not rec["protected"] and rec["key_data"] == "keychain" and _KEYRING_AVAILABLE and _keyring is not None:
        try:
            _keyring.delete_password(_KC_SERVICE, f"{_KC_MODEL_PREFIX}{key_id}")
        except Exception:
            pass
    delete_model_key(key_id)
    return {"status": "ok"}


# ── Legacy compat endpoint ────────────────────────────────────────────────────

@router.get("/db/api_keys")
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
