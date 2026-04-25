"""
metrics.py  –  Quantitative performance analytics for backtest runs.

Computes:
  total_return_pct   – simple return from first to last equity point
  cagr_pct           – compound annual growth rate
  max_drawdown_pct   – maximum peak-to-trough drawdown (negative number)
  sharpe_ratio       – annualised Sharpe (risk-free rate = 0)
  sortino_ratio      – annualised Sortino (downside-only std)
  win_rate_pct       – % of completed round-trips that were profitable
  profit_factor      – gross profit / gross loss
  total_trades       – total number of fill events
  avg_trade_pct      – mean P&L per round-trip as % of entry price
  avg_bars_held      – mean duration of completed round-trips (bars)

Input
-----
  equity_curve  : list of dicts  {t, equity, cash, asset_value}  (one per bar)
  trade_log     : list of Trade dataclasses (from portfolio.trade_log)
  starting_cash : float
  bars_per_year : int  (252 for daily, 52 for weekly, 12 for monthly, etc.)
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_metrics(
    equity_curve: List[Dict[str, Any]],
    trade_log: Any,           # list[Trade] (portfolio.Trade dataclasses)
    starting_cash: float,
    bars_per_year: int = 252,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "total_return_pct":  0.0,
        "cagr_pct":          0.0,
        "max_drawdown_pct":  0.0,
        "sharpe_ratio":      0.0,
        "sortino_ratio":     0.0,
        "calmar_ratio":      0.0,
        "win_rate_pct":      0.0,
        "profit_factor":     0.0,
        "total_trades":      0,  # updated below to round-trip count
        "avg_trade_pct":     0.0,
        "avg_bars_held":     0.0,
    }

    if not equity_curve:
        return metrics

    equities = [row["equity"] for row in equity_curve]
    n = len(equities)

    # ── total return ──────────────────────────────────────────────────────────
    first_eq = equities[0]
    last_eq  = equities[-1]
    if first_eq > 0:
        metrics["total_return_pct"] = round((last_eq - first_eq) / first_eq * 100, 4)

    # ── CAGR ──────────────────────────────────────────────────────────────────
    years = n / bars_per_year
    if first_eq > 0 and years > 0:
        if last_eq <= 0:
            metrics["cagr_pct"] = -100.0
        else:
            metrics["cagr_pct"] = round(((last_eq / first_eq) ** (1 / years) - 1) * 100, 4)

    # ── max drawdown (gated on asset_value — only track while in a position) ──
    max_dd = 0.0
    has_av = any("asset_value" in row for row in equity_curve)
    if has_av:
        peak = None
        in_position = False
        for row in equity_curve:
            eq = row["equity"]
            av = row.get("asset_value", 0) or 0
            if av > 0:
                if not in_position or peak is None:
                    peak = eq          # new position: reset peak to entry equity
                    in_position = True
                elif eq > peak:
                    peak = eq
                if peak > 0:
                    dd = (eq - peak) / peak * 100
                    if dd < max_dd:
                        max_dd = dd
            else:
                in_position = False
    else:
        # Legacy fallback: rolling peak across all bars
        peak = equities[0]
        for eq in equities:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (eq - peak) / peak * 100
                if dd < max_dd:
                    max_dd = dd
    metrics["max_drawdown_pct"] = round(max_dd, 4)

    # ── Calmar ratio (CAGR / |max drawdown|) ─────────────────────────────────

    # Calmar: CAGR / |max_drawdown|  (0 when no drawdown)
    if max_dd < 0:
        metrics["calmar_ratio"] = round(metrics["cagr_pct"] / abs(max_dd), 4)

    # ── bar returns for Sharpe / Sortino ──────────────────────────────────────
    bar_returns = []
    for i in range(1, n):
        prev = equities[i - 1]
        curr = equities[i]
        if prev > 0:
            bar_returns.append((curr - prev) / prev)

    if len(bar_returns) >= 2:
        mean_r = sum(bar_returns) / len(bar_returns)
        variance = sum((r - mean_r) ** 2 for r in bar_returns) / (len(bar_returns) - 1)
        std_r = math.sqrt(variance)

        if std_r > 0:
            metrics["sharpe_ratio"] = round(mean_r / std_r * math.sqrt(bars_per_year), 4)

        # Sortino: downside std only (sample variance, N-1)
        neg_returns = [r for r in bar_returns if r < 0]
        if len(neg_returns) >= 2:
            down_variance = sum(r ** 2 for r in neg_returns) / (len(neg_returns) - 1)
            down_std = math.sqrt(down_variance)
            if down_std > 0:
                metrics["sortino_ratio"] = round(mean_r / down_std * math.sqrt(bars_per_year), 4)

    # ── trade-level stats (FIFO round-trip matching) ──────────────────────────
    if trade_log:
        round_trips = _match_round_trips(trade_log, equity_curve)
        if round_trips:
            profits    = [rt["pnl"] for rt in round_trips if rt["pnl"] > 0]
            losses     = [rt["pnl"] for rt in round_trips if rt["pnl"] <= 0]
            total_rt   = len(round_trips)

            metrics["total_trades"] = total_rt
            metrics["win_rate_pct"] = round(len(profits) / total_rt * 100, 2) if total_rt else 0.0

            gross_profit = sum(profits)
            gross_loss   = abs(sum(losses))
            if gross_loss > 0:
                metrics["profit_factor"] = round(gross_profit / gross_loss, 4)
            elif gross_profit > 0:
                metrics["profit_factor"] = None  # no losses — avoid JSON-invalid Infinity

            pnl_pcts = [rt["pnl_pct"] for rt in round_trips]
            metrics["avg_trade_pct"] = round(sum(pnl_pcts) / len(pnl_pcts), 4) if pnl_pcts else 0.0

            bars = [rt["bars"] for rt in round_trips if rt["bars"] is not None]
            metrics["avg_bars_held"] = round(sum(bars) / len(bars), 1) if bars else 0.0

    return metrics


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_round_trips(trade_log, equity_curve=None) -> List[Dict[str, Any]]:
    """
    Match buy→sell and short→cover pairs using FIFO queues per symbol.
    Returns a list of round-trip dicts: {symbol, entry_price, exit_price, qty, pnl, pnl_pct, bars}.
    bars = actual equity-curve bar count between entry and exit fills.
    """
    # Build timestamp→bar-index map so bars_held reflects real elapsed bars,
    # not the distance between trade-log entries.
    time_to_bar: Dict[str, int] = {}
    if equity_curve:
        for i, pt in enumerate(equity_curve):
            time_to_bar[pt["t"]] = i

    def _bar_of(trade, fallback_idx: int) -> int:
        if trade.time and trade.time in time_to_bar:
            return time_to_bar[trade.time]
        return fallback_idx

    long_q:  Dict[str, list] = defaultdict(list)
    short_q: Dict[str, list] = defaultdict(list)
    round_trips: List[Dict[str, Any]] = []

    for idx, trade in enumerate(trade_log):
        action  = trade.action.lower()
        sym     = trade.symbol
        bar_idx = _bar_of(trade, idx)
        comm    = getattr(trade, "commission", 0.0) or 0.0

        if action == "buy":
            long_q[sym].append({"price": trade.price, "qty": trade.quantity,
                                 "bar": bar_idx, "commission": comm})

        elif action == "sell":
            remaining = trade.quantity
            exit_comm_per_unit = comm / trade.quantity if trade.quantity > 0 else 0.0
            while remaining > 0 and long_q[sym]:
                entry  = long_q[sym][0]
                filled = min(remaining, entry["qty"])
                entry_comm = entry["commission"] * (filled / entry["qty"]) if entry["qty"] > 0 else 0.0
                exit_comm  = exit_comm_per_unit * filled
                pnl     = (trade.price - entry["price"]) * filled - entry_comm - exit_comm
                pnl_pct = pnl / (entry["price"] * filled) * 100 if entry["price"] else 0
                round_trips.append({
                    "symbol":      sym,
                    "entry_price": entry["price"],
                    "exit_price":  trade.price,
                    "qty":         filled,
                    "pnl":         pnl,
                    "pnl_pct":     pnl_pct,
                    "bars":        bar_idx - entry["bar"],
                })
                entry["qty"]        -= filled
                entry["commission"] -= entry_comm
                remaining           -= filled
                if entry["qty"] <= 0:
                    long_q[sym].pop(0)

        elif action == "short":
            short_q[sym].append({"price": trade.price, "qty": trade.quantity,
                                  "bar": bar_idx, "commission": comm})

        elif action == "cover":
            remaining = trade.quantity
            exit_comm_per_unit = comm / trade.quantity if trade.quantity > 0 else 0.0
            while remaining > 0 and short_q[sym]:
                entry  = short_q[sym][0]
                filled = min(remaining, entry["qty"])
                entry_comm = entry["commission"] * (filled / entry["qty"]) if entry["qty"] > 0 else 0.0
                exit_comm  = exit_comm_per_unit * filled
                pnl     = (entry["price"] - trade.price) * filled - entry_comm - exit_comm
                pnl_pct = pnl / (entry["price"] * filled) * 100 if entry["price"] else 0
                round_trips.append({
                    "symbol":      sym,
                    "entry_price": entry["price"],
                    "exit_price":  trade.price,
                    "qty":         filled,
                    "pnl":         pnl,
                    "pnl_pct":     pnl_pct,
                    "bars":        bar_idx - entry["bar"],
                })
                entry["qty"]        -= filled
                entry["commission"] -= entry_comm
                remaining           -= filled
                if entry["qty"] <= 0:
                    short_q[sym].pop(0)

    return round_trips


def match_round_trips_from_dicts(fills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Match buy→sell and short→cover pairs from dict-format fills (as stored in DB).
    Each fill: {t, action, symbol, qty, price}.
    Returns round-trip dicts: {symbol, side, entry_time, exit_time, entry_price, exit_price, qty, pnl, pnl_pct}.
    """
    long_q:  Dict[str, list] = defaultdict(list)
    short_q: Dict[str, list] = defaultdict(list)
    trips: List[Dict[str, Any]] = []

    for f in fills:
        action = (f.get("action") or "").lower()
        sym    = f.get("symbol", "")
        price  = float(f.get("price", 0))
        qty    = float(f.get("qty", 0))
        t      = f.get("t", "")

        if qty <= 0:
            continue  # skip zero/negative-qty fills
        if action == "buy":
            long_q[sym].append({"price": price, "qty": qty, "t": t})
        elif action == "sell":
            remaining = qty
            while remaining > 0 and long_q[sym]:
                entry  = long_q[sym][0]
                filled = min(remaining, entry["qty"])
                pnl    = (price - entry["price"]) * filled
                pnl_pct = pnl / (entry["price"] * filled) * 100 if entry["price"] else 0
                trips.append({
                    "symbol": sym, "side": "long",
                    "entry_time": entry["t"], "exit_time": t,
                    "entry_price": entry["price"], "exit_price": price,
                    "qty": filled, "pnl": round(pnl, 4), "pnl_pct": round(pnl_pct, 2),
                })
                entry["qty"] -= filled
                remaining    -= filled
                if entry["qty"] <= 0:
                    long_q[sym].pop(0)
        elif action == "short":
            short_q[sym].append({"price": price, "qty": qty, "t": t})
        elif action == "cover":
            remaining = qty
            while remaining > 0 and short_q[sym]:
                entry  = short_q[sym][0]
                filled = min(remaining, entry["qty"])
                pnl    = (entry["price"] - price) * filled
                pnl_pct = pnl / (entry["price"] * filled) * 100 if entry["price"] else 0
                trips.append({
                    "symbol": sym, "side": "short",
                    "entry_time": entry["t"], "exit_time": t,
                    "entry_price": entry["price"], "exit_price": price,
                    "qty": filled, "pnl": round(pnl, 4), "pnl_pct": round(pnl_pct, 2),
                })
                entry["qty"] -= filled
                remaining    -= filled
                if entry["qty"] <= 0:
                    short_q[sym].pop(0)

    return trips
