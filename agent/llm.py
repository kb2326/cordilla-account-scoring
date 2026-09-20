"""The language model seam, and the mock that stands in for it.

`complete()` calls Anthropic when ANTHROPIC_API_KEY is set and falls back to a
deterministic stand-in when it is not. Both paths go through the same prompt, the
same verifier and the same cost accounting, so the repo runs for a reviewer with no
key and still exercises the real integration for anyone who has one.

Which path ran is recorded in every run: `cost.mocked` and `cost.model` in
runs.jsonl. sample_run/ holds output from a live call so the difference is visible
without needing a key.

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

SYSTEM_PROMPT = """You write one short call brief for a B2B sales development rep who
is about to phone this account.

Hard rules:
- 2 to 3 sentences, plain English, no sales jargon, no adjectives like "exciting".
- NEVER write a digit. Not one. Every number must be a {{placeholder}} taken from
  placeholders_available. To mention website visits, write {{web_touchpoints_90d}},
  never the number itself. A brief containing a digit is rejected automatically.
- Do not invent facts. Use only what is in facts_you_may_reference.
- If snapshot_age_days is large, say plainly that the information is old and should
  be treated as historical rather than current.
- Finish with one specific opening line the rep could say out loud.
- Plain prose only. No headings, no bold, no bullet points, no labels like
  "Opening line:". This goes into a list that already has its own formatting.

You are writing for someone who will read this aloud thirty seconds from now."""


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
    by a normal run, and it forces the mock even when a key is present so the demo
    is deterministic and free.
    """
    if os.getenv("ANTHROPIC_API_KEY") and not hallucinate:
        return _complete_live(user_prompt)
    return _complete_mock(user_prompt, hallucinate=hallucinate)


LIVE_MODEL = "claude-haiku-4-5-20251001"
# Published rates for that model, USD per million tokens. Still an assumption in the
# sense that they are read off a price list rather than an invoice, but the token
# counts on this path come from the API response, not an estimate.
LIVE_PRICE_INPUT_PER_M = 1.00
LIVE_PRICE_OUTPUT_PER_M = 5.00


def _complete_live(user_prompt: str) -> Completion:
    """The real call. Small model, zero temperature, tight token budget.

    A cheap model is the right choice here and the reason is design, not economy:
    the task is writing two sentences over facts that have already been decided.
    Every number is supplied, every decision is made. There is nothing to reason
    about, so paying for reasoning would be paying for variance.
    """
    from langchain_anthropic import ChatAnthropic  # lazy: the repo runs without it

    model = ChatAnthropic(model=LIVE_MODEL, max_tokens=300, temperature=0)
    response = model.invoke([("system", SYSTEM_PROMPT), ("human", user_prompt)])

    usage = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = int(usage.get("input_tokens") or estimate_tokens(SYSTEM_PROMPT + user_prompt))
    completion_tokens = int(usage.get("output_tokens") or estimate_tokens(str(response.content)))
    usd = round(prompt_tokens / 1e6 * LIVE_PRICE_INPUT_PER_M
                + completion_tokens / 1e6 * LIVE_PRICE_OUTPUT_PER_M, 6)
    text = response.content if isinstance(response.content, str) else response.text()
    return Completion(text=text.strip(), prompt_tokens=prompt_tokens,
                      completion_tokens=completion_tokens, usd=usd,
                      model=LIVE_MODEL, mocked=False)


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
