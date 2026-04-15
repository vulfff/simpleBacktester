"""Tests for engine.py — backtest engine integration tests."""
import os
import tempfile
import pytest

from actionmanager import ActionManager
from csvparser import CSVTickDataFeed
from engine import BacktestEngine
from fill_model import FillModel
from portfolio import Portfolio
from strategy import create_strategy
import strategy_rules  # noqa: F401 — registers rule_set


def _csv_path(rows: list[str]) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    f.write("\n".join(rows))
    f.close()
    return f.name


def _run(csv_rows, rule_set_config, starting_cash=10_000, sizing_mode="fixed", **kwargs):
    path = _csv_path(csv_rows)
    try:
        feed = CSVTickDataFeed(file_path=path)
        strategy = create_strategy("rule_set", {"rule_set": rule_set_config})
        portfolio = Portfolio(starting_cash=starting_cash, cash=starting_cash)
        engine = BacktestEngine(
            data_feed=feed, strategy=strategy, action_manager=ActionManager(),
            portfolio=portfolio, fill_model=FillModel(seed=42),
            sizing_mode=sizing_mode, **kwargs,
        )
        engine.run()
        return engine, portfolio
    finally:
        os.remove(path)


# Simple SMA cross strategy config
_SMA_CROSS = {
    "name": "Test SMA Cross",
    "rules": [
        {
            "name": "Buy", "role": "entry_long",
            "conditions": [{"left": {"type": "sma", "period": 3, "field": "close"},
                            "operator": "cross_above",
                            "right": {"type": "sma", "period": 5, "field": "close"},
                            "combiner": "and"}],
            "timing": "on_change", "quantity": 10,
        },
        {
            "name": "Sell", "role": "exit_long",
            "conditions": [{"left": {"type": "sma", "period": 3, "field": "close"},
                            "operator": "cross_below",
                            "right": {"type": "sma", "period": 5, "field": "close"},
                            "combiner": "and"}],
            "timing": "on_change", "quantity": 10,
        },
    ],
}

# Steadily rising prices to trigger a buy
_RISING_CSV = [
    "timestamp,open,high,low,close,volume",
    "2024-01-01,10,11,9,10,1000",
    "2024-01-02,10,11,9,10,1000",
    "2024-01-03,10,11,9,10,1000",
    "2024-01-04,10,11,9,10,1000",
    "2024-01-05,10,11,9,10,1000",
    # Now prices rise — SMA(3) should cross above SMA(5)
    "2024-01-06,11,12,10,12,1000",
    "2024-01-07,12,13,11,13,1000",
    "2024-01-08,13,14,12,14,1000",
    "2024-01-09,14,15,13,15,1000",
    "2024-01-10,15,16,14,16,1000",
    # Then prices drop — SMA(3) should cross below SMA(5)
    "2024-01-11,12,13,8,9,1000",
    "2024-01-12,9,10,7,8,1000",
    "2024-01-13,8,9,6,7,1000",
    "2024-01-14,7,8,5,6,1000",
    "2024-01-15,6,7,4,5,1000",
]


class TestBacktestEngine:
    def test_equity_curve_generated(self):
        engine, _ = _run(_RISING_CSV, _SMA_CROSS)
        # Should have one equity point per bar (minus warmup skipped by engine)
        assert len(engine._equity_curve) > 0
        assert "t" in engine._equity_curve[0]
        assert "equity" in engine._equity_curve[0]

    def test_trades_execute(self):
        engine, portfolio = _run(_RISING_CSV, _SMA_CROSS)
        # With rising then falling prices, we expect at least a buy and sell
        assert engine._fill_count >= 2
        assert len(portfolio.trade_log) >= 2

    def test_tick_count(self):
        engine, _ = _run(_RISING_CSV, _SMA_CROSS)
        assert engine._tick_count == 15

    def test_all_in_sizing(self):
        engine, portfolio = _run(_RISING_CSV, _SMA_CROSS, starting_cash=10_000, sizing_mode="all_in")
        # In all_in mode, the engine should size to full cash
        if portfolio.trade_log:
            first_buy = next((t for t in portfolio.trade_log if t.action == "buy"), None)
            if first_buy:
                # qty should be > 10 (the fixed quantity) since we have 10k cash
                assert first_buy.quantity > 10

    def test_signal_log_populated(self):
        engine, _ = _run(_RISING_CSV, _SMA_CROSS)
        # At least some signals should have fired
        assert len(engine._signal_log) > 0


class TestEngineWarnings:
    def test_zero_tick_warning(self):
        csv = [
            "timestamp,close",
            # No valid rows — empty feed
        ]
        engine, _ = _run(["timestamp,close,volume"], {"name": "empty", "rules": []})
        assert engine._tick_count == 0
