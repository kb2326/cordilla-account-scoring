# Cordilla account triage

**Every morning this decides three things: which accounts a rep should phone today, which ones need
fresh data bought before anyone wastes a call on them, and which to leave alone. Then it writes down
what it decided, what it cost, and whether today's data was trustworthy enough to act on at all.**

A model that scores these accounts already existed and had sat unused for months, because a number in
a spreadsheet does not tell anyone who to ring on Monday. This repo is the part in between, plus the
checks that notice when it quietly stops being right.

That last part is not decoration. Cordilla shipped a scoring system once before; it launched well and
lost the room two quarters later, when the numbers drifted away from what reps were seeing and nobody
was watching closely enough to catch it.

```bash
pip install -r requirements.txt
python analysis/profile.py
python -m agent.run --as-of 2026-08-01
```

Read `sample_run/` to see the output without installing anything.

**Optional, both off by default.** Run `cp .env.example .env`:
`ANTHROPIC_API_KEY` makes the call briefs live and unlocks `--investigate`;
`LANGSMITH_TRACING` + `LANGSMITH_API_KEY` turn on tracing, which needs no code at all.

---

## The problem

Cordilla has tens of thousands of non-customer accounts and five reps. A rep makes ~40 calls a day
and cold conversion is under 1%, so the only lever is **choosing better**.

A model already scored those accounts and then sat unused, because a number in a file changes
nobody's Tuesday. Three measured facts explain why it can't simply be switched on:

| What the data says | Why it matters |
|---|---|
| It is only trustworthy about its **top 10%**. Below that, its ordering is no better than shuffling | The list has to stop somewhere, and the model cannot say where. It never scores anything above 0.27, so the usual "act when it passes 0.5" rule would fire on nothing, ever |
| **73% of accounts** carry information over 90 days old, and every feature counts a 90-day window | For **218 of 300 accounts the period being predicted has already closed** |
| **39% have no buying-intent data**, and the step that prepares data for the model fills the gap with an average | "We know nothing about this company" silently becomes "normal interest", on the fact the model leans on most |

None of that is the model's fault. It was given nine facts about each company and the date was not one
of them, so it genuinely cannot tell fresh information from a year-old file.

## What we did about it

Five problems, five specific things built. This is the whole submission in one table.

| The problem | What we built |
|---|---|
| The model cannot say where the list should stop | A cut-off at the point its own evidence runs out, fixed in advance rather than "take the top 50 of whatever arrived today" |
| It cannot see how old the information is | Every account's age is worked out before scoring, and anything describing a period that has already closed is routed away from a phone call |
| It cannot tell "no data" from "average data" | We test whether the missing number would change the decision. If it would, we buy the data instead of guessing |
| It cannot tell a rep why | A plain-English reason per account, worked out from the model itself, plus two or three sentences they can actually open a call with |
| Nobody would notice it going wrong | Six checks comparing every batch against what normal looks like, with the authority to stop the run rather than publish a list nobody should trust |

The last row is the one that matters most, and the rest of this README is mostly about it.

---

## What the agent does

```mermaid
flowchart TD
    IN["Today's accounts"] --> CHK{"Does this batch look like<br/>the data the model was built on?"}
    CHK -->|"no"| STOP["Stop.<br/>Publish nothing.<br/>Tell a human."]
    CHK -->|"yes"| SCORE["Score with the existing model"]
    SCORE --> WHY["Work out why each<br/>account scored that way"]
    WHY --> ROUTE{"What should happen<br/>to this account?"}
    ROUTE --> CALL["Rep calls today"]
    ROUTE --> FRESH["Buy fresh data first"]
    ROUTE --> NURT["Marketing nurture"]
    ROUTE --> HOLD["Leave alone,<br/>reason recorded"]
    CALL --> BRIEF["Write the call brief:<br/>model writes the words,<br/>code fills every number"]
    BRIEF --> PUB["Publish to the rep's<br/>normal task list"]
    PUB --> REC["Record every decision,<br/>timing and cost"]
    STOP --> REC
```

The rep never opens a dashboard. The work appears where their work already is.

### How one account is decided

