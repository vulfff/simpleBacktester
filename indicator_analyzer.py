"""
indicator_analyzer.py – Multi-turn AI chat about a saved custom indicator.

Uses the existing AIProvider framework from ai_strategy_builder.py.
The indicator's expression tree is embedded in the system prompt so the AI
has full context for every turn of the conversation.
"""

from __future__ import annotations

import json
from typing import Any


INDICATOR_ANALYST_PROMPT = """You are an objective technical analysis expert. Your role is to provide
rigorous, unbiased assessments of custom indicators defined as expression trees.

When answering, follow these principles:
- Be factual and precise. Derive all conclusions from the expression tree — never invent behaviour.
- State the mathematical computation clearly: what is calculated, in what order, using what inputs.
- Explicitly describe the output value range (e.g. "0 or 1", "unbounded positive", "0–100").
- Identify both useful properties AND limitations with equal weight:
  - Lag introduced by moving averages or lookback windows
  - Sensitivity to parameter choices (period length, threshold values)
  - Edge cases: division by zero, undefined early values (warmup), clamp saturation
  - Whether the indicator is scale-dependent or normalised
- If the tree uses ifelse nodes, describe the condition and both branches precisely.
- Walk through the expression tree step-by-step when explaining complex calculations.
- Suggest parameter tuning guidelines or use cases only when asked, grounded in the math.
- Be concise. A direct, precise answer is more useful than a lengthy explanation.
- Do not use markdown formatting. No asterisks, no headers, no bullet dashes, no code fences. Write in plain prose with simple line breaks where needed.

The indicator definition is provided below.
"""


def analyze_indicator_chat(
    indicator_data: dict[str, Any],
    messages: list[dict],
    provider: Any,
    temperature: float = 0.7,
    language_directive: str = "",
) -> str:
    """
    Run one turn of a multi-turn chat about an indicator.

    Args:
        indicator_data: The parsed indicator dict (name + expression tree)
        messages: Full conversation history [{role: "user"|"assistant", content: str}, ...]
                  The last message must be the user's latest question.
        provider: Configured AIProvider instance from ai_strategy_builder
        temperature: AI creativity (0.0–1.0)

    Returns:
        The AI's plain-text reply for this turn.
    """
    context_block = (
        "INDICATOR DEFINITION (JSON):\n"
        "```json\n"
        + json.dumps(indicator_data, indent=2)
        + "\n```"
    )
    system = INDICATOR_ANALYST_PROMPT + "\n\n" + context_block + language_directive
    return provider._call_api_multi(messages, system, temperature)
