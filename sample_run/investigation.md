# Boundary accounts: what the investigator did

These are the accounts where the rules were close to arbitrary. Each was given to a
tool-using agent that chose what to check and then recommended an action. The policy
keeps the final say; any override is recorded.

### ACC-00100

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> Strong relative score (93rd percentile) and measured intent signal (42 vs. baseline 25) warrant a call, but the 90-day activity window is now 94 days stale with no CRM visibility into the last month. Refresh website and engagement data before dialing to confirm the account is still active.

### ACC-00101

- rules said: **NURTURE**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity, compare_to_similar_accounts

> The measured intent score (45.6) is genuinely strong and the account ranks at the 89th percentile of its peer group, but the snapshot is 140 days old and we have no visibility into the last 5 months of activity or status change. A fresh data pull on this former customer would either confirm the intent signal is still live or reveal why it should be deprioritized—worth the cost before dialing.

### ACC-00146

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Data is 192 days old and the decision hinges on a marginal score built on that stale snapshot. The weak intent signal (4.4) combined with unknown activity over the past 6 months means we need fresh data before committing a rep's call. A quick account refresh will clarify whether the trial converted, engagement continued, or the lead has cooled.

### ACC-00175

- rules said: **NURTURE**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> Former customer scoring 86th percentile among peers with 4 recent sales contacts, but snapshot is 98 days old and we have no visibility into the last month. Rep should call to confirm current status and intent, but must know the engagement signals are not current.

### ACC-00205

- rules said: **RE_ENRICH**
- agent recommended: **RE_ENRICH**
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts

> Strong measured intent (63) and 95th-percentile score among peers make this worth a call—but the snapshot is 419 days old and all activity metrics are stale. Refresh engagement and intent data before dialing; a year-old signal in Retail is not actionable without confirmation of current state.

### ACC-00265

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> Data is 93 days old with no visibility into trial engagement or recent activity. The marginal score (0.122 vs 0.109 threshold) combined with expired activity metrics means a fresh data pull is needed to decide whether this is a live opportunity or a stalled trial.

### ACC-00533

- rules said: **CALL_NOW**
- agent recommended: **CALL_NOW**
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts, check_recent_crm_activity

> Measured intent score of 63 is genuine and ranks this 65-person manufacturer at the 95th percentile among prospects. Data is current (13 days old). The intent signal alone justifies a call; website activity is secondary.

### ACC-00686

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts

> The score is marginally above threshold, but it rests entirely on trial and contact activity from 143 days ago—well outside any reasonable recency window. The trial may have stalled, contacts may have gone cold, or the company may have already decided. A rep's time is better spent on accounts with current signals. Refresh the data before dialing.

### ACC-00728

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts, check_recent_crm_activity

> Strong measured intent (8.9) and website engagement place this at 92nd percentile among Prospects, but the snapshot is 73 days old. Rep should call, but verify current engagement before investing heavily—the buying signal is real, but we don't know if momentum has continued.

### ACC-00768

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> Strong engagement signals (trial, 14 visits, right fit) but snapshot is 213 days old and covers activity through August 2026. No visibility into whether trial converted or engagement continued. Refresh data before calling to avoid wasting a rep on a cold trail.

### ACC-00832

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts, probe_intent_sensitivity

> Account ranks in the 90th percentile among Prospects and data is current, but the decision is marginal: intent is 40% below typical and there are zero website visits in 90 days. Rep should call, but treat this as a relationship-check rather than a hot lead, and be prepared for low engagement.

### ACC-00958

- rules said: **RE_ENRICH**
- agent recommended: **RE_ENRICH**
- checks it chose to run: check_data_freshness, check_recent_crm_activity

> Snapshot is 409 days old; all activity signals (5 contacts, 0 web visits) describe a window ending August 2025. For a Former Customer, the gap since then is unknown and material. The marginal score (0.112 vs. 0.109 threshold) does not justify a call on expired data—refresh first.

### ACC-00966

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> The snapshot is 207 days old and the score sits only 2.3% above threshold. Website activity and intent from August 2026 do not tell us whether this prospect is still engaged or has moved on. Refresh the data before calling.

### ACC-01019

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Snapshot is 130 days old; the 90-day activity window is closed. Intent score of 7.7 is weak and real. No visibility into CRM activity or website behavior since the snapshot. Refresh data before calling—the current score rests on expired signals and a marginal threshold.

### ACC-01102

- rules said: **NURTURE**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong measured intent (42.5, well above baseline) makes this worth calling, but the snapshot is 96 days old and we have no CRM activity visibility since. Refresh the data before the rep dials—the intent signal is too good to waste on stale information.

### ACC-01129

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, compare_to_similar_accounts

> Strong measured intent (77.5) and top-percentile score, but snapshot is 126 days old and the 90-day activity window is stale. Refresh intent and website activity data before calling; the decision hinges on whether momentum has persisted.

### ACC-01155

- rules said: **CALL_NOW**
- agent recommended: **CALL_WITH_CAVEAT**  ← changed
- checks it chose to run: check_data_freshness, check_recent_crm_activity, compare_to_similar_accounts, probe_intent_sensitivity

> Account scores at 93rd percentile among Prospects with measured intent of 23.5 and 7 prior touches—worth a call. However, the activity window is now 120 days stale; rep should verify current situation before investing heavily, as retail buying signals can shift in 30 days.

### ACC-01339

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, probe_intent_sensitivity, check_recent_crm_activity

> Strong measured intent (70) is the only reason this clears the call threshold, but the snapshot is 240 days old and we have no visibility into recent CRM activity or current engagement. Refresh the data before dialing—the intent signal may have decayed or the account may already be in motion.

### ACC-01382

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **RE_ENRICH**  ← changed
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity

> Snapshot is 335 days old; the intent score and contact history describe a 90-day window that closed nearly a year ago. The marginal score (0.116 vs. 0.109 threshold) is not reliable without current data. Refresh before dialing.

### ACC-01496

- rules said: **CALL_WITH_CAVEAT**
- agent recommended: **CALL_WITH_CAVEAT**
- checks it chose to run: check_data_freshness, compare_to_similar_accounts, check_recent_crm_activity, probe_intent_sensitivity

> Former Customer with measured intent score 38 (above retail median) and 92nd-percentile score among peers—genuine re-engagement signal. However, snapshot is 113 days old and recent CRM activity is unknown. Rep should call, but verify current status and intent before investing heavily; account may have cooled or moved on.
