# One real run, committed

Output of:

```bash
python -m agent.run --as-of 2026-08-01 --investigate
```

against the provided batch, with a live model — so the results can be read without
installing anything or holding an API key.

**This is the fullest version of the run**, with the boundary-account agent switched on.
The default command (no `--investigate`) queues **16** accounts instead of 10 and costs
about two cents; the agent is more cautious than the rules and moves several accounts from
"call with a caveat" to "refresh the data first". Both are honest outputs of the same
system, which is why the flag exists.

| | This run |
|---|---|
| Accounts scored | 300 |
| Queued to reps | **10** (7 more held back as a control group) |
| Sent for data refresh | 19 |
| Marketing nurture / left alone | 55 / 209 |
| Model | `claude-haiku-4-5-20251001`, live — `runs.jsonl` records `"mocked": false` |
| Model calls | 62 — 10 briefs, 52 investigation turns |
| **Measured cost** | **$0.1376**, of which **$0.1258 is the investigator** |
| Wall clock | 46.7s (both model stages run four at a time) |
| Briefs rejected by the verifier | 0 |
| Investigator recommendations overridden by policy | 0 |

The cost split is worth noticing: the boundary agent is **91% of the model spend for 6.7%
of the accounts**. It is also the only part of the system that is not perfectly repeatable —
re-running shifts a decision or two — which is why it is confined to accounts where the rule
was arbitrary to begin with. That is the argument for keeping it off by default and pointed only at
accounts where the rules are genuinely arbitrary — and for the run record carrying the
number, rather than an estimate of it.

| File | Who it is for |
|---|---|
| `call_queue.csv` | the SDR: who to call, in order, with talking points |
| `briefs.md` | the SDR: two or three sentences per account, model-written, numbers filled by code |
| `enrichment_requests.csv` | RevOps: accounts to refresh before anyone spends a call |
| `investigation.md` | what the boundary agent checked, and why it concluded what it did |
| `run_summary.txt` | the sales manager: five lines, no jargon |
| `decisions.csv` | the analyst: every account, every flag, joins to CRM outcomes in 90 days |
| `runs.jsonl` | the analyst: counts, timings, measured cost, alerts, and the exact config used |
