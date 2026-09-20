"""The run, as a state machine.

Why a graph and not a script - the honest version. The scoring path here is
deterministic, and stripped of the gate below this is about 150 lines of straight
Python. Four things earn the framework:

  1. the batch can stop. quality_gate routes to a halt that publishes nothing,
     and that branch is visible in the diagram rather than buried in an if;
  2. publishing pauses for a human when the batch looks odd - interrupt() is a
     first-class pause with the state preserved, not a boolean threaded through
     three functions;
  3. each decision is a node that can be invoked on its own in a REPL, which is
     how the policy bug in commit 67c2ec3 was found;
  4. retries and their reasons are declared per node instead of hand-rolled.

What LangGraph is NOT doing here is scheduling. In production this run is
triggered by Airflow or a Cloud Run job on a cron; the graph is what happens
inside one run. Conflating those two is how people end up with a graph library
impersonating a scheduler.

State note, learned the hard way: checkpointed state must be serializable, and
that includes InMemorySaver - it msgpack-encodes everything on the way in. My
first version carried the DataFrame in state and died on "Type is not msgpack
serializable: DataFrame". So state holds decisions, counts and health - things
worth replaying - while the batch itself lives in a run-scoped workspace passed
through context, which is never checkpointed. A distributed setup would go one
step further and put a parquet path in state instead of a frame anywhere.
"""

from __future__ import annotations

import operator
import time
from concurrent.futures import ThreadPoolExecutor
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

import pandas as pd
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy, interrupt

from monitoring import checks as monitoring_checks

from . import brief as brief_mod
from . import investigator, llm
from .contracts import add_quality_flags, validate_batch
from .emit import new_run_record, write_outputs
from .explain import baseline_from, explain_batch
from .policy import PolicyConfig, apply_capacity, assign_actions, summarise
from .scoring import LoadedModel, score_batch


class RunState(TypedDict, total=False):
    run_id: str
    rows: int                    # the batch lives in Deps.workspace, not here
    batch_health: dict
    counts: dict
    cost: dict
    brief_attempt: int            # drives the write -> verify -> write cycle
    briefs_pending: list          # account_ids still without an accepted brief
    brief_violations: dict        # account_id -> why the last attempt was rejected
    investigation: dict           # what the boundary-account agent did, if it ran
    written: dict
    halted: bool
    approved: bool
    investigate_requested: bool
    events: Annotated[list, operator.add]   # append-only; every node adds one


@dataclass
class Deps:
    """Everything the run needs from outside. Injected, never held in state."""
    model: LoadedModel
    policy: PolicyConfig
    baseline: dict               # analysis/findings.json
    reference: pd.DataFrame      # training data, for explanation baselines
    as_of: pd.Timestamp
    accounts_path: Path
    output_dir: Path
    auto_approve: bool = False   # CLI sets this; a human answers otherwise
    max_brief_attempts: int = 2  # then the deterministic template takes over
    hallucinate: bool = False    # demo switch: make the stand-in type a number
    investigate: bool = False    # send boundary accounts to the tool-using agent
    investigate_limit: int = 20  # how many, at roughly a cent each
    # Run-scoped scratch space for the batch itself. Context is not checkpointed,
    # so this is the seam between "state worth replaying" and "data too big and
    # too un-serializable to belong in a checkpoint".
    workspace: dict = field(default_factory=dict)


def _event(node: str, started: float, **extra: Any) -> dict:
    return {"node": node, "ms": round((time.perf_counter() - started) * 1000, 1), **extra}


# --------------------------------------------------------------------------- nodes

def load_batch(state: RunState, runtime: Runtime[Deps]) -> dict:
    t0 = time.perf_counter()
    d = runtime.context
    frame = pd.read_csv(d.accounts_path)
    # Structural validation raises here rather than returning a status: a batch
    # with missing columns or impossible values is not a degraded run, it is not
    # a run at all.
    validate_batch(frame).raise_if_failed()
    d.workspace["frame"] = add_quality_flags(frame, d.as_of)
    return {"rows": len(frame), "events": [_event("load_batch", t0, rows=len(frame))]}


