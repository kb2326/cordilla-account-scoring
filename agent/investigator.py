"""A real agent, for the one decision in this system that needs one.

Everything else here is a workflow: 300 accounts down a fixed path, because the
facts are all present at load time and the routing rule is a threshold. There is
nothing to discover, so there is nothing to decide about what to discover.

About twenty accounts a run are different. They sit close enough to the call
threshold that the rule is arbitrary, and what you would want to check next depends
on what the last check said. Is the record simply too old to matter? If not, would
the intent score nobody measured have changed the answer? If it might, has anything
happened in the CRM since the snapshot? A human would work through that in a
minute, in no fixed order, stopping as soon as it was obvious. That is an agent
loop, and this is one:

    investigate  <-->  tools          the model picks the next tool
         |                            and stops when it has enough
         v
    recommendation  ->  policy veto   it advises; the rules still decide

Two boundaries make it safe to let a model drive:

  * Tools read from injected state, never from arguments the model invents. It
    chooses WHICH question to ask; it cannot choose what the facts are.
  * Its recommendation is checked against the same hard rules as everything else
    (see apply_recommendations). It can never promote an expired account to a call,
    however persuasive its reasoning.

Requires a live model - a tool-choosing loop cannot be meaningfully faked, so with
no ANTHROPIC_API_KEY this stage is skipped and the run records why.
"""

from __future__ import annotations

import operator
import os
from typing import Annotated, Literal

import pandas as pd
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from langgraph.types import Command

from .policy import CALL_NOW, CALL_WITH_CAVEAT, NURTURE, RE_ENRICH

# The model may recommend only these. Anything else is rejected before it reaches
# an account, so the vocabulary is a contract rather than a suggestion.
ALLOWED = (CALL_NOW, CALL_WITH_CAVEAT, RE_ENRICH, NURTURE)

SYSTEM = """You are triaging a single B2B sales account that our scoring rules could not
place confidently. It sits near the threshold where we decide whether a rep should
call it.

Investigate before you decide. You have tools that answer one question each. Call
the ones that would change your mind; skip the ones that would not. Most accounts
need two or three, not all of them.

Then call recommend_action exactly once with one of:
  CALL_NOW          the case for a call today is clear
  CALL_WITH_CAVEAT  worth a call, but the rep must know the data is not current
  RE_ENRICH         the decision depends on information we do not have or that has
                    expired; buy fresh data before spending a call
  NURTURE           not worth a rep's time now; marketing can keep it warm

Judge the evidence, not the score. A high score built on a year-old snapshot is a
reason to refresh, not to dial. Be brief and concrete in your rationale - one or two
sentences a sales manager would accept."""


class InvestigationState(MessagesState):
    """Separate from the batch graph's state on purpose.

    The parent run carries counts and health; this carries a conversation about one
    account. Sharing a schema between them would force every unrelated field through
    the checkpointer for no reason.
    """

    account: dict
    checks_run: Annotated[list, operator.add]
    recommendation: dict


# --------------------------------------------------------------------------- tools
# Each tool answers one question and returns a Command: the observation goes back to
# the model as a ToolMessage, and the state records that the check happened. State is
# injected, so the model chooses the question but never supplies the facts.


