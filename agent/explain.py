"""Why did this account score what it did, and how much of that rests on nothing.

Method: leave-one-feature-out ablation against a reference account. For each
feature we re-score the account with that one value replaced by the population
baseline and record how far the score falls. The largest falls are the drivers.

Why not SHAP: it needs a dependency beyond the pinned four, and for a rep-facing
sentence the extra fidelity buys nothing. Stated limitation, because it is a real
one: ablation ignores interactions. If two features only matter together, knocking
out either one understates both. For this model - 40 trees of depth 2, so at most
two features interacting per tree - that is a mild distortion, not a fatal one.

Second job: intent sensitivity. 39% of accounts have no intent score and the
pipeline fills the gap with the training median, so the model reads "unknown" as
"average". Ablation cannot see that - replacing an imputed value with the median
changes nothing. Instead we ask a decision-shaped question: if that missing value
turned out to be low (training p25) or high (p75), would this account land on a
different side of the call threshold? If yes, the decision depends on data nobody
has, and the right action is to go and get it rather than guess.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import FEATURE_COLUMNS
from .scoring import LoadedModel, score_batch

NUMERIC_FEATURES = (
    "employee_count", "intent_score", "mql_count_90d", "trial_started",
    "trial_active_users", "web_touchpoints_90d", "sales_contacts_90d",
)
CATEGORICAL_FEATURES = ("account_type", "industry")

# How a driver is said out loud. {value} is filled by code, never by a language
# model, and {baseline} gives the rep the comparison that makes it meaningful.
PHRASES: dict[str, str] = {
    "intent_score": "third-party intent score of {value:.0f}, against a typical {baseline:.0f}",
    "web_touchpoints_90d": "{value:.0f} website visits in the 90 days to {as_of}",
    "sales_contacts_90d": "{value:.0f} logged sales contacts",
    "mql_count_90d": "{value:.0f} marketing leads",
    "trial_started": "started a trial",
    "trial_active_users": "{value:.0f} people active in the trial",
    "employee_count": "{value:.0f} employees",
    "account_type": "listed as a {value}",
    "industry": "in {value}",
}


def baseline_from(reference: pd.DataFrame) -> dict:
    """The 'typical account' every explanation is measured against.

    Built from the training population rather than today's batch: the question a
    rep is asking is "why this account rather than a normal one", and normal is
    defined by what the model learned from, not by whoever happens to be in the
    file this morning.
    """
    baseline = {c: float(reference[c].median()) for c in NUMERIC_FEATURES}
    baseline.update({c: reference[c].mode().iat[0] for c in CATEGORICAL_FEATURES})
    observed_intent = reference["intent_score"].dropna()
    baseline["_intent_p25"] = float(observed_intent.quantile(0.25))
    baseline["_intent_p75"] = float(observed_intent.quantile(0.75))
    return baseline


def explain_batch(
    model: LoadedModel,
    df: pd.DataFrame,
    baseline: dict,
    as_of: pd.Timestamp,
    top_k: int = 3,
) -> pd.DataFrame:
    """Add drivers, rep-readable phrases, and the intent sensitivity pair.

    Cost is 11 vectorised predict_proba calls over the whole batch, not one per
    account: each ablation is applied to every row at once.
    """
    out = df.copy()
    if "score" not in out.columns:
        raise ValueError("explain_batch expects the batch to be scored already")
    base_scores = out["score"].to_numpy()

    contributions = {}
    for feature in FEATURE_COLUMNS:
        probe = out.copy()
        probe[feature] = baseline[feature]
        # Positive = removing this feature lowers the score, i.e. it was helping.
        contributions[feature] = base_scores - score_batch(model, probe)

    # What if the missing intent value were actually low, or actually high?
    intent_low, intent_high = out.copy(), out.copy()
    intent_low["intent_score"] = baseline["_intent_p25"]
    intent_high["intent_score"] = baseline["_intent_p75"]
    out["score_if_intent_low"] = score_batch(model, intent_low)
    out["score_if_intent_high"] = score_batch(model, intent_high)

    contrib_frame = pd.DataFrame(contributions, index=out.index)
    out["drivers"] = [
        _drivers_for(row, contrib_frame.loc[idx], baseline, as_of, top_k)
        for idx, row in zip(out.index, out.itertuples(index=False))
    ]
    out["why"] = [" · ".join(d["phrase"] for d in drivers) if drivers else "nothing stands out"
                  for drivers in out["drivers"]]
    return out


def _drivers_for(row, contributions: pd.Series, baseline: dict, as_of: pd.Timestamp, top_k: int) -> list[dict]:
    """Top positive contributors for one account, phrased for a human.

    Only features that pushed the score *up* are reported: a rep needs a reason to
    pick up the phone, not a list of everything the account lacks. Contributions
    below 0.001 are dropped as noise rather than padded into a third bullet.
    """
    drivers = []
    for feature, delta in contributions.sort_values(ascending=False).head(top_k).items():
        if delta < 0.001:
            continue
        value = getattr(row, feature)
        if feature == "trial_started" and not value:
            continue  # "started a trial" is not a reason when they didn't
        if feature == "intent_score" and pd.isna(value):
            continue  # never quote an intent number we do not have
        drivers.append({
            "feature": feature,
            "contribution": round(float(delta), 4),
            "value": None if pd.isna(value) else (float(value) if feature in NUMERIC_FEATURES else str(value)),
            "phrase": PHRASES[feature].format(
                value=value, baseline=baseline.get(feature, float("nan")), as_of=as_of.date()
            ),
        })
    return drivers


def fact_set(row) -> dict:
    """Everything the brief is allowed to state, and nothing else.

    The language model receives this and may reference only these values; the
    verifier later checks the finished brief against exactly this dictionary. A
    number that is not in here cannot legitimately appear in a brief.
    """
    facts = {
        "account_id": row.account_id,
        # The driver phrases are built by code in explain_batch and contain numbers,
        # so they travel as a placeholder like every other value. The model may say
        # {{evidence}}; it may not retype what is inside it.
        "evidence": " · ".join(d["phrase"] for d in row.drivers) if getattr(row, "drivers", None) else "no standout signals",
        "account_type": row.account_type,
        "industry": row.industry,
        "employee_count": int(row.employee_count),
        "score_rank": int(row.get("rank", 0)),
        "snapshot_age_days": int(row.snapshot_age_days),
        "web_touchpoints_90d": int(row.web_touchpoints_90d),
        "mql_count_90d": int(row.mql_count_90d),
        "sales_contacts_90d": int(row.sales_contacts_90d),
        "trial_started": bool(row.trial_started),
        "trial_active_users": int(row.trial_active_users),
    }
    # Only ever expose intent when it was actually measured.
    if not row.intent_imputed:
        facts["intent_score"] = round(float(row.intent_score), 1)
    return facts


def decision_depends_on_missing_intent(df: pd.DataFrame, call_threshold: float) -> pd.Series:
    """True where the unknown intent value straddles the call threshold.

    Not "intent matters to this score" - that is true almost everywhere and would
    flag half the batch. The question is narrower and actionable: could the value
    nobody measured move this account across the line we act on? If so, buying the
    data is worth more than acting on the guess.
    """
    if not {"score_if_intent_low", "score_if_intent_high", "intent_imputed"} <= set(df.columns):
        return pd.Series(False, index=df.index)
    low = np.minimum(df.score_if_intent_low, df.score_if_intent_high)
    high = np.maximum(df.score_if_intent_low, df.score_if_intent_high)
    return df.intent_imputed & (low < call_threshold) & (high >= call_threshold)