def quality_gate(state: RunState, runtime: Runtime[Deps]) -> dict:
    """Does this batch look like the population the model was fitted on?"""
    t0 = time.perf_counter()
    health = monitoring_checks.run_input_checks(runtime.context.workspace["frame"], runtime.context.baseline)
    return {
        "batch_health": health.to_dict(),
        "events": [_event("quality_gate", t0, status=health.status)],
    }


def halt(state: RunState, runtime: Runtime[Deps]) -> dict:
    """A red batch publishes nothing. A late queue costs a morning; a wrong one costs trust."""
    t0 = time.perf_counter()
    return {"halted": True, "events": [_event("halt", t0)]}


def score(state: RunState, runtime: Runtime[Deps]) -> dict:
    t0 = time.perf_counter()
    frame = runtime.context.workspace["frame"].copy()
    frame["score"] = score_batch(runtime.context.model, frame)
    health = monitoring_checks.run_score_checks(frame["score"], runtime.context.baseline)
    merged = monitoring_checks.merge(
        monitoring_checks.BatchHealth(
            status=state["batch_health"]["status"],
            checks=[monitoring_checks.Check(**c) for c in state["batch_health"]["checks"]],
        ),
        health,
    )
    runtime.context.workspace["frame"] = frame
    return {
        "batch_health": merged.to_dict(),
        "events": [_event("score", t0, mean=round(float(frame.score.mean()), 4))],
    }


def explain(state: RunState, runtime: Runtime[Deps]) -> dict:
    t0 = time.perf_counter()
    d = runtime.context
    d.workspace["frame"] = explain_batch(d.model, d.workspace["frame"], baseline_from(d.reference), d.as_of)
    return {"events": [_event("explain", t0)]}


def triage(state: RunState, runtime: Runtime[Deps]) -> dict:
    t0 = time.perf_counter()
    d = runtime.context
    frame = assign_actions(d.workspace["frame"], d.policy)
    frame = apply_capacity(frame, d.policy)
    d.workspace["frame"] = frame
    counts = summarise(frame)
    return {"counts": counts, "events": [_event("triage", t0, **counts["by_action"])]}



def write_briefs(state: RunState, runtime: Runtime[Deps]) -> dict:
    """Ask the language model for a brief per queued account still needing one.

    The model writes sentences containing {{placeholders}} and no digits. It never
    sees the frame, other accounts, or any tool - it is handed a fact set and asked
    for two sentences. That is the whole of its authority in this system.
    """
    t0 = time.perf_counter()
    d = runtime.context
    frame = d.workspace["frame"]
    drafts = d.workspace.setdefault("drafts", {})

    pending = state.get("briefs_pending") or list(frame[frame.queued].account_id)
    cost = dict(state.get("cost") or {"llm_calls": 0, "prompt_tokens": 0,
                                      "completion_tokens": 0, "usd": 0.0})

    violations = state.get("brief_violations") or {}
    # Sequentially this node was 39.6s of a 39.8s run - 16 independent API calls
    # waiting on each other for no reason. They share nothing, so a small pool
    # turns it into ~4s. Deliberately small: four concurrent calls is polite to
    # rate limits, and this is a nightly batch, not a latency-critical path.
    def draft_one(account_id: str):
        row = frame[frame.account_id == account_id].iloc[0]
        return account_id, brief_mod.generate(row, hallucinate=d.hallucinate,
                                              corrections=violations.get(account_id))

    with ThreadPoolExecutor(max_workers=4) as pool:
        for account_id, completion in pool.map(draft_one, pending):
            drafts[account_id] = completion.text
            cost["llm_calls"] += 1
            cost["prompt_tokens"] += completion.prompt_tokens
            cost["completion_tokens"] += completion.completion_tokens
            cost["usd"] = round(cost["usd"] + completion.usd, 6)
            cost["model"] = completion.model
            cost["mocked"] = completion.mocked

    cost["pricing"] = "ASSUMED rates in agent/llm.py; token counts measured on the real prompt"
    attempt = state.get("brief_attempt", 0) + 1
    return {
        "cost": cost,
        "brief_attempt": attempt,
        "events": [_event("write_briefs", t0, attempt=attempt, drafted=len(pending))],
    }


