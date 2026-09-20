"""What happens to each account, and why that number and not another.

Every threshold in this file has a measured source recorded next to it. They are
deliberately absolute - taken from the model's behaviour on its training data -
rather than relative to today's batch ("top 50"). Two reasons:

  * batches stay comparable over time, so a shift is visible rather than absorbed;
  * if a batch suddenly overflows the call tier, that is itself a signal, and a
    relative cut would hide it by construction.

Regenerate the provenance for any number here with:  python analysis/profile.py
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contracts import EXPIRED_DAYS, HORIZON_DAYS

# Actions, not scores. The output of this module is a decision a human can act on.
CALL_NOW = "CALL_NOW"
CALL_WITH_CAVEAT = "CALL_WITH_CAVEAT"
RE_ENRICH = "RE_ENRICH"
NURTURE = "NURTURE"
HOLD = "HOLD"


@dataclass(frozen=True)
class PolicyConfig:
    # --- score thresholds, from the model's own training distribution -----------
    # p90 = 0.1088. Above it, conversion runs at 26.7% against a 6.5% base (4.1x).
    # The next decile drops to 1.28x and decile 5 converts *worse* than decile 10,
    # so this is where the model's evidence stops, not a round number.
    call_threshold: float = 0.1088
    # p70 = 0.0727. Deciles 2-3 convert at ~1.3-1.4x: too weak to spend a call on,
    # strong enough for a campaign that costs nothing per account.
    nurture_threshold: float = 0.0727

    # --- freshness, from the features' own definition ---------------------------
    # Every activity column counts the 90 days before snapshot_date. Past that, the
    # window described no longer overlaps the window being predicted.
    stale_after_days: int = HORIZON_DAYS
    # Past a year, a call would reference events more than 12 months old.
    expired_after_days: int = EXPIRED_DAYS

    # --- operational ------------------------------------------------------------
    # Rep capacity for one run. ASSUMPTION, not measured: 5 SDRs x 40 dials. On the
    # 300-row exercise batch this never binds; on the real database it is the
    # binding constraint and the only reason ranking matters.
    capacity: int = 200
    # Hold back a share of the call tier, unworked, so lift can be measured against
    # something instead of asserted. 30% in the first quarter: at ~30 queued per
    # week, anything smaller cannot detect a change inside a quarter (the power
    # arithmetic is in PROPOSAL.md). Taper once a baseline exists.
    holdout_share: float = 0.30
    # Changing this re-randomises the control group and breaks comparability with
    # every earlier run, so it is a deliberate, versioned decision.
    holdout_salt: str = "cordilla-2026-q3"
    # Specified, not implemented: suppress accounts contacted in the last N days.
    # Needs a contact history this exercise does not ship. The seam is
    # apply_capacity(recently_contacted=...).
    cooldown_days: int = 30

    notes: dict[str, str] = field(default_factory=lambda: {
        "call_threshold": "training p90; decile 1 = 26.7% vs 6.5% base",
        "nurture_threshold": "training p70; deciles 2-3 = ~1.3x",
        "capacity": "ASSUMED 5 reps x 40 dials",
        "holdout_share": "ASSUMED 30%, from the power calculation in PROPOSAL.md",
    })


def assign_actions(df: pd.DataFrame, config: PolicyConfig) -> pd.DataFrame:
    """Give every account an action and a plain-English reason for it.

    Expects the columns added by contracts.add_quality_flags plus `score`, and
    optionally `intent_drives_score` from explain.py. Nothing is dropped: an
    account that gets no call still leaves with a recorded reason, because
    "why wasn't this one called?" is a question reps and managers actually ask.
    """
    required = {"score", "snapshot_age_days", "intent_imputed"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"assign_actions needs {sorted(missing)}; run add_quality_flags and score first")

    out = df.copy()
    # Optional input: explain.py sets this when the imputed intent value is one of
    # the two features doing the most work in that account's score. Absent it, we
    # do not guess - imputed intent alone becomes a caveat, not a re-enrichment.
    drives = out.get("intent_drives_score", pd.Series(False, index=out.index)).fillna(False)

    above_bar = out.score >= config.call_threshold
    expired = out.snapshot_age_days > config.expired_after_days
    stale = out.snapshot_age_days > config.stale_after_days
    # The score rests on a number nobody measured: refresh it, don't act on it.
    fabricated = out.intent_imputed & drives

    actions = np.select(
        [
            above_bar & (expired | fabricated),
            above_bar & stale,
            above_bar,
            out.score >= config.nurture_threshold,
        ],
        [RE_ENRICH, CALL_WITH_CAVEAT, CALL_NOW, NURTURE],
        default=HOLD,
    )
    out["action"] = actions
    out["reason"] = [
        _reason(row, config) for row in out.itertuples(index=False)
    ]
    return out


def _reason(row, config: PolicyConfig) -> str:
    """One sentence a sales manager could read without a glossary."""
    age = int(row.snapshot_age_days)
    if row.action == RE_ENRICH:
        if age > config.expired_after_days:
            return f"scores in the top tier but its information is {age} days old; refresh before calling"
        return "scores in the top tier, but that score leans on an intent value that was never measured"
    if row.action == CALL_WITH_CAVEAT:
        return f"top tier; information is {age} days old, so treat the activity as historical"
    if row.action == CALL_NOW:
        return f"top tier and current ({age} days old)"
    if row.action == NURTURE:
        return "middle of the range - worth a campaign, not a call"
    return f"below the level where this model's ranking carries any signal (score {row.score:.3f})"


def _stable_holdout(account_id: str, salt: str, share: float) -> bool:
    """Deterministic control-group assignment.

    Hash-based rather than random, so an account stays on the same side of the
    experiment across runs. Random assignment per run would let an account drift
    between treated and control and quietly destroy the comparison.
    """
    digest = hashlib.sha256(f"{salt}:{account_id}".encode()).hexdigest()
    return (int(digest[:8], 16) % 10_000) < share * 10_000


def apply_capacity(
    df: pd.DataFrame,
    config: PolicyConfig,
    recently_contacted: set[str] | None = None,
) -> pd.DataFrame:
    """Rank the call tier, hold back the control group, and cut to capacity.

    Order matters: holdout is drawn from everything that qualified, before the
    capacity cut. Drawing it afterwards would bias the control group towards
    lower-ranked accounts and make the comparison meaningless.
    """
    out = df.copy()
    recently_contacted = recently_contacted or set()

    callable_tier = out.action.isin([CALL_NOW, CALL_WITH_CAVEAT])
    out["rank"] = out.score.rank(ascending=False, method="first").astype(int)

    # Specified, not built: a contact history would populate recently_contacted.
    suppressed = callable_tier & out.account_id.isin(recently_contacted)
    out.loc[suppressed, "action"] = HOLD
    out.loc[suppressed, "reason"] = f"contacted within the last {config.cooldown_days} days"
    callable_tier = out.action.isin([CALL_NOW, CALL_WITH_CAVEAT])

    out["in_holdout"] = False
    out.loc[callable_tier, "in_holdout"] = [
        _stable_holdout(a, config.holdout_salt, config.holdout_share)
        for a in out.loc[callable_tier, "account_id"]
    ]

    eligible = callable_tier & ~out.in_holdout
    ordered = out[eligible].sort_values("score", ascending=False)
    queued_ids = set(ordered.head(config.capacity).account_id)

    out["queued"] = out.account_id.isin(queued_ids)
    out["queue_position"] = (
        out[out.queued].score.rank(ascending=False, method="first").astype(int)
        if out.queued.any() else pd.Series(dtype=int)
    )
    # Over capacity is not an error, but somebody should know it happened.
    out.attrs["over_capacity"] = int(eligible.sum() - len(queued_ids))
    return out


def summarise(df: pd.DataFrame) -> dict:
    """Counts the run record and the manager's summary both need."""
    counts = df.action.value_counts().to_dict()
    return {
        "scored": int(len(df)),
        "by_action": {a: int(counts.get(a, 0)) for a in (CALL_NOW, CALL_WITH_CAVEAT, RE_ENRICH, NURTURE, HOLD)},
        "queued": int(df.queued.sum()) if "queued" in df else 0,
        "held_out": int(df.in_holdout.sum()) if "in_holdout" in df else 0,
        "over_capacity": int(df.attrs.get("over_capacity", 0)),
    }
