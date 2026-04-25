"""
test_api.py — FastAPI endpoint coverage via TestClient.

Covers: health, strategy/indicator CRUD, run persistence, backtest upload,
regression guards (strategy_name != "rule_set", two runs → two IDs, etc.)
"""
import io
import json
import math
import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_csv(n: int = 30, start: float = 100.0, step: float = 0.5) -> bytes:
    """Build a minimal OHLCV CSV with n bars."""
    rows = ["timestamp,open,high,low,close,volume"]
    price = start
    for i in range(n):
        rows.append(f"2024-01-{(i % 28) + 1:02d},{price:.2f},{price + 0.5:.2f},{price - 0.5:.2f},{price:.2f},10000")
        price += step
    return "\n".join(rows).encode()


def _strategy_payload(name: str = "TestStrat") -> str:
    """Minimal rule_set strategy JSON string: buy when SMA(5) > 0, exit after 5 bars."""
    cfg = {
        "name": name,
        "logic": "rule_set",
        "config": {
            "rule_set": {
                "rules": [
                    {
                        "name": "Buy",
                        "role": "entry_long",
                        "conditions": [
                            {
                                "left": {"type": "sma", "period": 5, "field": "close"},
                                "operator": ">",
                                "right": {"type": "constant", "value": 0},
                                "combiner": "and",
                            }
                        ],
                        "timing": "on_change",
                        "quantity": 10,
                    },
                    {
                        "name": "Sell",
                        "role": "exit_long",
                        "conditions": [
                            {
                                "kind": "exit_condition",
                                "exit_type": "bars_held",
                                "bars": 5,
                            }
                        ],
                        "timing": "on_change",
                        "quantity": 10,
                    },
                ],
            }
        },
    }
    return json.dumps([cfg])


