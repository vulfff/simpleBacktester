"""Database helper module.

This module centralizes SQLite access and server-side encryption helpers.
Call `create_tables()` to create the required schema.
"""
import sqlite3
import base64
import os
from typing import Dict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


DB_PATH = os.path.join(os.path.dirname(__file__), 'backtester.db')


def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables() -> None:
    """Create tables if they don't exist."""
    conn = get_db_conn()
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
    conn.commit()
    conn.close()


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


if __name__ == '__main__':
    # simple CLI to inspect/create the DB
    print('DB path:', DB_PATH)
    create_tables()
    print('Tables created/verified.')
