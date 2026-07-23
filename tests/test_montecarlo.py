import pytest

from montecarlo import bar_returns, run_monte_carlo, trade_returns


def _trip(pnl_pct):
    return {"symbol": "TST", "side": "long", "entry_time": "t0", "exit_time": "t1",
            "entry_price": 100.0, "exit_price": 100.0 * (1 + pnl_pct / 100), "qty": 1.0,
            "pnl": pnl_pct, "pnl_pct": pnl_pct}


def _curve(equities):
    return [{"t": f"2024-01-{i+1:02d}", "equity": e, "cash": e, "asset_value": 0.0}
            for i, e in enumerate(equities)]


def test_trade_returns_converts_pct_to_fractions():
    assert trade_returns([_trip(2.5), _trip(-1.0)]) == [0.025, -0.01]


def test_bar_returns_from_equity_curve():
    out = bar_returns(_curve([100.0, 110.0, 99.0]))
    assert out == pytest.approx([0.1, -0.1])


def test_bar_returns_skips_zero_equity():
    out = bar_returns(_curve([100.0, 0.0, 50.0]))
    assert out == pytest.approx([-1.0])  # 100 -> 0 recorded; 0 -> 50 skipped (div by zero)


def test_rejects_too_few_samples():
    with pytest.raises(ValueError):
        run_monte_carlo([0.01] * 4)


def test_seed_determinism():
    returns = [0.05, -0.03, 0.02, 0.01, -0.02, 0.04]
    a = run_monte_carlo(returns, n_sims=200, seed=42)
    b = run_monte_carlo(returns, n_sims=200, seed=42)
    c = run_monte_carlo(returns, n_sims=200, seed=7)
    assert a == b
    assert a != c


def test_constant_returns_known_values():
    # Every resample of a constant sequence is identical.
    result = run_monte_carlo([0.01] * 50, n_sims=100, seed=1)
    expected_final = (1.01 ** 50 - 1) * 100
    fr = result["final_return_pct"]
    for key in ("p5", "p25", "p50", "p75", "p95"):
        assert fr[key] == pytest.approx(expected_final)
        assert result["max_drawdown_pct"][key] == pytest.approx(0.0)
    assert result["prob_loss_pct"] == 0.0
    assert result["n_sims"] == 100
    assert result["n_steps"] == 50


def test_bands_shape_and_ordering():
    returns = [0.05, -0.04, 0.03, -0.02, 0.01, 0.06, -0.05, 0.02]
    result = run_monte_carlo(returns, n_sims=300, seed=3)
    bands = result["bands"]
    assert bands[0]["step"] == 0
    assert bands[0]["p50"] == pytest.approx(1.0)
    assert bands[-1]["step"] == len(returns)
    steps = [b["step"] for b in bands]
    assert steps == sorted(steps)
    for b in bands:
        assert b["p5"] <= b["p25"] <= b["p50"] <= b["p75"] <= b["p95"]


def test_bands_capped_at_200_points():
    returns = [0.001] * 1000
    result = run_monte_carlo(returns, n_sims=10, seed=1)
    assert len(result["bands"]) <= 201  # 200 sampled steps + step 0
    assert result["bands"][-1]["step"] == 1000


def test_n_sims_clamped():
    result = run_monte_carlo([0.01] * 10, n_sims=99999, seed=1)
    assert result["n_sims"] == 10000


def test_all_losing_returns_prob_loss_100():
    result = run_monte_carlo([-0.01, -0.02, -0.03, -0.01, -0.02], n_sims=50, seed=1)
    assert result["prob_loss_pct"] == 100.0
    assert result["max_drawdown_pct"]["p50"] > 0
