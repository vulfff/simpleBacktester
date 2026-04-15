"""Tests for fill_model.py — realistic fill simulation."""
import pytest
from fill_model import FillModel
from events import OrderEvent
from tickdata import TickData


def _tick(close=100.0, open_=100.0, volume=10_000):
    return TickData(name="TEST", close=close, open=open_, volume=volume, high=close, low=close)


def _order(action="buy", qty=100):
    return OrderEvent(symbol="TEST", action=action, quantity=qty)


class TestFillModel:
    def test_basic_fill(self):
        fm = FillModel(seed=42)
        filled, price, unfilled, warns = fm.compute_fill(_order(), _tick(), use_open=True)
        assert filled == 100
        assert unfilled == 0
        assert price > 0

    def test_buy_pays_more_than_base(self):
        """Buy fills should have adverse price impact (pay more)."""
        fm = FillModel(seed=42, slippage_sigma=0.0)
        _, price, _, _ = fm.compute_fill(_order("buy", 100), _tick(close=100, open_=100, volume=10_000), use_open=True)
        assert price >= 100.0

    def test_sell_receives_less_than_base(self):
        """Sell fills should have adverse price impact (receive less)."""
        fm = FillModel(seed=42, slippage_sigma=0.0)
        _, price, _, _ = fm.compute_fill(_order("sell", 100), _tick(close=100, open_=100, volume=10_000), use_open=True)
        assert price <= 100.0

    def test_liquidity_limit(self):
        """Order exceeding available liquidity should be partially filled."""
        fm = FillModel(participation_rate=0.25, seed=42)
        # Volume=100, participation=0.25 → max fill = 25
        filled, _, unfilled, _ = fm.compute_fill(_order("buy", 50), _tick(volume=100), use_open=True)
        assert filled == 25
        assert unfilled == 25

    def test_zero_volume_fallback(self):
        """Zero volume should fill at base price with a warning."""
        fm = FillModel(seed=42)
        filled, price, unfilled, warns = fm.compute_fill(_order("buy", 10), _tick(volume=0), use_open=True)
        assert filled == 10
        assert unfilled == 0
        assert len(warns) == 1
        assert "volume is 0" in warns[0].lower()

    def test_use_open_price(self):
        """use_open=True should use tick.open as base price."""
        fm = FillModel(seed=42, slippage_sigma=0.0, price_impact_factor=0.0)
        _, price, _, _ = fm.compute_fill(_order("buy", 1), _tick(close=100, open_=105, volume=10_000), use_open=True)
        assert price == pytest.approx(105.0, abs=0.01)

    def test_deterministic_with_seed(self):
        """Same seed should produce identical results."""
        tick = _tick()
        order = _order()
        r1 = FillModel(seed=123).compute_fill(order, tick, use_open=True)
        r2 = FillModel(seed=123).compute_fill(order, tick, use_open=True)
        assert r1[0] == r2[0]
        assert r1[1] == pytest.approx(r2[1])