def verify_briefs(state: RunState, runtime: Runtime[Deps]) -> dict:
    """Reject any brief containing a number the model typed itself.

    Not a small problem: a rep reads this aloud to a customer. Failures go back to
    write_briefs; anything still failing after the attempt budget gets the
    deterministic template instead of a third roll of the dice.
    """
    t0 = time.perf_counter()
    d = runtime.context
    frame = d.workspace["frame"]
    briefs = d.workspace.setdefault("briefs", {})
    drafts = d.workspace.get("drafts", {})

    still_failing, rejected = [], []
    for account_id, draft in list(drafts.items()):
        row = frame[frame.account_id == account_id].iloc[0]
        text, violations = brief_mod.accept(row, draft)
        if text is not None:
            briefs[account_id] = brief_mod.Brief(
                account_id=account_id, text=text,
                attempts=state["brief_attempt"], verified=True)
            drafts.pop(account_id)
        else:
            rejected.append((account_id, violations))
            still_failing.append(account_id)

    if state["brief_attempt"] >= d.max_brief_attempts:
        for account_id in still_failing:
            row = frame[frame.account_id == account_id].iloc[0]
            briefs[account_id] = brief_mod.Brief(
                account_id=account_id, text=brief_mod.fallback_text(row),
                attempts=state["brief_attempt"], verified=False, fell_back=True,
                violations=[v for a, vs in rejected if a == account_id for v in vs])
            drafts.pop(account_id, None)
        still_failing = []

    cost = dict(state["cost"])
    cost["rejected_by_verifier"] = cost.get("rejected_by_verifier", 0) + len(rejected)
    cost["fell_back_to_template"] = sum(1 for b in briefs.values() if b.fell_back)
    cost["briefs_written"] = len(briefs)
    return {
        "briefs_pending": still_failing,
        "brief_violations": {a: v for a, v in rejected},
        "cost": cost,
        "events": [_event("verify_briefs", t0, rejected=len(rejected), accepted=len(briefs))],
    }


def _route_after_verify(state: RunState) -> str:
    """The cycle: anything still failing goes back for another attempt."""
    return "write_briefs" if state.get("briefs_pending") else "publish"



