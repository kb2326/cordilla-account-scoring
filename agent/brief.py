"""Turn a decided account into two sentences a rep can use - without letting the
language model near a number.

The split: the model writes the sentence and chooses the emphasis; code owns every
figure in it. The model emits {{placeholders}}, the filler substitutes values from
the account's fact set, and the verifier rejects any digit the model typed itself.

Why bother, when a template alone would do? Because the template is the fallback,
not the goal - a model writes a better sentence, and the day someone swaps the mock
for a real call, this is the machinery that stops a confident wrong number being
read aloud to a customer. Wrong numbers in a rep's mouth are how the last scoring
effort at Cordilla lost its credibility, and that failure leaves no error behind.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import llm
from .explain import fact_set

SLOT = re.compile(r"\{\{(\w+)\}\}")
# A digit anywhere outside a placeholder. Deliberately blunt: "12 visits", "3rd",
# "2026" and "40%" all trip it, because a model with a legitimate reason to write
# a number always has a placeholder available instead.
BARE_DIGIT = re.compile(r"\d")


@dataclass
class Brief:
    account_id: str
    text: str
    attempts: int = 1
    verified: bool = True
    violations: list[str] = field(default_factory=list)
    fell_back: bool = False
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def build_prompt(row, corrections: list[str] | None = None) -> str:
    """Everything the model is allowed to know, as JSON.

    It sees facts and pre-computed evidence phrases, never the raw frame, and
    never other accounts. Nothing here is free text it could misread.
    """
    facts = fact_set(row)
    payload = {
        "action": row.action,
        "snapshot_age_days": facts["snapshot_age_days"],
        "facts_you_may_reference": facts,
        "placeholders_available": sorted(facts.keys()),
    }
    if corrections:
        # A retry that re-asks the identical question only works against a
        # deterministic stand-in. A real model needs to be told what was wrong with
        # its last attempt, or the second call fails exactly like the first.
        payload["your_previous_attempt_was_rejected_because"] = corrections
    return json.dumps(payload, indent=1)


def verify(text: str, facts: dict) -> list[str]:
    """Two failure modes, both fatal to trust.

    1. a placeholder we cannot fill - the model invented a field;
    2. a digit outside a placeholder - the model wrote a number itself.
    """
    violations = []
    for slot in SLOT.findall(text):
        if slot not in facts:
            violations.append(f"unknown placeholder {{{{{slot}}}}}")
    stripped = SLOT.sub("", text)
    if BARE_DIGIT.search(stripped):
        found = "".join(sorted(set(re.findall(r"\d+", stripped))))
        violations.append(f"model wrote a number itself ({found}); numbers must come from placeholders")
    return violations


def fill(text: str, facts: dict) -> str:
    def replace(match: re.Match) -> str:
        value = facts[match.group(1)]
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    return SLOT.sub(replace, text)


def fallback_text(row) -> str:
    """Deterministic, unglamorous, always correct. Used when the model fails twice."""
    facts = fact_set(row)
    age = facts["snapshot_age_days"]
    currency = "current" if age <= 90 else f"{age} days old - treat the activity as historical"
    return (f"{facts['account_id']}, {facts['employee_count']}-person {facts['industry']} company, "
            f"ranked {facts['score_rank']} today. What stands out: {facts['evidence']}. "
            f"Record is {currency}.")


def generate(row, hallucinate: bool = False, corrections: list[str] | None = None):
    """One attempt. The graph owns the retry, not this function.

    Deliberate: a retry loop buried in a helper is invisible in the flow diagram
    and untestable on its own. As a graph cycle it shows up in the picture, the
    attempt count lands in the run record, and the node can be invoked alone.
    """
    return llm.complete(build_prompt(row, corrections), hallucinate=hallucinate)


def accept(row, text: str) -> tuple[str | None, list[str]]:
    """Fill the placeholders if the text is clean; otherwise say what was wrong."""
    facts = fact_set(row)
    violations = verify(text, facts)
    if violations:
        return None, violations
    return fill(text, facts), []


def render_markdown(frame, briefs: dict[str, Brief]) -> str:
    """What the rep actually reads, in queue order."""
    lines = ["# Call briefs", ""]
    queued = frame[frame.queued].sort_values("score", ascending=False)
    for row in queued.itertuples(index=False):
        brief = briefs.get(row.account_id)
        if brief is None:
            continue
        flag = "" if brief.verified else "  _(template fallback: model output failed verification)_"
        lines += [
            f"### {int(row.queue_position)}. {row.account_id} — {row.action.replace('_', ' ').title()}{flag}",
            "",
            brief.text,
            "",
            f"*Why it surfaced: {row.reason}*",
            "",
        ]
    return "\n".join(lines)
