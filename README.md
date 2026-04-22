# Backtester

Beginner-friendly backtesting application for validating algorithmic trading strategies.

- Rule-based strategy builder with AI assistance
- Custom indicator expression tree editor
- Multi-run analytics with equity curves, drawdown, and trade log
- Supports Alpha Vantage, Polygon, Yahoo Finance, Finnhub, IEX Cloud, and CSV uploads

## Install

Pre-built installers for Windows, macOS, and Linux are on the [Releases page](https://github.com/vulfff/simpleBacktester/releases/latest).

See [docs/INSTALL.md](docs/INSTALL.md) for step-by-step instructions including Gatekeeper / SmartScreen notes and where your data is stored.

## Build from source

See [docs/BUILD.md](docs/BUILD.md).

Quick start:
```bash
pip install -r requirements-dev.txt
uvicorn api:app --reload          # backend on :8000
cd frontend && npm install && npm run dev  # frontend on :5173
```

## Tests

```bash
python -m pytest tests/ -v
```
