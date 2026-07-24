# Backtester

Beginner-friendly desktop app for building and validating algorithmic trading strategies — no code required. FastAPI + SQLite backend, React 19 + Vite frontend, shipped as a one-click installer.

## About this project

This tool was developed as part of the Bachelor's thesis **"Design and Comparative Evaluation of a No-Code Approach to Backtesting Algorithmic Trading Strategies"** by Oliver-Markus Vulf (University of Tartu, Institute of Computer Science, 2026).

The thesis analysed six existing backtesting tools (backtrader, ZipLine, QuantConnect, TradingView, VectorBT, Jesse), found that none offer an integrated no-code approach to strategy building, and designed this tool to close that gap. In a comparative user evaluation against Jesse (the strongest existing baseline), the no-code builder raised the end-to-end test completion rate from 0% to 20%, and enabling the integrated AI-assistance raised it to 88.9% — a statistically significant improvement (McNemar exact test, p=0.031), with system usability scores improving significantly at every step (Wilcoxon signed-rank, Holm-corrected).

## Features

- **Rule-based strategy builder** — compose entry/exit rules visually from indicators, comparisons, and logic operators, or describe the strategy in plain English and let the AI chat build it for you
- **Custom indicators** — expression-tree editor (or AI chat) for defining your own technical indicators on top of the built-in registry
- **Realistic execution** — next-bar-open fills with no lookahead, liquidity-aware fill model with price impact and stochastic slippage
- **Analytics dashboard** — run history, equity curves, drawdown, trade log, multi-run comparison
- **Monte Carlo analysis** — bootstrap resampling of trade returns with a fan chart of possible equity paths and risk-of-ruin estimate
- **AI analysts** — chat about any strategy, indicator, or finished run to understand what happened and why
- **Data providers** — Alpha Vantage, Polygon, Yahoo Finance, Finnhub, or your own CSV uploads; API keys stored securely in the OS keyring, never in config files

## Install

Pre-built installers for Windows, macOS, and Linux are on the [Releases page](https://github.com/vulfff/simpleBacktester/releases/latest).

See [docs/INSTALL.md](docs/INSTALL.md) for step-by-step instructions, Gatekeeper / SmartScreen notes, and where your data is stored.

## Run from source

```bash
# Backend (repo root) — Python 3.10+
pip install -r requirements-dev.txt
uvicorn api:app --reload              # http://localhost:8000

# Frontend (separate terminal) — Node 18+
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

Interactive API docs at `http://localhost:8000/docs`.

## Tests

```bash
python -m pytest tests/ -v
```

## Building installers

See [docs/BUILD.md](docs/BUILD.md), or:

```bash
python scripts/build.py
```

## Documentation

- [PROJECT.md](PROJECT.md) — full architecture, module reference, API endpoints, database schema
- [docs/INSTALL.md](docs/INSTALL.md) — end-user install guide
- [docs/BUILD.md](docs/BUILD.md) — building from source / packaging