def investigate(state: RunState, runtime: Runtime[Deps]) -> dict:
    """Send the genuinely ambiguous accounts to a tool-using agent.

    Off by default (--investigate turns it on), and skipped without a live model,
    because a loop whose whole point is choosing what to check next cannot be
    faked by a deterministic stand-in. Skipping is recorded, not silent.
    """
    t0 = time.perf_counter()
    d = runtime.context
    frame = d.workspace["frame"]

    if not investigator.available():
        return {"investigation": {"ran": False, "reason": "no ANTHROPIC_API_KEY; needs a live model"},
                "events": [_event("investigate", t0, skipped=True)]}

    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(model=llm.LIVE_MODEL, max_tokens=700, temperature=0)
    app = investigator.build_investigator(model)
    candidates = investigator.select_boundary_accounts(frame, d.policy.call_threshold,
                                                       limit=d.investigate_limit)

    def investigate_one(row):
        ctx = investigator.account_context(row, frame, d.policy.call_threshold)
        final = app.invoke(
            {"messages": [("user", investigator.opening_message(ctx))], "account": ctx,
             "checks_run": []},
            # A hard ceiling on the loop. A model that cannot decide in this many
            # turns is not going to, and an agent without a stop condition is an
            # outage waiting for a quiet weekend.
            {"recursion_limit": 12},
        )
        return row, final

    results, transcripts, calls = {}, [], 0
    tokens_in = tokens_out = 0
    # Same reasoning as write_briefs: 20 independent investigations, nothing shared.
    # Sequentially this was 152s of wall clock, which is fine for a nightly batch and
    # unbearable in front of a panel.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, final in pool.map(investigate_one, candidates.itertuples(index=False)):
            recommendation = final.get("recommendation") or {}
            results[row.account_id] = recommendation
            for m in final["messages"]:
                if m.type != "ai":
                    continue
                calls += 1
                usage = getattr(m, "usage_metadata", None) or {}
                tokens_in += int(usage.get("input_tokens") or 0)
                tokens_out += int(usage.get("output_tokens") or 0)
            transcripts.append({
                "account_id": row.account_id,
                "rule_based": row.action,
                "tools_called": final.get("checks_run", []),
                "recommended": recommendation.get("action"),
                "rationale": recommendation.get("rationale"),
            })
    transcripts.sort(key=lambda t: t["account_id"])

    # The investigator spends real money and it belongs in the same cost line as the
    # briefs. Leaving it out would make "cost is measured" quietly false - it is more
    # than half the model spend on a run that uses it.
    investigation_usd = round(tokens_in / 1e6 * llm.LIVE_PRICE_INPUT_PER_M
                              + tokens_out / 1e6 * llm.LIVE_PRICE_OUTPUT_PER_M, 6)
    cost = dict(state.get("cost") or {"llm_calls": 0, "prompt_tokens": 0,
                                      "completion_tokens": 0, "usd": 0.0})
    cost["llm_calls"] = cost.get("llm_calls", 0) + calls
    cost["prompt_tokens"] = cost.get("prompt_tokens", 0) + tokens_in
    cost["completion_tokens"] = cost.get("completion_tokens", 0) + tokens_out
    cost["usd"] = round(cost.get("usd", 0.0) + investigation_usd, 6)
    cost["investigation_usd"] = investigation_usd
    cost["model"] = llm.LIVE_MODEL
    cost["mocked"] = False

    reviewed = investigator.apply_recommendations(frame, results, d.policy.call_threshold)
    # The queue is built FROM actions, and we have just changed actions - so it has to
    # be rebuilt, or the advice is cosmetic. Caught by checking the output rather than
    # the code: six accounts the agent had sent for enrichment were still sitting in
    # the rep's call list, correctly labelled and entirely wrong to be there.
    d.workspace["frame"] = apply_capacity(reviewed, d.policy)
    d.workspace["investigation"] = transcripts

    changed = sum(1 for t in transcripts if t["recommended"] and t["recommended"] != t["rule_based"])
    return {
        "cost": cost,
        "investigation": {
            "ran": True, "accounts": len(transcripts), "llm_calls": calls,
            "changed_from_rules": changed,
            "vetoed": int(d.workspace["frame"].investigator_vetoed.notna().sum()),
            "model": llm.LIVE_MODEL, "usd": investigation_usd,
        },
        "counts": summarise(d.workspace["frame"]),
        "events": [_event("investigate", t0, accounts=len(transcripts), changed=changed)],
    }


