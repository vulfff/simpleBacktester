"""
run_analyzer.py — Multi-turn AI chat analyst for backtest run results.
Injects a summarized run report (metrics, trades, equity summary) into the system
prompt and delegates to the active AI provider for each conversational turn.
"""
from __future__ import annotations

import json
from typing import Any

RUN_ANALYST_PROMPT = """You are an objective quantitative trading performance analyst.

Your role is to evaluate completed backtest runs based on their quantitative data.

Data layout:
- "metrics" contains aggregate statistics for the entire run (return, Sharpe, drawdown, win rate, etc.).
- "completed_trades" is a list of every finished trade — each entry is one round trip (entry + exit) with its entry date, exit date, entry price, exit price, PnL in dollars, PnL as a percentage, and outcome ("win" or "loss"). The count of completed_trades equals total_trades in metrics.
- "equity_summary" gives the starting and ending equity, peak equity, lowest equity, total bars, and starting/ending asset price.
- "execution" holds settings like sizing mode, leverage, and commission.

When talking to the user:
- Refer to "completed_trades" as "trades" or "completed trades". Never say "round_trips" or "completed_trades" as raw field names.
- Refer to "pnl" as "profit/loss" or "P&L". Refer to "pnl_pct" as "return on that trade".
- Refer to "entry_time"/"exit_time" as "entry date"/"exit date". Refer to "outcome" as "won" or "lost".
- Refer to sizing_mode="all_in" as "full-capital sizing" or "compounding mode".

Guidelines:
- Be factual and analytical. Ground every observation in the provided data.
- Identify both strengths and weaknesses with equal weight. Do not default to optimism or pessimism.
- Flag structural concerns explicitly: poor risk-adjusted returns (low Sharpe/Sortino), high drawdown relative to return, very few trades (insufficient sample size), concentrated win/loss periods, or real leverage above 1x.
- Full-capital sizing (sizing_mode="all_in") means all available cash is deployed on every trade and profits compound automatically. This is not a flaw — note it as a compounding approach with the trade-off of full concentration (no partial exposure).
- When the user asks about buy-and-hold comparison, derive it from price_start and price_end in the equity summary.
- Use plain language. Be concise. Avoid over-hedging with unnecessary caveats.
- Never speculate about future live performance or generalise beyond what the data shows.
- If a metric is null or missing, say so rather than guessing.
- Do not use markdown formatting. No asterisks, no headers, no bullet dashes, no code fences. Write in plain prose with simple line breaks where needed.
"""


def analyze_run_chat(
    run_data: dict[str, Any],
    messages: list[dict],
    provider: Any,
    temperature: float = 0.2,
    language_directive: str = "",
) -> str:
    """
    Multi-turn chat about a completed backtest run.

    run_data — summarized dict (not raw DB row; equity_curve excluded, equity_summary used instead)
    messages — full conversation history [{role, content}, ...]
    provider — AIProvider instance
    temperature — kept low (0.2) for objective analytical output
    """
    context_block = (
        "RUN PERFORMANCE REPORT (JSON):\n"
        "```json\n"
        + json.dumps(run_data, indent=2)
        + "\n```"
    )
    system = RUN_ANALYST_PROMPT + "\n\n" + context_block + language_directive
    return provider._call_api_multi(messages, system, temperature)
