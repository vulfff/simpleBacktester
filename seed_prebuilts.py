"""
seed_prebuilts.py
=================
Inserts pre-built strategies and indicators into the database.
Safe to run multiple times — skips any entry that already exists by name.

Run:
    python seed_prebuilts.py
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from db import get_db_conn, create_tables

create_tables()

# ── helpers ───────────────────────────────────────────────────────────────────

def cond(left, op, right, combiner="and"):
    return {"left": left, "operator": op, "right": right, "combiner": combiner}

def exit_cond(exit_type, value):
    return {"kind": "exit_condition", "exitType": exit_type, "value": value}

def price(field="close"):
    return {"type": "price", "field": field}

def const(value):
    return {"type": "constant", "value": value}

def sma(period, field="close"):
    return {"type": "sma", "field": field, "period": period}

def ema(period, field="close"):
    return {"type": "ema", "field": field, "period": period}

def rsi(period=14, field="close"):
    return {"type": "rsi", "field": field, "period": period}

def macd_comp(component, fast=12, slow=26, signal=9):
    return {"type": "macd", "fast": fast, "slow": slow, "signal": signal, "component": component}

def boll(component, period=20, std_dev=2.0, field="close"):
    return {"type": "bollinger", "field": field, "period": period,
            "std_dev": std_dev, "component": component}

def rule(name, role, conditions, timing="on_change", quantity=1.0):
    return {"name": name, "role": role, "conditions": conditions,
            "timing": timing, "quantity": quantity}

def rule_set(name, rules):
    return {"name": name, "rules": rules}

# Expression tree node helpers for indicators
def n_const(v):
    return {"node": "const", "value": v}

def n_op(operand_dict):
    return {"node": "operand", "operand": operand_dict}

def n_binop(op, left, right):
    return {"node": "binop", "op": op, "left": left, "right": right}

def n_ifelse(cond_left, cond_op, cond_right, then, else_):
    return {"node": "ifelse", "cond_left": cond_left, "cond_op": cond_op,
            "cond_right": cond_right, "then": then, "else_": else_}

def n_clamp(value, lo, hi):
    return {"node": "clamp", "value": value, "lo": lo, "hi": hi}

def n_unop(op, operand):
    return {"node": "unop", "op": op, "operand": operand}

def highest_high(period, field="high"):
    return {"type": "highest_high", "field": field, "period": period}

def lowest_low(period, field="low"):
    return {"type": "lowest_low", "field": field, "period": period}

def atr(period=14):
    return {"type": "atr", "period": period}

def typical_price():
    return {"type": "typical_price"}

def lookback(period, field="close"):
    return {"type": "lookback", "field": field, "period": period}


# ── Pre-built strategies ──────────────────────────────────────────────────────

STRATEGIES = [

    # ── 1. Golden Cross ───────────────────────────────────────────────────────
    {
        "name": "Golden Cross",
        "logic": "rule_set",
        "config": rule_set("Golden Cross", [
            rule(
                "Buy when 50-SMA crosses above 200-SMA",
                "entry_long",
                [cond(sma(50), "cross_above", sma(200))],
            ),
            rule(
                "Sell when 50-SMA crosses below 200-SMA",
                "exit_long",
                [cond(sma(50), "cross_below", sma(200))],
            ),
        ]),
        "desc": (
            "Classic long-term trend strategy. Buys when the fast moving average "
            "crosses above the slow one (golden cross) and exits on the reversal "
            "(death cross). Best on daily/weekly charts."
        ),
    },

    # ── 2. RSI Mean Reversion ────────────────────────────────────────────────
    {
        "name": "RSI Mean Reversion",
        "logic": "rule_set",
        "config": rule_set("RSI Mean Reversion", [
            rule(
                "Buy when RSI is oversold (< 30)",
                "entry_long",
                [cond(rsi(14), "<", const(30))],
            ),
            rule(
                "Sell when RSI is overbought (> 70)",
                "exit_long",
                [cond(rsi(14), ">", const(70))],
                timing="every_tick",
            ),
            rule(
                "Stop loss at 5%",
                "exit_long",
                [exit_cond("stop_loss_pct", 5.0)],
                timing="every_tick",
            ),
            rule(
                "Take profit at 8%",
                "exit_long",
                [exit_cond("take_profit_pct", 8.0)],
                timing="every_tick",
            ),
        ]),
        "desc": (
            "Counter-trend strategy. Buys during extreme oversold readings and exits "
            "when the market recovers (RSI > 70) or a stop-loss/take-profit is hit. "
            "Works well in ranging markets."
        ),
    },

    # ── 3. MACD Momentum ────────────────────────────────────────────────────
    {
        "name": "MACD Momentum",
        "logic": "rule_set",
        "config": rule_set("MACD Momentum", [
            rule(
                "Buy on MACD bullish crossover",
                "entry_long",
                [cond(macd_comp("macd"), "cross_above", macd_comp("signal"))],
            ),
            rule(
                "Sell on MACD bearish crossover",
                "exit_long",
                [cond(macd_comp("macd"), "cross_below", macd_comp("signal"))],
            ),
        ]),
        "desc": (
            "Trend-following strategy using MACD. Buys when the MACD line crosses "
            "above its signal line (bullish momentum) and sells on the reversal. "
            "Good for capturing medium-term trends."
        ),
    },

    # ── 4. Bollinger Band Bounce ────────────────────────────────────────────
    {
        "name": "Bollinger Band Bounce",
        "logic": "rule_set",
        "config": rule_set("Bollinger Band Bounce", [
            rule(
                "Buy when price drops below Lower Band",
                "entry_long",
                [cond(price(), "cross_below", boll("lower", 20, 2.0))],
            ),
            rule(
                "Sell when price recovers to Middle Band",
                "exit_long",
                [cond(price(), "cross_above", boll("middle", 20, 2.0))],
                timing="every_tick",
            ),
            rule(
                "Stop loss at 3%",
                "exit_long",
                [exit_cond("stop_loss_pct", 3.0)],
                timing="every_tick",
            ),
            rule(
                "Take profit at 6%",
                "exit_long",
                [exit_cond("take_profit_pct", 6.0)],
                timing="every_tick",
            ),
        ]),
        "desc": (
            "Mean-reversion strategy using Bollinger Bands. Enters when price dips "
            "below the lower band (statistically cheap) and exits when it bounces "
            "back to the middle band. Tight stop-loss at 3%."
        ),
    },

    # ── 5. EMA Trend Follow ─────────────────────────────────────────────────
    {
        "name": "EMA Trend Follow",
        "logic": "rule_set",
        "config": rule_set("EMA Trend Follow", [
            rule(
                "Buy when price crosses above 21-EMA",
                "entry_long",
                [cond(price(), "cross_above", ema(21))],
            ),
            rule(
                "Sell when price crosses below 21-EMA",
                "exit_long",
                [cond(price(), "cross_below", ema(21))],
                timing="every_tick",
            ),
            rule(
                "Stop loss at 3%",
                "exit_long",
                [exit_cond("stop_loss_pct", 3.0)],
                timing="every_tick",
            ),
        ]),
        "desc": (
            "Fast trend-following strategy. Buys when price rises above the "
            "21-bar EMA and rides the trend until price crosses back below. "
            "3% stop-loss keeps losses small."
        ),
    },

]


# ── Pre-built indicators ──────────────────────────────────────────────────────

INDICATORS = [

    # ── 1. RSI Oversold Signal ───────────────────────────────────────────────
    {
        "name": "RSI Oversold Signal",
        "description": "Returns 1 when RSI(14) is below 30 (oversold), else 0. Use as a binary buy-signal filter.",
        "color": "#a78bfa",
        "expr": n_ifelse(
            n_op(rsi(14)), "<", n_const(30),
            n_const(1), n_const(0),
        ),
    },

    # ── 2. Price Distance from SMA (%) ──────────────────────────────────────
    {
        "name": "Price vs SMA Distance %",
        "description": (
            "How far price is above/below its 20-bar SMA, as a percentage. "
            "Positive = price is above average (overbought zone). "
            "Negative = price is below average (oversold zone)."
        ),
        "color": "#34d399",
        "expr": n_binop(
            "*",
            n_binop(
                "/",
                n_binop("-", n_op(price()), n_op(sma(20))),
                n_op(sma(20)),
            ),
            n_const(100),
        ),
    },

    # ── 3. Momentum (5 bars) ────────────────────────────────────────────────
    {
        "name": "Momentum (5 bars)",
        "description": (
            "Raw price change over the last 5 bars. "
            "Positive = price is higher than 5 bars ago (upward momentum). "
            "Negative = downward momentum. Great for detecting early trend shifts."
        ),
        "color": "#fb923c",
        "expr": n_binop(
            "-",
            n_op(price()),
            n_op({"type": "lookback", "field": "close", "period": 5}),
        ),
    },

    # ── 4. Volume Ratio ──────────────────────────────────────────────────────
    {
        "name": "Volume Ratio",
        "description": (
            "Current bar's volume divided by its 20-bar average volume. "
            "A value above 1.5 means the current bar has 50% more volume than usual — "
            "a potential breakout or significant move."
        ),
        "color": "#f59e0b",
        "expr": n_binop(
            "/",
            n_op(price("volume")),
            n_op(sma(20, field="volume")),
        ),
    },

    # ── 5. Bollinger %B (0–100) ──────────────────────────────────────────────
    {
        "name": "Bollinger %B",
        "description": (
            "Where price sits within the Bollinger Bands, scaled to 0–100. "
            "0 = at the lower band (oversold), 100 = at the upper band (overbought), "
            "50 = at the middle band. Clipped so it stays in a readable range."
        ),
        "color": "#f472b6",
        "expr": n_clamp(
            n_binop("*", n_op(boll("pct_b", 20, 2.0)), n_const(100)),
            n_const(-20),
            n_const(120),
        ),
    },

    # ── 6. Williams %R (14) ─────────────────────────────────────────────────
    # %R = (HighestHigh - Close) / (HighestHigh - LowestLow) * -100
    {
        "name": "Williams %R",
        "description": (
            "Williams %R oscillator (14 bars). Ranges from -100 (oversold) to 0 (overbought). "
            "Readings below -80 suggest oversold conditions; above -20 suggest overbought."
        ),
        "color": "#818cf8",
        "expr": n_binop(
            "*",
            n_binop(
                "/",
                n_binop("-", n_op(highest_high(14)), n_op(price())),
                n_binop("-", n_op(highest_high(14)), n_op(lowest_low(14))),
            ),
            n_const(-100),
        ),
    },

    # ── 7. Stochastic %K (14) ──────────────────────────────────────────────
    # %K = (Close - LowestLow) / (HighestHigh - LowestLow) * 100
    {
        "name": "Stochastic %K",
        "description": (
            "Stochastic oscillator %K (14 bars). Ranges 0–100. "
            "Below 20 = oversold; above 80 = overbought. "
            "Shows where close sits relative to the recent high-low range."
        ),
        "color": "#c084fc",
        "expr": n_clamp(
            n_binop(
                "*",
                n_binop(
                    "/",
                    n_binop("-", n_op(price()), n_op(lowest_low(14))),
                    n_binop("-", n_op(highest_high(14)), n_op(lowest_low(14))),
                ),
                n_const(100),
            ),
            n_const(0),
            n_const(100),
        ),
    },

    # ── 8. Rate of Change (ROC 12) ─────────────────────────────────────────
    # ROC = (Close - Close[12]) / Close[12] * 100
    {
        "name": "Rate of Change (12)",
        "description": (
            "12-bar Rate of Change (%). Measures percentage change from 12 bars ago. "
            "Positive = price rising; negative = price falling. "
            "A classic momentum indicator for trend strength."
        ),
        "color": "#fbbf24",
        "expr": n_binop(
            "*",
            n_binop(
                "/",
                n_binop("-", n_op(price()), n_op(lookback(12))),
                n_op(lookback(12)),
            ),
            n_const(100),
        ),
    },

    # ── 9. Keltner Channel Width ───────────────────────────────────────────
    # Width = 2 * ATR(10) / EMA(20) * 100
    {
        "name": "Keltner Channel Width",
        "description": (
            "Width of a Keltner Channel (2×ATR(10) around EMA(20)) as a percentage of price. "
            "Higher values indicate wider channels (more volatility). "
            "Useful for detecting volatility squeezes when width contracts."
        ),
        "color": "#2dd4bf",
        "expr": n_binop(
            "*",
            n_binop(
                "/",
                n_binop("*", n_const(2), n_op(atr(10))),
                n_op(ema(20)),
            ),
            n_const(100),
        ),
    },

    # ── 10. Donchian Midline (20) ──────────────────────────────────────────
    # Midline = (HighestHigh(20) + LowestLow(20)) / 2
    {
        "name": "Donchian Midline (20)",
        "description": (
            "Midpoint of the 20-bar Donchian Channel: average of the highest high and "
            "lowest low over 20 bars. Acts as a dynamic support/resistance level. "
            "When price is above midline, trend is up; below, trend is down."
        ),
        "color": "#38bdf8",
        "expr": n_binop(
            "/",
            n_binop("+", n_op(highest_high(20)), n_op(lowest_low(20))),
            n_const(2),
        ),
    },

    # ── 11. ATR (14) ───────────────────────────────────────────────────────
    {
        "name": "ATR (14)",
        "description": (
            "Average True Range over 14 bars. Measures market volatility in price units. "
            "Higher ATR = more volatile. Useful for setting stop-loss distances "
            "and position sizing relative to volatility."
        ),
        "color": "#f97316",
        "expr": n_op(atr(14)),
    },

    # ── 12. MACD Histogram ─────────────────────────────────────────────────
    # Histogram = MACD line - Signal line
    {
        "name": "MACD Histogram",
        "description": (
            "Difference between MACD line and its signal line (12/26/9). "
            "Positive = bullish momentum increasing; negative = bearish. "
            "When histogram crosses zero, it confirms MACD crossovers."
        ),
        "color": "#e879c0",
        "expr": n_binop(
            "-",
            n_op(macd_comp("macd")),
            n_op(macd_comp("signal")),
        ),
    },

    # ── 13. EMA Ribbon Distance ────────────────────────────────────────────
    # (EMA(8) - EMA(21)) / EMA(21) * 100
    {
        "name": "EMA Ribbon Distance",
        "description": (
            "Percentage gap between fast EMA(8) and slow EMA(21). "
            "Positive = price in uptrend with separation; negative = downtrend. "
            "Narrowing toward zero signals potential trend reversal or consolidation."
        ),
        "color": "#4ade80",
        "expr": n_binop(
            "*",
            n_binop(
                "/",
                n_binop("-", n_op(ema(8)), n_op(ema(21))),
                n_op(ema(21)),
            ),
            n_const(100),
        ),
    },

]


# ── DB insertion ──────────────────────────────────────────────────────────────

def seed():
    import paths
    paths.ensure_data_dir()
    conn = get_db_conn()
    cur  = conn.cursor()

    # ── strategies ────────────────────────────────────────────────────────────
    s_inserted = 0
    s_skipped  = 0
    for s in STRATEGIES:
        cur.execute("SELECT id FROM strategies WHERE name = ?", (s["name"],))
        row = cur.fetchone()
        config = s["config"]
        config_str = json.dumps({"rule_set": config}) if "rules" in config else json.dumps(config)
        if row:
            cur.execute(
                "UPDATE strategies SET config = ?, is_builtin = 1 WHERE id = ?",
                (config_str, row["id"]),
            )
            s_skipped += 1
            continue
        cur.execute(
            "INSERT INTO strategies (name, logic, config, is_builtin) VALUES (?, ?, ?, 1)",
            (s["name"], s["logic"], config_str),
        )
        s_inserted += 1

    # ── indicators ────────────────────────────────────────────────────────────
    i_inserted = 0
    i_skipped  = 0
    for ind in INDICATORS:
        expr_json = json.dumps({
            "expr":        ind["expr"],
            "description": ind["description"],
            "color":       ind["color"],
        })
        cur.execute("SELECT id FROM indicators WHERE name = ?", (ind["name"],))
        row = cur.fetchone()
        if row:
            # Ensure is_builtin flag is set on existing rows
            cur.execute("UPDATE indicators SET is_builtin = 1 WHERE id = ?", (row["id"],))
            i_skipped += 1
        else:
            cur.execute(
                "INSERT INTO indicators (name, expression, is_builtin) VALUES (?, ?, 1)",
                (ind["name"], expr_json),
            )
            i_inserted += 1

    conn.commit()
    conn.close()

    print(f"Strategies : {s_inserted} inserted, {s_skipped} already existed")
    print(f"Indicators : {i_inserted} inserted, {i_skipped} already existed")


if __name__ == "__main__":
    seed()
    print("Done.")