```mermaid
flowchart TD
    A["One account"] --> B{"Score in the top 10%?"}
    B -->|"no, but top 30%"| N["NURTURE"]
    B -->|"no"| H["HOLD — reason recorded"]
    B -->|"yes"| C{"How old is the data?"}
    C -->|"over a year"| F["RE-ENRICH<br/>refresh before calling"]
    C -->|"3–12 months"| E["CALL WITH CAVEAT<br/>brief states the age"]
    C -->|"under 90 days"| D{"Was intent measured,<br/>or filled in?"}
    D -->|"filled in, and it<br/>decides the outcome"| F
    D -->|"measured"| G["CALL NOW"]
```

Every threshold traces to something measured:

| Rule | Value | Where it comes from |
|---|---|---|
| Top 10% | score ≥ **0.1088** | Training 90th percentile. Above it, conversion is 26.7% against a 6.5% base |
| Too old to act on | **90 days** | The features' own window. Past it, nothing overlaps the period being predicted |
| Expired | **365 days** | A call would reference events more than a year old |

Absolute cuts rather than "top 50 of today", so a batch that suddenly overflows the tier is itself an
alarm.

---

## Architecture

**The distinction this design turns on:** a *workflow* runs a predetermined path; an *agent* decides
its own next step. Most of this is a workflow, on purpose. One part is an agent, also on purpose.

Three layers, and the split is the whole design.

```mermaid
flowchart LR
        subgraph D["RULES · ~280 accounts"]
        direction TB
        D1["Check the data<br/>is usable"] --> D2["Ask the model<br/>for a score"] --> D3["Work out why<br/>it scored that"] --> D4["Apply the<br/>thresholds"]
    end
        subgraph A["AGENT · ~20 borderline accounts"]
        direction TB
        A1["Model picks<br/>what to check next"] --> A2["Recommends<br/>an action"] --> A3["Rules can<br/>overrule it"]
    end
        subgraph L["WRITING · queued accounts only"]
        direction TB
        L1["Model writes the words,<br/>leaving gaps for numbers"] --> L2["Code fills<br/>every number"] --> L3["Any invented number<br/>is rejected"]
    end
    D --> A --> L --> OUT["Queue · briefs<br/>enrichment list · run record"]
```

**Why so little is agentic.** Every fact is present at load time and the routing rule is a threshold
comparison. There is nothing to discover, so nothing to decide about what to discover. Asking a
language model whether 0.15 is at least 0.1088 would cost determinism, break the control-group
comparison, and discard the one component with historical evidence in it.

**Where an agent genuinely earns its place**: roughly 20 accounts a run sit close enough to the
threshold that the rule is arbitrary, and there the next question depends on the last answer. Those
get a real tool-calling loop (`agent/investigator.py`, off by default, `--investigate`):

```mermaid
flowchart LR
    S["Boundary account"] --> M["Model decides<br/>what to check next"]
    M -->|"tool call"| T["check_data_freshness<br/>probe_intent_sensitivity<br/>compare_to_similar_accounts<br/>check_recent_crm_activity"]
    T -->|"observation"| M
    M -->|"enough"| R["recommend_action"]
    R --> V{"Policy veto"}
    V -->|"allowed"| OK["Applied"]
    V -->|"unsafe"| NO["Blocked, reason recorded"]
```

The model chooses **which** question to ask. It never supplies the facts, because tools read from
injected state, and it never has the last word: an expired account cannot reach a rep however
persuasive the reasoning. On the committed run it investigated 20 accounts in 52 turns and changed 16 decisions,
**most of them more cautious than the rules**, moving accounts from "call with a caveat" to "refresh
the data first". It is not fully deterministic: re-running shifts a decision or two either way, which
is exactly why it is confined to the ~20 accounts where the rule was arbitrary anyway.

It is also **91% of the model spend for 6.7% of the accounts** ($0.126 of $0.138), which is why it is
off by default and pointed only where the rules are genuinely arbitrary.

### The graph, generated from the code

`python -m agent.run --as-of 2026-08-01 --print-graph`

```mermaid
flowchart TD
    start(["start"]) --> load_batch
    load_batch --> quality_gate
    quality_gate -. "red" .-> halt
    quality_gate -. "green / amber" .-> score
    score --> explain --> triage
    triage -. "--investigate" .-> investigate --> write_briefs
    triage -. "default" .-> write_briefs
    write_briefs --> verify_briefs
    verify_briefs -. "invented a number" .-> write_briefs
    verify_briefs -. "clean" .-> publish
    halt --> finish(["end"])
    publish --> finish
```

