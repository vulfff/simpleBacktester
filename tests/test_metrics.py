"""Tests for metrics.py — compute_metrics and round-trip matching."""
import pytest
from dataclasses import dataclass
from metrics import compute_metrics, match_round_trips_from_dicts


# Minimal Trade stand-in for compute_metrics
@dataclass
class FakeTrade:
    action: str
    symbol: str
    quantity: float
    price: float
    time: str = ""
    commission: float = 0.0


def _equity_curve(values, starting_cash=10_000):
    """Build a simple equity curve from a list of total equity values."""
    return [
        {"t": f"2024-01-{i+1:02d} 00:00:00", "equity": v, "cash": starting_cash, "asset_value": v - starting_cash}
        for i, v in enumerate(values)
    ]


class TestComputeMetrics:
    def test_empty_curve(self):
        m = compute_metrics([], [], 10_000)
        assert m["total_return_pct"] == 0.0
        assert m["total_trades"] == 0

    def test_total_return(self):
        curve = _equity_curve([10_000, 10_500, 11_000])
        m = compute_metrics(curve, [], 10_000)
        assert m["total_return_pct"] == pytest.approx(10.0, abs=0.01)

    def test_negative_return(self):
        curve = _equity_curve([10_000, 9_500, 9_000])
        m = compute_metrics(curve, [], 10_000)
        assert m["total_return_pct"] == pytest.approx(-10.0, abs=0.01)

    def test_max_drawdown_active_only(self):
        # asset_value=0 means no position — drawdown should not track
        curve = [
            {"t": "2024-01-01", "equity": 10_000, "cash": 10_000, "asset_value": 0},
            {"t": "2024-01-02", "equity": 10_500, "cash": 0, "asset_value": 10_500},
            {"t": "2024-01-03", "equity": 9_500, "cash": 0, "asset_value": 9_500},
            {"t": "2024-01-04", "equity": 10_000, "cash": 10_000, "asset_value": 0},
        ]
        m = compute_metrics(curve, [], 10_000)
        # Drawdown should be ~ -9.52% (9500/10500 - 1)
        assert m["max_drawdown_pct"] < 0
        assert m["max_drawdown_pct"] == pytest.approx(-9.52, abs=0.5)

    def test_round_trip_count(self):
        trades = [
            FakeTrade("buy", "AAPL", 10, 100.0, "2024-01-01"),
            FakeTrade("sell", "AAPL", 10, 110.0, "2024-01-05"),
            FakeTrade("buy", "AAPL", 5, 105.0, "2024-01-06"),
            FakeTrade("sell", "AAPL", 5, 115.0, "2024-01-10"),
        ]
        curve = _equity_curve([10_000] * 10)
        m = compute_metrics(curve, trades, 10_000)
        assert m["total_trades"] == 2

    def test_win_rate(self):
        trades = [
            FakeTrade("buy", "AAPL", 10, 100.0, "2024-01-01"),
            FakeTrade("sell", "AAPL", 10, 110.0, "2024-01-02"),  # win
            FakeTrade("buy", "AAPL", 10, 110.0, "2024-01-03"),
            FakeTrade("sell", "AAPL", 10, 105.0, "2024-01-04"),  # loss
        ]
        curve = _equity_curve([10_000] * 4)
        m = compute_metrics(curve, trades, 10_000)
        assert m["win_rate_pct"] == pytest.approx(50.0)


class TestMatchRoundTripsFromDicts:
    def test_basic_long(self):
        fills = [
            {"t": "2024-01-01", "action": "buy", "symbol": "AAPL", "qty": 10, "price": 100},
            {"t": "2024-01-05", "action": "sell", "symbol": "AAPL", "qty": 10, "price": 110},
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1
        assert trips[0]["side"] == "long"
        assert trips[0]["pnl"] == pytest.approx(100.0)
        assert trips[0]["pnl_pct"] == pytest.approx(10.0)

    def test_basic_short(self):
        fills = [
            {"t": "2024-01-01", "action": "short", "symbol": "AAPL", "qty": 10, "price": 110},
            {"t": "2024-01-05", "action": "cover", "symbol": "AAPL", "qty": 10, "price": 100},
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1
        assert trips[0]["side"] == "short"
        assert trips[0]["pnl"] == pytest.approx(100.0)

    def test_partial_fill(self):
        fills = [
            {"t": "2024-01-01", "action": "buy", "symbol": "X", "qty": 20, "price": 50},
            {"t": "2024-01-02", "action": "sell", "symbol": "X", "qty": 10, "price": 60},
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1
        assert trips[0]["qty"] == 10
        assert trips[0]["pnl"] == pytest.approx(100.0)

    def test_multiple_symbols(self):
        fills = [
            {"t": "1", "action": "buy", "symbol": "A", "qty": 5, "price": 10},
            {"t": "2", "action": "buy", "symbol": "B", "qty": 5, "price": 20},
            {"t": "3", "action": "sell", "symbol": "A", "qty": 5, "price": 15},
            {"t": "4", "action": "sell", "symbol": "B", "qty": 5, "price": 18},
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 2
        a_trip = next(t for t in trips if t["symbol"] == "A")
        b_trip = next(t for t in trips if t["symbol"] == "B")
        assert a_trip["pnl"] == pytest.approx(25.0)
        assert b_trip["pnl"] == pytest.approx(-10.0)

    def test_empty_fills(self):
        assert match_round_trips_from_dicts([]) == []
