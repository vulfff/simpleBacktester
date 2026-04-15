# Application Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the Backtester (FastAPI + React) as a one-click, cross-platform desktop app that double-clicks to launch — tray icon + browser tab — with no Python/Node/terminal required from the end user.

**Architecture:** A new launcher process (`backtester_launcher.py`) starts FastAPI on a free loopback port in a background thread, registers a `pystray` tray icon on the main thread, and opens the user's default browser. FastAPI serves the pre-built React bundle as static files at `/`, and all backend routes move under `/api/*`. A new `paths.py` module is the single source of truth for the user-data directory (DB, logs) using `platformdirs`, with a portable-mode override. PyInstaller bundles the Python runtime + backend + frontend into a single per-OS artifact, shipped via GitHub Releases.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, SQLite, React 19 / Vite, PyInstaller, pystray, platformdirs, pillow, NSIS (Windows), hdiutil (macOS), appimagetool + dpkg-deb (Linux), GitHub Actions.

**Spec source:** [wrapper.md](../../../wrapper.md)

---

## Build Order Overview

This plan implements the spec's §11 build sequence. Each phase is independently shippable and each task ends with a commit.

1. **Phase 1** — `paths.py` + DB path migration (no user-visible change)
2. **Phase 2** — `/api` route prefix + frontend relative URLs (dev workflow only)
3. **Phase 3** — Static-file mount in FastAPI (single-port serving)
4. **Phase 4** — `backtester_launcher.py` (tray + browser, runs from source)
5. **Phase 5** — PyInstaller `.spec` + local binary
6. **Phase 6** — Native installers (NSIS / DMG / AppImage / DEB)
7. **Phase 7** — GitHub Actions release pipeline
8. **Phase 8** — Update-check banner (`/api/version` + UI)
9. **Phase 9** — Documentation (README, install guide, contributor guide)

---

## File Structure

### New files
| Path | Responsibility |
|---|---|
| `paths.py` | Resolve user-data dir, DB path, logs dir, frontend-dist dir. Single source of truth for paths. |
| `backtester_launcher.py` | PyInstaller entry point: start uvicorn in background, run pystray on main thread, open browser. |
| `backtester.spec` | PyInstaller config (onedir, windowed, add-data for frontend, hidden imports). |
| `scripts/build.py` | Local + CI build orchestration (npm build → PyInstaller → installer). |
| `scripts/backtester.nsi` | NSIS Windows installer script. |
| `scripts/backtester.desktop` | Linux `.desktop` entry for `.deb`. |
| `assets/icon.svg` | Source icon (committed; ico/icns/png regenerated from this). |
| `assets/icon.ico` | Windows multi-size icon. |
| `assets/icon.icns` | macOS icon. |
| `assets/icon.png` | Linux 256x256 tray icon. |
| `.github/workflows/release.yml` | Tag-triggered matrix release pipeline. |
| `tests/test_paths.py` | Unit tests for path resolution (portable, env var, OS defaults). |
| `tests/test_launcher.py` | Integration test for the launcher subprocess (health probe + clean shutdown). |

### Modified files
| Path | Change |
|---|---|
| `db.py` | Replace module-level `DB_PATH` with lazy `_db_path()` that reads `BACKTESTER_DATA_DIR` via `paths.py`. |
| `api.py` | Add `/api/health`, `/api/version`; mount routers under `/api`; mount React static bundle at `/`; move `@app.get("/health")`, `@app.get("/strategies")`, `@app.post("/backtest/upload")` under `/api`. |
| `routes_ai.py`, `routes_data.py`, `routes_db.py` | No change to handlers; only included with `prefix="/api"` in `api.py`. |
| `seed_prebuilts.py` | Ensure parent dirs exist before opening DB. |
| `requirements.txt` | Add `platformdirs`, `pystray`, `pillow`. |
| `frontend/vite.config.js` | Add `base: './'`. |
| `frontend/src/AIIndicatorChat.jsx` | `API_BASE` default `''`; prefix `/ai/...` → `/api/ai/...`. |
| `frontend/src/AIStrategyChat.jsx` | Same as above. |
| `frontend/src/Analytics.jsx` | `API` default `''`; prefix `/db/...` → `/api/db/...`. |
| `frontend/src/Analyzer.jsx` | `API_BASE` default `''`; prefix paths. |
| `frontend/src/Backtest.jsx` | `API` default `''`; prefix paths. |
| `frontend/src/IndicatorBuilder.jsx` | Audit fetches; use relative `/api/...`. |
| `frontend/src/KeyManager.jsx` | Audit fetches; use relative `/api/...`. |
| `frontend/src/StrategyBuilder.jsx` | Audit fetches; use relative `/api/...`. |
| `frontend/src/App.jsx` | Add update-banner component. |
| `.gitignore` | Add `dist/`, `build/`, `frontend_dist/`, `*.spec~`. |

---

# Phase 1: Path Layer

Goal: introduce `paths.py`, route `db.py`'s DB path through it, no other behaviour changes.

## Task 1.1: Add `platformdirs` to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Edit `requirements.txt`**

Append after existing entries:
```
platformdirs>=4.0
pystray>=0.19
pillow>=10.0
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: `Successfully installed platformdirs-... pystray-... pillow-...`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add platformdirs, pystray, pillow for desktop wrapper"
```

## Task 1.2: Create `paths.py` with failing test for portable-mode detection

**Files:**
- Create: `paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_paths.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paths'`

- [ ] **Step 3: Create `paths.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_paths.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add paths.py tests/test_paths.py
git commit -m "feat(paths): add user-data path resolution module with tests"
```

## Task 1.3: Migrate `db.py` to use `paths.db_path()`