@tool
def check_data_freshness(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """How old is this account's information, and does that still describe the present?"""
    a = state["account"]
    age = a["snapshot_age_days"]
    verdict = ("current" if age <= 90 else
               "the 90-day activity window it describes closed before today" if age <= 365 else
               "expired - this describes a period more than a year ago")
    return Command(update={
        "messages": [ToolMessage(
            content=f"Snapshot is {age} days old ({verdict}). Every activity count in this "
                    f"record covers the 90 days ending on that date, not the 90 days ending today.",
            tool_call_id=tool_call_id)],
        "checks_run": ["check_data_freshness"],
    })


@tool
def probe_intent_sensitivity(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Would the buying-intent score we never measured have changed this decision?"""
    a = state["account"]
    if not a["intent_imputed"]:
        content = (f"Intent was actually measured for this account: {a['intent_score']:.1f}. "
                   f"Nothing is being guessed here.")
    else:
        low, high = a["score_if_intent_low"], a["score_if_intent_high"]
        straddles = min(low, high) < a["threshold"] <= max(low, high)
        content = (f"No intent data. The pipeline filled it with the population median, so the "
                   f"model read 'unknown' as 'average'. If the real value were low the score "
                   f"would be {low:.3f}; if high, {high:.3f}. The call threshold is "
                   f"{a['threshold']:.3f}, so the missing number "
                   f"{'WOULD change which side of the line this lands on' if straddles else 'would not change the decision'}.")
    return Command(update={
        "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)],
        "checks_run": ["probe_intent_sensitivity"],
    })


@tool
def compare_to_similar_accounts(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """How does this account look beside others of the same type in today's batch?"""
    a = state["account"]
    return Command(update={
        "messages": [ToolMessage(
            content=(f"Among {a['cohort_label']} accounts in this batch, its score of "
                     f"{a['score']:.3f} sits at the {a['cohort_percentile']:.0f}th percentile. "
                     f"Cohort median score {a['cohort_median_score']:.3f}, median snapshot age "
                     f"{a['cohort_median_age']:.0f} days."),
            tool_call_id=tool_call_id)],
        "checks_run": ["compare_to_similar_accounts"],
    })


@tool
def check_recent_crm_activity(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Has anything happened on this account since the snapshot was taken? (MOCKED)

    A real implementation queries Salesforce activity for events after snapshot_date:
    tasks, emails, opportunity changes, support tickets. The exercise ships two static
    CSVs and no CRM, so this returns the honest answer - that nothing is known - rather
    than inventing activity. The seam is this function body and nothing else.
    """
    a = state["account"]
    return Command(update={
        "messages": [ToolMessage(
            content=(f"[MOCKED CRM LOOKUP] No activity feed is available in this environment. "
                     f"What we know stops at the snapshot, {a['snapshot_age_days']} days ago. "
                     f"Treat the gap since then as unknown rather than as silence."),
            tool_call_id=tool_call_id)],
        "checks_run": ["check_recent_crm_activity"],
    })


@tool
def recommend_action(
    action: Literal["CALL_NOW", "CALL_WITH_CAVEAT", "RE_ENRICH", "NURTURE"],
    rationale: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Record the decision and end the investigation. Call exactly once."""
    return Command(update={
        "messages": [ToolMessage(content=f"Recorded: {action}", tool_call_id=tool_call_id)],
        "recommendation": {"action": action, "rationale": rationale.strip()},
    })


TOOLS = [check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts,
         check_recent_crm_activity, recommend_action]


# --------------------------------------------------------------------------- graph

def build_investigator(model):
    """The loop: the model calls tools until it recommends, then stops."""
    bound = model.bind_tools(TOOLS)

    def investigate(state: InvestigationState) -> dict:
        return {"messages": [bound.invoke([SystemMessage(content=SYSTEM)] + state["messages"])]}

    def after_tools(state: InvestigationState) -> str:
        # recommend_action is the only terminal tool; everything else loops back.
        return END if state.get("recommendation") else "investigate"

    g = StateGraph(InvestigationState)
    g.add_node("investigate", investigate)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "investigate")
    g.add_conditional_edges("investigate", tools_condition, {"tools": "tools", END: END})
    g.add_conditional_edges("tools", after_tools, {"investigate": "investigate", END: END})
    return g.compile()


def available() -> bool:
    """A tool-choosing loop cannot be meaningfully faked, so it needs a real model."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def select_boundary_accounts(frame: pd.DataFrame, threshold: float, band: float = 0.25,
                             limit: int = 20) -> pd.DataFrame:
    """The accounts where the rule is arbitrary and a second opinion is worth paying for.

    Two ways in: a score within +/-25% of the threshold, or an imputed intent value that
    could move the account across it. Everything else is decided by evidence the rules
    handle perfectly well, and sending those to a model would cost money to add variance.
    """
    near = (frame.score >= threshold * (1 - band)) & (frame.score <= threshold * (1 + band))
    straddles = frame.intent_imputed & (
        frame[["score_if_intent_low", "score_if_intent_high"]].min(axis=1) < threshold) & (
        frame[["score_if_intent_low", "score_if_intent_high"]].max(axis=1) >= threshold)
    return frame[near | straddles].nlargest(limit, "score")


def account_context(row, frame: pd.DataFrame, threshold: float) -> dict:
    """Everything the tools may reveal. Assembled by code, never by the model."""
    cohort = frame[frame.account_type == row.account_type]
    return {
        "account_id": row.account_id,
        "account_type": row.account_type,
        "industry": row.industry,
        "employee_count": int(row.employee_count),
        "score": float(row.score),
        "threshold": float(threshold),
        "snapshot_age_days": int(row.snapshot_age_days),
        "intent_imputed": bool(row.intent_imputed),
        "intent_score": None if row.intent_imputed else float(row.intent_score),
        "score_if_intent_low": float(row.score_if_intent_low),
        "score_if_intent_high": float(row.score_if_intent_high),
        "rule_based_action": row.action,
        "evidence": row.why,
        "cohort_label": row.account_type,
        "cohort_percentile": float((cohort.score < row.score).mean() * 100),
        "cohort_median_score": float(cohort.score.median()),
        "cohort_median_age": float(cohort.snapshot_age_days.median()),
    }


def opening_message(ctx: dict) -> str:
    return (
        f"Account {ctx['account_id']}: a {ctx['employee_count']}-person {ctx['industry']} "
        f"company, currently listed as a {ctx['account_type']}.\n"
        f"Model score {ctx['score']:.3f} against a call threshold of {ctx['threshold']:.3f}.\n"
        f"Our rules would currently say {ctx['rule_based_action']}.\n"
        f"Evidence behind the score: {ctx['evidence']}.\n\n"
        f"Investigate and recommend."
    )


def apply_recommendations(frame: pd.DataFrame, results: dict, threshold: float) -> pd.DataFrame:
    """The veto. The model advises; these rules still decide.

    Two things it can never do, no matter how good its reasoning: send an expired
    account to a rep, or promote an account that is below the evidence bar into a
    call. Both refusals are recorded rather than silently applied, because an
    override that leaves no trace is indistinguishable from a bug.
    """
    out = frame.copy()
    out["investigated"] = False
    out["investigator_action"] = None
    out["investigator_rationale"] = None
    out["investigator_vetoed"] = None

    for account_id, result in results.items():
        mask = out.account_id == account_id
        row = out[mask].iloc[0]
        proposed = result.get("action")
        rule_based = row.action
        veto = None

        # Decide the final action explicitly, then assign once. The first version of
        # this recorded the veto and assigned the model's action anyway - a guardrail
        # that logs a violation and then commits it. It never fired in a live run, so
        # only a deliberate test caught it. Guardrails need adversarial tests, not
        # observation.
        if proposed not in ALLOWED:
            veto, final = f"recommended an action outside the allowed set: {proposed!r}", rule_based
        elif proposed in (CALL_NOW, CALL_WITH_CAVEAT) and row.snapshot_age_days > 365:
            veto, final = "expired account (over a year old) cannot go to a rep", RE_ENRICH
        elif proposed == CALL_NOW and row.score < threshold:
            veto, final = "cannot promote an account below the evidence bar to CALL_NOW", rule_based
        elif proposed == CALL_NOW and row.snapshot_age_days > 90:
            veto, final = "data older than 90 days cannot be presented as current", CALL_WITH_CAVEAT
        else:
            final = proposed

        out.loc[mask, "investigated"] = True
        out.loc[mask, "investigator_action"] = proposed
        out.loc[mask, "investigator_rationale"] = result.get("rationale")
        out.loc[mask, "investigator_vetoed"] = veto
        out.loc[mask, "action"] = final
        out.loc[mask, "reason"] = (
            f"policy override ({veto}); investigator had said {proposed}" if veto
            else f"investigated: {result.get('rationale', '')}"
        )
    return out
