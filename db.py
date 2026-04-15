"""Database helper module.

This module centralizes SQLite access and server-side encryption helpers.
Call `create_tables()` to create the required schema.
"""
import sqlite3
import base64
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


DB_PATH = os.path.join(os.path.dirname(__file__), 'backtester.db')


def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class db_conn:
    """Context manager for SQLite connections — guarantees close on exit."""
    def __init__(self, commit: bool = False):
        self._commit = commit
        self._conn = None

    def __enter__(self):
        self._conn = get_db_conn()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn is not None:
            if self._commit and exc_type is None:
                self._conn.commit()
            self._conn.close()
        return False


def _infer_provider(model_name: str) -> str:
    """Derive provider name from model identifier."""
    mn = model_name.lower()
    if "claude" in mn:
        return "anthropic"
    if "gpt" in mn or "o1" in mn or "o3" in mn or "o4" in mn:
        return "openai"
    if "grok" in mn:
        return "grok"
    if "gemini" in mn:
        return "gemini"
    return "unknown"


def create_tables() -> None:
    """Create tables if they don't exist."""
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY,
            name TEXT,
            logic TEXT,
            config TEXT
        )
        ''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS indicators (
            id INTEGER PRIMARY KEY,
            name TEXT,
            expression TEXT
        )
        ''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY,
            service TEXT,
            model_name TEXT,
            data_key TEXT,
            model_key TEXT,
            protected INTEGER
        )
        ''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS data_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            key_data TEXT DEFAULT '',
            protected INTEGER DEFAULT 0,
            active INTEGER DEFAULT 0,
            label TEXT DEFAULT ''
        )
        ''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS model_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT '',
            key_data TEXT DEFAULT '',
            protected INTEGER DEFAULT 0,
            active INTEGER DEFAULT 0,
            label TEXT DEFAULT ''
        )
        ''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT,
            strategy_hash TEXT UNIQUE,
            ticker TEXT,
            timeframe TEXT,
            start_date TEXT,
            end_date TEXT,
            starting_cash REAL,
            run_at TEXT,
            params_json TEXT,
            metrics_json TEXT,
            equity_curve_json TEXT,
            trade_log_json TEXT,
            signal_log_json TEXT
        )
        ''')

        # Idempotent migrations: only ignore "duplicate column" errors
        def _add_column(sql: str) -> None:
            try:
                cur.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

        _add_column("ALTER TABLE backtest_runs ADD COLUMN signal_log_json TEXT")
        _add_column("ALTER TABLE indicators ADD COLUMN is_builtin INTEGER DEFAULT 0")
        _add_column("ALTER TABLE strategies ADD COLUMN is_builtin INTEGER DEFAULT 0")

        # ── Migrate from legacy api_keys table ────────────────────────────────
        try:
            cur.execute("SELECT service, model_name, data_key, model_key, protected FROM api_keys LIMIT 1")
            old = cur.fetchone()
            if old:
                cur.execute("SELECT COUNT(*) as cnt FROM data_api_keys")
                if cur.fetchone()["cnt"] == 0 and old["data_key"]:
                    svc = old["service"] or "unknown"
                    cur.execute(
                        "INSERT INTO data_api_keys (service, key_data, protected, active, label) VALUES (?, ?, ?, 1, ?)",
                        (svc, old["data_key"], old["protected"] or 0, f"{svc} (migrated)"),
                    )
                cur.execute("SELECT COUNT(*) as cnt FROM model_api_keys")
                if cur.fetchone()["cnt"] == 0 and old["model_key"]:
                    mn = old["model_name"] or "unknown"
                    cur.execute(
                        "INSERT INTO model_api_keys (model_name, provider, key_data, protected, active, label) VALUES (?, ?, ?, ?, 1, ?)",
                        (mn, _infer_provider(mn), old["model_key"], old["protected"] or 0, f"{mn} (migrated)"),
                    )
        except Exception:
            pass  # legacy table may not exist in fresh DBs


# ── Data API key helpers ───────────────────────────────────────────────────────

def list_data_keys() -> List[Dict[str, Any]]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, service, label, active, protected FROM data_api_keys ORDER BY active DESC, id")
        return [dict(r) for r in cur.fetchall()]


def save_data_key(service: str, key_data: str, protected: bool, label: str = "", activate: bool = True) -> int:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        if activate:
            cur.execute("UPDATE data_api_keys SET active=0")
        cur.execute(
            "INSERT INTO data_api_keys (service, key_data, protected, active, label) VALUES (?, ?, ?, ?, ?)",
            (service, key_data, 1 if protected else 0, 1 if activate else 0, label),
        )
        return cur.lastrowid


def activate_data_key(key_id: int) -> bool:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE data_api_keys SET active=0")
        cur.execute("UPDATE data_api_keys SET active=1 WHERE id=?", (key_id,))
        return cur.rowcount > 0


def delete_data_key(key_id: int) -> bool:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM data_api_keys WHERE id=?", (key_id,))
        return cur.rowcount > 0


def get_active_data_key() -> Optional[Dict[str, Any]]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, service, key_data, protected FROM data_api_keys WHERE active=1 LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None


def get_data_key_by_id(key_id: int) -> Optional[Dict[str, Any]]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, service, key_data, protected FROM data_api_keys WHERE id=?", (key_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_data_key_data(key_id: int, key_data: str) -> None:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE data_api_keys SET key_data=? WHERE id=?", (key_data, key_id))


def list_all_data_keys_full() -> List[Dict[str, Any]]:
    """Return id, key_data, protected for all data keys (used for migration)."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, key_data, protected FROM data_api_keys")
        return [dict(r) for r in cur.fetchall()]


# ── Model API key helpers ─────────────────────────────────────────────────────

def list_model_keys() -> List[Dict[str, Any]]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, model_name, provider, label, active, protected FROM model_api_keys ORDER BY active DESC, id")
        return [dict(r) for r in cur.fetchall()]


def save_model_key(model_name: str, provider: str, key_data: str, protected: bool, label: str = "", activate: bool = True) -> int:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        if activate:
            cur.execute("UPDATE model_api_keys SET active=0")
        cur.execute(
            "INSERT INTO model_api_keys (model_name, provider, key_data, protected, active, label) VALUES (?, ?, ?, ?, ?, ?)",
            (model_name, provider, key_data, 1 if protected else 0, 1 if activate else 0, label),
        )
        return cur.lastrowid


def activate_model_key(key_id: int) -> bool:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE model_api_keys SET active=0")
        cur.execute("UPDATE model_api_keys SET active=1 WHERE id=?", (key_id,))
        return cur.rowcount > 0


def delete_model_key(key_id: int) -> bool:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM model_api_keys WHERE id=?", (key_id,))
        return cur.rowcount > 0


def get_active_model_key() -> Optional[Dict[str, Any]]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, model_name, provider, key_data, protected FROM model_api_keys WHERE active=1 LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None


def get_model_key_by_id(key_id: int) -> Optional[Dict[str, Any]]:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, model_name, provider, key_data, protected FROM model_api_keys WHERE id=?", (key_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_model_key_data(key_id: int, key_data: str) -> None:
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE model_api_keys SET key_data=? WHERE id=?", (key_data, key_id))


def list_all_model_keys_full() -> List[Dict[str, Any]]:
    """Return id, key_data, protected for all model keys (used for migration)."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, key_data, protected FROM model_api_keys")
        return [dict(r) for r in cur.fetchall()]


def _derive_fernet_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode())
    return base64.urlsafe_b64encode(key)


def encrypt_with_password(password: str, plaintext: str) -> str:
    """Encrypt plaintext with password. Returns salt:token base64 encoded string."""
    salt = os.urandom(16)
    key = _derive_fernet_key(password, salt)
    f = Fernet(key)
    token = f.encrypt(plaintext.encode())
    return base64.b64encode(salt).decode() + ':' + token.decode()


def decrypt_with_password(password: str, stored: str) -> str:
    """Decrypt a stored value produced by `encrypt_with_password`."""
    try:
        salt_b64, token = stored.split(':', 1)
        salt = base64.b64decode(salt_b64.encode())
        key = _derive_fernet_key(password, salt)
        f = Fernet(key)
        return f.decrypt(token.encode()).decode()
    except Exception as exc:
        raise ValueError('Decryption failed') from exc


def ensure_db():
    """Ensure DB and tables exist. Safe to call at startup."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    create_tables()


# ---------------------------------------------------------------------------
# Backtest run storage
# ---------------------------------------------------------------------------

def _sanitize_floats(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None so JSON stays RFC-compliant."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


def _make_run_hash(params: Dict[str, Any]) -> str:
    """SHA-256 of the canonicalised params dict for deduplication."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def save_run(
    strategy_name: str,
    ticker: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    starting_cash: float,
    strategy_config: Any,
    metrics: Dict[str, Any],
    equity_curve: List[Dict],
    trade_log: List[Dict],
    signal_log: Optional[List[Dict]] = None,
    extra_params: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Persist a backtest run. Returns the new run id.
    Every call inserts a fresh row — run_at is included in the hash so the
    UNIQUE constraint on strategy_hash is never violated by re-runs.
    """
    run_at = datetime.now(timezone.utc).isoformat()

    params = {
        "strategy_name":   strategy_name,
        "strategy_config": strategy_config,
        "ticker":          ticker,
        "timeframe":       timeframe,
        "start_date":      start_date,
        "end_date":        end_date,
        "starting_cash":   starting_cash,
    }
    if extra_params:
        params.update(extra_params)

    # Include run_at so every run gets a unique hash even with identical params
    hash_params = dict(params, run_at=run_at)
    run_hash = _make_run_hash(hash_params)

    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT OR IGNORE INTO backtest_runs
               (strategy_name, strategy_hash, ticker, timeframe, start_date, end_date,
                starting_cash, run_at, params_json, metrics_json, equity_curve_json,
                trade_log_json, signal_log_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                strategy_name,
                run_hash,
                ticker,
                timeframe,
                start_date,
                end_date,
                starting_cash,
                run_at,
                json.dumps(params),
                json.dumps(metrics),
                json.dumps(equity_curve),
                json.dumps(trade_log),
                json.dumps(signal_log or []),
            ),
        )
        return cur.lastrowid


def list_runs() -> List[Dict[str, Any]]:
    """Return all runs (metadata only, no equity curve) ordered newest first."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, strategy_name, ticker, timeframe, start_date, end_date,
                      starting_cash, run_at, metrics_json
               FROM backtest_runs
               ORDER BY id DESC"""
        )
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["metrics"] = _sanitize_floats(json.loads(d.pop("metrics_json") or "{}"))
            except Exception:
                d["metrics"] = {}
            rows.append(d)
        return rows


def get_run(run_id: int) -> Optional[Dict[str, Any]]:
    """Return a full run including equity curve and trade log."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    _list_fields = {"equity_curve", "trade_log"}
    for key in ("params_json", "metrics_json", "equity_curve_json", "trade_log_json"):
        raw = d.pop(key, None)
        field_name = key.replace("_json", "")
        default = [] if field_name in _list_fields else {}
        try:
            d[field_name] = _sanitize_floats(json.loads(raw) if raw else default)
        except Exception:
            d[field_name] = default
    # signal_log is a list; handle separately so old runs default to []
    raw_sl = d.pop("signal_log_json", None)
    try:
        d["signal_log"] = json.loads(raw_sl) if raw_sl else []
    except Exception:
        d["signal_log"] = []
    return d


def delete_run(run_id: int) -> bool:
    """Delete a run by id. Returns True if a row was deleted."""
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM backtest_runs WHERE id = ?", (run_id,))
        return cur.rowcount > 0


def delete_all_runs() -> int:
    """Delete every backtest run. Returns count of rows deleted."""
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM backtest_runs")
        return cur.rowcount


def delete_runs_batch(ids: List[int]) -> int:
    """Delete multiple runs by id. Returns count of rows deleted."""
    if not ids:
        return 0
    with db_conn(commit=True) as conn:
        cur = conn.cursor()
        placeholders = ",".join("?" * len(ids))
        cur.execute(f"DELETE FROM backtest_runs WHERE id IN ({placeholders})", ids)
        return cur.rowcount


def get_strategy(strategy_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single strategy row by id. Returns None if not found."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, logic, config, is_builtin FROM strategies WHERE id = ?", (strategy_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "logic": row[2],
            "config": row[3],
            "is_builtin": bool(row[4]),
        }


def get_indicator(indicator_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single indicator row by id. Returns None if not found."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, expression, is_builtin FROM indicators WHERE id = ?", (indicator_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "expression": row[2],
            "is_builtin": bool(row[3]),
        }


if __name__ == '__main__':
    # simple CLI to inspect/create the DB
    print('DB path:', DB_PATH)
    create_tables()
    print('Tables created/verified.')
