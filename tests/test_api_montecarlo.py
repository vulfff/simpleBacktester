"""
test_api_montecarlo.py — POST /api/backtest/montecarlo endpoint coverage.
"""
import pytest

import db


def _save_run(trade_count=6, pnl_pct=2.0):
    """Persist a minimal run with `trade_count` closed long round trips."""
    trade_log = []
    equity_curve = []
    equity = 1000.0
    for i in range(trade_count):
        buy_t = f"2024-01-{2*i+1:02d}T00:00:00"
        sell_t = f"2024-01-{2*i+2:02d}T00:00:00"
        trade_log.append({"t": buy_t, "action": "buy", "symbol": "TST", "qty": 1.0, "price": 100.0})
        trade_log.append({"t": sell_t, "action": "sell", "symbol": "TST", "qty": 1.0,
                          "price": 100.0 * (1 + pnl_pct / 100)})
        equity_curve.append({"t": buy_t, "equity": equity, "cash": equity, "asset_value": 0.0})
        equity *= 1 + pnl_pct / 100
        equity_curve.append({"t": sell_t, "equity": equity, "cash": equity, "asset_value": 0.0})
    return db.save_run(
        strategy_name="mc-test", ticker="TST", timeframe="1d",
        start_date="2024-01-01", end_date="2024-02-01", starting_cash=1000.0,
        strategy_config={}, metrics={}, equity_curve=equity_curve, trade_log=trade_log,
    )


def test_montecarlo_unknown_run_404(test_client):
    resp = test_client.post("/api/backtest/montecarlo", json={"run_id": 999999})
    assert resp.status_code == 404


def test_montecarlo_too_few_trades_400(test_client):
    run_id = _save_run(trade_count=3)
    resp = test_client.post("/api/backtest/montecarlo", json={"run_id": run_id, "method": "trades"})
    assert resp.status_code == 400
    assert "at least 5" in resp.json()["detail"]


def test_montecarlo_trades_happy_path(test_client):
    run_id = _save_run(trade_count=8)
    resp = test_client.post("/api/backtest/montecarlo",
                       json={"run_id": run_id, "n_sims": 200, "seed": 42})
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["method"] == "trades"
    assert body["n_sims"] == 200
    assert body["n_steps"] == 8
    assert body["bands"][0]["step"] == 0
    assert body["bands"][-1]["step"] == 8
    # 8 identical +2% trades -> deterministic outcome regardless of resampling
    assert body["final_return_pct"]["p50"] == pytest.approx((1.02 ** 8 - 1) * 100, rel=1e-6)
    assert body["prob_loss_pct"] == 0.0


def test_montecarlo_returns_method(test_client):
    run_id = _save_run(trade_count=8)  # 16 equity points -> 15 bar returns
    resp = test_client.post("/api/backtest/montecarlo",
                       json={"run_id": run_id, "method": "returns", "n_sims": 100, "seed": 1})
    assert resp.status_code == 200
    assert resp.json()["method"] == "returns"
    assert resp.json()["n_steps"] == 15


def test_montecarlo_seed_reproducible(test_client):
    run_id = _save_run(trade_count=8, pnl_pct=3.0)
    payload = {"run_id": run_id, "n_sims": 100, "seed": 7}
    a = test_client.post("/api/backtest/montecarlo", json=payload).json()
    b = test_client.post("/api/backtest/montecarlo", json=payload).json()
    assert a == b
