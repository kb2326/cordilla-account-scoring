# Research log

Kept as I go. Hypotheses, what the data actually said, dead ends, and what I asked my AI tooling
and what came back. Tool used throughout: **Claude Code (Opus)**, driven from the terminal in this
repo. Times are IST, 20 Sep 2026.

---

### 10:05 — First read of the packet, before touching anything

Read the exercise twice and wrote down what I thought the job was before opening a single file, so
I could check later whether the data changed my mind.

Going-in hypotheses:

1. The model will be decent-but-not-great, and the interesting work will be everything around it.
2. The vague mandate is the test. "Do something with all this account data" has no success metric
   attached, so defining the decision is part of the deliverable.
3. The story about the earlier scoring effort that "quietly lost credibility a couple of quarters
   after launch" is not colour. It's the brief telling me what they actually want to see.

One thing I noted immediately: the packet says `snapshot_date` and `account_id` "are identifiers,
not model inputs." That is a strange thing to spell out unless the date matters. Flagged to check.

---

### 10:20 — What is actually in the pickle

I did not want to unpickle a file blind — loading a pickle executes whatever is inside it — so I
scanned the opcodes first without executing, then loaded it.

**Asked Claude Code:** *"inspect the model pickle without executing it, then load it and describe
the pipeline."*

**Came back:** a static scan listing only `sklearn`/`numpy` classes and `_sklearn_version -> 1.5.2`,
then the loaded structure: `ColumnTransformer` (one-hot on `account_type` and `industry`,
`SimpleImputer(strategy="median")` on the seven numerics) feeding a
`GradientBoostingClassifier(n_estimators=40, max_depth=2, learning_rate=0.05, subsample=0.7)`.

Two things I pulled out of that myself:

- **`SimpleImputer(strategy="median")` with no `add_indicator`.** Missing values get silently
  replaced with the training median and the model never learns that anything was missing. Worth
  checking how often that fires.
- **`subsample=0.7`** means each tree was fitted on 70% of rows, so scikit-learn will have recorded
  out-of-bag improvement per tree. That is the only out-of-sample signal available without
  retraining, which the packet forbids. Noted to come back to.

---

### 10:35 — Profiling the two CSVs

Base rate first, because everything downstream depends on it.

- **1,200 training rows, 78 conversions = 6.5%.**
- The packet says real outreach-to-conversion is "well under 1% for cold accounts."

So the training sample converts at roughly 7–10x the real cold rate. A random draw from the
database could not look like this. **Conclusion: the sample is enriched, so the model's outputs are
ranks inside a warm population, not probabilities that transfer to the full database.** That single
fact rules out the obvious impact framing — score x deal value x account count — and I'd rather
find that now than have it picked apart in the room.

Then missingness: **`intent_score` is missing on 40.2% of training rows and 38.7% of the batch**,
and it is the feature the model leans on most. Combined with the median imputer, "the vendor does
not cover this company" becomes "this company has average intent." Conversion when intent is
present is **8.2%**, when missing **3.9%** — so missingness is informative, and the pipeline
deletes that information.

**Dead end:** I spent ten minutes checking whether missing intent skewed toward smaller companies,
because the packet states intent data "skews toward larger accounts." **In this snapshot it
doesn't** — coverage is 0.59–0.62 across all four employee-count quartiles, essentially flat. So
either the fixture doesn't reflect that claim or the claim isn't true here. Not a finding I can use,
but worth stating that I checked a claim in the brief rather than repeating it.

---

### 10:50 — The staleness thing, which turned out to be the centre of the exercise

Chased the `snapshot_date` flag from 10:05. Every activity column counts a **90-day window ending
on the snapshot date**, and the label is measured in the **90 days after** it. So the date isn't
metadata, it defines what every number in the row means.

Measured against 2026-08-01, as the packet instructs:

- Median snapshot age in the batch: **121 days**. **73% older than 90 days.** 14% over a year.
- **218 of the 300 accounts have an outcome window that already closed.**
- The model's **highest-scoring account, ACC-01491, was last updated 15 Oct 2025** — 290 days ago.
  Its 90-day outcome window ended in January.

And the model cannot see any of this, because `snapshot_date` is not one of its nine inputs. It
gives a stale account the same confident score as a fresh one.

That is the failure mode the packet describes: nothing crashes, the list looks fine, and reps are
handed accounts whose "recent activity" ended last spring. Do that a few mornings running and they
stop opening the list. **This is now the spine of the design.**

---

### 11:05 — Censored labels

Follow-on from the same window logic: a row snapshotted fewer than 90 days before the data was cut
cannot know its own outcome yet.

**101 training rows are younger than 90 days. All 101 are labelled "did not convert."** Zero
conversions among them. They are structurally negative regardless of what really happened.

