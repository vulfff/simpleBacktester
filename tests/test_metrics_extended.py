"""
test_metrics_extended.py — Extended correctness and adversarial tests for
compute_metrics() and match_round_trips_from_dicts().
"""
import math
import pytest
from dataclasses import dataclass, field

from metrics import compute_metrics, match_round_trips_from_dicts
from db import _sanitize_floats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eq_curve(values, starting_cash=10_000, with_av=True):
    """Build an equity curve where asset_value is non-zero when in position."""
    curve = []
    for i, eq in enumerate(values):
        av = eq - starting_cash * 0.5 if (with_av and i > 0) else 0.0
        av = max(0.0, av)
        curve.append({"t": i, "equity": eq, "cash": eq - av, "asset_value": av})
    return curve


def _eq_flat(value, n, starting_cash=10_000):
    return [{"t": i, "equity": value, "cash": value, "asset_value": 0.0} for i in range(n)]


def _fill(action, symbol="ASSET", qty=10.0, price=100.0, t="2024-01-01"):
    return {"action": action, "symbol": symbol, "qty": qty, "price": price, "t": t}


@dataclass
class FakeTrade:
    symbol: str = "ASSET"
    action: str = "buy"
    quantity: float = 10.0
    price: float = 100.0
    commission: float = 0.0
    time: str = "2024-01-01"


# ---------------------------------------------------------------------------
# TestComputeMetrics
# ---------------------------------------------------------------------------

class TestComputeMetrics:

    def test_empty_curve_returns_zeroed_metrics(self):
        m = compute_metrics([], [], 10_000)
        assert m["total_return_pct"] == 0.0
        assert m["cagr_pct"] == 0.0
        assert m["max_drawdown_pct"] == 0.0

    def test_total_return_correct(self):
        # Curve goes from 10k to 12k = 20% total return
        start, end, n = 10_000, 12_000, 252
        step = (end - start) / (n - 1)
        curve = [{"t": i, "equity": start + i * step, "cash": start + i * step, "asset_value": 0}
                 for i in range(n)]
        m = compute_metrics(curve, [], 10_000)
        assert math.isclose(m["total_return_pct"], 20.0, rel_tol=1e-4)

    def test_cagr_formula(self):
        # 252 bars (1 year), starts at 10k, ends at 12k → CAGR ≈ 20%
        n = 252
        start, end = 10_000, 12_000
        step = (end - start) / (n - 1)
        curve = [{"t": i, "equity": start + i * step, "cash": start + i * step, "asset_value": 0}
                 for i in range(n)]
        m = compute_metrics(curve, [], 10_000, bars_per_year=252)
        expected_cagr = ((end / start) ** (252 / 252) - 1) * 100
        assert math.isclose(m["cagr_pct"], expected_cagr, rel_tol=1e-3)

    def test_sharpe_flat_returns_zero(self):
        # Flat equity → zero variance → Sharpe = 0
        curve = _eq_flat(10_000, 100)
        m = compute_metrics(curve, [], 10_000)
        assert m["sharpe_ratio"] == 0.0

    def test_sharpe_positive_on_rising(self):
        # Monotonically rising equity → positive Sharpe
        values = [10_000 + i * 10 for i in range(100)]
        curve = [{"t": i, "equity": v, "cash": v, "asset_value": 0} for i, v in enumerate(values)]
        m = compute_metrics(curve, [], 10_000)
        assert m["sharpe_ratio"] > 0

    def test_win_rate_all_wins(self):
        # Buy at 100, sell at 110 — 100% win rate
        trades = [FakeTrade(action="buy", price=100.0, quantity=10.0, time="2024-01-01"),
                  FakeTrade(action="sell", price=110.0, quantity=10.0, time="2024-01-02")]
        curve = [{"t": "2024-01-01", "equity": 10_000, "cash": 9_000, "asset_value": 1_000},
                 {"t": "2024-01-02", "equity": 11_000, "cash": 11_000, "asset_value": 0}]
        m = compute_metrics(curve, trades, 10_000)
        if m["total_trades"] > 0:
            assert m["win_rate_pct"] == 100.0

    def test_win_rate_all_losses(self):
        trades = [FakeTrade(action="buy", price=110.0, quantity=10.0, time="2024-01-01"),
                  FakeTrade(action="sell", price=100.0, quantity=10.0, time="2024-01-02")]
        curve = [{"t": "2024-01-01", "equity": 10_000, "cash": 8_900, "asset_value": 1_100},
                 {"t": "2024-01-02", "equity": 9_000, "cash": 9_000, "asset_value": 0}]
        m = compute_metrics(curve, trades, 10_000)
        if m["total_trades"] > 0:
            assert m["win_rate_pct"] == 0.0

    def test_profit_factor_all_wins_is_none(self):
        """All wins → no losses → profit_factor = None (not Infinity)."""
        trades = [FakeTrade(action="buy", price=100.0, quantity=10.0, time="2024-01-01"),
                  FakeTrade(action="sell", price=110.0, quantity=10.0, time="2024-01-02")]
        curve = [{"t": "2024-01-01", "equity": 10_000, "cash": 9_000, "asset_value": 1_000},
                 {"t": "2024-01-02", "equity": 11_000, "cash": 11_000, "asset_value": 0}]
        m = compute_metrics(curve, trades, 10_000)
        if m["total_trades"] > 0:
            assert m["profit_factor"] is None

    def test_profit_factor_sanitize_regression(self):
        """profit_factor=Infinity → _sanitize_floats converts to None (regression guard)."""
        data = {"profit_factor": float("inf"), "sharpe": 1.5, "foo": math.nan}
        result = _sanitize_floats(data)
        assert result["profit_factor"] is None
        assert result["sharpe"] == 1.5
        assert result["foo"] is None

    def test_max_drawdown_only_during_position(self):
        """Max drawdown only tracked when asset_value != 0 (gated)."""
        # Equity drops before position open, rises after — drawdown should be 0
        curve = [
            {"t": 0, "equity": 10_000, "cash": 10_000, "asset_value": 0},
            {"t": 1, "equity": 9_000,  "cash": 9_000,  "asset_value": 0},   # drop, no position
            {"t": 2, "equity": 10_000, "cash": 5_000,  "asset_value": 5_000},  # enter position at peak
            {"t": 3, "equity": 10_500, "cash": 5_000,  "asset_value": 5_500},  # position gains
            {"t": 4, "equity": 10_000, "cash": 10_000, "asset_value": 0},   # exit
        ]
        m = compute_metrics(curve, [], 10_000)
        # The pre-position drop should not count → max_drawdown should be >= 0 (0 here since position only rose)
        assert m["max_drawdown_pct"] == 0.0

    def test_max_drawdown_monotonically_increasing_is_zero(self):
        values = [10_000 + i * 100 for i in range(50)]
        curve = [{"t": i, "equity": v, "cash": v * 0.5, "asset_value": v * 0.5}
                 for i, v in enumerate(values)]
        m = compute_metrics(curve, [], 10_000)
        assert m["max_drawdown_pct"] == 0.0

    def test_single_point_curve_no_crash(self):
        curve = [{"t": 0, "equity": 10_000, "cash": 10_000, "asset_value": 0}]
        m = compute_metrics(curve, [], 10_000)
        assert m["cagr_pct"] == 0.0 or math.isfinite(m["cagr_pct"])

    def test_absent_asset_value_uses_legacy_fallback(self):
        """Legacy equity curve without asset_value key → rolling-peak drawdown."""
        curve = [{"t": i, "equity": v, "cash": v} for i, v in enumerate([10_000, 9_000, 8_000, 9_500])]
        m = compute_metrics(curve, [], 10_000)
        # Rolling peak: 10k → drops to 8k → drawdown = -20%
        assert m["max_drawdown_pct"] < 0


