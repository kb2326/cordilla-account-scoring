"""Write the run's outputs. Four audiences, four artifacts, one record.

Kept out of graph.py so the graph reads as decisions rather than file handling,
and so the formats can change without touching the flow.

The split matters more than it looks. A rep needs 20 rows and a sentence; RevOps
needs a different 7 rows; a manager needs five lines of English; the analyst needs
every account with every flag, in a shape that joins to Salesforce outcomes in 90
days' time. One combined CSV would serve none of them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .policy import CALL_NOW, CALL_WITH_CAVEAT, RE_ENRICH

# The analyst's table. Ordered deliberately: identity, decision, then the evidence
# behind the decision, so the file is readable left to right without a schema.
DECISION_COLUMNS = [
    "run_id", "as_of", "account_id", "account_type", "industry",
    "action", "reason", "queued", "queue_position", "in_holdout",
    "score", "rank", "snapshot_age_days", "intent_imputed", "never_contacted",
    "score_if_intent_low", "score_if_intent_high", "why",
    # Present only when --investigate ran. The analyst needs to see which decisions a
    # model touched, what it said, and whether policy overrode it.
    "investigated", "investigator_action", "investigator_rationale", "investigator_vetoed",
]


def write_outputs(df: pd.DataFrame, run_record: dict, output_dir: Path,
                  briefs_markdown: str | None = None,
                  investigation: list[dict] | None = None) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    # --- the rep's queue -------------------------------------------------------
    queue = df[df.queued].sort_values("score", ascending=False)
    queue_out = queue[[
        "queue_position", "account_id", "account_type", "industry", "employee_count",
        "action", "score", "snapshot_age_days", "why", "reason",
    ]].rename(columns={"why": "talking_points", "reason": "why_this_account"})
    written["call_queue"] = _csv(queue_out, output_dir / "call_queue.csv")

    # --- RevOps' list ----------------------------------------------------------
    enrich = df[df.action == RE_ENRICH].sort_values("score", ascending=False)
    enrich_out = enrich[[
        "account_id", "account_type", "industry", "score",
        "snapshot_age_days", "intent_imputed", "reason",
    ]].rename(columns={"reason": "why_refresh"})
    written["enrichment_requests"] = _csv(enrich_out, output_dir / "enrichment_requests.csv")

    # --- the analyst's table ---------------------------------------------------
    decisions = df.assign(run_id=run_record["run_id"], as_of=run_record["as_of"])
    decisions = decisions[[c for c in DECISION_COLUMNS if c in decisions.columns]]
    written["decisions"] = _csv(decisions, output_dir / "decisions.csv")

    # --- the run record, appended not overwritten ------------------------------
    runs_path = output_dir / "runs.jsonl"
    with runs_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run_record, default=str) + "\n")
    written["runs"] = runs_path

    if briefs_markdown:
        written["briefs"] = _text(briefs_markdown, output_dir / "briefs.md")

    if investigation:
        written["investigation"] = _text(_investigation_text(investigation),
                                         output_dir / "investigation.md")

    written["summary"] = _text(_summary_text(df, run_record), output_dir / "run_summary.txt")
    return written


def _csv(frame: pd.DataFrame, path: Path) -> Path:
    frame.to_csv(path, index=False)
    return path


def _text(content: str, path: Path) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _summary_text(df: pd.DataFrame, run: dict) -> str:
    """Five lines a sales manager can read without asking what a percentile is."""
    counts = run["counts"]
    health = run["batch_health"]
    lines = [
        f"Account triage - {run['as_of']} (run {run['run_id'][:8]})",
        "",
        f"  {counts['scored']} accounts reviewed.",
        f"  {counts['queued']} went to reps to call today.",
        f"  {counts['by_action'][RE_ENRICH]} need their data refreshed before anyone calls them.",
        f"  {counts['by_action']['NURTURE']} went to marketing.",
        f"  {counts['held_out']} good-looking accounts were deliberately held back, unworked, so we can",
        f"     measure in 90 days whether this is actually beating guesswork.",
        "",
        f"  Data quality: {health['status'].upper()}",
    ]
    for alert in health.get("alerts", []):
        lines.append(f"    - {alert}")
    if not health.get("alerts"):
        lines.append("    - nothing unusual about today's batch")

    stale_share = float((df.snapshot_age_days > 90).mean())
    lines += [
        "",
        f"  Worth knowing: {stale_share:.0%} of these accounts are working from information more",
        f"  than 3 months old. Those are flagged in the queue, not hidden.",
        "",
        f"  Run took {_duration(run['duration_ms'])} and cost ${run['cost']['usd']:.2f}.",
    ]
    return "\n".join(lines) + "\n"


def _investigation_text(transcripts: list[dict]) -> str:
    """What the boundary-account agent looked at, and what it concluded.

    Written out per account because "the agent decided" is not an audit trail. Which
    tools it chose is as informative as the answer - an account it resolved in two
    checks was never really ambiguous.
    """
    lines = ["# Boundary accounts: what the investigator did", "",
             "These are the accounts where the rules were close to arbitrary. Each was given to a",
             "tool-using agent that chose what to check and then recommended an action. The policy",
             "keeps the final say; any override is recorded.", ""]
    for t in transcripts:
        changed = t["recommended"] and t["recommended"] != t["rule_based"]
        lines += [
            f"### {t['account_id']}",
            "",
            f"- rules said: **{t['rule_based']}**",
            f"- agent recommended: **{t['recommended']}**" + ("  ← changed" if changed else ""),
            f"- checks it chose to run: {', '.join(t['tools_called']) or 'none'}",
            "",
            f"> {t['rationale']}",
            "",
        ]
    return chr(10).join(lines)


def _duration(ms: float) -> str:
    """Seconds for a human, milliseconds only when it really is that fast.

    The run record keeps the raw number; this is the line a sales manager reads,
    and '46701.2 ms' is engineer units leaking into somebody else's document.
    """
    return f"{ms/1000:.0f} seconds" if ms >= 1000 else f"{ms:.0f} ms"


def new_run_record(run_id: str, as_of: str, **parts) -> dict:
    """The observability payload. One line per run, appended to runs.jsonl.

    Input and model hashes are in here so that a surprising queue can always be
    traced back to exactly which file and which artifact produced it - the first
    question anyone asks when a list looks wrong three weeks later.
    """
    return {
        "run_id": run_id,
        "as_of": as_of,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **parts,
    }