*(Boundary note, caught when I moved this from an ad-hoc query into `analysis/profile.py`: my first
pass said 103 because I used `age <= 90`. There are exactly 2 rows sitting at 90 days, whose window
has just closed and whose label is therefore legitimate. The script uses the strict `< 90` and
reports **101**. Small, but it's the difference between a number I can defend and one I can't —
and it's why the write-up quotes the script rather than my notes.)*

It doesn't wreck the model — it's 8.4% of rows — but it matters for two reasons: it drags the base
rate down slightly, and **anyone retraining this on a rolling window repeats it every cycle**, so
the base rate sags and the scores drift with no error anywhere. That goes into the monitoring design
as a hard assertion on any future retrain.

---

### 11:20 — How good is the model, honestly

In-sample, on the rows it was fitted to: **AUC 0.759, PR-AUC 0.231** against a 0.065 baseline. That
is a ceiling, not an estimate, and I won't present it as anything else.

The out-of-bag trace from 10:20 is the more honest number:

- Total OOB improvement across all 40 trees: **+0.0097**.
- **19 of 40 trees made held-out loss worse.**
- The **last 10 trees sum to −0.0099** — actively harmful. It was overfitting by the end.

Then decile behaviour, which changed the design more than anything else:

| Decile | Conversion | Lift |
|---|---|---|
| 1 | **26.7%** | **4.1x** |
| 2 | 8.3% | 1.3x |
| 3 | 9.2% | 1.4x |
| 4–10 | 0.8%–6.7% | 0.1x–1.0x |

**The signal is in the top decile and nowhere else** — decile 5 converts worse than decile 10. So
"rank the list and work down it" is wrong; the list has to stop. I took the cut from the training
90th percentile score (**0.1088**) rather than "top 50 of the batch," so batches stay comparable
over time and a sudden overflow is itself a signal.

Also: **the maximum score across 1,200 rows is 0.27.** At the conventional 0.5 threshold this model
fires zero times, forever. It cannot be used as a yes/no classifier at all — somebody has to choose
a cutoff, and that somebody is me. Worth saying out loud in the proposal.

Calibration: decile 1 predicts 13.9% and delivers 26.7%; the middle deciles predict 5.6% and
deliver 0.8%. **The scores are ordering marks, not odds.**

---

### 11:45 — Where I overrode the AI (the required entry)

**What it proposed.** With the staleness finding in hand, Claude Code drafted a routing policy with
a hard gate: an account only reaches a rep if its snapshot is under 90 days old *and* its intent
score was actually measured. It read as rigorous, and it followed directly from the evidence I'd
just produced. I nearly took it.

**What I asked next:** *"run that rule against the real batch and show me what a rep actually
receives."*

**What came back:** of 300 accounts, 28 cleared the score bar and **6 survived the gates.** Six.

**Why I rejected it.** Six accounts is not a morning's work — and the failure is conceptual, not
just arithmetic. My own stated principle was that the scarce resource is rep trust. A system that
silently withholds 94% of its top tier is not protecting trust, it's replacing the rep's judgement
with mine and hiding the reasoning. Being honest about what we know is not the same as deciding for
somebody.

**What I changed it to.** Rank everything above the evidence bar, and *label* the uncertainty
instead of hiding it:

- `CALL_NOW` — above the bar, data under 90 days old
- `CALL_WITH_CAVEAT` — above the bar, data 3–12 months old, and the brief says so in plain words
- `RE_ENRICH` — above the bar but over a year old, or resting on intent nobody measured
- `NURTURE` / `HOLD` — below the bar, with the reason recorded

That produces ~22 queued accounts instead of 6, the rep sees why each one sits where it does, and
the genuinely expired accounts still get pulled. Same evidence, opposite handling of the human.

**The general lesson**, which I'd repeat in the room: the model's suggestion was defensible on
paper and wrong in practice, and the only reason I caught it was running it against the real batch
instead of reading it. Any rule that hasn't been executed against real data is a hypothesis.

---

### 12:15 — Framework choice, and checking my own bias

I wanted to use LangGraph, and I was suspicious of wanting it, because the honest description of
this job is "a batch pipeline that scores 300 rows." So I went looking for the case against.

**Asked Claude Code:** *"when is LangGraph overkill for a deterministic batch pipeline, according to
practitioners?"* and had it pull current sources rather than answer from memory.

**Came back**, consistently across sources: a graph framework earns its place when a system needs to
**branch, resume after failure, or wait for human approval mid-run**, and is ceremony below about
five linear steps. Several sources also make a distinction I had been blurring: **for static
deterministic scheduling the right tool is Airflow or Prefect, not an agent framework.**

That sharpened the answer rather than changing it. My flow branches five ways, loops the brief back
through a verifier, retries, and pauses for human approval before anything is published — so the
graph is doing real work. But the scheduling layer is not its job. **Airflow schedules the run;
LangGraph decides inside it.** Both go in the proposal, including the counter-argument: strip the
approval gate and this is a 150-line script.

---

### 12:40 — Scope decisions

Cut from the plan, deliberately, and recorded here so it's clear they were choices rather than
omissions:

- **No test suite.** The packet says "No formal test suite, no packaging, no CI/CD."
- **No retraining, no calibration layer, no missingness indicator** — all of which the data argues
  for, and all of which are explicitly a different role's job per the packet. I route around the
  imputation problem instead of fixing it.
- **Capacity optimiser and cooldown store: specified, not built.** The packet accepts a precisely
  specified check on equal terms with a built one, and the writing matters more than a fourth
  output file.

Earlier in prep I had planned an LLM-judge evaluation harness with judge calibration. Reading the
packet properly killed it: evals are not one of the three scored areas, monitoring is, and
"no formal test suite" is explicit. Dropped it before writing any of it.
