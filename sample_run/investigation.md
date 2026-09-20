# Boundary accounts: what the investigator did

These are the accounts where the rules were close to arbitrary. Each was given to a
tool-using agent that chose what to check and then recommended an action. The policy
keeps the final say; any override is recorded.

### ACC-00100

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> Strong relative score (93rd percentile) and measured intent signal (42 vs. baseline 25) warrant a call, but the activity snapshot is 94 days old and the 90-day window is fully expired. Refresh website and intent data before dialing to confirm engagement is still active.

### ACC-00101

- rules said: **NURTURE**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity, compare_to_similar_accounts

> Former customer with measured intent 82% above baseline, but snapshot is 140 days old and we have no visibility into recent CRM activity or current engagement. The intent signal is real and worth pursuing, but only after confirming whether the account has already been re-contacted or whether conditions have changed since May.

### ACC-00146

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity, compare_to_similar_accounts

> Snapshot is 192 days old and covers a closed activity window; trial status and engagement momentum are unknown. Weak intent signal (4.4 vs. typical 25) combined with stale data makes this a poor candidate for a cold call without current information. Refresh data on trial outcome and recent engagement before dialing.

### ACC-00175

- rules said: **NURTURE**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> Score of 0.106 is just below threshold but ranks 86th percentile among Former Customers, and data is fresher than peer median. However, the snapshot is 98 days old with no visibility into the last 8 days of activity. Rep should call, but must verify current engagement status before investing heavily—this is a re-engagement play, not a cold outreach.

### ACC-00205

- rules said: **RE_ENRICH**
- agent recommended: **RE_ENRICH**
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong intent signal (63.3) is real, but all other account data is 419 days old. Website activity, company profile, and market status are unknown. Refresh before dialing to avoid wasting a call on stale intelligence.

### ACC-00265

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> Snapshot is 93 days old; the 90-day activity window is now closed and tells us nothing about current engagement. Trial status and recent contact activity are unknown. The marginal score (0.122 vs 0.109 threshold) does not justify a call on expired data—refresh before dialing.

### ACC-00533

- rules said: **CALL_NOW**
- agent recommended: **CALL_NOW**
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity, compare_to_similar_accounts

> Strong, measured intent signal (63 vs. baseline 25) on fresh data (13 days old) places this account at the 95th percentile of prospects. The score is above threshold and the evidence is real, not inferred. Call to validate intent and capture the opportunity while the signal is hot.

### ACC-00686

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> The score is solid (90th percentile among prospects), but it rests on a 143-day-old snapshot describing a closed 90-day window. Trial activity and contact counts tell us nothing about the account's state today. Refresh the data before dialing—a 46-person services firm that was actively trialing 5 months ago may have bought, churned, or gone cold, and we cannot tell which.

### ACC-00728

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts, check_recent_crm_activity

> Measured intent (8.9) and 10 visits in 90 days place this account at the 92nd percentile of Prospects—a genuine outlier. However, the snapshot is 73 days old and we have no visibility into recent activity. Rep should call, but verify current engagement before investing heavily.

### ACC-00768

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> The 89th-percentile score is built on a 213-day-old snapshot. Trial activity and website engagement are strong signals, but we have no visibility into the past 7 months. Refresh the data before dialing—the account may have converted, churned, or remained engaged, and a current picture will make the call decision much sharper.

### ACC-00832

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts, probe_intent_sensitivity

> Account ranks in the 90th percentile among peers and has recent sales contact history, but measured intent is 40% below typical and there are no website visits in 90 days. Rep should call, but expect lower conversion probability and confirm buying timeline before investing heavily.

### ACC-00958

- rules said: **RE_ENRICH**
- agent recommended: **RE_ENRICH**
- checks it chose to run: check_data_freshness, check_recent_crm_activity

> Snapshot is 409 days old; the "0 website visits" metric covers August 2025, not current behavior. For a Former Customer, we need fresh data on whether they've re-engaged, changed leadership, or remain dormant before a rep invests time. Current score is unreliable.

### ACC-00966

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> The score rests on activity (8 visits, intent 52) from a 207-day-old snapshot. Website engagement and intent signals decay quickly in Retail; we need current data to know if this prospect is still warm before committing a call. The measured intent score is solid, but it's stale.

### ACC-01019

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Data is 130 days old and the score margin is negligible (0.007 above threshold). The measured intent score of 7.7 is genuinely weak. Refresh contact and engagement data before deciding whether to call; the current snapshot is too stale to support a confident decision on a borderline account.

### ACC-01102

- rules said: **NURTURE**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts

> Account ranks 88th percentile among Prospects with measured intent of 42.5 (68% above baseline). Snapshot is 96 days old; rep should verify current engagement status before dialing, but the intent signal and cohort standing justify the call attempt.

### ACC-01129

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts

> The measured intent score of 77.5 is genuinely strong, but the snapshot is 126 days old and the 90-day activity window has expired. Before committing a rep's time, refresh the intent and website activity data to confirm the signal is still live.

### ACC-01155

- rules said: **CALL_NOW**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts, probe_intent_sensitivity

> Score is marginal and rests on a 30-day-old snapshot; the 7 contacts and intent score are from an even older 90-day window. Recent engagement is unknown. Refresh the data before committing a call.

### ACC-01339

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong measured intent (70) is the only reason this clears the call threshold, but the entire snapshot is 240 days old. Current engagement state and whether the buying signal persists are unknown. Refresh the data before dialing—the intent may still be hot, but we need to know today's picture, not August's.

### ACC-01382

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> The score of 0.116 sits only 6% above threshold and rests on a 335-day-old snapshot. Intent and engagement data are stale; we have no visibility into the past year. Fresh data is required to make a confident call decision on this account.

### ACC-01496

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> This account shows genuine above-market intent (38 vs. 25 median) and was a strong outlier among Former Customers, but the snapshot is 113 days old and we have no visibility into the last 23 days. For a former customer, that gap is material—a rep needs current engagement data before investing a call. Refresh the website activity and intent signals, then decide.
