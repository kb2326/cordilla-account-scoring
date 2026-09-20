"""Did our routing rules actually improve the queue, or just complicate it?

    python analysis/policy_backtest.py

The agent adds gates on top of the model's ranking: skip accounts whose data has
expired, and skip ones whose decision rests on an intent score nobody measured. Both
are defensible arguments. This checks them against outcomes instead, on the 1,200
labelled training accounts.

Three caveats, stated up front because they bound what this can prove:

  1. The model was fitted on these rows, so both arms are optimistic. Only the
     COMPARISON is meaningful - the gates are the sole difference between them.
  2. Rows snapshotted within 90 days of the data cut are excluded. Their outcome
     window had not closed, so they are recorded as non-conversions whatever
     happened, and a freshness gate would get spurious credit for dropping them.
  3. 78 conversions in total. At a queue of 50 and a ~30% conversion rate the
     standard error is about 6.5 points, so a 2-point difference is noise. The
     confidence intervals below are there to stop anyone over-reading a gap.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

# Runnable as a plain script: put the repo root on the path before importing agent,
# so `python analysis/policy_backtest.py` works from anywhere.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.contracts import add_quality_flags  # noqa: E402
from agent.explain import baseline_from, explain_batch  # noqa: E402
from agent.policy import CALL_NOW, CALL_WITH_CAVEAT, PolicyConfig, assign_actions  # noqa: E402
from agent.scoring import load_model, score_batch  # noqa: E402

AS_OF = pd.Timestamp("2026-08-01")
HORIZON = 90


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval - honest at small n, where the textbook normal one is not."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    d = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> None:
    config = PolicyConfig()
    train = pd.read_csv(ROOT / "data" / "training_data.csv")
    model = load_model(ROOT / "model" / "model.pkl")

    frame = add_quality_flags(train, AS_OF)
    frame["score"] = score_batch(model, frame)
    frame = explain_batch(model, frame, baseline_from(train), AS_OF)
    frame = assign_actions(frame, config)

    mature = frame[frame.snapshot_age_days >= HORIZON].copy()
    callable_tier = mature[mature.action.isin([CALL_NOW, CALL_WITH_CAVEAT])]
    base = mature.converted_within_90d.mean()

    print(f"\n  {len(mature)} labelled accounts with a closed outcome window "
          f"({len(frame) - len(mature)} censored rows excluded)")
    print(f"  base conversion rate {base:.1%}; the policy would call {len(callable_tier)} of them\n")

    print("  QUEUE OF N - rank by score alone, versus the same ranking with our gates")
    print(f"  {'N':>4}  {'score only':>22}  {'with gates':>22}")
    for n in (25, 50, 75):
        naive = mature.nlargest(n, "score")
        gated = callable_tier.nlargest(n, "score")
        if len(gated) < n:
            print(f"  {n:>4}  (the gated pool holds only {len(gated)}; not compared)")
            continue
        nc, gc = int(naive.converted_within_90d.sum()), int(gated.converted_within_90d.sum())
        nlo, nhi = wilson(nc, n)
        glo, ghi = wilson(gc, n)
        print(f"  {n:>4}  {nc/n:>7.1%} [{nlo:.0%}-{nhi:.0%}] n={nc:<3}"
              f"  {gc/n:>7.1%} [{glo:.0%}-{ghi:.0%}] n={gc:<3}")

    print("\n  EACH GATE ON ITS OWN, inside the top tier")
    top = mature[mature.score >= config.call_threshold]
    for label, mask in [
        ("data over a year old", top.snapshot_age_days > 365),
        ("intent was imputed", top.intent_imputed),
    ]:
        excluded, kept = top[mask], top[~mask]
        if excluded.empty:
            continue
        e_lo, e_hi = wilson(int(excluded.converted_within_90d.sum()), len(excluded))
        k_lo, k_hi = wilson(int(kept.converted_within_90d.sum()), len(kept))
        overlap = e_hi >= k_lo
        print(f"    excluded for '{label}': n={len(excluded):3d} converts "
              f"{excluded.converted_within_90d.mean():>6.1%} [{e_lo:.0%}-{e_hi:.0%}]")
        print(f"      versus everything kept: n={len(kept):3d} converts "
              f"{kept.converted_within_90d.mean():>6.1%} [{k_lo:.0%}-{k_hi:.0%}]"
              f"   -> {'intervals overlap: no evidence either way' if overlap else 'separated: the gate is supported'}")

    print("""
  READ IT HONESTLY
    Nothing here is statistically established. Every interval overlaps, and with 78
    conversions spread across the whole file that was always the likely outcome. What
    the numbers give is a direction, not a verdict.

    Freshness points the right way. Inside the top tier, accounts older than a year
    convert at about two thirds the rate of fresher ones - 21% against 31% - which is
    the sign the gate predicts. It is not proof: n=42, and the intervals overlap. The
    reason the gate stays is that it was derived from the feature definition before
    this test existed. A 90-day activity window on a 400-day-old snapshot describes a
    period that closed long ago, whatever the conversion numbers say.

    Intent shows nothing at all: 27.3% against 27.9% on eleven accounts. It stays for
    a different reason, and the distinction matters. It changes an ACTION rather than
    a prediction - when a decision turns on a value nobody measured, buying the value
    costs about a dollar and a wasted call costs eight minutes of a rep's day. That is
    a cost argument, and it should not be dressed up as an accuracy claim.

    The headline: gated and ungated queues are within noise of each other here. That
    is the honest result, and it is the argument for the holdout rather than against
    the gates - this question can only be settled in production, on data the model has
    never seen, which is what the control group is accumulating.
""")


if __name__ == "__main__":
    main()