**Files:**
- Modify: `db.py:21,25`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_paths.py`:
```python
def test_db_module_uses_paths(tmp_path, monkeypatch):
    """db.get_db_conn() must open the DB at paths.db_path()."""
    monkeypatch.setenv("BACKTESTER_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(exist_ok=True)

    import importlib
    import db
    importlib.reload(db)
    conn = db.get_db_conn()
    try:
        assert (tmp_path / "backtester.db").exists()
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py::test_db_module_uses_paths -v`
Expected: FAIL — DB created at the old hardcoded path, not under `tmp_path`.

- [ ] **Step 3: Edit `db.py`**

Replace the line `DB_PATH = os.path.join(os.path.dirname(__file__), 'backtester.db')` with:
```python
import paths


def _db_path() -> str:
    paths.ensure_data_dir()
    return str(paths.db_path())
```

Then change `get_db_conn`:
```python
def get_db_conn():
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

(Preserve any existing `row_factory` / pragma lines that were there.)

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass, including the existing engine/metrics/csvparser tests.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_paths.py
git commit -m "refactor(db): resolve DB path via paths module"
```

## Task 1.4: Make `seed_prebuilts.py` create parent dirs

**Files:**
- Modify: `seed_prebuilts.py`

- [ ] **Step 1: Inspect current code**

Run: `grep -n "def seed\|db_conn\|sqlite3" c:/backtester/seed_prebuilts.py | head -10`

- [ ] **Step 2: Add `paths.ensure_data_dir()` at top of `seed()`**

In `seed_prebuilts.py`, find the `def seed():` (or equivalent) function and add as the first line of its body:
```python
    import paths
    paths.ensure_data_dir()
```

- [ ] **Step 3: Verify by running the API once with a temp data dir**

Run (Bash):
```bash
BACKTESTER_DATA_DIR=/tmp/btest_seed python -c "import seed_prebuilts; seed_prebuilts.seed()"
ls /tmp/btest_seed/
```
Expected: `backtester.db` exists.

- [ ] **Step 4: Commit**

```bash
git add seed_prebuilts.py
git commit -m "fix(seed): create user-data dir if missing before seeding"
```

---

# Phase 2: `/api` Route Prefix + Relative Frontend URLs

Goal: every backend handler lives under `/api/*`; every frontend `fetch()` becomes same-origin relative. Dev workflow (Vite on 5173 → Uvicorn on 8000) still works via Vite proxy.

## Task 2.1: Prefix routers and move app-level routes under `/api`

**Files:**
- Modify: `api.py:199-201,224,229,236`

- [ ] **Step 1: Edit `api.py` router includes**

Replace:
```python
app.include_router(ai_router)
app.include_router(data_router)
app.include_router(db_router)
```
with:
```python
app.include_router(ai_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(db_router, prefix="/api")
```

- [ ] **Step 2: Move app-level routes under `/api`**

In `api.py`, change:
- `@app.get("/health")` → `@app.get("/api/health")`
- `@app.get("/strategies")` → `@app.get("/api/strategies")`
- `@app.post("/backtest/upload", ...)` → `@app.post("/api/backtest/upload", ...)`

- [ ] **Step 3: Manual smoke test**

In one terminal: `uvicorn api:app --reload`
In another: `curl http://localhost:8000/api/health`
Expected: 200 with `{"ok": true}` (or current health response shape).

Also: `curl -i http://localhost:8000/health`
Expected: 404.

- [ ] **Step 4: Commit**

```bash
git add api.py
git commit -m "refactor(api): move all backend routes under /api prefix"
```

## Task 2.2: Add `/api/health` endpoint (for launcher readiness probe)

**Files:**
- Modify: `api.py`

- [ ] **Step 1: Add endpoint**

In `api.py`, near the other top-level routes, ensure the following exists (replace the moved `/api/health` from Task 2.1 if its body is different):
```python
@app.get("/api/health")
def health():
    return {"ok": True}
```

- [ ] **Step 2: Verify**

Restart `uvicorn api:app --reload`.
Run: `curl http://localhost:8000/api/health`
Expected: `{"ok":true}`.

- [ ] **Step 3: Commit**

```bash
git add api.py
git commit -m "feat(api): add /api/health for launcher readiness probe and CI smoke tests"
```

## Task 2.3: Configure Vite proxy so dev mode keeps working

**Files:**
- Modify: `frontend/vite.config.js`

- [ ] **Step 1: Edit `frontend/vite.config.js`**

Replace the contents with:
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 2: Verify**

Run `cd frontend && npm run dev` and load `http://localhost:5173/`.
Expected: page loads; network tab shows `/api/...` requests proxied to 8000.

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.js
git commit -m "build(frontend): proxy /api to backend in dev; set base ./ for portable bundle"
```

## Task 2.4: Switch frontend `API_BASE` defaults to `''` and prefix `/api`

**Files:**
- Modify: `frontend/src/AIIndicatorChat.jsx:4`
- Modify: `frontend/src/AIStrategyChat.jsx:4`
- Modify: `frontend/src/Analytics.jsx:8`
- Modify: `frontend/src/Analyzer.jsx:4`
- Modify: `frontend/src/Backtest.jsx:4`
- Modify: `frontend/src/IndicatorBuilder.jsx`
- Modify: `frontend/src/KeyManager.jsx`
- Modify: `frontend/src/StrategyBuilder.jsx`

- [ ] **Step 1: Replace API_BASE defaults**

In each file with the pattern `import.meta.env.VITE_API_BASE || 'http://localhost:8000'`, replace with:
```js
import.meta.env.VITE_API_BASE || ''
```

Apply across all 8 files. Use:
```bash
grep -rln "VITE_API_BASE || 'http://localhost:8000'" c:/backtester/frontend/src/
```
Then edit each file.

- [ ] **Step 2: Add `/api` prefix to fetch paths in each component**

For each file, find every `fetch(\`${API_BASE}/...\`)` (or `${API}/...`) and rewrite the path so it begins with `/api`. Examples:
- `${API}/db/runs` → `${API}/api/db/runs`
- `${API_BASE}/ai/strategy-builder` → `${API_BASE}/api/ai/strategy-builder`
- `${API_BASE}/ai/indicator-builder` → `${API_BASE}/api/ai/indicator-builder`
- `${API_BASE}/ai/analyze` → `${API_BASE}/api/ai/analyze`
- `${API}/data/...` → `${API}/api/data/...`
- `${API}/db/...` → `${API}/api/db/...`
- `${API}/strategies` → `${API}/api/strategies`
- `${API}/backtest/upload` → `${API}/api/backtest/upload`
- `${API}/health` → `${API}/api/health`

For each file, use `grep -n "fetch(" <file>` to enumerate call sites. Edit each one.

- [ ] **Step 3: Verify dev mode end-to-end**

Run backend: `uvicorn api:app --reload`
Run frontend: `cd frontend && npm run dev`
Open `http://localhost:5173/`.
Click through: load runs list (Analytics), open Strategy Builder, run a backtest.
Expected: every screen works; no 404s in network tab; all calls go to `/api/...`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "refactor(frontend): use relative /api/* URLs (same-origin with backend)"
```

---

# Phase 3: Static-File Mount

Goal: FastAPI serves the built React bundle at `/`. Single port for everything.

## Task 3.1: Build the frontend once

**Files:** none (build artifact only)

- [ ] **Step 1: Build**

Run: `cd c:/backtester/frontend && npm ci && npm run build`
Expected: `frontend/dist/index.html` exists.

## Task 3.2: Mount StaticFiles in `api.py`

**Files:**
- Modify: `api.py` (append after all routers)

- [ ] **Step 1: Add static mount**

At the **end** of `api.py` (after every `app.include_router(...)` and every `@app.get/post`), append:
```python
from fastapi.staticfiles import StaticFiles
import paths

_dist = paths.frontend_dist_dir()
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
```

- [ ] **Step 2: Verify**

Restart `uvicorn api:app --reload`.
Open `http://localhost:8000/` in a browser.
Expected: React app loads (served from `frontend/dist`).
Run: `curl -s http://localhost:8000/api/health`
Expected: `{"ok":true}` (the static mount must NOT shadow `/api/*`).

- [ ] **Step 3: Commit**

```bash
git add api.py
git commit -m "feat(api): mount built React bundle at / via StaticFiles"
```

## Task 3.3: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append**

```
# PyInstaller
build/
dist/
*.spec~
frontend_dist/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore build artifacts (dist/, build/, frontend_dist/)"
```

---

# Phase 4: Launcher

Goal: `python backtester_launcher.py` starts uvicorn in background, registers tray icon, opens browser. Quit from tray cleanly stops everything.

## Task 4.1: Generate placeholder icon assets

**Files:**
- Create: `assets/icon.svg`, `assets/icon.png`, `assets/icon.ico`, `assets/icon.icns`

- [ ] **Step 1: Create source SVG**

Create `assets/icon.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="48" fill="#0f1722"/>
  <path d="M40 200 L80 140 L120 170 L180 80 L216 100" stroke="#3ab7f5" stroke-width="14" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="216" cy="100" r="10" fill="#2fd89a"/>
</svg>
```

- [ ] **Step 2: Generate PNG / ICO / ICNS from SVG**

Use ImageMagick (Windows: choco install imagemagick; macOS: brew install imagemagick; Linux: apt install imagemagick):
```bash
cd c:/backtester/assets
magick icon.svg -resize 256x256 icon.png
magick icon.svg -define icon:auto-resize=16,32,48,256 icon.ico
# icns (macOS only — placeholder copy on other OSes; CI replaces it)
cp icon.png icon.icns 2>/dev/null || true
```

If ImageMagick is unavailable on the dev box, leave a 1x1 PNG placeholder; CI regenerates them. Document this in the README later (Phase 9).

- [ ] **Step 3: Commit**

```bash
git add assets/
git commit -m "feat(assets): add icon set (svg source + ico/icns/png exports)"
```

## Task 4.2: Launcher skeleton — port picker + uvicorn in background thread

**Files:**
- Create: `backtester_launcher.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_launcher.py`:
```python
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


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
            import json
            try:
                return json.loads(lock.read_text())["port"]
            except Exception:
                pass
        time.sleep(0.1)
    raise TimeoutError("lockfile never appeared")


@pytest.mark.timeout(30)
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

        # Static bundle mounted at /
        r = httpx.get(f"http://127.0.0.1:{port}/", timeout=2.0)
        # OK if the dist isn't built — at minimum the route should not 500.
        assert r.status_code in (200, 404)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("launcher did not shut down within 5s")

    assert proc.returncode in (0, -signal.SIGTERM, signal.SIGTERM)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_launcher.py -v`
Expected: FAIL — `backtester_launcher.py` does not exist.

- [ ] **Step 3: Create `backtester_launcher.py` (no tray yet — `--no-tray` path only)**

```python
"""Backtester desktop launcher.

Boots uvicorn on a free loopback port in a background thread, registers a
pystray tray icon on the main thread, and opens the user's default browser.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import paths


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _configure_logging() -> None:
    logs = paths.logs_dir()
    logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        logs / "backtester.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _start_uvicorn(port: int) -> "tuple[threading.Thread, object]":
    """Start uvicorn in a background thread; return (thread, server)."""
    import uvicorn
    import api

    config = uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="uvicorn", daemon=False)
    thread.start()
    return thread, server


def _wait_for_health(port: int, timeout_s: float = 10.0) -> bool:
    import httpx
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


def _write_lockfile(data_dir: Path, port: int) -> Path:
    lock = data_dir / "backtester.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "port": port}))
    return lock


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="backtester")
    p.add_argument("--portable", action="store_true", help="store data next to the executable")
    p.add_argument("--port", type=int, default=0, help="loopback port (0 = auto)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    p.add_argument("--no-tray", action="store_true", help="do not register a tray icon (CI/test)")
    p.add_argument("--dev", action="store_true", help="dev mode (verbose logging)")
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)

    data_dir = paths.resolve_user_data_dir(portable_flag=args.portable)
    os.environ["BACKTESTER_DATA_DIR"] = str(data_dir)
    paths.ensure_data_dir()

    _configure_logging()
    log = logging.getLogger("launcher")
    log.info("data dir: %s", data_dir)

    port = args.port if args.port else _pick_free_port()
    log.info("port: %d", port)

    lock = _write_lockfile(data_dir, port)
    log.info("lockfile: %s", lock)

    thread, server = _start_uvicorn(port)

    if not _wait_for_health(port, timeout_s=10.0):
        log.error("server failed readiness probe")
        server.should_exit = True
        thread.join(timeout=5)
        return 1

    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")

    if args.no_tray:
        # Block until SIGTERM/SIGINT.
        try:
            while thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
        return 0

    # Tray loop is added in Task 4.3.
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the launcher test**

Run: `python -m pytest tests/test_launcher.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backtester_launcher.py tests/test_launcher.py
git commit -m "feat(launcher): boot uvicorn on free port; --no-tray path for CI"
```

## Task 4.3: Add pystray tray icon with menu

**Files:**
- Modify: `backtester_launcher.py`

- [ ] **Step 1: Add tray support**

Add at top of `backtester_launcher.py`:
```python
import subprocess
```

Add helper functions before `main()`:
```python
def _open_data_dir(data_dir: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(data_dir))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(data_dir)])
    else:
        subprocess.Popen(["xdg-open", str(data_dir)])


def _icon_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "assets"
    else:
        base = Path(__file__).resolve().parent / "assets"
    return base / "icon.png"


def _run_tray(port: int, data_dir: Path, server, thread, lock: Path) -> None:
    import pystray
    from PIL import Image

    image = Image.open(_icon_path())

    def _quit(icon, _item):
        server.should_exit = True
        thread.join(timeout=5)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        icon.stop()

    def _open(_icon, _item):
        webbrowser.open(f"http://127.0.0.1:{port}/")

    def _copy_url(_icon, _item):
        url = f"http://127.0.0.1:{port}"
        try:
            import pyperclip
            pyperclip.copy(url)
        except Exception:
            # pyperclip is optional; fall back to logging the URL.
            logging.getLogger("launcher").info("URL: %s", url)

    def _open_dir(_icon, _item):
        _open_data_dir(data_dir)

    def _about(_icon, _item):
        logging.getLogger("launcher").info("Backtester — data dir: %s", data_dir)

    menu = pystray.Menu(
        pystray.MenuItem("Open Backtester", _open, default=True),
        pystray.MenuItem("Copy URL", _copy_url),
        pystray.MenuItem("Open data folder", _open_dir),
        pystray.MenuItem("About", _about),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
    icon = pystray.Icon("backtester", image, "Backtester", menu)
    icon.run()
```

In `main()`, replace the `if args.no_tray:` block's `else` branch (the `# Tray loop` comment) with:
```python
    try:
        _run_tray(port, data_dir, server, thread, lock)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
    return 0
```

- [ ] **Step 2: Manual smoke test**

Run: `python backtester_launcher.py`
Expected:
- A tray icon appears.
- Default browser opens to `http://127.0.0.1:<port>/`.
- Menu **Quit** stops the server and removes the tray icon within ~5s.
- After quit, no orphan python process; `<data_dir>/backtester.lock` is gone.

- [ ] **Step 3: Re-run automated tests**

Run: `python -m pytest tests/test_launcher.py -v`
Expected: PASS (still uses `--no-tray`).

- [ ] **Step 4: Commit**

```bash
git add backtester_launcher.py
git commit -m "feat(launcher): add pystray tray icon (Open / Copy URL / Open data folder / Quit)"
```

## Task 4.4: Single-instance lockfile (PID liveness check)

**Files:**
- Modify: `backtester_launcher.py`

- [ ] **Step 1: Add liveness check**

Add helper near `_write_lockfile`:
```python
def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _check_existing_instance(data_dir: Path) -> Optional[int]:
    """Return the port of an existing running instance, or None."""
    lock = data_dir / "backtester.lock"
    if not lock.exists():
        return None
    try:
        info = json.loads(lock.read_text())
        if _pid_alive(int(info["pid"])):
            return int(info["port"])
    except Exception:
        pass
    return None
```

In `main()`, after `paths.ensure_data_dir()` and before `_pick_free_port`:
```python
    existing_port = _check_existing_instance(data_dir)
    if existing_port is not None:
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{existing_port}/")
        log.info("another instance is running at port %d; opening browser and exiting", existing_port)
        return 0
```

- [ ] **Step 2: Add a test**

Append to `tests/test_launcher.py`:
```python
@pytest.mark.timeout(30)
def test_second_launcher_exits_when_first_is_running(tmp_path):
    env = os.environ.copy()
    env["BACKTESTER_DATA_DIR"] = str(tmp_path)
    p1 = subprocess.Popen(
        [sys.executable, str(REPO / "backtester_launcher.py"), "--no-browser", "--no-tray", "--port", "0"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        port = _read_port_from_lockfile(tmp_path)
        assert _wait_for_health(port)

        p2 = subprocess.run(
            [sys.executable, str(REPO / "backtester_launcher.py"), "--no-browser", "--no-tray", "--port", "0"],
            env=env, capture_output=True, timeout=15,
        )
        assert p2.returncode == 0, p2.stderr.decode(errors="replace")
    finally:
        p1.terminate()
        try:
            p1.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p1.kill()
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_launcher.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add backtester_launcher.py tests/test_launcher.py
git commit -m "feat(launcher): single-instance lockfile with PID liveness; second launch reopens browser"
```

## Task 4.5: Native error dialogs for fatal startup failures

**Files:**
- Modify: `backtester_launcher.py`

- [ ] **Step 1: Add tkinter dialog helper**

Add helper near other helpers:
```python
def _show_fatal_dialog(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        # No display (e.g. Linux headless / CI). Log instead.
        logging.getLogger("launcher").error("[FATAL] %s — %s", title, message)
```

- [ ] **Step 2: Wire into health-probe failure**

Replace the readiness-failure block in `main()` with:
```python
    if not _wait_for_health(port, timeout_s=10.0):
        log_path = paths.logs_dir() / "backtester.log"
        msg = f"Backtester could not start.\n\nLog file:\n{log_path}"
        log.error("server failed readiness probe")
        _show_fatal_dialog("Backtester — startup failed", msg)
        server.should_exit = True
        thread.join(timeout=5)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        return 1
```

- [ ] **Step 3: Wrap `main()` body in try/except for unexpected errors**

Wrap the body of `main()`:
```python
    try:
        # ... existing body ...
    except Exception as exc:
        logging.getLogger("launcher").exception("unhandled error in launcher")
        _show_fatal_dialog(
            "Backtester — internal error",
            f"{exc}\n\nLog: {paths.logs_dir() / 'backtester.log'}",
        )
        return 2
```

- [ ] **Step 4: Manual sanity check**

Run: `python backtester_launcher.py --port 1` (privileged port; will fail to bind)
Expected: Error dialog appears with log path. (On Windows, an admin-elevated shell may bind 1; pick another guaranteed-fail scenario like `--port 65536`.)

- [ ] **Step 5: Commit**

```bash
git add backtester_launcher.py
git commit -m "feat(launcher): native tkinter error dialogs for fatal startup failures"
```

## Task 4.6: Detect missing frontend bundle and DB corruption (spec §7)

**Files:**
- Modify: `backtester_launcher.py`, `api.py`

- [ ] **Step 1: Frontend-bundle check at launcher startup**

In `backtester_launcher.py`, inside `main()` immediately after `paths.ensure_data_dir()`:
```python
    dist = paths.frontend_dist_dir()
    if not dist.exists() or not (dist / "index.html").exists():
        _show_fatal_dialog(
            "Backtester — internal error (packaging)",
            f"Frontend bundle missing at:\n{dist}\n\nPlease file an issue.",
        )
        return 3
```

- [ ] **Step 2: DB-corruption recovery on startup**

Add to `backtester_launcher.py` after the data-dir check:
```python
def _check_db_health(db_file: Path) -> bool:
    if not db_file.exists():
        return True  # fresh install — fine
    import sqlite3
    try:
        c = sqlite3.connect(str(db_file))
        c.execute("PRAGMA integrity_check").fetchone()
        c.close()
        return True
    except sqlite3.DatabaseError:
        return False


def _offer_db_reseed(db_file: Path) -> bool:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        ok = messagebox.askyesno(
            "Backtester — data file corrupt",
            f"Your data file appears corrupt:\n{db_file}\n\n"
            "Rename it to *.corrupt.<ts> and start with a fresh DB?\n"
            "(Your old file is preserved, not deleted.)",
        )
        root.destroy()
        return ok
    except Exception:
        return False
```

In `main()`, after `paths.ensure_data_dir()`:
```python
    db_file = paths.db_path()
    if not _check_db_health(db_file):
        if _offer_db_reseed(db_file):
            import time as _t
            db_file.rename(db_file.with_suffix(f".db.corrupt.{int(_t.time())}"))
            import seed_prebuilts
            seed_prebuilts.seed()
        else:
            return 4
```

- [ ] **Step 3: Manual smoke test**

```bash
echo "garbage" > /tmp/btest_corrupt/backtester.db
BACKTESTER_DATA_DIR=/tmp/btest_corrupt python backtester_launcher.py --no-tray --no-browser
```
Expected: dialog appears asking to reseed; clicking Yes renames the corrupt file and creates a fresh DB.

- [ ] **Step 4: Commit**

```bash
git add backtester_launcher.py
git commit -m "feat(launcher): fatal dialog for missing frontend bundle; opt-in DB reseed on corruption"
```

> **Future-work note (spec §7 'tray turns red'):** the per-spec behaviour where a crashed uvicorn thread paints the tray icon red and adds a "Restart server" menu item is **not** in this plan. It requires a second icon asset and a watchdog thread; defer until v1.1 unless field reports demand it.

---

# Phase 5: PyInstaller Bundle

Goal: produce a runnable single-folder bundle locally with PyInstaller.

## Task 5.1: Add `pyinstaller` and `httpx` (used by launcher) check

**Files:**
- Modify: `requirements.txt` (dev section)

- [ ] **Step 1: Verify httpx is already in requirements**

Run: `grep httpx c:/backtester/requirements.txt`
Expected: `httpx>=0.27.0` (already present).

- [ ] **Step 2: Add PyInstaller as a dev dependency**

If you have a separate `requirements-dev.txt`, add PyInstaller there. Otherwise create one:

Create `requirements-dev.txt`:
```
-r requirements.txt
pyinstaller>=6.0
pytest
pytest-timeout
```

- [ ] **Step 3: Install**

Run: `pip install -r requirements-dev.txt`
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add requirements-dev.txt
git commit -m "build: add requirements-dev.txt with pyinstaller + test deps"
```

## Task 5.2: Write `backtester.spec`

**Files:**
- Create: `backtester.spec`

- [ ] **Step 1: Create the spec file**

Create `backtester.spec` at repo root:
```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve()


HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "pystray._win32",
    "pystray._darwin",
    "pystray._appindicator",
    "pystray._gtk",
    "PIL.Image",
]


def _icon_for_platform():
    if sys.platform.startswith("win"):
        return str(ROOT / "assets" / "icon.ico")
    if sys.platform == "darwin":
        return str(ROOT / "assets" / "icon.icns")
    return str(ROOT / "assets" / "icon.png")


a = Analysis(
    [str(ROOT / "backtester_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend_dist"),
        (str(ROOT / "assets"), "assets"),
    ],
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Backtester",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # --windowed
    icon=_icon_for_platform(),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Backtester",
)
```

- [ ] **Step 2: Build locally**

Run:
```bash
cd c:/backtester/frontend && npm run build && cd ..
pyinstaller backtester.spec --noconfirm
```
Expected: `dist/Backtester/Backtester.exe` (Windows) or equivalent.

- [ ] **Step 3: Smoke-test the bundle**

Run (Bash on Windows):
```bash
BACKTESTER_DATA_DIR=/tmp/btest_bundle ./dist/Backtester/Backtester.exe --no-browser --no-tray --port 0 &
PID=$!
sleep 5
# Find the picked port via the lockfile
PORT=$(python -c "import json; print(json.load(open('/tmp/btest_bundle/backtester.lock'))['port'])")
curl -s http://127.0.0.1:$PORT/api/health
kill $PID
```
Expected: `{"ok":true}`.

- [ ] **Step 4: Commit**

```bash
git add backtester.spec
git commit -m "build: pyinstaller spec for cross-platform onedir windowed bundle"
```

## Task 5.3: Local build orchestration script

**Files:**
- Create: `scripts/build.py`

- [ ] **Step 1: Create script directory**

```bash
mkdir -p c:/backtester/scripts
```

- [ ] **Step 2: Write `scripts/build.py`**

```python
"""Local + CI build orchestration for the Backtester desktop bundle."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def check_prereqs() -> None:
    py = sys.version_info
    assert py >= (3, 11), f"python 3.11+ required, got {py.major}.{py.minor}"
    if shutil.which("node") is None:
        sys.exit("error: node not found on PATH")
    if shutil.which("npm") is None:
        sys.exit("error: npm not found on PATH")


def build_frontend() -> None:
    run(["npm", "ci"], cwd=ROOT / "frontend")
    run(["npm", "run", "build"], cwd=ROOT / "frontend")


def build_pyinstaller() -> None:
    run(["pyinstaller", "backtester.spec", "--noconfirm"], cwd=ROOT)


def post_windows() -> None:
    nsi = ROOT / "scripts" / "backtester.nsi"
    if shutil.which("makensis") and nsi.exists():
        run(["makensis", str(nsi)], cwd=ROOT)
    else:
        print("skip: makensis or backtester.nsi missing — installer not built")


def post_macos() -> None:
    # Phase 6 wires hdiutil here.
    print("skip: macOS .dmg packaging not yet wired (Phase 6 task)")


def post_linux() -> None:
    # Phase 6 wires AppImage + .deb here.
    print("skip: linux .AppImage / .deb packaging not yet wired (Phase 6 task)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-frontend", action="store_true")
    p.add_argument("--skip-installer", action="store_true")
    args = p.parse_args()

    check_prereqs()
    if not args.skip_frontend:
        build_frontend()
    build_pyinstaller()
    if not args.skip_installer:
        if sys.platform.startswith("win"):
            post_windows()
        elif sys.platform == "darwin":
            post_macos()
        else:
            post_linux()
    print("\n✓ build complete: dist/Backtester/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verify**

Run: `python scripts/build.py --skip-installer`
Expected: full pipeline runs, `dist/Backtester/` exists.

- [ ] **Step 4: Commit**

```bash
git add scripts/build.py
git commit -m "build: scripts/build.py orchestrates frontend + pyinstaller + installer steps"
```

---

# Phase 6: Native Installers

Goal: per-OS installer artefacts produced from the PyInstaller `dist/Backtester/` folder.

## Task 6.1: Windows NSIS installer

**Files:**
- Create: `scripts/backtester.nsi`

- [ ] **Step 1: Create the NSIS script**

```nsi
; Backtester — NSIS installer
!define APPNAME "Backtester"
!define VERSION "1.0.0"
!define INSTALL_DIR "$PROGRAMFILES64\${APPNAME}"

OutFile "..\dist\release\backtester-${VERSION}-windows-x64.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin
Name "${APPNAME}"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\Backtester\*.*"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\Backtester.exe"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\Backtester.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
```

- [ ] **Step 2: Local build**

```bash
mkdir -p c:/backtester/dist/release
cd c:/backtester
makensis scripts/backtester.nsi
```
Expected: `dist/release/backtester-1.0.0-windows-x64.exe` exists.

- [ ] **Step 3: Run the installer manually**

Double-click the produced installer. Confirm install completes, Start-menu shortcut launches the app, browser opens, app works.

- [ ] **Step 4: Commit**

```bash
git add scripts/backtester.nsi
git commit -m "build(win): NSIS installer + uninstaller for Backtester"
```

## Task 6.2: macOS `.dmg` packaging

**Files:**
- Modify: `scripts/build.py` (`post_macos`)

- [ ] **Step 1: Implement `post_macos`**

Replace the body of `post_macos()` in `scripts/build.py` with:
```python
def post_macos() -> None:
    release = ROOT / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)
    app_bundle = ROOT / "dist" / "Backtester.app"
    dmg = release / "Backtester-1.0.0.dmg"
    if dmg.exists():
        dmg.unlink()
    if not app_bundle.exists():
        # PyInstaller writes a folder; build an .app wrapper here if missing.
        sys.exit(f"missing {app_bundle} — adjust .spec to produce a .app bundle on macOS")
    run([
        "hdiutil", "create",
        "-volname", "Backtester",
        "-srcfolder", str(app_bundle),
        "-ov", "-format", "UDZO",
        str(dmg),
    ])
```

NOTE: producing a `.app` bundle requires the spec to use `BUNDLE(...)` on macOS. Add this to `backtester.spec` at the bottom (guarded):
```python
import sys as _sys
if _sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Backtester.app",
        icon=str(ROOT / "assets" / "icon.icns"),
        bundle_identifier="org.backtester.Backtester",
        info_plist={"LSUIElement": True},  # tray-only, no Dock icon
    )
```

- [ ] **Step 2: Verify on macOS (CI catches if local box is not macOS)**

If on macOS: `python scripts/build.py`. Expected: `dist/release/Backtester-1.0.0.dmg`.

- [ ] **Step 3: Commit**

```bash
git add scripts/build.py backtester.spec
git commit -m "build(macos): produce .app bundle (tray-only) and .dmg via hdiutil"
```

## Task 6.3: Linux `.AppImage` and `.deb`

**Files:**
- Create: `scripts/backtester.desktop`
- Modify: `scripts/build.py` (`post_linux`)

- [ ] **Step 1: Create `.desktop` entry**

Create `scripts/backtester.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Backtester
Comment=Algorithmic trading backtester
Exec=/opt/backtester/Backtester
Icon=/opt/backtester/assets/icon.png
Categories=Office;Finance;
Terminal=false
```

- [ ] **Step 2: Implement `post_linux`**

Replace the body of `post_linux()` in `scripts/build.py`:
```python
def post_linux() -> None:
    import os
    release = ROOT / "dist" / "release"
    release.mkdir(parents=True, exist_ok=True)

    # AppImage
    appdir = ROOT / "dist" / "Backtester.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    shutil.copytree(ROOT / "dist" / "Backtester", appdir / "usr" / "bin")
    shutil.copy(ROOT / "scripts" / "backtester.desktop", appdir / "backtester.desktop")
    shutil.copy(ROOT / "assets" / "icon.png", appdir / "backtester.png")
    apprun = appdir / "AppRun"
    apprun.write_text("#!/bin/sh\nexec \"$(dirname \"$0\")/usr/bin/Backtester\" \"$@\"\n")
    apprun.chmod(0o755)
    if shutil.which("appimagetool"):
        run(["appimagetool", str(appdir), str(release / "Backtester-1.0.0-x86_64.AppImage")])
    else:
        print("skip: appimagetool missing — AppImage not built")

    # Debian package
    deb_root = ROOT / "dist" / "deb"
    if deb_root.exists():
        shutil.rmtree(deb_root)
    (deb_root / "DEBIAN").mkdir(parents=True)
    (deb_root / "opt" / "backtester").mkdir(parents=True)
    (deb_root / "usr" / "share" / "applications").mkdir(parents=True)
    shutil.copytree(ROOT / "dist" / "Backtester", deb_root / "opt" / "backtester", dirs_exist_ok=True)
    shutil.copy(ROOT / "scripts" / "backtester.desktop", deb_root / "usr" / "share" / "applications" / "backtester.desktop")
    (deb_root / "DEBIAN" / "control").write_text(
        "Package: backtester\n"
        "Version: 1.0.0\n"
        "Section: misc\n"
        "Priority: optional\n"
        "Architecture: amd64\n"
        "Maintainer: Backtester Team <noreply@example.com>\n"
        "Description: Algorithmic trading backtester (desktop)\n"
    )
    if shutil.which("dpkg-deb"):
        run(["dpkg-deb", "--build", str(deb_root), str(release / "backtester_1.0.0_amd64.deb")])
    else:
        print("skip: dpkg-deb missing — .deb not built")
```

- [ ] **Step 3: Verify on Linux (or rely on CI)**

If on Linux: `python scripts/build.py`. Expected: `.AppImage` and `.deb` in `dist/release/`.

- [ ] **Step 4: Commit**

```bash
git add scripts/build.py scripts/backtester.desktop
git commit -m "build(linux): produce AppImage and .deb artefacts"
```

---

# Phase 7: GitHub Actions Release Pipeline

Goal: pushing a `v*.*.*` tag triggers a matrix build that publishes a GitHub Release with all artefacts.

## Task 7.1: Create the workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create directory and file**

```bash
mkdir -p c:/backtester/.github/workflows
```

Create `.github/workflows/release.yml`:
```yaml
name: release

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - { os: windows-latest, arch: x64,   artifact_glob: 'dist/release/*' }
          - { os: macos-13,       arch: x64,   artifact_glob: 'dist/release/*' }
          - { os: macos-14,       arch: arm64, artifact_glob: 'dist/release/*' }
          - { os: ubuntu-22.04,   arch: x64,   artifact_glob: 'dist/release/*' }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Linux packaging tools
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y dpkg fuse libfuse2 imagemagick xdg-utils
          wget -O /usr/local/bin/appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
          chmod +x /usr/local/bin/appimagetool

      - name: Install Windows packaging tools
        if: runner.os == 'Windows'
        shell: pwsh
        run: choco install nsis -y

      - name: Install Python deps
        run: pip install -r requirements-dev.txt

      - name: Build
        run: python scripts/build.py

      - name: Smoke test packaged binary (non-Windows)
        if: runner.os != 'Windows'
        run: |
          mkdir -p /tmp/btest_smoke
          BACKTESTER_DATA_DIR=/tmp/btest_smoke ./dist/Backtester/Backtester --no-browser --no-tray --port 0 &
          PID=$!
          for i in $(seq 1 30); do
            if [ -f /tmp/btest_smoke/backtester.lock ]; then
              PORT=$(python -c "import json; print(json.load(open('/tmp/btest_smoke/backtester.lock'))['port'])")
              if curl -sf "http://127.0.0.1:$PORT/api/health"; then exit_smoke=0; break; fi
            fi
            sleep 1
          done
          kill $PID
          wait $PID 2>/dev/null || true
          test "${exit_smoke:-1}" = "0"

      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.os }}-${{ matrix.arch }}
          path: ${{ matrix.artifact_glob }}

  release:
    needs: build
    runs-on: ubuntu-22.04
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: artifacts
      - uses: softprops/action-gh-release@v2
        with:
          files: artifacts/**/*
          generate_release_notes: true
```

- [ ] **Step 2: Push a test tag against a fork (do NOT push to upstream until reviewed)**

Locally:
```bash
git tag -a v0.0.1-rc1 -m "test release pipeline"
# Push only to a fork remote, e.g. `origin-fork`
git push origin-fork v0.0.1-rc1
```
Expected: workflow runs to completion in the fork's Actions tab; release is created on the fork.

- [ ] **Step 3: Commit (workflow file)**

```bash
git add .github/workflows/release.yml
git commit -m "ci: matrix release pipeline (win/macos/linux) on v*.*.* tags"
```

---

# Phase 8: Update-Check Banner

Goal: app polls GitHub Releases once per launch (cached 1h), shows a dismissible banner if newer.

## Task 8.1: Backend `/api/version` endpoint

**Files:**
- Modify: `api.py`

- [ ] **Step 1: Add the endpoint**

In `api.py`, add near the other top-level routes:
```python
import time
import httpx as _httpx

_VERSION = "1.0.0"
_GITHUB_REPO = "backtester/backtester"  # TODO: set to actual repo before release
_version_cache: dict = {"ts": 0.0, "data": {"current": _VERSION, "latest": None, "url": None}}


@app.get("/api/version")
def version():
    now = time.time()
    if now - _version_cache["ts"] < 3600:
        return _version_cache["data"]
    data = {"current": _VERSION, "latest": None, "url": None}
    try:
        r = _httpx.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest",
            timeout=3.0, headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code == 200:
            j = r.json()
            data["latest"] = j.get("tag_name", "").lstrip("v") or None
            data["url"] = j.get("html_url")
    except Exception:
        pass
    _version_cache["ts"] = now
    _version_cache["data"] = data
    return data
```

- [ ] **Step 2: Verify**

Run: `curl http://localhost:8000/api/version`
Expected: JSON with `current: "1.0.0"`. `latest` may be null if the repo doesn't have releases yet (silent failure is intentional).

- [ ] **Step 3: Commit**

```bash
git add api.py
git commit -m "feat(api): /api/version endpoint with 1h-cached GitHub Releases lookup"
```

## Task 8.2: Frontend update banner

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Inspect current App.jsx**

Run: `grep -n "function App\|return (" c:/backtester/frontend/src/App.jsx | head -10`

- [ ] **Step 2: Add the banner**

In `App.jsx`, add at the top of the file:
```jsx
import { useEffect, useState } from 'react'

function UpdateBanner() {
  const [info, setInfo] = useState(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    fetch('/api/version').then(r => r.json()).then(setInfo).catch(() => {})
  }, [])

  if (!info || !info.latest || dismissed) return null
  if (info.latest === info.current) return null

  return (
    <div className="alert alert-warn" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span>
        Update available: <strong>{info.latest}</strong> (you are on {info.current}).{' '}
        {info.url && <a href={info.url} target="_blank" rel="noreferrer">Download</a>}
      </span>
      <button className="btn btn-sm" onClick={() => setDismissed(true)}>Dismiss</button>
    </div>
  )
}
```

Then render `<UpdateBanner />` as the first child inside the top-level `App` return (before the tab strip).

- [ ] **Step 3: Verify**

Set `_VERSION = "0.0.1"` temporarily in `api.py`, restart, and visit the app. Expected: banner appears (assuming the repo has at least one release).

Restore `_VERSION = "1.0.0"`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(frontend): dismissible update banner driven by /api/version"
```

---

# Phase 9: Documentation

Goal: README + install guide + contributor build guide so end users and contributors can use this without reading source.

## Task 9.1: User install guide

**Files:**
- Create: `docs/INSTALL.md`

- [ ] **Step 1: Create**

```markdown
# Installing Backtester

## Windows
1. Download `backtester-<ver>-windows-x64.exe` from the [Releases page](https://github.com/backtester/backtester/releases/latest).
2. Run it. SmartScreen may warn that the publisher is unknown — click **More info** → **Run anyway**. The binary is unsigned (see Roadmap).
3. The installer adds a Start-menu and Desktop shortcut.
4. Launch **Backtester** — a tray icon appears and your default browser opens to the app.

### Portable Windows
Download `backtester-<ver>-windows-x64.zip`, extract, and run `Backtester.exe`. Create a file named `portable.txt` next to the executable to make all data live in `./data/` instead of `%APPDATA%`.

## macOS
Download `Backtester-<ver>.dmg`, drag to Applications, double-click. On first launch right-click → **Open** to bypass Gatekeeper (the app is unsigned).

## Linux
- AppImage: `chmod +x Backtester-<ver>-x86_64.AppImage && ./Backtester-<ver>-x86_64.AppImage`
- Debian/Ubuntu: `sudo dpkg -i backtester_<ver>_amd64.deb && backtester`

## Where is my data?
| OS | Path |
|---|---|
| Windows | `%APPDATA%\Backtester\` |
| macOS | `~/Library/Application Support/Backtester/` |
| Linux | `$XDG_DATA_HOME/Backtester/` (default `~/.local/share/Backtester/`) |

The tray menu's **Open data folder** opens this directly.

## Updating
The app shows a banner when a new version is on GitHub. Download and run the new installer — your data is preserved.
```

## Task 9.2: Contributor build guide

**Files:**
- Create: `docs/BUILD.md`

- [ ] **Step 1: Create**

```markdown
# Building Backtester from source

## Prerequisites
- Python 3.11+
- Node 20+
- Platform-specific packaging tools:
  - **Windows:** [NSIS](https://nsis.sourceforge.io/) (`choco install nsis`)
  - **macOS:** Xcode CLT + `hdiutil` (built-in)
  - **Linux:** `appimagetool`, `dpkg-deb`, `imagemagick`

## One-shot
```bash
pip install -r requirements-dev.txt
python scripts/build.py
```
Outputs go to `dist/Backtester/` (raw bundle) and `dist/release/` (installers).

## Dev mode (no packaging)
```bash
# terminal 1
uvicorn api:app --reload

# terminal 2
cd frontend && npm install && npm run dev
```
Vite proxies `/api` → 8000.

## Tests
```bash
python -m pytest tests/ -v
```
```

## Task 9.3: Update the main README

**Files:**
- Modify: `README.md` (or `PROJECT.md` if README absent)

- [ ] **Step 1: Add a top-level "Install" section**

Append/insert a section pointing to `docs/INSTALL.md` for end users and `docs/BUILD.md` for contributors.

- [ ] **Step 2: Commit all docs**

```bash
git add docs/INSTALL.md docs/BUILD.md README.md
git commit -m "docs: install guide for users + build guide for contributors"
```

---

# Self-Review Checklist

Before declaring this plan complete, the executor should verify:

- [ ] `paths.py` is the only module that knows about user-data directories (no other file reads `BACKTESTER_DATA_DIR` or hardcodes `backtester.db`).
- [ ] All 8 frontend files use `''` as the API_BASE default and prefix paths with `/api`.
- [ ] No `@app.get("/...")` or `@app.post("/...")` route remains on a non-`/api` path (search: `grep -n "@app\.\(get\|post\|put\|delete\)" api.py`).
- [ ] `npm run build` then loading `http://localhost:8000/` shows the React app.
- [ ] Launcher quits cleanly: tray Quit → uvicorn stops within 5s → no orphan process → lockfile deleted.
- [ ] Second-launch behaviour: while one launcher is running, starting another opens a browser at the running port and exits 0.
- [ ] `scripts/build.py` runs end-to-end on the dev OS and produces an installer in `dist/release/`.
- [ ] CI workflow file is valid YAML and the job names match the matrix entries.
- [ ] Update banner appears when `_VERSION` < `latest` and is silent when `latest is None`.
- [ ] All existing tests still pass: `python -m pytest tests/ -v`.