Two cycles carry the weight. `quality_gate → halt` stops a bad batch before it reaches anyone;
`verify_briefs → write_briefs` sends a brief back when the model writes a number it wasn't given.
`publish` pauses for a human when the batch is amber.

### Every node, and what happens when it fails

Which steps involve a model, and what each does when something goes wrong. Error handling is
assigned by *type* rather than uniformly. A retry helps a flaky network call and does nothing for a
bad threshold.

| Node | What it does | Model? | On failure |
|---|---|---|---|
| `load_batch` | Reads the CSV, refuses it if the schema is wrong, adds each account's age and data-gap flags | no | **Retry** once, since a file read can fail transiently |
| `quality_gate` | Compares the batch against what the training data looked like | no | **Routes to `halt`** on red. Publishing nothing is the correct outcome, not an error |
| `score` | `predict_proba` on the exact nine-column contract | no | **Retry** once, then raise |
| `explain` | Re-scores each account with one feature removed to find its drivers | no | **Raise**, because a pure function failing means a real bug |
| `triage` | Applies the thresholds, fills rep capacity, assigns the control group | no | **Raise** |
| `investigate` *(optional)* | Tool-calling agent on ~20 borderline accounts | **yes**, chooses tools | **Skipped and recorded** when no key; capped at 12 turns; policy vetoes unsafe output |
| `write_briefs` | Asks the model for 2-3 sentences per queued account | **yes**, writes prose only | **Retry** once, since an API call is the one thing here that fails randomly |
| `verify_briefs` | Rejects any number the model typed itself | no | **Loops back** to `write_briefs`, twice, then falls back to a deterministic template |
| `publish` | Writes the outputs and the run record | no | **Pauses for a human** when the batch is amber, via `interrupt()` rather than a boolean |

**What travels between nodes.** The run's state holds decisions, counts and health: things worth
replaying. The batch itself travels beside it, because checkpointed state must be serialisable and a
dataframe is not. In production that becomes a file path rather than a frame anywhere.

**So: seven of nine nodes never touch a model.** The two that do are confined to language and to
twenty ambiguous accounts, and both are checked afterwards by code that can overrule them.

---

## Monitoring

These systems fail without crashing. `python -m monitoring.demo_silent_failure` breaks the real
batch three ways and runs the real agent against each:

| Broken how | What the model reports | What the checks do |
|---|---|---|
| Intent vendor coverage collapses | 300 accounts, mean 0.0607, all valid | **RED — halted** |
| Refresh pipeline stalls (+200 days) | 300 accounts, **mean 0.0655 — identical** | **RED — halted** |
| Upstream filter halves the batch | 105 accounts, all valid | **AMBER — paused** |

Zero exceptions in all three. The middle row is the demonstration: ageing every snapshot by 200
days leaves the mean score exactly where it was, because the model cannot see dates.

**Three clocks.** Coverage, staleness, batch size and score drift are checked **daily**. Needing no
labels, they are the only signals that catch anything this week. Rep dispositions are a
**four-week** signal. Conversion against the held-back control group is the **quarterly** verdict.
One bad week means nothing at 30 accounts a week. The arithmetic is in `PROPOSAL.md`.

`monitoring/RUNBOOK.md` gives every alert an owner and a first move.

---

## Observability

| File | For | Contents |
|---|---|---|
| `runs.jsonl` | analyst | One line per run: config used, counts by action, per-node timings, **measured cost**, alerts |
| `decisions.csv` | analyst | One row per account — score, data age, action, reason, control-group flag. **Joins to CRM outcomes in 90 days** |
| `run_summary.txt` | sales manager | Five lines, no jargon |

Cost is measured rather than estimated, and includes every model call. The committed run
(`--investigate`, live) is `claude-haiku-4-5-20251001`, **62 calls, $0.1376** — 10 briefs at $0.012 and
52 investigation turns at $0.126 — with tokens taken from the API responses. The default run, without
the boundary agent, is 16 briefs for about **$0.019**. Every figure is tagged **measured** or
**assumed**.

Accept-rate and lift print as **pending**, never estimated — that data does not exist for 14 weeks,
and filling the gap with a guess is what cost the previous effort its credibility.

