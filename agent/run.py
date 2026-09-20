"""Run the triage agent over a batch.

    python -m agent.run --accounts data/accounts_to_score.csv --as-of 2026-08-01

--as-of has no default on purpose. Both provided CSVs are snapshots taken on
2026-08-01, and letting "today" come from the system clock would silently change
every freshness decision in the run depending on when it happened to execute.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from langgraph.types import Command

from monitoring.checks import load_baseline

from .graph import Deps, build_graph, new_run_id
from .policy import PolicyConfig
from .scoring import load_model

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Score a batch of accounts and decide what happens to each.")
    p.add_argument("--accounts", type=Path, default=ROOT / "data" / "accounts_to_score.csv")
    p.add_argument("--as-of", required=True, help="the date to treat as today, e.g. 2026-08-01")
    p.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    p.add_argument("--capacity", type=int, default=None, help="override how many accounts reps can take")
    p.add_argument("--yes", action="store_true",
                   help="approve publishing without asking, even if checks are amber")
    p.add_argument("--print-graph", action="store_true", help="print the flow as mermaid and exit")
    args = p.parse_args(argv)

    app = build_graph()
    if args.print_graph:
        print(app.get_graph().draw_mermaid())
        return 0

    policy = PolicyConfig(capacity=args.capacity) if args.capacity else PolicyConfig()
    deps = Deps(
        model=load_model(ROOT / "model" / "model.pkl"),
        policy=policy,
        baseline=load_baseline(),
        reference=pd.read_csv(ROOT / "data" / "training_data.csv"),
        as_of=pd.Timestamp(args.as_of),
        accounts_path=args.accounts,
        output_dir=args.output_dir,
        auto_approve=args.yes,
    )
    config = {"configurable": {"thread_id": new_run_id()}}
    run_id = config["configurable"]["thread_id"]

    result = app.invoke({"run_id": run_id, "events": []}, config, context=deps, version="v2")

    # An amber batch pauses here rather than publishing. In production this
    # payload goes to Slack and the resume is a button; at a terminal it is a
    # question, because a person deciding is the point.
    if result.interrupts:
        payload = result.interrupts[0].value
        print(f"\n  PAUSED: {payload['question']}")
        print(f"  batch status: {payload['status']}")
        for alert in payload["alerts"]:
            print(f"    - {alert}")
        print(f"  would queue {payload['would_queue']} accounts to reps")
        answer = input("\n  publish? [y/N] ").strip().lower()
        result = app.invoke(Command(resume={"approve": answer == "y"}), config,
                            context=deps, version="v2")

    state = result.value
    if state.get("halted") and not state.get("approved"):
        print("\n  nothing published.")
        print(f"  batch status: {state['batch_health']['status']}")
        for alert in state["batch_health"]["alerts"]:
            print(f"    - {alert}")
        return 1

    counts = state["counts"]
    print(f"\n  {counts['scored']} accounts scored, batch status {state['batch_health']['status']}")
    for action, n in counts["by_action"].items():
        print(f"    {action:18s} {n:4d}")
    print(f"    {'queued to reps':18s} {counts['queued']:4d}   ({counts['held_out']} held back as control)")
    print("\n  wrote:")
    for name, path in state["written"].items():
        print(f"    {name:20s} {_display(Path(path))}")
    return 0


def _display(path: Path) -> str:
    """Repo-relative when it can be, absolute when it can't.

    --output-dir can point anywhere, including another drive on Windows, where
    relative_to raises rather than returning something sensible.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
