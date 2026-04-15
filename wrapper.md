# Backtester — Application Wrapper / Packaging Spec

Status: **design approved (all sections).** Ready for user sign-off and handoff to implementation planning.
Target: one-click, cross-platform, open-source distribution of the Backtester app.

---

## 1. Goals & Non-Goals

### Goals
- User downloads a single file per OS, double-clicks, and the app runs.
- No Python, Node, uvicorn, or terminal use required from the end user.
- Frontend + backend + DB all launch from one binary.
- Data persists across upgrades in an OS-appropriate location.
- Open-source friendly: buildable by contributors from source, shipped via GitHub Releases.

### Non-Goals (explicit YAGNI)
- Self-updating binaries. We show an update banner; user installs manually.
- Multi-user / server deployment. App is a local single-user tool.
- Mobile. Desktop only.
- In-flight backtest resume across restarts. If app is closed mid-run, run is lost.
- UI-state restoration (open tab, scroll, partial form). Only DB data persists.

---

## 2. Decisions Recap (from brainstorm)

| # | Topic | Decision |
|---|---|---|
| 1 | Target platforms | Windows + macOS + Linux (all three) |
| 2 | App style | Tray icon + default-browser tab (no native window framework) |
| 3 | Data location | OS user-data dir by default, portable mode via marker file |
| 4 | What persists | Only DB-backed data (already handled by `db.py`) |
| 5 | Frontend serving | `npm run build` once, FastAPI serves static bundle (single port, single process) |
| 6 | Packaging tool | PyInstaller |
| 7 | Distribution format | Native installers **and** portable archives per OS; unsigned initially |
| 8 | Update strategy | "Update available" banner from GitHub Releases API; no auto-update |

---

## 3. High-Level Architecture

### Shipped artifacts per release

```
backtester-1.0.0-windows-x64.exe        ← NSIS installer  (primary Windows)
backtester-1.0.0-windows-x64.zip        ← portable Windows
Backtester-1.0.0.dmg                    ← macOS installer
backtester-1.0.0-macos-x64.zip          ← portable macOS
backtester-1.0.0-macos-arm64.zip        ← portable macOS (Apple Silicon)
Backtester-1.0.0-x86_64.AppImage        ← portable Linux
backtester_1.0.0_amd64.deb              ← Debian/Ubuntu install
```

### Bundle contents (produced by PyInstaller)

```
Backtester[.exe|.app|ELF]
├─ Python 3.11 runtime (bundled)
├─ backtester_launcher.py         ← NEW: entry point (PyInstaller target)
├─ api.py, engine.py, db.py, …    ← all existing backend unchanged
├─ frontend_dist/                 ← output of `npm run build`
├─ assets/
│   ├─ icon.ico                   ← Windows tray / exe icon
│   ├─ icon.icns                  ← macOS app icon
│   └─ icon.png                   ← Linux tray icon
└─ seed_data/ (if needed)
```

### Runtime flow

1. User double-clicks installed app / portable binary.
2. `backtester_launcher.py` runs:
   - Resolves user-data directory (portable vs `platformdirs`).
   - Ensures DB exists at that path; runs idempotent migrations.
   - Picks a free loopback port (not hardcoded 8000).
   - Starts FastAPI via `uvicorn.Server` on `127.0.0.1:<port>` in a background thread.
   - Registers `pystray` tray icon with menu.
   - Opens default browser to `http://127.0.0.1:<port>/` via `webbrowser.open`.
3. FastAPI serves:
   - `/api/**` → existing routes (backtest, AI, data, DB)
   - `/` and `/assets/**` → static React bundle from `frontend_dist/`
4. Closing the browser tab does **not** quit. Only tray **Quit** shuts down uvicorn cleanly.

---

## 4. New Code

### 4.1 `backtester_launcher.py` (new file, repo root)

PyInstaller entry point. Responsibilities:

- Parse CLI args: `--portable`, `--dev`, `--port <n>`, `--no-browser`.
- Call `paths.resolve_user_data_dir()`.
- Set env var `BACKTESTER_DATA_DIR` so `db.py` / `api.py` pick it up (see §6.1).
- Pick free port via `socket.socket(); s.bind(("127.0.0.1", 0)); s.getsockname()[1]`.
- Start uvicorn in background thread (non-daemon, so shutdown is controlled).
- Start `pystray.Icon` on main thread (macOS requires tray on main thread).
- Tray menu items:
  - **Open Backtester** → re-open browser tab.
  - **Copy URL** → copy `http://127.0.0.1:<port>` to clipboard.
  - **Open data folder** → `os.startfile` / `subprocess.Popen(["open", ...])` / `xdg-open`.
  - **About** → version string + data-dir path.
  - **Quit** → uvicorn `server.should_exit = True`; join thread; `icon.stop()`.
