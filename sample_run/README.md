# One real run, committed

Output of `python -m agent.run --as-of 2026-08-01` against the provided batch, so the
results can be read without installing anything or holding an API key.

**This run used a live model** — `claude-haiku-4-5-20251001`, 16 calls, 0 rejected by the
verifier, $0.0186. `runs.jsonl` records `"mocked": false` so you can tell which path ran.
Without `ANTHROPIC_API_KEY` the same command produces the same structure using the
documented stand-in in `agent/llm.py`.

| File | Who it is for |
|---|---|
| `call_queue.csv` | the SDR: who to call, in order, with talking points |
| `briefs.md` | the SDR: two or three sentences per queued account, written by the model, numbers filled by code |
| `enrichment_requests.csv` | RevOps: accounts to refresh before anyone calls |
| `run_summary.txt` | the sales manager: five lines, no jargon |
| `decisions.csv` | the analyst: every account, every flag, joins to CRM outcomes in 90 days |
| `runs.jsonl` | the analyst: counts, timings, measured cost, alerts, and the config used |
