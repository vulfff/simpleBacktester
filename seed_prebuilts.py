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

def exit_cond(exit_type, value, combiner="and"):
    return {"kind": "exit_condition", "exitType": exit_type, "value": value, "combiner": combiner}

def price(field="mid"):
    return {"type": "price", "field": field}

def const(value):
    return {"type": "constant", "value": value}

def sma(period, field="mid"):
    return {"type": "sma", "field": field, "period": period}

def ema(period, field="mid"):
    return {"type": "ema", "field": field, "period": period}

def rsi(period=14, field="mid"):
    return {"type": "rsi", "field": field, "period": period}

def macd_comp(component, fast=12, slow=26, signal=9):
    return {"type": "macd", "fast": fast, "slow": slow, "signal": signal, "component": component}

def boll(component, period=20, std_dev=2.0, field="mid"):
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
                "Sell when RSI is overbought (> 70) or stop-loss hit",
                "exit_long",
                [
                    cond(rsi(14), ">", const(70)),
                    exit_cond("stop_loss_pct",  5.0, combiner="or"),
                    exit_cond("take_profit_pct", 8.0, combiner="or"),
                ],
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
                "Sell when price recovers to Middle Band or stop-loss",
                "exit_long",
                [
                    cond(price(), "cross_above", boll("middle", 20, 2.0)),
                    exit_cond("stop_loss_pct",   3.0, combiner="or"),
                    exit_cond("take_profit_pct", 6.0, combiner="or"),
                ],
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
                "Sell when price crosses below 21-EMA or stop-loss",
                "exit_long",
                [
                    cond(price(), "cross_below", ema(21)),
                    exit_cond("stop_loss_pct", 3.0, combiner="or"),
                ],
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
            n_op({"type": "lookback", "field": "mid", "period": 5}),
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

]


# ── DB insertion ──────────────────────────────────────────────────────────────

def seed():
    conn = get_db_conn()
    cur  = conn.cursor()

    # ── strategies ────────────────────────────────────────────────────────────
    s_inserted = 0
    s_skipped  = 0
    for s in STRATEGIES:
        cur.execute("SELECT id FROM strategies WHERE name = ?", (s["name"],))
        row = cur.fetchone()
        if row:
            # Ensure is_builtin flag is set on existing rows
            cur.execute("UPDATE strategies SET is_builtin = 1 WHERE id = ?", (row["id"],))
            s_skipped += 1
            continue
        config = s["config"]
        config_str = json.dumps({"rule_set": config}) if "rules" in config else json.dumps(config)
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
