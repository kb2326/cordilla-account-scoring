# Runbook — what each alert means and what to do about it

Alerts nobody knows how to action get muted, and a muted alert is worse than no
alert because everyone believes it is still watching. So: every check below has an
owner, a first move, and a stated tolerance for being wrong.

**Baselines** come from `analysis/findings.json`, measured from the training data by
`analysis/profile.py`. Regenerate that file and the thresholds move with it.

---

## The three clocks

Different signals arrive at different speeds, and treating them alike is how
monitoring becomes noise.

| Clock | Signals | Latency | What it is for |
|---|---|---|---|
| **Daily** | coverage, staleness, batch size, score distribution | next run | Operational alarms. No labels needed, so they are the only thing that can catch a problem *this week* |
| **Weekly (4-week rolling)** | rep dispositions by tier | ~1 month | Early warning that the scores have drifted from what reps see. This is the signal Cordilla's last effort lacked |
| **Quarterly** | realised conversion, queued vs held-out control | ~90 days | The verdict on whether any of this works. Never an alarm — too slow and too noisy to act on |

---

## Daily checks (implemented in `checks.py`, enforced by the graph)

### `intent_coverage`
**Watching:** share of accounts with no third-party intent score.
**Baseline:** 40.2% missing in training, 38.7% in the reference batch.
**Amber** at ±5pp, **red** at ±10pp.

**Why it matters:** `intent_score` carries 27% of the model's weight, and the
pipeline fills a missing value with the training median — so "the vendor does not
cover this company" silently becomes "this company has average intent." A coverage
change moves every score and raises no error.

**Noise vs real:** training and the reference batch differ by 1.5pp, so a 10pp move
is roughly seven times the gap we see between two legitimate batches. That is not
sampling noise.

**First move:** the batch is held automatically. Check the vendor feed landed and
its row count. If coverage genuinely dropped, do **not** re-run with a wider band —
the scores are now less reliable for the affected accounts, which is exactly what
the enrichment queue is for.
**Owner:** whoever owns the vendor contract (RevOps).

---

### `staleness` and `median_age`
**Watching:** share of the batch older than 90 days, and the median age.
**Baseline:** 72.7% over 90 days, median 121 days.
**Amber** at +10pp or +30 days; **red** at +20pp.

**Why it matters:** every feature counts a 90-day window ending at the snapshot.
Past 90 days that window no longer overlaps the one being predicted. The model
cannot see this — `snapshot_date` is not an input — so a refresh pipeline that
stops produces confident scores about last year. In the demo, aging every snapshot
by 200 days left the mean score **completely unchanged**.

**Noise vs real:** age drifts up by roughly a day per day when nothing refreshes,
so a jump of 30+ days between consecutive runs means an upstream job stopped, not
that accounts got quieter.

**First move:** check the enrichment job ran. Until it is fixed, the queue is built
from history; the `CALL_WITH_CAVEAT` wording is doing real work in the meantime.
**Owner:** data engineering.

---

### `batch_size`
**Watching:** row count against the reference batch.
**Amber** outside 0.5x–2x.

**Why it matters:** a changed filter upstream is invisible in every per-account
metric, because each surviving account still looks perfect. Only the volume shows
it. In the demo this was the one scenario where every score, and the distribution
they came from, looked entirely normal.

**First move:** diff the extraction query against the previous run. A legitimate
shrink (a suppression list, a territory change) gets approved through the pause; an
unexplained one does not.
**Owner:** whoever owns the extraction.

---

### `score_mean` and `call_tier_size`
**Watching:** mean score, and the share of the batch clearing the call threshold.
**Baseline:** mean 0.0661 in training; ~10% should clear the p90 bar.
**Amber** at ±0.02 on the mean, or more than 25% clearing the bar.

**Why it matters:** this catches what the input checks miss — a swapped model
artifact, a changed preprocessing step, a join that duplicated rows. **A sudden
surplus of high scorers is not good news.** It is the same shape as a distribution
shift, and the absolute threshold is what makes it visible; a relative "top 50" cut
would absorb it silently.

**First move:** compare the model hash in `runs.jsonl` against the previous run —
the run record exists for exactly this question. Then compare feature distributions.
**Owner:** whoever owns this agent.

---

## Weekly: rep dispositions (specified, not built — needs CRM feedback)

**Watching:** share of queued accounts a rep marks "not a fit" or "bad data",
split by tier.

**Why it matters:** this is the earliest honest signal that the scores have stopped
matching the field, and it is the one Cordilla's previous effort never had.

**Noise vs real — the arithmetic that decides the threshold:** at ~30 queued
accounts a week and a disposition rate around 20%, the standard error on one week
is **7.3pp**. A jump from 20% to 30% in a single week is noise. On a four-week
rolling window (n≈120) the standard error falls to **3.6pp**, so a 10pp shift is
~2.7 standard errors.

**Alert rule:** four-week rolling rate above baseline + 2 SE, for two consecutive
weeks. Anything twitchier trains people to ignore it.

**First move:** read ten dispositioned accounts before touching a threshold. If
reps are rejecting for reasons the data can see (stale, wrong contact), that is a
routing fix. If they are rejecting for reasons it cannot (they already bought
elsewhere), that is a model-scope problem and a conversation with the VP.

---

## Quarterly: did it actually work

**Watching:** realised conversion of queued accounts versus the held-out control
group, with a confidence interval.

**Why the holdout exists:** without a counterfactual, nobody can distinguish "the
model works" from "reps got better" or "the quarter was good." Offline metrics
cannot establish that the queue *caused* anything.

**How long before it says anything:** distinguishing a 15% conversion rate from
6.5% at 80% power needs roughly **208 accounts per arm** — about **14 weeks** in
the treated arm, **~23 weeks** in a 30% control. Publishing a lift number before
then is the exact overclaim that cost the last effort its credibility.

**Until then, the honest report is "pending"** — which is what
`outputs/run_summary.txt` prints, deliberately, rather than an estimate.

---

## When the agent halts

A red batch publishes nothing and reps simply get no new queue that morning. That
is the intended trade: **a late queue costs a morning, a wrong queue costs the
programme.** The previous scoring effort was never able to make that trade,
because nothing was watching.