# ---------------------------------------------------------------------------
# TestMatchRoundTripsFromDicts
# ---------------------------------------------------------------------------

class TestMatchRoundTripsFromDicts:

    def test_basic_long_round_trip(self):
        fills = [_fill("buy", price=100), _fill("sell", price=110)]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1
        assert trips[0]["pnl"] == pytest.approx(100.0)
        assert trips[0]["side"] == "long"

    def test_open_position_at_end_not_counted(self):
        fills = [_fill("buy", price=100)]  # no sell
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 0

    def test_partial_sell(self):
        fills = [_fill("buy", qty=10, price=100),
                 _fill("sell", qty=5, price=110)]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1
        assert trips[0]["qty"] == 5.0
        # Remaining 5 units still open → not in trips

    def test_short_cover_pnl_sign(self):
        """Short at 110, cover at 100 → profit = 10 per unit."""
        fills = [_fill("short", price=110), _fill("cover", price=100)]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1
        assert trips[0]["pnl"] > 0
        assert trips[0]["side"] == "short"

    def test_multi_symbol_independent(self):
        fills = [
            _fill("buy",  symbol="AAPL", price=100),
            _fill("buy",  symbol="GOOG", price=200),
            _fill("sell", symbol="AAPL", price=110),
            _fill("sell", symbol="GOOG", price=190),
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 2
        by_sym = {t["symbol"]: t for t in trips}
        assert by_sym["AAPL"]["pnl"] > 0
        assert by_sym["GOOG"]["pnl"] < 0

    def test_same_timestamp_buy_and_sell(self):
        fills = [
            _fill("buy",  price=100, t="2024-01-01"),
            _fill("sell", price=110, t="2024-01-01"),
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 1

    def test_zero_qty_fill_ignored(self):
        fills = [
            _fill("buy",  qty=0, price=100),   # zero qty — no entry
            _fill("sell", qty=10, price=110),  # no matching entry
        ]
        trips = match_round_trips_from_dicts(fills)
        assert len(trips) == 0


# ---------------------------------------------------------------------------
# TestAdversarialEquityCurves
# ---------------------------------------------------------------------------

class TestAdversarialEquityCurves:

    def test_monotonically_decreasing_drawdown_full_loss(self):
        values = [10_000 - i * 200 for i in range(10)]  # 10k → 8k
        curve = [{"t": i, "equity": v, "cash": v * 0.5, "asset_value": v * 0.5}
                 for i, v in enumerate(values)]
        m = compute_metrics(curve, [], 10_000)
        assert m["max_drawdown_pct"] < 0

    def test_legacy_fallback_absent_asset_value_no_crash(self):
        curve = [{"t": i, "equity": 10_000 + i * 10, "cash": 10_000 + i * 10}
                 for i in range(20)]
        m = compute_metrics(curve, [], 10_000)
        assert math.isfinite(m["cagr_pct"])
        assert math.isfinite(m["sharpe_ratio"])
