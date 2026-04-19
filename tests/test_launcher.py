import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx


REPO = Path(__file__).resolve().parent.parent


def _wait_for_health(port: int, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _read_port_from_lockfile(data_dir: Path, timeout_s: float = 10.0) -> int:
    lock = data_dir / "backtester.lock"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if lock.exists():
            try:
                return json.loads(lock.read_text())["port"]
            except Exception:
                pass
        time.sleep(0.1)
    raise TimeoutError("lockfile never appeared")


def test_launcher_serves_health_and_shuts_down(tmp_path):
    env = os.environ.copy()
    env["BACKTESTER_DATA_DIR"] = str(tmp_path)
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "backtester_launcher.py"), "--no-browser", "--no-tray", "--port", "0"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        port = _read_port_from_lockfile(tmp_path)
        assert _wait_for_health(port), "launcher never became ready"

        r = httpx.get(f"http://127.0.0.1:{port}/", timeout=2.0)
        assert r.status_code in (200, 404)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            raise AssertionError("launcher did not shut down within 10s of SIGTERM")

    assert proc.returncode in (0, -signal.SIGTERM, signal.SIGTERM, 1)
