# Cordilla Systems, AI Engineer Exercise — Impact Framing, Agent Build, Monitoring

## Setup

    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

Tested against Python 3.11+ with the exact pinned versions above. If you'd rather work in a notebook than plain scripts (either is fine, see the take-home packet), `pip install -r requirements-notebook.txt` instead (adds Jupyter on top of the same pinned core).

Loading the model (already trained, don't retrain it):

    import pickle
    with open("model/model.pkl", "rb") as f:
        model = pickle.load(f)
    # model.predict_proba(df[feature_columns]), feature columns are listed below and in the take-home packet

Expected feature columns, in the order the model was trained on: `account_type`, `employee_count`, `industry`, `intent_score`, `mql_count_90d`, `trial_started`, `trial_active_users`, `web_touchpoints_90d`, `sales_contacts_90d`. `snapshot_date` and `account_id` are identifiers, not model inputs.

**Treat 2026-08-01 as "today" for this exercise.** Both CSVs are static snapshots generated as of that date. Any recency/age calculation (e.g. "how old is this account's snapshot") should use 2026-08-01 as the reference point, not your actual system clock.

## What's here

- `model/model.pkl`, a real, already-trained scikit-learn pipeline. Don't retrain it. You don't need to audit it to research rigor, this exercise isn't scored on that, but it's real data worth actually looking at if it changes your impact framing or monitoring design.
- `data/training_data.csv`, the labeled historical data the model above was actually trained on. Look at it enough to ground your impact-framing numbers and your monitoring design, that's the bar, not a full audit.
- `data/accounts_to_score.csv`, an unlabeled batch you'll run the model against as part of the agent build. Don't modify or regenerate either CSV; everyone works from the same files.
- `agent/`, your agent: load the model, score `accounts_to_score.csv`, and build something real that does something with the output. Vague on purpose, see the take-home packet's hints on what we'd minimally want to see (tools/actions, structure, framework choice and why, deployment). Mock any LLM/API calls, no key is provided, see the packet.
- `monitoring/`, at least one real, concrete monitoring check (a health check, a data-quality assertion, a drift signal, an alert condition). Can live here or be folded into `agent/`, your call. See the packet, this is scored as its own dimension, not a bullet point.
- `PROPOSAL.md`, your written design proposal covering all three: impact framing, agent design, monitoring design (see the take-home packet for the required sections).
- `RESEARCH-LOG.md`, your running log as you work: hypotheses, what you tried, dead ends, and specifically what you asked your AI tool and how you used what came back.

## Working process

Commit as you actually go, small, real commits over time, not one commit at the end. We read the commit history as part of how you reason and work, not just the final diff.

**We'd genuinely like you to use AI here, assisted coding tools especially (Claude Code, Codex, Cursor, Antigravity, or similar), on your own accounts.** Dialpad doesn't provide one for this exercise. Disclose your actual sessions/prompts in `RESEARCH-LOG.md`, specific enough that we can see what shaped a decision, not a vague "used AI throughout."

## When you're done

Push this to a public git repo and send us the link. That's the submission. The presentation gets scheduled as a separate follow-up after that, not something to prepare beforehand.
