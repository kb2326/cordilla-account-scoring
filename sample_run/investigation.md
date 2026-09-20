# Boundary accounts: what the investigator did

These are the accounts where the rules were close to arbitrary. Each was given to a
tool-using agent that chose what to check and then recommended an action. The policy
keeps the final say; any override is recorded.

### ACC-00966

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> The score is solid and ranks 96th percentile among Prospects, but the evidence is 207 days stale—the 90-day activity window closed before late August 2026. Website visits and intent data from that period no longer predict current readiness. Refresh the account data before dialing to confirm the company is still engaged.

### ACC-00205

- rules said: **RE_ENRICH**
- agent recommended: **RE_ENRICH**
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong measured intent (63.3) is offset by a 419-day-old snapshot. Website activity, company status, and any recent engagement are unknown. Refresh the data before dialing to confirm the intent signal still applies and the account remains active.

### ACC-00265

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> Snapshot is 93 days old with no visibility into trial outcome or recent engagement. The marginal score (0.122 vs 0.109 threshold) combined with stale data means a call decision should wait for fresh firmographic and activity data to confirm the trial converted and the account remains active.

### ACC-00533

- rules said: **CALL_NOW**
- agent recommended: **CALL_NOW**
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity, compare_to_similar_accounts

> Measured intent score of 63 (2.5× baseline) is the primary driver and is real, not inferred. Account ranks 95th percentile among current Prospects. Data is 13 days fresh. No known CRM activity in the gap, but the intent signal is strong enough to warrant immediate outreach.

### ACC-00146

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Data is 192 days old and the decision hinges on a trial outcome we cannot see. The measured intent score (4.4) is weak enough that a call is only justified if recent activity shows genuine engagement. Refresh the account snapshot before dialing.

### ACC-01382

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> The score of 0.116 barely clears the call threshold, but it rests entirely on a 335-day-old snapshot. Intent and engagement signals are stale; recent CRM activity is unknown. Refresh the data before committing a rep's time.

### ACC-01019

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Data is 130 days old; the activity window it describes closed in early August. The 4 prior contacts show some interest, but we cannot tell if momentum persists. Refresh intent and engagement signals before spending a call on a prospect with weak, stale signals.

### ACC-01155

- rules said: **CALL_NOW**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts, probe_intent_sensitivity

> Score is marginal (0.116 vs. 0.109 threshold) and rests on a 30-day-old activity window; recent CRM movement is unknown. Refresh contact and intent data before committing a call—the account may have warmed or cooled in the last month.

### ACC-00728

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts, check_recent_crm_activity

> Measured intent of 8.9 and 10 visits in 90 days are genuine signals, and the account ranks at 92nd percentile among peers. However, the snapshot is 73 days old and recent activity is unknown; the rep should verify current engagement before investing heavily.

### ACC-01129

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts

> Strong measured intent (77.5) and top-percentile score, but snapshot is 126 days old and no longer reflects current engagement. Refresh activity data before calling—the decision is sound only if intent has held or grown.

### ACC-00100

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **CALL_WITH_CAVEAT**
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> Account scores at 93rd percentile among Suspects with genuine elevated intent (42 vs. typical 25) and 12 recent visits, but the snapshot is 94 days old and we have no visibility into the last 4 days. Rep should call, but must know the activity baseline may have shifted since August 1st.

### ACC-00958

- rules said: **RE_ENRICH**
- agent recommended: **RE_ENRICH**
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> Snapshot is 409 days old; all activity metrics reflect mid-2025. The account scores well relative to its cohort, but that strength is built on expired data. A rep needs current firmographic and engagement signals before calling a Former Customer with no known recent activity.

### ACC-01339

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong measured intent (70) is the only reason this account qualifies, but the snapshot is 240 days old and covers activity through August 2026. Before a rep calls, refresh the intent score and recent engagement to confirm the buying signal is still active in a healthcare prospect this size.

### ACC-00686

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> The trial and contact activity that drove the score ended 143 days ago; we have no visibility into the past 53 days. A 46-person services firm with trial engagement is worth calling, but only with current data. Refresh before dialing.

### ACC-00832

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts, probe_intent_sensitivity

> Account ranks in the 90th percentile among Prospects and has recent contact history, but the measured intent score (14.6) is 40% below typical and zero website visits in 90 days suggest dormancy. Rep should call, but treat the account as potentially colder than the score implies and be prepared to pivot to nurture if there's no fresh buying signal in the conversation.

### ACC-01496

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **CALL_WITH_CAVEAT**
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> Former Customer with 92nd-percentile score among peers and measured intent 53% above Retail baseline, but snapshot is 113 days old and recent engagement is unknown. Rep should call, but must verify current activity before investing heavily; this could be stale momentum.

### ACC-00768

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> The account's strong relative score (89th percentile) is built on a 213-day-old snapshot. The trial and engagement signals are real but expired; we need current data on whether this prospect has progressed, stalled, or converted before a rep invests a call.

### ACC-01102

- rules said: **NURTURE**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong measured intent (42.5) makes this worth pursuing, but the snapshot is 96 days old and we have no CRM activity visibility since. Refresh website activity and intent data before the rep calls; the signal is too good to ignore, but too stale to trust.

### ACC-00101

- rules said: **NURTURE**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity, compare_to_similar_accounts

> Former customer with measured intent 82% above baseline (45.6), but snapshot is 140 days old and we have no visibility into the last 5 months of activity or engagement. The intent signal is strong enough to warrant a call, but only after confirming the account hasn't already been worked and that conditions haven't changed. Refresh the data before dialing.

### ACC-00175

- rules said: **NURTURE**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> The account is a former customer scoring in the 86th percentile of its cohort, but the snapshot is 98 days old with a 1-month blind spot on recent activity. For a lapsed customer, current engagement status (re-engagement signals, new hiring, or deepening silence) would likely change the call decision. Refresh the data before dialing.
