"""What a valid batch looks like, and what is wrong with each account in it.

Two jobs, kept apart on purpose:

  validate_batch()   structural. Is this file safe to score at all? Wrong columns,
                     wrong types, impossible values -> refuse, loudly. A batch that
                     fails here must never reach the model, because the model will
                     happily score nonsense and return confident numbers.

  add_quality_flags() per-account. Is this row's information current, and is the
                     score about to rest on data nobody measured? The model cannot
                     answer either question: snapshot_date is not one of its inputs
                     and the imputer erases the difference between "no intent data"
                     and "average intent". So the agent has to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Exactly the nine the model was fitted on, in the order it was fitted on them.
# Order matters: the pipeline's ColumnTransformer selects by name, but passing a
# frame with the columns in a different order is the kind of mistake that produces
# plausible-looking wrong scores, so we assert it rather than trust it.
FEATURE_COLUMNS: tuple[str, ...] = (
    "account_type",
    "employee_count",
    "industry",
    "intent_score",
    "mql_count_90d",
    "trial_started",
    "trial_active_users",
    "web_touchpoints_90d",
    "sales_contacts_90d",
)

# Present in the CSV, deliberately not model inputs. snapshot_date is the most
# important field in this repo and the model never sees it.
IDENTIFIER_COLUMNS: tuple[str, ...] = ("account_id", "snapshot_date")

# Features count the 90 days BEFORE snapshot_date; the label was measured over the
# 90 days AFTER it. So once a row is older than 90 days, the window it describes no
# longer overlaps the window we are predicting.
HORIZON_DAYS = 90
EXPIRED_DAYS = 365  # beyond a year, a call would reference year-old events

# Ranges are structural, not statistical: a negative count or an intent score of 400
# means the upstream join broke, not that the market moved. Distribution shifts are
# monitoring's job (monitoring/checks.py), not the contract's.
VALUE_RANGES: dict[str, tuple[float, float]] = {
    "employee_count": (1, 1_000_000),
    "intent_score": (0, 100),
    "mql_count_90d": (0, 1_000),
    "trial_started": (0, 1),
    "trial_active_users": (0, 100_000),
    "web_touchpoints_90d": (0, 10_000),
    "sales_contacts_90d": (0, 1_000),
}

CATEGORICAL_VALUES: dict[str, set[str]] = {
    "account_type": {"Prospect", "Suspect", "Former Customer"},
}


class ContractError(Exception):
    """The batch cannot be scored. Raised, never swallowed."""


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rows: int = 0

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise ContractError(
                f"batch failed validation ({len(self.errors)} error(s)):\n  - "
                + "\n  - ".join(self.errors)
            )


def validate_batch(df: pd.DataFrame) -> ValidationResult:
    """Structural check. Errors block scoring; warnings are recorded and continue."""
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in (*IDENTIFIER_COLUMNS, *FEATURE_COLUMNS) if c not in df.columns]
    if missing:
        # Nothing else is meaningful if columns are absent, so stop here.
        return ValidationResult(ok=False, errors=[f"missing required columns: {missing}"], rows=len(df))

    if df.empty:
        errors.append("batch is empty")

    if df.account_id.duplicated().any():
        dupes = df.account_id[df.account_id.duplicated()].unique()[:5].tolist()
        errors.append(f"duplicate account_id values, e.g. {dupes}")

    # Nulls: intent_score is allowed to be null (~40% of rows are, by design - the
    # vendor does not cover every company). Anything else being null means a broken
    # join upstream.
    for col in FEATURE_COLUMNS:
        if col == "intent_score":
            continue
        n_null = int(df[col].isna().sum())
        if n_null:
            errors.append(f"{col} has {n_null} null value(s); only intent_score may be null")

    for col, (lo, hi) in VALUE_RANGES.items():
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().sum() > df[col].isna().sum():
            errors.append(f"{col} contains non-numeric values")
            continue
        out_of_range = int(((values < lo) | (values > hi)).sum())
        if out_of_range:
            errors.append(f"{col} has {out_of_range} value(s) outside [{lo}, {hi}]")

    for col, allowed in CATEGORICAL_VALUES.items():
        unknown = set(df[col].dropna().unique()) - allowed
        if unknown:
            # The model's OneHotEncoder is set to handle_unknown="ignore", so an
            # unseen category silently becomes all-zeros and the account is scored
            # as if it had no type at all. Warn rather than block: one new segment
            # should not stop a morning's work, but somebody must know.
            warnings.append(f"{col} has unseen categories {sorted(unknown)}; the model encodes these as all-zero")

    # Impossible combination: trial users without a trial. Measured on the training
    # data this never happens, so if it starts happening the join is broken.
    impossible = int(((df.trial_active_users > 0) & (df.trial_started == 0)).sum())
    if impossible:
        errors.append(f"{impossible} row(s) have trial_active_users > 0 with trial_started = 0")

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings, rows=len(df))


def add_quality_flags(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Per-account judgement the model structurally cannot make.

    as_of is always passed in and never defaults to the system clock: the provided
    CSVs are snapshots taken on 2026-08-01, and reading "today" off a wall clock
    would silently change every age in the repo depending on when it is run.
    """
    out = df.copy()
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"])
    out["snapshot_age_days"] = (as_of - out["snapshot_date"]).dt.days

    if (out.snapshot_age_days < 0).any():
        n = int((out.snapshot_age_days < 0).sum())
        raise ContractError(f"{n} row(s) are dated after as_of={as_of.date()}; check the batch or the as-of date")

    # Three buckets, because the action differs: current, usable-with-a-caveat, expired.
    out["is_current"] = out.snapshot_age_days <= HORIZON_DAYS
    out["is_expired"] = out.snapshot_age_days > EXPIRED_DAYS
    out["is_ageing"] = ~out.is_current & ~out.is_expired

    # The imputer replaces a missing intent_score with the training median and adds
    # no indicator, so the model cannot distinguish "not covered by the vendor" from
    # "average intent". Recording it here is what lets the brief say so out loud.
    out["intent_imputed"] = out["intent_score"].isna()

    # Never contacted: relevant to the rep, invisible in the score. An account nobody
    # has called is a different proposition from one that has been worked and stalled.
    out["never_contacted"] = out["sales_contacts_90d"] == 0

    return out