def _post_backtest(client, csv_bytes: bytes, strategy_payload: str, **extra_data):
    return client.post(
        "/api/backtest/upload",
        files={"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"strategies": strategy_payload, **extra_data},
    )


# ---------------------------------------------------------------------------
# TestHealth
# ---------------------------------------------------------------------------

class TestHealth:

    def test_health_returns_ok(self, test_client):
        r = test_client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# TestStrategyDB
# ---------------------------------------------------------------------------

class TestStrategyDB:

    def test_get_strategies_returns_list(self, test_client):
        r = test_client.get("/api/db/strategies")
        assert r.status_code == 200
        data = r.json()
        assert "strategies" in data
        assert isinstance(data["strategies"], list)

    def test_get_strategies_includes_builtins(self, test_client):
        r = test_client.get("/api/db/strategies")
        names = [s["name"] for s in r.json()["strategies"]]
        # seed_prebuilts inserts at least one built-in
        assert len(names) > 0

    def test_post_strategy_upsert_deduplicates_by_name(self, test_client):
        """Posting same name twice should not create duplicate entries."""
        payload = {"strategies": [{"name": "UniqueTestStrat_99", "logic": "rule_set", "config": {}}]}
        test_client.post("/api/db/strategies", json=payload)
        test_client.post("/api/db/strategies", json=payload)
        r = test_client.get("/api/db/strategies")
        names = [s["name"] for s in r.json()["strategies"]]
        assert names.count("UniqueTestStrat_99") == 1

    def test_post_strategy_returns_ok(self, test_client):
        payload = {"strategies": [{"name": "TempStrat_01", "logic": "rule_set", "config": {}}]}
        r = test_client.post("/api/db/strategies", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_delete_builtin_strategy_returns_403(self, test_client):
        r = test_client.get("/api/db/strategies")
        builtins = [s for s in r.json()["strategies"] if s.get("is_builtin")]
        if not builtins:
            pytest.skip("No builtin strategies seeded")
        bid = builtins[0]["id"]
        r = test_client.delete(f"/api/db/strategies/{bid}")
        assert r.status_code == 403

    def test_delete_user_strategy(self, test_client):
        payload = {"strategies": [{"name": "ToDelete_Strategy", "logic": "rule_set", "config": {}}]}
        test_client.post("/api/db/strategies", json=payload)
        r = test_client.get("/api/db/strategies")
        match = [s for s in r.json()["strategies"] if s["name"] == "ToDelete_Strategy"]
        assert match, "Strategy not found after insert"
        sid = match[0]["id"]
        r = test_client.delete(f"/api/db/strategies/{sid}")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# TestIndicatorDB
# ---------------------------------------------------------------------------

class TestIndicatorDB:

    def test_get_indicators_returns_list(self, test_client):
        r = test_client.get("/api/db/indicators")
        assert r.status_code == 200
        assert "indicators" in r.json()

    def test_post_indicators_persists_and_get_reflects_it(self, test_client):
        expr = {"type": "operand", "operand": {"type": "sma", "period": 10}}
        payload = {
            "indicators": [
                {"name": "TestSMA10", "expr": expr, "description": "test", "color": "#ff0000"}
            ]
        }
        r = test_client.post("/api/db/indicators", json=payload)
        assert r.status_code == 200
        r2 = test_client.get("/api/db/indicators")
        names = [ind["name"] for ind in r2.json()["indicators"]]
        assert "TestSMA10" in names

    def test_post_indicators_replaces_non_builtins(self, test_client):
        """Posting an empty indicators list removes all non-builtin indicators."""
        # First insert one
        expr = {"type": "operand", "operand": {"type": "sma", "period": 3}}
        test_client.post("/api/db/indicators", json={"indicators": [{"name": "Temp_ind", "expr": expr}]})
        # Now replace with empty
        test_client.post("/api/db/indicators", json={"indicators": []})
        r = test_client.get("/api/db/indicators")
        non_builtins = [i for i in r.json()["indicators"] if not i.get("is_builtin")]
        assert len(non_builtins) == 0


# ---------------------------------------------------------------------------
# TestBacktestUpload
# ---------------------------------------------------------------------------

class TestBacktestUpload:

    def test_valid_backtest_returns_200_with_fields(self, test_client):
        r = _post_backtest(test_client, _make_csv(), _strategy_payload())
        assert r.status_code == 200
        body = r.json()
        for field in ("cash", "total_value", "metrics", "equity_curve", "trade_log", "signal_log", "run_id", "warmup_bars"):
            assert field in body, f"Missing field: {field}"

    def test_valid_backtest_equity_curve_populated(self, test_client):
        r = _post_backtest(test_client, _make_csv(), _strategy_payload())
        assert r.status_code == 200
        assert len(r.json()["equity_curve"]) > 0

    def test_no_strategy_returns_400(self, test_client):
        r = _post_backtest(test_client, _make_csv(), "[]")
        assert r.status_code == 400

    def test_no_file_returns_400(self, test_client):
        r = test_client.post(
            "/api/backtest/upload",
            data={"strategies": _strategy_payload()},
        )
        assert r.status_code == 400

    def test_missing_close_column_returns_error(self, test_client):
        """CSV with no recognisable price column must return an HTTP error (4xx or 5xx)."""
        bad_csv = b"timestamp,notclose\n2024-01-01,100\n2024-01-02,101\n"
        r = _post_backtest(test_client, bad_csv, _strategy_payload())
        # CSVTickDataFeed raises ValueError lazily during engine.run(), which the
        # engine error handler wraps as 500. Either 422 or 500 is acceptable.
        assert r.status_code >= 400

    def test_legacy_bid_column_accepted(self, test_client):
        """CSV with 'bid' column (alias for close) should parse successfully."""
        bid_csv = b"timestamp,bid,volume\n2024-01-01,100,1000\n2024-01-02,101,1000\n2024-01-03,102,1000\n"
        r = _post_backtest(test_client, bid_csv, _strategy_payload())
        # Parser accepts bid as close alias — should not 422
        assert r.status_code == 200

    def test_strategy_name_stored_not_rule_set(self, test_client):
        """Regression guard: strategy_name in DB must be display name, not 'rule_set'."""
        r = _post_backtest(test_client, _make_csv(), _strategy_payload("MyDisplayName"))
        assert r.status_code == 200
        run_id = r.json().get("run_id")
        if run_id is None:
            pytest.skip("run not saved")
        r2 = test_client.get(f"/api/db/runs/{run_id}")
        assert r2.status_code == 200
        run_data = r2.json()
        assert run_data.get("strategy_name") == "MyDisplayName"

    def test_response_json_contains_no_infinity(self, test_client):
        """JSON response must be valid (no Infinity or NaN values)."""
        r = _post_backtest(test_client, _make_csv(), _strategy_payload())
        assert r.status_code == 200
        # If the JSON is invalid (Infinity), json() would raise
        body = r.json()
        metrics = body.get("metrics", {})
        for k, v in metrics.items():
            if isinstance(v, float):
                assert math.isfinite(v) or v is None, f"metrics[{k}]={v} is not finite"

    def test_two_identical_backtests_produce_two_run_ids(self, test_client):
        """Every backtest run must be stored uniquely (run_at timestamp in hash)."""
        r1 = _post_backtest(test_client, _make_csv(), _strategy_payload("DupTest"))
        r2 = _post_backtest(test_client, _make_csv(), _strategy_payload("DupTest"))
        assert r1.status_code == 200
        assert r2.status_code == 200
        id1 = r1.json().get("run_id")
        id2 = r2.json().get("run_id")
        assert id1 is not None and id2 is not None
        assert id1 != id2, "Duplicate runs should get distinct run_ids"

    def test_ohlcv_backtest_returns_warmup_bars(self, test_client):
        r = _post_backtest(test_client, _make_csv(), _strategy_payload())
        assert r.status_code == 200
        assert r.json()["warmup_bars"] >= 5  # SMA-5 requires 5 warmup bars


# ---------------------------------------------------------------------------
# TestRunHistory
# ---------------------------------------------------------------------------

class TestRunHistory:

    def _saved_run_id(self, test_client) -> int:
        """Run a backtest and return the saved run_id."""
        r = _post_backtest(test_client, _make_csv(), _strategy_payload("HistoryTest"))
        assert r.status_code == 200
        run_id = r.json().get("run_id")
        assert run_id is not None, "Run was not saved"
        return run_id

    def test_get_runs_returns_list(self, test_client):
        r = test_client.get("/api/db/runs")
        assert r.status_code == 200
        assert "runs" in r.json()

    def test_get_run_by_id_returns_full_detail(self, test_client):
        run_id = self._saved_run_id(test_client)
        r = test_client.get(f"/api/db/runs/{run_id}")
        assert r.status_code == 200
        run = r.json()
        for field in ("strategy_name", "metrics", "equity_curve", "trade_log", "signal_log"):
            assert field in run, f"Missing field in run detail: {field}"

    def test_get_run_by_id_has_signal_log_field(self, test_client):
        run_id = self._saved_run_id(test_client)
        r = test_client.get(f"/api/db/runs/{run_id}")
        assert r.status_code == 200
        assert isinstance(r.json().get("signal_log"), list)

    def test_get_nonexistent_run_returns_404(self, test_client):
        r = test_client.get("/api/db/runs/999999")
        assert r.status_code == 404

    def test_delete_run_returns_ok(self, test_client):
        run_id = self._saved_run_id(test_client)
        r = test_client.delete(f"/api/db/runs/{run_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_delete_run_then_get_returns_404(self, test_client):
        run_id = self._saved_run_id(test_client)
        test_client.delete(f"/api/db/runs/{run_id}")
        r = test_client.get(f"/api/db/runs/{run_id}")
        assert r.status_code == 404

    def test_delete_nonexistent_run_returns_404(self, test_client):
        r = test_client.delete("/api/db/runs/888888")
        assert r.status_code == 404

    def test_batch_delete_runs(self, test_client):
        """POST /api/db/runs/batch-delete removes the requested run IDs."""
        r1 = _post_backtest(test_client, _make_csv(), _strategy_payload("BatchDel"))
        r2 = _post_backtest(test_client, _make_csv(), _strategy_payload("BatchDel"))
        id1, id2 = r1.json()["run_id"], r2.json()["run_id"]
        r = test_client.post("/api/db/runs/batch-delete", json={"ids": [id1, id2]})
        assert r.status_code == 200
        assert r.json()["deleted"] == 2

    def test_delete_all_runs(self, test_client):
        # Insert at least one run
        _post_backtest(test_client, _make_csv(), _strategy_payload("DeleteAll"))
        r = test_client.delete("/api/db/runs")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        # Verify runs list is now empty
        r2 = test_client.get("/api/db/runs")
        assert r2.json()["runs"] == []
