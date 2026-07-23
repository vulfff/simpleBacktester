"""
Monte Carlo bootstrap resampling of backtest results.

Resamples a return sequence (per-trade or per-bar) with replacement and
compounds each resampled sequence into a normalized equity path (start = 1.0).
Compounding assumes full reinvestment each step — an approximation of the
engine's all-in sizing.
"""

import random
from typing import Any, Dict, List, Optional

PERCENTILES = (5, 25, 50, 75, 95)
MAX_SIMS = 10_000
MIN_SAMPLES = 5
BAND_POINTS = 200
MAX_TOTAL_STEPS = 5_000_000


def trade_returns(round_trips: List[Dict[str, Any]]) -> List[float]:
    """Fractional returns from round-trip dicts (metrics.match_round_trips_from_dicts)."""
    return [t["pnl_pct"] / 100.0 for t in round_trips]


def bar_returns(equity_curve: List[Dict[str, Any]]) -> List[float]:
    """Fractional bar-to-bar returns from an equity curve. Bars after a zero-equity bar are skipped."""
    out: List[float] = []
    prev: Optional[float] = None
    for point in equity_curve:
        eq = float(point.get("equity") or 0.0)
        if prev:  # deliberately skips the first point (prev is None) and the point
                  # after a zero-equity bar (prev == 0.0) to avoid ZeroDivisionError
            out.append(eq / prev - 1.0)
        prev = eq
    return out


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Linear-interpolation percentile of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _pct_summary(values: List[float]) -> Dict[str, float]:
    vals = sorted(values)
    return {f"p{p}": _percentile(vals, p) for p in PERCENTILES}


def run_monte_carlo(returns: List[float], n_sims: int = 1000,
                    seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Bootstrap-resample `returns` n_sims times.

    Returns {n_sims, n_steps, bands, final_return_pct, max_drawdown_pct,
    prob_loss_pct}. `bands` holds the normalized-equity percentile envelope at
    <= BAND_POINTS evenly spaced steps (plus step 0). Raises ValueError if
    fewer than MIN_SAMPLES returns are supplied. Equity is floored at 0.0 each
    step (ruin is absorbing, so a <= -100% draw can't flip the sign and
    "recover" on a later multiplication), and n_sims is further capped so that
    n_sims * len(returns) stays within MAX_TOTAL_STEPS of total resampling work.
    """
    if len(returns) < MIN_SAMPLES:
        raise ValueError(f"Need at least {MIN_SAMPLES} returns, got {len(returns)}")
    n_sims = max(1, min(int(n_sims), MAX_SIMS))
    n_sims = max(1, min(n_sims, MAX_TOTAL_STEPS // len(returns)))
    rng = random.Random(seed)
    n_steps = len(returns)

    step_count = min(n_steps, BAND_POINTS)
    band_steps = sorted({0} | {round(i * n_steps / step_count) for i in range(1, step_count + 1)})
    band_values: Dict[int, List[float]] = {s: [] for s in band_steps}
    finals: List[float] = []
    max_dds: List[float] = []

    for _ in range(n_sims):
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        band_values[0].append(1.0)
        for step in range(1, n_steps + 1):
            equity = max(0.0, equity * (1.0 + rng.choice(returns)))
            if equity > peak:
                peak = equity
            elif peak > 0:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
            if step in band_values:
                band_values[step].append(equity)
        finals.append(equity)
        max_dds.append(max_dd)

    bands = []
    for s in band_steps:
        summary = _pct_summary(band_values[s])
        summary["step"] = s
        bands.append(summary)

    return {
        "n_sims": n_sims,
        "n_steps": n_steps,
        "bands": bands,
        "final_return_pct": {k: (v - 1.0) * 100.0 for k, v in _pct_summary(finals).items()},
        "max_drawdown_pct": {k: v * 100.0 for k, v in _pct_summary(max_dds).items()},
        "prob_loss_pct": 100.0 * sum(1 for f in finals if f < 1.0) / n_sims,
    }
