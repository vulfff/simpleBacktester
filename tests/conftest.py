"""Shared fixtures for backtester tests."""
import sys
import os

# Ensure repo root is on sys.path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import random
import tempfile
from datetime import datetime, timedelta, date
from typing import List

import pytest

# ─── imports from repo root (sys.path already set above) ─────────────────────
from tickdata import TickData
from csvparser import CSVTickDataFeed
from portfolio import Portfolio
from fill_model import FillModel
from actionmanager import ActionManager
from engine import BacktestEngine
from strategy import create_strategy
import strategy_rules  # noqa: F401 — registers rule_set
from indicator_registry import INDICATOR_REGISTRY


# ---------------------------------------------------------------------------
# price_series_factory
# ---------------------------------------------------------------------------

@pytest.fixture
def price_series_factory():
    """
    Returns a factory(pattern, n_bars, **kwargs) -> List[TickData].

    Supported patterns:
      trending_up    – kwargs: start=100, step_pct=0.005
      trending_down  – kwargs: start=100, step_pct=0.005
      flat           – kwargs: price=100
      volatile       – kwargs: sigma=0.03, seed=42
      sawtooth       – kwargs: period=10, step=2.0
      gap_open       – kwargs: seed=42
      crash          – kwargs: crash_bar=100
      squeeze        – kwargs: (none)

    Each bar: high = max(open,close)*(1+spread), low = min(open,close)*(1-spread)
    with spread=0.001. Prices clamped to >= 0.01. Volume = 1000.
    Symbol = "ASSET". timestamp = datetime(2024,1,1) + timedelta(days=i).
    """
    _SPREAD = 0.001

    def _make_tick(i: int, open_: float, close: float, volume: int = 1000) -> TickData:
        open_ = max(0.01, open_)
        close = max(0.01, close)
        high = max(open_, close) * (1 + _SPREAD)
        low = min(open_, close) * (1 - _SPREAD)
        ts = datetime(2024, 1, 1) + timedelta(days=i)
        return TickData(
            name="ASSET",
            close=round(close, 6),
            volume=volume,
            time=ts,
            open=round(open_, 6),
            high=round(high, 6),
            low=round(low, 6),
        )

    def factory(pattern: str, n_bars: int, **kwargs) -> List[TickData]:
        ticks: List[TickData] = []

        if pattern == "trending_up":
            start = kwargs.get("start", 100.0)
            step_pct = kwargs.get("step_pct", 0.005)
            prev_close = start
            for i in range(n_bars):
                open_ = prev_close
                close = prev_close * (1 + step_pct)
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        elif pattern == "trending_down":
            start = kwargs.get("start", 100.0)
            step_pct = kwargs.get("step_pct", 0.005)
            prev_close = start
            for i in range(n_bars):
                open_ = prev_close
                close = prev_close * (1 - step_pct)
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        elif pattern == "flat":
            price = kwargs.get("price", 100.0)
            for i in range(n_bars):
                ts = datetime(2024, 1, 1) + timedelta(days=i)
                ticks.append(TickData(
                    name="ASSET", close=price, open=price,
                    high=price, low=price, volume=1000.0, time=ts
                ))

        elif pattern == "volatile":
            sigma = kwargs.get("sigma", 0.03)
            seed = kwargs.get("seed", 42)
            rng = random.Random(seed)
            prev_close = 100.0
            for i in range(n_bars):
                open_ = prev_close
                close = max(0.01, prev_close * (1 + rng.gauss(0, sigma)))
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        elif pattern == "sawtooth":
            period = kwargs.get("period", 10)
            step = kwargs.get("step", 2.0)
            prev_close = 100.0
            for i in range(n_bars):
                direction = 1 if (i // period) % 2 == 0 else -1
                open_ = prev_close
                close = max(0.01, prev_close + direction * step)
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        elif pattern == "gap_open":
            seed = kwargs.get("seed", 42)
            rng = random.Random(seed)
            prev_close = 100.0
            for i in range(n_bars):
                gap_pct = rng.uniform(0.02, 0.05) * (1 if rng.random() > 0.5 else -1)
                open_ = max(0.01, prev_close * (1 + gap_pct))
                intraday = rng.gauss(0, 0.01)
                close = max(0.01, open_ * (1 + intraday))
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        elif pattern == "crash":
            crash_bar = kwargs.get("crash_bar", 100)
            prev_close = 100.0
            for i in range(n_bars):
                open_ = prev_close
                if i == crash_bar:
                    close = max(0.01, prev_close * 0.6)
                else:
                    close = prev_close * 1.001
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        elif pattern == "squeeze":
            # Low volatility expanding to high: sigma increases linearly
            rng = random.Random(0)
            prev_close = 100.0
            for i in range(n_bars):
                sigma = 0.001 + (i / n_bars) * 0.04
                open_ = prev_close
                close = max(0.01, prev_close * (1 + rng.gauss(0, sigma)))
                ticks.append(_make_tick(i, open_, close))
                prev_close = close

        else:
            raise ValueError(f"Unknown pattern: {pattern!r}")

        return ticks

    return factory


# ---------------------------------------------------------------------------
# csv_feed_from_ticks
# ---------------------------------------------------------------------------

@pytest.fixture
def csv_feed_from_ticks(tmp_path):
    """
    factory(ticks: List[TickData]) -> CSVTickDataFeed

    Writes ticks to a temp CSV in tmp_path and returns a CSVTickDataFeed.
    """
    def factory(ticks: List[TickData]) -> CSVTickDataFeed:
        csv_path = tmp_path / "ticks.csv"
        with open(csv_path, "w", newline="") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for tick in ticks:
                ts = tick.time.strftime("%Y-%m-%d")
                f.write(
                    f"{ts},{tick.open},{tick.high},{tick.low},{tick.close},{tick.volume}\n"
                )
        return CSVTickDataFeed(file_path=str(csv_path))

    return factory


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------

@pytest.fixture
def run_backtest(tmp_path):
    """
    factory(ticks, rule_set_config, **engine_kwargs) -> (BacktestEngine, Portfolio)

    Accepts rule_set_config either as:
      - {"rule_set": {...}}  (full wrapped form)
      - {...}                (raw rule set, will be wrapped automatically)
    """
    def factory(ticks: List[TickData], rule_set_config: dict, **engine_kwargs):
        # Wrap raw rule set config if needed
        if "rule_set" not in rule_set_config:
            cfg = {"rule_set": rule_set_config}
        else:
            cfg = rule_set_config

        csv_path = tmp_path / "run_ticks.csv"
        with open(csv_path, "w", newline="") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for tick in ticks:
                ts = tick.time.strftime("%Y-%m-%d")
                f.write(
                    f"{ts},{tick.open},{tick.high},{tick.low},{tick.close},{tick.volume}\n"
                )

        feed = CSVTickDataFeed(file_path=str(csv_path))
        strategy = create_strategy("rule_set", cfg)
        starting_cash = engine_kwargs.pop("starting_cash", 10_000)
        portfolio = Portfolio(starting_cash=starting_cash, cash=starting_cash)
        engine = BacktestEngine(
            data_feed=feed,
            strategy=strategy,
            action_manager=ActionManager(),
            portfolio=portfolio,
            fill_model=FillModel(seed=42),
            **engine_kwargs,
        )
        engine.run()
        return engine, portfolio

    return factory


# ---------------------------------------------------------------------------
# fresh_registry
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_registry():
    """Clears the INDICATOR_REGISTRY before and after each test."""
    INDICATOR_REGISTRY.load([])
    yield INDICATOR_REGISTRY
    INDICATOR_REGISTRY.load([])


# ---------------------------------------------------------------------------
# test_client  (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_client(tmp_path_factory):
    """
    Spins up a FastAPI TestClient pointed at a temp SQLite database.

    Sets BACKTESTER_DATA_DIR before any api/db import so paths.py resolves
    to the temp dir, then patches db.DB_PATH (if present) and re-runs
    create_tables() against the isolated DB.
    """
    import importlib
    tmp = tmp_path_factory.mktemp("db")
    os.environ["BACKTESTER_DATA_DIR"] = str(tmp)

    # Import (or reload) db so create_tables() runs against the temp path
    import db as _db
    _db.create_tables()

    from api import app
    from fastapi.testclient import TestClient
    import seed_prebuilts

    seed_prebuilts.seed()

    with TestClient(app) as client:
        yield client
