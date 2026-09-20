"""Prove the checks catch failures that leave no error behind.

    python -m monitoring.demo_silent_failure

The failure mode that killed Cordilla's last scoring effort does not raise an
exception. Every column is present, every probability is between 0 and 1, the
queue arrives on time, and it is quietly wrong for a quarter. This script breaks
the batch in three realistic ways and shows, for each one, that:

  * the model still returns perfectly plausible scores,
  * the run still completes without a single error,
  * and only the checks notice.

Nothing here is simulated at the check level - each scenario runs the real graph
end to end against a degraded copy of the real batch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from agent.graph import Deps, build_graph, new_run_id
from agent.policy import PolicyConfig
from agent.scoring import load_model
from monitoring.checks import load_baseline

ROOT = Path(__file__).resolve().parents[1]
AS_OF = pd.Timestamp("2026-08-01")


def scenario_vendor_coverage_collapses(df: pd.DataFrame) -> pd.DataFrame:
    """The intent vendor loses a data partner and coverage halves overnight.

    Nobody is told. The imputer fills the gap with the training median, so every
    affected account is scored as though it had average buying intent.
    """
    out = df.copy()
    have = out[out.intent_score.notna()]
    out.loc[have.sample(frac=0.6, random_state=7).index, "intent_score"] = np.nan
    return out


def scenario_refresh_pipeline_stalls(df: pd.DataFrame) -> pd.DataFrame:
    """The nightly enrichment job fails silently and snapshots stop advancing.

    Six months later every account is being scored on six-month-old behaviour.
    The model cannot notice: snapshot_date is not one of its inputs.
    """
    out = df.copy()
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"]) - pd.Timedelta(days=200)
    return out


def scenario_upstream_filter_halves_the_batch(df: pd.DataFrame) -> pd.DataFrame:
    """A changed WHERE clause upstream quietly drops most of the population.

    Per-account metrics all look normal, because each surviving account is fine.
    Only the volume gives it away.
    """
    return df.sample(frac=0.35, random_state=3).copy()


SCENARIOS = [
    ("baseline (untouched)", lambda df: df.copy()),
    ("intent vendor coverage collapses", scenario_vendor_coverage_collapses),
    ("snapshot refresh pipeline stalls", scenario_refresh_pipeline_stalls),
    ("upstream filter halves the batch", scenario_upstream_filter_halves_the_batch),
]


def run_once(path: Path, tmp_dir: Path) -> dict:
    """Run the real graph against a batch and report what happened."""
    app = build_graph()
    deps = Deps(
        model=load_model(ROOT / "model" / "model.pkl"),
        policy=PolicyConfig(),
        baseline=load_baseline(),
        reference=pd.read_csv(ROOT / "data" / "training_data.csv"),
        as_of=AS_OF,
        accounts_path=path,
        output_dir=tmp_dir,
        auto_approve=False,   # so an amber batch pauses instead of publishing
    )
    result = app.invoke({"run_id": new_run_id(), "events": []},
                        {"configurable": {"thread_id": new_run_id()}},
                        context=deps, version="v2")
    paused = bool(result.interrupts)
    state = result.value
    return {
        "status": state.get("batch_health", {}).get("status", "?"),
        "alerts": state.get("batch_health", {}).get("alerts", []),
        "halted": bool(state.get("halted")),
        "paused": paused,
        "queued": state.get("counts", {}).get("queued"),
        "errors": 0,   # if we got here, nothing raised
    }


def score_only(df: pd.DataFrame) -> dict:
    """What the model alone would report - i.e. what you see if you are not looking."""
    from agent.contracts import add_quality_flags
    from agent.scoring import score_batch
    model = load_model(ROOT / "model" / "model.pkl")
    scores = score_batch(model, add_quality_flags(df, AS_OF))
    return {"n": len(df), "mean": float(scores.mean()), "max": float(scores.max()),
            "in_range": bool(((scores >= 0) & (scores <= 1)).all())}


def main() -> int:
    tmp = ROOT / "outputs" / "_demo"
    tmp.mkdir(parents=True, exist_ok=True)
    original = pd.read_csv(ROOT / "data" / "accounts_to_score.csv")

    print("\nSILENT FAILURE DEMO")
    print("=" * 78)
    print("Each row below is the real agent, run end to end, against a broken batch.\n")

    rows = []
    for name, degrade in SCENARIOS:
        broken = degrade(original)
        path = tmp / f"{name.replace(' ', '_')}.csv"
        broken.to_csv(path, index=False)

        model_view = score_only(broken)
        outcome = run_once(path, tmp / "out")
        rows.append((name, model_view, outcome))

        verdict = ("HALTED, nothing published" if outcome["halted"]
                   else "PAUSED for a human" if outcome["paused"]
                   else f"published {outcome['queued']} accounts")
        print(f"  {name}")
        print(f"    what the model reports : {model_view['n']} accounts, mean score "
              f"{model_view['mean']:.4f}, max {model_view['max']:.4f}, all in [0,1]: {model_view['in_range']}")
        print(f"    errors raised          : {outcome['errors']}")
        print(f"    checks say             : {outcome['status'].upper()}")
        for alert in outcome["alerts"]:
            print(f"        - {alert}")
        print(f"    agent does             : {verdict}\n")

    print("=" * 78)
    print("The point: in every broken case the model returned valid probabilities and")
    print("the run completed without a single error. Nothing crashed. A queue would")
    print("have gone out looking exactly as trustworthy as yesterday's.")
    print("The checks are the only thing standing between that and a rep's phone.\n")

    print("What it would have cost to find out the slow way:")
    print("  - reps work the bad queue for a quarter before anyone senses it")
    print("  - conversion data to prove it takes ~14 weeks at this volume (PROPOSAL.md)")
    print("  - by then the scores have lost the room, which is what happened last time\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