def publish(state: RunState, runtime: Runtime[Deps]) -> dict:
    """Write the outputs - but pause first if the batch looked unusual.

    The interrupt is deliberately placed before any file is written, and the node
    re-runs from the top on resume, so nothing is half-published while waiting.
    """
    t0 = time.perf_counter()
    d = runtime.context
    health = state["batch_health"]
    approved = True

    if health["status"] != monitoring_checks.GREEN and not d.auto_approve:
        decision = interrupt({
            "question": "This batch failed one or more checks. Publish it to reps anyway?",
            "status": health["status"],
            "alerts": health["alerts"],
            "would_queue": state["counts"]["queued"],
        })
        approved = bool(decision.get("approve")) if isinstance(decision, dict) else bool(decision)

    if not approved:
        return {"approved": False, "halted": True, "events": [_event("publish", t0, published=False)]}

    frame = d.workspace["frame"]
    total_ms = sum(e["ms"] for e in state["events"]) + (time.perf_counter() - t0) * 1000
    record = new_run_record(
        run_id=state["run_id"],
        as_of=str(d.as_of.date()),
        duration_ms=round(total_ms, 1),
        input={"file": d.accounts_path.name, "rows": int(len(frame))},
        model={"sklearn": d.model.running_sklearn, "description": d.model.describe()},
        config={
            "call_threshold": d.policy.call_threshold,
            "nurture_threshold": d.policy.nurture_threshold,
            "stale_after_days": d.policy.stale_after_days,
            "expired_after_days": d.policy.expired_after_days,
            "capacity": d.policy.capacity,
            "holdout_share": d.policy.holdout_share,
            "assumptions": d.policy.notes,
        },
        counts=state["counts"],
        cost=state.get("cost", {"usd": 0.0, "llm_calls": 0}),
        batch_health=health,
        investigation=state.get("investigation", {"ran": False, "reason": "not requested"}),
        node_ms={e["node"]: e["ms"] for e in state["events"]},
    )
    written = write_outputs(
        frame, record, d.output_dir,
        briefs_markdown=brief_mod.render_markdown(frame, d.workspace.get("briefs", {})),
        investigation=d.workspace.get("investigation"),
    )
    return {
        "approved": True,
        "written": {k: str(v) for k, v in written.items()},
        "events": [_event("publish", t0, published=True)],
    }


def _route_after_triage(state: RunState) -> str:
    """Only worth the detour when it was asked for."""
    return "investigate" if state.get("investigate_requested") else "write_briefs"


def _route_after_gate(state: RunState) -> str:
    """Red stops the run. Amber continues to a human at the publish step."""
    return "halt" if state["batch_health"]["status"] == monitoring_checks.RED else "score"


def build_graph():
    g = StateGraph(RunState, context_schema=Deps)
    # Reading a file and calling a model are the only steps that can fail for
    # reasons a retry would fix. The rest are pure functions over a DataFrame:
    # retrying them would just fail again more slowly.
    g.add_node("load_batch", load_batch, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("quality_gate", quality_gate)
    g.add_node("halt", halt)
    g.add_node("score", score, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("explain", explain)
    g.add_node("triage", triage)
    # Optional: a real agent loop for the ~20 accounts where the rules are
    # arbitrary. Everything else stays deterministic, which is what makes the
    # holdout comparison mean anything.
    g.add_node("investigate", investigate)
    # The language model step, and the check on it. Two nodes rather than one
    # function with a loop inside, so the retry is a visible cycle in the graph
    # instead of control flow buried in a helper.
    g.add_node("write_briefs", write_briefs, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("verify_briefs", verify_briefs)
    g.add_node("publish", publish)

    g.add_edge(START, "load_batch")
    g.add_edge("load_batch", "quality_gate")
    g.add_conditional_edges("quality_gate", _route_after_gate, {"halt": "halt", "score": "score"})
    g.add_edge("score", "explain")
    g.add_edge("explain", "triage")
    g.add_conditional_edges("triage", _route_after_triage,
                            {"investigate": "investigate", "write_briefs": "write_briefs"})
    g.add_edge("investigate", "write_briefs")
    g.add_edge("write_briefs", "verify_briefs")
    g.add_conditional_edges("verify_briefs", _route_after_verify,
                            {"write_briefs": "write_briefs", "publish": "publish"})
    g.add_edge("publish", END)
    g.add_edge("halt", END)
    return g.compile(checkpointer=InMemorySaver())


def new_run_id() -> str:
    return str(uuid.uuid4())