- SIGINT/SIGTERM handlers for clean shutdown when run from terminal.

### 4.2 `paths.py` (new module)

Centralises path resolution; no other module computes paths.

```python
def resolve_user_data_dir() -> Path:
    # 1. --portable flag or portable.txt next to exe → return <exe_dir>/data
    # 2. Env var BACKTESTER_DATA_DIR set → use it
    # 3. platformdirs.user_data_dir("Backtester", "Backtester")
    ...

def db_path() -> Path: ...
def logs_dir() -> Path: ...
def frontend_dist_dir() -> Path:
    # In PyInstaller bundle:  sys._MEIPASS / "frontend_dist"
    # In dev:                  repo_root / "frontend" / "dist"
    ...
```

Platform defaults:
- Windows: `%APPDATA%\Backtester\`
- macOS: `~/Library/Application Support/Backtester/`
- Linux: `$XDG_DATA_HOME/Backtester/` (fallback `~/.local/share/Backtester/`)

### 4.3 Static-file mount in `api.py`

Appended near the end of `api.py`, after all routers are included:

```python
from fastapi.staticfiles import StaticFiles
from paths import frontend_dist_dir

dist = frontend_dist_dir()
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
```

Important: this mount must come **after** all API routers, or it will shadow `/api/*`. Also requires moving any bare `@app.get("/")` routes under `/api/`.

### 4.4 Update-check endpoint + UI banner

**Backend** — new route in `routes_data.py` or `api.py`:
```
GET /api/version  →  { "current": "1.0.0", "latest": "1.0.1", "url": "https://github.com/.../releases/tag/v1.0.1" }
```
Calls `https://api.github.com/repos/<owner>/backtester/releases/latest`. Cached 1 h in memory. Silent on network failure (returns `latest: null`).

**Frontend** — top-of-App banner in `App.jsx`; dismissible; re-shows on next startup if still outdated.

### 4.5 `GET /api/health` (new endpoint)

Added to `api.py`:

```python
@app.get("/api/health")
def health():
    return {"ok": True}
```

Sole purpose: launcher readiness probe (see §6.1) + CI smoke test target. Distinct from `/api/version` which handles update-check.

### 4.6 Tray icon assets

Store under `assets/` in repo:
- `icon.ico` (Windows, multi-size 16/32/48/256)
- `icon.icns` (macOS)
- `icon.png` (Linux, 256×256)

Source SVG committed so icons can be regenerated.

---

## 5. Changes to Existing Code

Minimal, deliberately. Goal: dev workflow stays identical (`uvicorn api:app --reload` + `npm run dev`), packaged workflow adds one extra layer.

| File | Change |
|---|---|
| `db.py` | Replace hardcoded `"backtester.db"` with `paths.db_path()`. Current code already has `_sanitize_floats()` and works through a single `db_conn` context manager — minimal edit. |
| `api.py` | Add `StaticFiles` mount (see §4.3). Add `/api/health` endpoint (§4.5). Prefix all routers with `/api`. Move any root-path GET handlers under `/api/`. Read `BACKTESTER_DATA_DIR` env var during startup. |
| `seed_prebuilts.py` | Verify it handles the case where the DB path is in a user-data dir that may not exist yet (create parents). |
| `requirements.txt` | Add `platformdirs`, `pystray`, `pillow` (pystray icon rendering). |
| `frontend/vite.config.js` | Confirm `base: './'` so the built bundle works under any mount path. |
| `frontend/src/App.jsx` | Add version banner (§4.4). Change any hardcoded `http://localhost:8000` to relative URLs (`/api/...`) since frontend and API are now same-origin. |
| `.gitignore` | Add `dist/`, `build/`, `*.spec~`, `frontend_dist/` (if copied during build). |

### Route prefix + frontend URL audit

**Decision: prefix all backend routes with `/api`.** Currently routes live at `/db/...`, `/ai/...`, `/data/...`; after this change they live at `/api/db/...`, `/api/ai/...`, `/api/data/...`. Without the prefix, SPA client-side routes like `/strategies` would collide with backend paths.

Mechanically: change `app.include_router(routes_db.router)` → `app.include_router(routes_db.router, prefix="/api")` for all three route modules.

In the frontend, every `fetch()` call must become a **relative** URL — e.g. `fetch("/api/db/runs")` instead of `fetch("http://localhost:8000/db/runs")`. Same-origin means no CORS config is needed and the app works regardless of the port picked at runtime.

---

## 6. Data Flow & Runtime Behaviour

### 6.1 Startup sequence

```
1. User launches Backtester binary
2. backtester_launcher.py runs:
   a. Parse CLI flags  (--portable, --port, --no-browser, --dev)
   b. Resolve data dir  (see 6.2)
   c. Set os.environ["BACKTESTER_DATA_DIR"]  so db.py / api.py pick it up
   d. Pick free loopback port  (socket bind to 127.0.0.1:0, read back)
   e. Acquire lockfile  (see 6.5)
   f. Configure rotating file logger  (<data_dir>/logs/)
   g. Start uvicorn in background thread
   h. Poll GET /api/health until 200  (timeout 10 s → error dialog + exit)
   i. Register pystray icon on main thread  (macOS requires main thread)
   j. webbrowser.open("http://127.0.0.1:<port>/")
   k. Block on tray icon event loop
```

A new `GET /api/health` endpoint (returns `{"ok": true}`) is added solely for the launcher's readiness probe. Reused in CI smoke tests.

### 6.2 Data directory resolution (precedence)

```
1. --portable CLI flag                 → <exe_dir>/data/
2. portable.txt next to exe            → <exe_dir>/data/
3. BACKTESTER_DATA_DIR env var set     → that path  (dev / CI override)
4. platformdirs.user_data_dir(...)     → OS default
```

OS defaults:
- Windows: `%APPDATA%\Backtester\`
- macOS: `~/Library/Application Support/Backtester/`
- Linux: `$XDG_DATA_HOME/Backtester/` (fallback `~/.local/share/Backtester/`)

All app-owned data (DB, logs, future exports) lives under this one dir.

### 6.3 DB path resolution chain

`db.py`'s module-level DB path becomes a lazy getter that reads the env var:

```python
def _db_path() -> str:
    return os.path.join(os.environ.get("BACKTESTER_DATA_DIR", "."), "backtester.db")
```

The existing `db_conn` context manager is unchanged — it just calls `_db_path()` now.

### 6.4 Port selection

Never hardcoded. Bind a socket to `127.0.0.1:0`, read back the OS-assigned port, close the socket, hand the port to uvicorn. Prevents collisions with whatever the user already has running on 8000 (including their own dev backend).

### 6.5 Single-instance (lockfile)

Lockfile at `<data_dir>/backtester.lock` contains the launcher PID and bound port. On startup:

- If no lockfile → acquire, write `{pid, port}`.
- If lockfile exists:
  - PID is still alive → this is a second launch. Open browser at the running instance's port, exit 0.
  - PID is **not** alive (previous crash) → treat as stale, overwrite.

This prevents two launchers fighting over the same DB, while gracefully recovering from prior crashes.

### 6.6 Logging

Rotating file handler, 10 MB × 5 files, at `<data_dir>/logs/backtester.log`. Captures uvicorn access/error logs + application logs. Single artefact for bug reports — end users never see a terminal.

### 6.7 Shutdown sequence

Tray **Quit** fires →

1. `uvicorn.Server.should_exit = True`.
2. Join uvicorn thread (up to 5 s grace).
3. Release lockfile.
4. `icon.stop()` → process exits.

Clean shutdown matters because SQLite WAL files can leave the DB in an odd state if killed mid-write.

---

## 7. Error Handling & Edge Cases

The app runs on strangers' machines with no visible terminal. Every failure either (a) recovers silently, or (b) surfaces a clear native dialog with an actionable next step and the log path. "Fails silently and does nothing" is never acceptable.

### Failure table

| Failure | Behaviour | User sees |
|---|---|---|
| Free-port bind fails 3× | Fatal. Log, show dialog, exit. | "Could not start — no ports available. Log: `<path>`." |
| Uvicorn doesn't hit `/api/health` within 10 s | Fatal. Tear down, show dialog. | Dialog with log path + **Copy log path** button. |
| Uvicorn thread dies after startup | Non-fatal. Tray icon turns red; menu gains **Restart server**. | Red tray icon; browser shows a "server stopped" HTML page. |
| DB migration fails | Fatal, but **DB preserved**. | "Could not upgrade data; your data is safe at `<path>`. Please report this with the log." Never a silent wipe. |
| DB corrupt (SQLite `malformed`) | Fatal. Offer opt-in rename-and-reseed. | "Data file appears corrupt." Confirm → rename `backtester.db` → `backtester.db.corrupt.<ts>`, create fresh DB, run `seed_prebuilts.seed()` (user gets out-of-the-box prebuilt strategies + indicators back). Never silent. |
| Frontend bundle missing from `_MEIPASS` | Fatal — packaging bug reaching production. | "Internal error (packaging). Please file an issue." |
| GitHub `/releases/latest` HTTP error | Silent swallow. No banner. | Nothing. |
| User double-clicks a second time | See §6.5 — second launcher opens browser at running port and exits. | Browser tab opens; no error. |
| No writable data dir (sandbox, locked profile) | Caught at startup. | Dialog with attempted path + "use `--portable`" hint. |
| Antivirus quarantines the unsigned exe (Windows) | Can't handle from inside. | Addressed in README + release notes: "Code is unsigned; SmartScreen warning is normal." |

### Native-dialog mechanism

Dialogs use `tkinter.messagebox` — stdlib, cross-platform, no extra dependency. Every fatal-dialog includes the log-file path so users can attach it to a bug report.

### Explicitly NOT handled

- **Disk full mid-write** — SQLite rolls back the transaction; the frontend sees a normal error toast; the log captures it. No pre-flight space check.
- **Clock skew vs GitHub** (for update check) — we only parse a version string.
- **Network offline at startup** — the app works fully offline except for update-check and live data-provider fetches. No offline dialog.

---

## 8. Build & Release Pipeline

### 8.1 Local build script: `scripts/build.py`

Single Python script that:

1. Validates `python --version` ≥ 3.11 and `node --version`.
2. Runs `cd frontend && npm ci && npm run build`.
3. Copies `frontend/dist` → repo-root `frontend_dist/` (PyInstaller's `--add-data` source).
4. Invokes PyInstaller with `backtester.spec`.
5. Runs platform-specific post-steps:
   - Windows: call `makensis backtester.nsi` to produce the installer.
   - macOS: `hdiutil create` to produce the `.dmg`.
   - Linux: build `.AppImage` via `appimagetool`; build `.deb` via `dpkg-deb`.
6. Outputs all artefacts to `dist/release/`.

### 8.2 `backtester.spec` (PyInstaller)

- `--onedir` (not `--onefile`) for Windows/Linux — faster startup, smaller updates, simpler debugging.
- `--windowed` / `--noconsole` so no terminal pops up.
- `--add-data "frontend_dist:frontend_dist"`.
- `--icon assets/icon.ico` (resp. `.icns`).
- Hidden imports for uvicorn: `uvicorn.logging`, `uvicorn.loops`, `uvicorn.loops.auto`, `uvicorn.protocols`, `uvicorn.protocols.http`, `uvicorn.protocols.http.auto`, `uvicorn.lifespan`, `uvicorn.lifespan.on`.
- PyInstaller hook for `pydantic` (usually auto-detected in recent versions).

### 8.3 GitHub Actions workflow `.github/workflows/release.yml`

Trigger: git tag `v*.*.*`. Matrix:

```yaml
matrix:
  include:
    - os: windows-latest, arch: x64
    - os: macos-13,       arch: x64          # Intel
    - os: macos-14,       arch: arm64        # Apple Silicon
    - os: ubuntu-22.04,   arch: x64
```

Per job: checkout → set up Python/Node → `python scripts/build.py` → upload artefacts. Final step creates a GitHub Release with all artefacts attached and an auto-generated changelog from commit messages since the previous tag.

### 8.4 Reproducible-build note

All dependencies pinned via `requirements.txt` + `frontend/package-lock.json`. Node and Python versions pinned in CI config. This makes the release verifiable by contributors and removes the "works on my machine" class of bugs.

---

## 9. Testing Strategy

### 9.1 Unit tests (existing `tests/` folder)

- Unchanged — existing metrics/fill/engine/csv tests keep running.
- Add `tests/test_paths.py`:
  - portable-mode detection (via `portable.txt` fixture)
  - `BACKTESTER_DATA_DIR` env var override
  - `platformdirs` fallback per OS (mock `sys.platform`)

### 9.2 Launcher integration test

`tests/test_launcher.py`:
- Spawn `backtester_launcher.py --no-browser --port 0` as subprocess with `BACKTESTER_DATA_DIR=<tmp>` in env.
- Poll `GET /api/health` until 200 (10 s timeout).
- Hit `GET /` and assert HTML contains the React root `<div id="root">`.
- Send SIGTERM; assert process exits cleanly within 5 s.

### 9.3 Packaged-binary smoke test (in CI)

After PyInstaller finishes in each matrix job:
- Launch the binary with `--no-browser --port 0` and `BACKTESTER_DATA_DIR=<tmp>` in env.
- Same `/api/health` + `/` checks as above.
- Assert the binary exits cleanly on SIGTERM.

This catches packaging bugs (missing hidden imports, wrong data-dir resolution in `_MEIPASS`) that unit tests can't.

### 9.4 Manual test matrix (release checklist)

For each OS, verify:
- First-run: app starts, browser opens, DB created in correct location.
- Second run: data persists, no duplicate seed.
- Portable mode: `portable.txt` creates `data/` next to exe, app uses it.
- Tray menu: all items work.
- Update banner: shows when `latest > current`, hides when equal, silent on network error.
- Uninstaller (Windows MSI / `.deb`): removes app, leaves user data intact.

---

## 10. File/Module Inventory

### New files
```
backtester_launcher.py             entry point for PyInstaller
paths.py                           path resolution (single source of truth)
backtester.spec                    PyInstaller config
scripts/build.py                   local + CI build orchestration
scripts/backtester.nsi             Windows NSIS installer script
scripts/backtester.desktop         Linux .desktop entry for .deb
assets/icon.svg                    source icon
assets/icon.ico                    Windows icon (generated)
assets/icon.icns                   macOS icon (generated)
assets/icon.png                    Linux tray icon (generated)
.github/workflows/release.yml      release pipeline
tests/test_paths.py
tests/test_launcher.py
```

### Modified files
```
api.py            StaticFiles mount; route prefix /api; env var read
db.py             lazy DB path via paths.py
seed_prebuilts.py ensure parent dirs exist
requirements.txt  + platformdirs, pystray, pillow
frontend/vite.config.js   base: './'
frontend/src/App.jsx       version banner + relative URLs
frontend/src/**            audit all fetch() calls → relative URLs
.gitignore        dist/, build/, frontend_dist/
```

---

## 11. Build Sequence (implementation order)

1. **Path layer** — add `paths.py`, migrate `db.py`, no user-visible change.
2. **Route prefix** — add `/api` prefix to all backend routers; update frontend fetches to relative URLs. Verify dev mode still works end-to-end.
3. **Static mount** — add `StaticFiles` mount in `api.py`. Run `npm run build`, point FastAPI at `frontend/dist/`, verify React app loads at `http://localhost:8000/`. Dev workflow (Vite on 5173) unchanged.
4. **Launcher** — write `backtester_launcher.py` + `paths` integration; run from source (`python backtester_launcher.py`) and verify tray + browser + shutdown behaviour.
5. **PyInstaller** — create `.spec`, produce a local binary, smoke-test.
6. **Installers** — NSIS (Windows) → `.dmg` (macOS) → `.AppImage` + `.deb` (Linux).
7. **CI pipeline** — GitHub Actions matrix release workflow.
8. **Update banner** — `/api/version` endpoint + frontend banner.
9. **Documentation** — README quickstart, contributor build guide, user install guide.

Each step is independently shippable and test-verifiable.

---

## 12. Open Questions / Future Work

- **Code signing** — deferred. Document SmartScreen / Gatekeeper workaround in README. Revisit after first few releases.
- **Homebrew cask** (macOS) and **winget / scoop** manifests — publish after first stable release, not in v1.0.
- **AppImage desktop integration** — users may want `appimaged` or manual `.desktop` install; document but don't automate for v1.0.
- **Telemetry** — none. Not planned. If ever added, must be opt-in and documented.
- **Self-update** — reconsider if distribution pain warrants it; for now, GitHub Releases + banner is enough.
