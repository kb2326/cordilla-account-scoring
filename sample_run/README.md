# One real run, committed

Output of `python -m agent.run --as-of 2026-08-01` against the provided batch, so the
results can be read without installing anything. Regenerating it overwrites `outputs/`,
which is gitignored; this folder is the snapshot.

| File | Who it is for |
|---|---|
| `call_queue.csv` | the SDR: who to call, in order, with talking points |
| `briefs.md` | the SDR: two or three sentences per queued account |
| `enrichment_requests.csv` | RevOps: accounts to refresh before anyone calls |
| `run_summary.txt` | the sales manager: five lines, no jargon |
| `decisions.csv` | the analyst: every account, every flag, joins to CRM outcomes in 90 days |
| `runs.jsonl` | the analyst: one line per run — counts, timings, cost, alerts, config used |
