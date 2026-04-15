"""
strategy_analyzer.py – Multi-turn AI chat about a saved trading strategy.

Uses the existing AIProvider framework from ai_strategy_builder.py.
The strategy definition is embedded in the system prompt so the AI has full
context for every turn of the conversation.
"""

from __future__ import annotations

import json
from typing import Any


STRATEGY_ANALYST_PROMPT = """You are an objective quantitative trading analyst. Your role is to provide
rigorous, unbiased assessments of rule-based trading strategies.

When answering, follow these principles:
- Be factual and analytical. Do not overstate a strategy's potential or dismiss its flaws.
- Ground every observation in the actual JSON definition — never invent rules that are not present.
- Identify both advantages AND disadvantages with equal weight. Avoid one-sided praise.
- Flag structural problems explicitly: missing exit rules, unbounded risk, no stop-loss,
  timing mismatches, parameter sensitivity, regime dependence, overfitting risk, look-ahead bias.
- When comparing to benchmarks (e.g. buy-and-hold), be precise about what conditions would
  favour or hurt the strategy.
- Suggest improvements only when asked, and back each suggestion with a concrete reason.
- Use plain language. Avoid jargon unless the context is clearly technical.
- Be concise. A focused, direct answer is more useful than a lengthy general overview.
- Never speculate about live performance without data. Reason from the rules only.
- Do not use markdown formatting. No asterisks, no headers, no bullet dashes, no code fences. Write in plain prose with simple line breaks where needed.

The strategy definition is provided below.
"""


def analyze_strategy_chat(
    strategy_data: dict[str, Any],
    messages: list[dict],
    provider: Any,
    temperature: float = 0.7,
    language_directive: str = "",
) -> str:
    """
    Run one turn of a multi-turn chat about a strategy.

    Args:
        strategy_data: The parsed strategy dict (name + rule_set config)
        messages: Full conversation history [{role: "user"|"assistant", content: str}, ...]
                  The last message must be the user's latest question.
        provider: Configured AIProvider instance from ai_strategy_builder
        temperature: AI creativity (0.0–1.0)

    Returns:
        The AI's plain-text reply for this turn.
    """
    context_block = (
        "STRATEGY DEFINITION (JSON):\n"
        "```json\n"
        + json.dumps(strategy_data, indent=2)
        + "\n```"
    )
    system = STRATEGY_ANALYST_PROMPT + "\n\n" + context_block + language_directive
    return provider._call_api_multi(messages, system, temperature)