### Tracing

**LangSmith needs no code** — LangGraph emits to it natively, so two environment variables are the
whole integration. Verified on a live run rather than assumed:

```
chain  publish              15ms
chain  verify_briefs         5ms
llm    ChatAnthropic      2566ms | 687 tokens
llm    ChatAnthropic      2134ms | 700 tokens     ... x16
```

It earns its place on the LLM layer: debugging a tool-choosing loop from a JSON file is painful, and
`--investigate` makes 50+ model calls a run. What it does **not** do is answer the question the
business actually has. *"Did the accounts we queued in August beat the ones we held back?"* is a join
between `decisions.csv` and the CRM ninety days later, and no tracing tool stores that. Nor can a trace
stop a bad batch: `monitoring/checks.py` runs **before** anything publishes, which is where the value
is. Our worst failure produces a perfectly clean trace.

Langfuse is the same two ideas with one extra dependency, and self-hostable: the right call if CRM
records cannot leave the building.

---

## The language model

Runs live when `ANTHROPIC_API_KEY` is set and falls back to a documented stand-in when it isn't, so
the repo works either way and the run record says which path ran.

Its authority is deliberately narrow: it writes sentences, and on boundary accounts it chooses what
to check. Every number in a brief is substituted by code from a fixed fact set, and a verifier rejects
any digit the model typed itself. A brief that misquotes a figure to a customer costs trust that is
hard to win back, and nothing in the logs would show it happened.

---

## Run everything

```bash
python analysis/profile.py                             # regenerate every number quoted anywhere
python analysis/policy_backtest.py                     # do our gates actually beat raw ranking?
python -m agent.run --as-of 2026-08-01                 # the agent
python -m agent.run --as-of 2026-08-01 --investigate   # + the tool-using agent (needs a key)
python -m monitoring.checks --as-of 2026-08-01         # checks alone; exit 0/1/2 = green/amber/red
python -m monitoring.demo_silent_failure               # proof the checks catch silent failures

# with tracing on - no code changes, just the environment
LANGSMITH_TRACING=true LANGSMITH_API_KEY=... python -m agent.run --as-of 2026-08-01
```

`--as-of` is required and never defaults to the system clock: both CSVs are snapshots taken on
2026-08-01, and every age here is measured from that date. Python 3.11 or 3.12 (numpy 1.26.4 has no
3.13 wheels).

---

## Where each deliverable lives

| The exercise asks for | Here |
|---|---|
| **Impact framing**, grounded in the data | `PROPOSAL.md` §1, numbers from `analysis/findings.json` |
| **A working agent** that changes a rep's day | `agent/` · `sample_run/` · 0.1s mocked, 13s live, 47s with `--investigate` |
| Tools and actions, **and why those** | `PROPOSAL.md` §2 · `agent/policy.py` · `agent/investigator.py` |
| Structure, control flow, framework choice | The diagrams above · `agent/graph.py` |
| **Monitoring**: what to watch, noise vs signal, response | `PROPOSAL.md` §3 · `monitoring/` |
| One concrete, runnable piece of it | `monitoring/checks.py` + `demo_silent_failure.py` |
| Written proposal, 800–1,200 words | `PROPOSAL.md` |
| Research log, kept as the work happened | `RESEARCH-LOG.md` |

```
analysis/     profile.py            measures the data and the model; writes findings.json
              policy_backtest.py    tests our own routing gates against outcomes
agent/        run.py                entry point
              graph.py              the flow above, as a LangGraph state machine
              contracts.py          what a valid batch is; per-account quality flags
              scoring.py            loads the pickle safely, scores a fixed contract
              policy.py             the thresholds, each beside its evidence
              explain.py            why an account scored what it did
              investigator.py       the tool-using agent for boundary accounts
              brief.py, llm.py      slot filling, the verifier, the model seam
              emit.py               the audience-specific outputs
monitoring/   checks.py, demo_silent_failure.py, RUNBOOK.md
```

## What this is not

Not a retrained model: the pickle is used exactly as provided. Not a lookup tool; nobody types in an
account number. Not an autonomous emailer, since it queues work for humans and stops before anything
leaves the building. Not production code, with no test suite, packaging or CI, as the exercise asks.
