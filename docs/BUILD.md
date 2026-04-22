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
