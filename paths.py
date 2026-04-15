"""Single source of truth for user-data paths (DB, logs, frontend bundle).

Resolution order for the user-data directory:
  1. portable_flag=True (passed in from launcher CLI --portable)
  2. portable.txt next to the executable
  3. BACKTESTER_DATA_DIR env var
  4. platformdirs.user_data_dir("Backtester", "Backtester")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import platformdirs


def _executable_dir() -> Path:
    """Directory containing the running executable.

    In a PyInstaller bundle, sys.executable is the bundled binary.
    In dev, it's the Python interpreter — fall back to the repo root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resolve_user_data_dir(portable_flag: bool = False) -> Path:
    if portable_flag:
        return _executable_dir() / "data"

    if (_executable_dir() / "portable.txt").exists():
        return _executable_dir() / "data"

    env_override = os.environ.get("BACKTESTER_DATA_DIR")
    if env_override:
        return Path(env_override)

    return Path(platformdirs.user_data_dir("Backtester", "Backtester"))


def _data_dir() -> Path:
    """Read from the env var the launcher sets at startup; fall back to default."""
    env_override = os.environ.get("BACKTESTER_DATA_DIR")
    if env_override:
        return Path(env_override)
    return resolve_user_data_dir(portable_flag=False)


def db_path() -> Path:
    return _data_dir() / "backtester.db"


def logs_dir() -> Path:
    return _data_dir() / "logs"


def frontend_dist_dir() -> Path:
    """Where the built React bundle lives.

    PyInstaller bundle: sys._MEIPASS/frontend_dist
    Dev:                <repo>/frontend/dist
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend_dist"
    return Path(__file__).resolve().parent / "frontend" / "dist"


def ensure_data_dir() -> Path:
    """Create the user-data dir (and logs subdir) if missing. Returns the data dir."""
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
    return d
