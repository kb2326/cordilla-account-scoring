"""Is today's batch normal enough to act on?

These run before anything is published, and they answer a different question from
agent/contracts.py. Contracts asks "is this file structurally valid" - wrong
columns, impossible values, broken joins. These checks ask "does this file look
like the population the model was fitted on", which is the failure that does not
crash anything: every column present, every value plausible, and the scores
quietly meaningless because the world underneath moved.

Baselines are not hand-written. They come from analysis/findings.json, measured
from the training data by analysis/profile.py - the same source the written
proposal quotes, so a threshold and the claim it supports can never drift apart.

Status has three levels because the responses differ:
    green  publish
    amber  publish only with a human's say-so (the graph pauses)
    red    do not publish; a wrong queue costs more than a late one
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

FINDINGS = Path(__file__).resolve().parents[1] / "analysis" / "findings.json"

GREEN, AMBER, RED = "green", "amber", "red"


@dataclass
class Check:
    name: str
    status: str
    measured: float | None
    expected: str
    message: str


@dataclass
class BatchHealth:
    status: str
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status != GREEN]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checks": [c.__dict__ for c in self.checks],
            "alerts": [f"{c.name}: {c.message}" for c in self.failures],
        }


def load_baseline(path: Path = FINDINGS) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run `python analysis/profile.py` first")
    return json.loads(path.read_text(encoding="utf-8"))


def run_input_checks(df: pd.DataFrame, baseline: dict) -> BatchHealth:
    """Compare this batch against what the training population looked like.

    Bands are deliberately wide. The training and scoring files differ by only
    1.5 points of intent coverage today, so a 10-point move is roughly seven times
    the difference we can already see between two legitimate batches - unlikely to
    be noise, and worth a human's attention before 200 reps act on it.
    """
    checks: list[Check] = []

    # --- intent coverage. The cleanest silent failure in this system: the vendor
    # drops or expands coverage, the imputer fills the gap with a median, every
    # score shifts, and nothing anywhere reports an error.
    expected_missing = baseline["coverage"]["intent_missing_train"]
    actual_missing = float(df.intent_score.isna().mean())
    drift = abs(actual_missing - expected_missing)
    checks.append(Check(
        name="intent_coverage",
        status=GREEN if drift <= 0.05 else (AMBER if drift <= 0.10 else RED),
        measured=round(actual_missing, 4),
        expected=f"{expected_missing:.1%} ±5pp (amber) / ±10pp (red)",
        message=(f"{actual_missing:.1%} of accounts have no intent score "
                 f"(training population: {expected_missing:.1%})"),
    ))

    # --- staleness. If the upstream refresh breaks, yesterday's queue quietly
    # becomes last year's: the model cannot see snapshot_date, so nothing errors.
    expected_stale = baseline["freshness"]["score"]["share_older_than_90d"]
    actual_stale = float((df.snapshot_age_days > baseline["meta"]["horizon_days"]).mean())
    stale_drift = actual_stale - expected_stale
    checks.append(Check(
        name="staleness",
        status=GREEN if stale_drift <= 0.10 else (AMBER if stale_drift <= 0.20 else RED),
        measured=round(actual_stale, 4),
        expected=f"{expected_stale:.1%} +10pp (amber) / +20pp (red)",
        message=(f"{actual_stale:.1%} of the batch is older than "
                 f"{baseline['meta']['horizon_days']} days (reference batch: {expected_stale:.1%})"),
    ))

    median_age = float(df.snapshot_age_days.median())
    expected_median = baseline["freshness"]["score"]["median_age_days"]
    checks.append(Check(
        name="median_age",
        status=GREEN if median_age <= expected_median + 30 else AMBER,
        measured=median_age,
        expected=f"≤ {expected_median + 30:.0f} days",
        message=f"median snapshot age {median_age:.0f} days (reference: {expected_median:.0f})",
    ))

    # --- batch size. A silent upstream filter halving the batch is invisible in
    # every per-account metric, because each surviving account still looks fine.
    expected_rows = baseline["data_shape"]["score_rows"]
    ratio = len(df) / expected_rows if expected_rows else 1.0
    checks.append(Check(
        name="batch_size",
        status=GREEN if 0.5 <= ratio <= 2.0 else AMBER,
        measured=len(df),
        expected=f"0.5x-2x of {expected_rows} rows",
        message=f"{len(df)} accounts in this batch (reference: {expected_rows})",
    ))

    status = RED if any(c.status == RED for c in checks) else (
        AMBER if any(c.status == AMBER for c in checks) else GREEN)
    return BatchHealth(status=status, checks=checks)


def run_score_checks(scores: pd.Series, baseline: dict) -> BatchHealth:
    """Has the score distribution itself moved?

    Checked separately from the inputs because it can move for reasons no input
    check would catch - a changed upstream join, a swapped model artifact, a
    silently different preprocessing step.
    """
    ref = baseline["drift_baseline"]["score_distribution"]["train"]
    checks = [
        Check(
            name="score_mean",
            status=GREEN if abs(scores.mean() - ref["mean"]) <= 0.02 else AMBER,
            measured=round(float(scores.mean()), 4),
            expected=f"{ref['mean']} ±0.02",
            message=f"mean score {scores.mean():.4f} (training: {ref['mean']})",
        ),
        Check(
            name="call_tier_size",
            # Training p90 means ~10% of a normal batch should clear the bar. Far
            # more than that is not good news, it is a distribution shift.
            status=GREEN if (share := float((scores >= ref["p90"]).mean())) <= 0.25 else AMBER,
            measured=round(share, 4),
            expected="≤ 25% of the batch above the call threshold",
            message=f"{share:.1%} of accounts clear the call bar (expected around 10%)",
        ),
    ]
    status = AMBER if any(c.status != GREEN for c in checks) else GREEN
    return BatchHealth(status=status, checks=checks)


def merge(*healths: BatchHealth) -> BatchHealth:
    checks = [c for h in healths for c in h.checks]
    status = RED if any(c.status == RED for c in checks) else (
        AMBER if any(c.status == AMBER for c in checks) else GREEN)
    return BatchHealth(status=status, checks=checks)


def _main(argv: list[str] | None = None) -> int:
    """Run the checks against a batch without running the agent.

        python -m monitoring.checks --accounts data/accounts_to_score.csv --as-of 2026-08-01

    Exit code is the point: 0 green, 1 amber, 2 red. That makes this usable from
    cron or a scheduler without anyone parsing output.
    """
    import argparse

    import pandas as pd

    from agent.contracts import add_quality_flags, validate_batch
    from agent.scoring import load_model, score_batch

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Check whether a batch is fit to act on.")
    parser.add_argument("--accounts", type=Path, default=root / "data" / "accounts_to_score.csv")
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)

    baseline = load_baseline()
    frame = pd.read_csv(args.accounts)
    structural = validate_batch(frame)
    if not structural.ok:
        print(f"  STRUCTURAL FAILURE - not scoreable")
        for error in structural.errors:
            print(f"    - {error}")
        return 2

    frame = add_quality_flags(frame, pd.Timestamp(args.as_of))
    health = run_input_checks(frame, baseline)
    scores = pd.Series(score_batch(load_model(root / "model" / "model.pkl"), frame))
    health = merge(health, run_score_checks(scores, baseline))

    print(f"\n  batch: {args.accounts.name}  ({len(frame)} accounts, as of {args.as_of})")
    print(f"  status: {health.status.upper()}\n")
    for check in health.checks:
        mark = {GREEN: "ok  ", AMBER: "warn", RED: "FAIL"}[check.status]
        print(f"    [{mark}] {check.name:18s} {check.message}")
        if check.status != GREEN:
            print(f"           expected {check.expected}")
    print()
    return {GREEN: 0, AMBER: 1, RED: 2}[health.status]


if __name__ == "__main__":
    import sys

    sys.exit(_main())
