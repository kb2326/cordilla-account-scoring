"""The language model seam, and the mock that stands in for it.

No API key is provided for this exercise, so `complete()` returns a deterministic
stand-in. Everything around the call is real: the prompt is built exactly as it
would be sent, tokens are counted, cost is priced, and the result goes through the
same verifier a live response would. Swapping in a real model is the body of
`_complete_live()` and one environment variable.

WHERE A REAL CALL PLUGS IN
--------------------------
  model        a small, cheap one. This is constrained sentence-writing over
               facts that have already been decided, not reasoning.
  system       the SYSTEM_PROMPT below, verbatim
  user         the account's fact set, as JSON (see explain.fact_set)
  tools        none. The model writes one sentence; it does not choose actions,
               look anything up, or decide who gets called. Tool access here
               would be authority nobody asked for.
  returns      2-3 sentences containing {{slot}} placeholders and no digits
  guardrail    brief.verify() rejects any number the model typed itself and
               sends it back; after two attempts we fall back to a template.

COST
----
Prices below are a documented ASSUMPTION - published rates for a small model at
the time of writing - not a measurement. Token counts ARE measured, on the real
prompt. Everything in the run record is tagged accordingly, because a cost figure
that mixes the two is worse than no cost figure.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

MODEL_NAME = "mock-small-v1"
# USD per million tokens. ASSUMED, not measured.
PRICE_INPUT_PER_M = 0.80
PRICE_OUTPUT_PER_M = 4.00

SYSTEM_PROMPT = """You write one short call brief for a B2B sales rep.

Rules:
- 2 to 3 sentences. Plain English. No sales jargon, no adjectives like "exciting".
- You may ONLY refer to numbers using the {{placeholders}} provided. Never write a
  digit yourself. If you want to mention the number of website visits, write
  {{web_touchpoints_90d}}.
- If the account's information is old, say so plainly in the brief.
- End with a specific opening line the rep could actually use.
"""


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    usd: float
    model: str
    mocked: bool


def estimate_tokens(text: str) -> int:
    """~4 characters per token. An approximation, and labelled as one.

    A live call would report exact usage from the API response; this is the
    honest stand-in, and it is applied to the real prompt text rather than a
    guess at its length.
    """
    return max(1, len(text) // 4)


def price(prompt_tokens: int, completion_tokens: int) -> float:
    return round(prompt_tokens / 1e6 * PRICE_INPUT_PER_M + completion_tokens / 1e6 * PRICE_OUTPUT_PER_M, 6)


def complete(user_prompt: str, *, hallucinate: bool = False) -> Completion:
    """Return a brief. Live if a key is configured, mocked otherwise.

    `hallucinate` exists for the demo in monitoring/: it makes the stand-in type a
    number directly, which is what the verifier is there to catch. It is never set
    by a normal run.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return _complete_live(user_prompt)
    return _complete_mock(user_prompt, hallucinate=hallucinate)


def _complete_live(user_prompt: str) -> Completion:  # pragma: no cover - no key in this exercise
    """The real call. Untested here because no key is provided; kept honest and small.

        pip install langchain-anthropic
    """
    from langchain_anthropic import ChatAnthropic  # imported lazily so the repo runs without it

    model = ChatAnthropic(model="claude-haiku-4-5-20251001", max_tokens=300, temperature=0)
    response = model.invoke([("system", SYSTEM_PROMPT), ("human", user_prompt)])
    usage = getattr(response, "usage_metadata", {}) or {}
    prompt_tokens = usage.get("input_tokens", estimate_tokens(SYSTEM_PROMPT + user_prompt))
    completion_tokens = usage.get("output_tokens", estimate_tokens(response.text()))
    return Completion(
        text=response.text(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        usd=price(prompt_tokens, completion_tokens),
        model=model.model,
        mocked=False,
    )


# --------------------------------------------------------------------------- mock

# The stand-in composes from these. They are sentence shapes with slots - exactly
# the shape a real response is required to take - so the verifier, the slot filler
# and the cost accounting all exercise the same path they would in production.
_OPENINGS = {
    "CALL_NOW": "{{account_id}} is a {{employee_count}}-person {{industry}} company, ranked {{score_rank}} in today's batch.",
    "CALL_WITH_CAVEAT": "{{account_id}}, a {{employee_count}}-person {{industry}} company, ranked {{score_rank}} today.",
}
_AGE_CLAUSE = {
    "fresh": "Their record was refreshed {{snapshot_age_days}} days ago, so this is current.",
    "ageing": "Note their record is {{snapshot_age_days}} days old - treat the activity below as historical, not as something happening now.",
}
_CLOSERS = [
    "Open by asking what prompted the research rather than pitching.",
    "Open on the specific thing they looked at, not the product.",
    "Ask whether the evaluation is still live before anything else.",
]


def _complete_mock(user_prompt: str, *, hallucinate: bool = False) -> Completion:
    action = _extract(user_prompt, "action") or "CALL_NOW"
    age = int(_extract(user_prompt, "snapshot_age_days") or 0)

    opening = _OPENINGS.get(action, _OPENINGS["CALL_NOW"])
    age_clause = _AGE_CLAUSE["fresh"] if age <= 90 else _AGE_CLAUSE["ageing"]
    closer = _CLOSERS[age % len(_CLOSERS)]
    body = "What stands out: {{evidence}}."
    if hallucinate:
        # What a real model does under pressure: restates a number in its own
        # words, slightly wrong. The verifier's entire reason for existing.
        body = "What stands out: {{evidence}}. They have visited the site 12 times this month."

    text = f"{opening} {body} {age_clause} {closer}"
    prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user_prompt)
    completion_tokens = estimate_tokens(text)
    return Completion(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        usd=price(prompt_tokens, completion_tokens),
        model=MODEL_NAME,
        mocked=True,
    )


def _extract(prompt: str, key: str) -> str | None:
    match = re.search(rf'"{key}":\s*"?([^",\n}}]+)"?', prompt)
    return match.group(1).strip() if match else None
