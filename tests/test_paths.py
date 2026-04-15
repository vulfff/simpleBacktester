import os
from pathlib import Path
import pytest
import paths


def test_portable_mode_via_marker_file(tmp_path, monkeypatch):
    fake_exe_dir = tmp_path / "app"
    fake_exe_dir.mkdir()
    (fake_exe_dir / "portable.txt").write_text("")
    monkeypatch.setattr(paths, "_executable_dir", lambda: fake_exe_dir)
    monkeypatch.delenv("BACKTESTER_DATA_DIR", raising=False)

    assert paths.resolve_user_data_dir(portable_flag=False) == fake_exe_dir / "data"


def test_portable_mode_via_cli_flag(tmp_path, monkeypatch):
    fake_exe_dir = tmp_path / "app"
    fake_exe_dir.mkdir()
    monkeypatch.setattr(paths, "_executable_dir", lambda: fake_exe_dir)
    monkeypatch.delenv("BACKTESTER_DATA_DIR", raising=False)

    assert paths.resolve_user_data_dir(portable_flag=True) == fake_exe_dir / "data"


def test_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTESTER_DATA_DIR", str(tmp_path))
    assert paths.resolve_user_data_dir(portable_flag=False) == tmp_path


def test_platformdirs_fallback(tmp_path, monkeypatch):
    fake_exe_dir = tmp_path / "app"
    fake_exe_dir.mkdir()
    monkeypatch.setattr(paths, "_executable_dir", lambda: fake_exe_dir)
    monkeypatch.delenv("BACKTESTER_DATA_DIR", raising=False)

    result = paths.resolve_user_data_dir(portable_flag=False)
    assert result.name == "Backtester"


def test_db_path_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTESTER_DATA_DIR", str(tmp_path))
    assert paths.db_path() == tmp_path / "backtester.db"


def test_logs_dir_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTESTER_DATA_DIR", str(tmp_path))
    assert paths.logs_dir() == tmp_path / "logs"
