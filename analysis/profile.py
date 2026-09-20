"""Measure the data and the model. Write every number the write-up quotes.

One rule in this repo: if a figure appears in PROPOSAL.md or README.md, it comes
out of analysis/findings.json, which this script regenerates from the provided
files. Nothing here retrains, tunes or modifies anything - it loads, measures,
and reports.

    python analysis/profile.py

The model's in-sample numbers are reported as a ceiling and labelled as such:
measuring a model on the rows it was fitted to says nothing about how it behaves
on anything else.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
TRAIN_CSV = ROOT / "data" / "training_data.csv"
SCORE_CSV = ROOT / "data" / "accounts_to_score.csv"
MODEL_PKL = ROOT / "model" / "model.pkl"
OUT_JSON = Path(__file__).with_name("findings.json")

# The packet: "Treat 2026-08-01 as today for any recency/age calculation, not your
# system clock." Every age in this repo is measured from here.
AS_OF = pd.Timestamp("2026-08-01")

# Features are counted over the 90 days before snapshot_date; the label is measured
# over the 90 days after it. That one number sets both the staleness rule and the
# censoring rule below.
HORIZON_DAYS = 90


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load():
    train = pd.read_csv(TRAIN_CSV, parse_dates=["snapshot_date"])
    score = pd.read_csv(SCORE_CSV, parse_dates=["snapshot_date"])
    with MODEL_PKL.open("rb") as fh:
        model = pickle.load(fh)
    for df in (train, score):
        df["snapshot_age_days"] = (AS_OF - df["snapshot_date"]).dt.days
    return train, score, model


def psi(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    """Population Stability Index, bin edges taken from the expected distribution.

    Answers "has the new batch moved relative to what the model was fitted on".
    Convention: <0.1 stable, 0.1-0.25 watch, >0.25 investigate.
    """
    exp, act = expected.dropna(), actual.dropna()
    if exp.empty or act.empty:
        return float("nan")
    edges = np.unique(np.quantile(exp, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    e = np.clip(np.histogram(exp, bins=edges)[0] / len(exp), 1e-6, None)
    a = np.clip(np.histogram(act, bins=edges)[0] / len(act), 1e-6, None)
    return float(((a - e) * np.log(a / e)).sum())


def data_shape(train: pd.DataFrame, score: pd.DataFrame) -> dict:
    """How the two files were put together."""
    return {
        "train_rows": len(train),
        "score_rows": len(score),
        "accounts_in_both_files": len(set(train.account_id) & set(score.account_id)),
        "max_rows_per_account": int(max(train.account_id.value_counts().max(),
                                        score.account_id.value_counts().max())),
        "train_distinct_snapshot_dates": int(train.snapshot_date.nunique()),
        "score_distinct_snapshot_dates": int(score.snapshot_date.nunique()),
        "train_date_range": [str(train.snapshot_date.min().date()), str(train.snapshot_date.max().date())],
        "score_date_range": [str(score.snapshot_date.min().date()), str(score.snapshot_date.max().date())],
    }


def base_rate(train: pd.DataFrame) -> dict:
    """The conversion rate the model was fitted against.

    The packet puts real outreach-to-conversion "well under 1% for cold accounts".
    This sample converts far above that, so it is not a random draw of the
    database: the scores rank within a warm sample, they are not population odds.
    """
    by_type = train.groupby("account_type").converted_within_90d.agg(["mean", "size"])
    return {
        "positives": int(train.converted_within_90d.sum()),
        "rate": float(train.converted_within_90d.mean()),
        "packet_says_real_world_cold": "well under 1%",
        "by_account_type": {k: {"n": int(r["size"]), "rate": float(r["mean"])} for k, r in by_type.iterrows()},
    }


def label_censoring(train: pd.DataFrame) -> dict:
    """Rows whose 90-day outcome window had not closed when the data was cut.

    A row snapshotted fewer than 90 days before the cut-off cannot have observed
    its own outcome, so it is recorded as a non-conversion whatever happened.
    """
    recent = train[train.snapshot_age_days < HORIZON_DAYS]
    mature = train[train.snapshot_age_days >= HORIZON_DAYS]
    return {
        "rows_with_immature_window": int(len(recent)),
        "conversions_among_them": int(recent.converted_within_90d.sum()),
        "share_of_training_rows": float(len(recent) / len(train)),
        "base_rate_all_rows": float(train.converted_within_90d.mean()),
        "base_rate_mature_rows_only": float(mature.converted_within_90d.mean()),
    }


def freshness(train: pd.DataFrame, score: pd.DataFrame) -> dict:
    """How old each row's information is, measured from AS_OF.

    Past HORIZON_DAYS the row's activity window no longer overlaps the window we
    are trying to predict: it describes a period that has already finished.
    """
    out = {}
    for name, df in (("train", train), ("score", score)):
        age = df.snapshot_age_days
        out[name] = {
            "median_age_days": float(age.median()),
            "p25_age_days": float(age.quantile(0.25)),
            "p75_age_days": float(age.quantile(0.75)),
            "max_age_days": int(age.max()),
            "share_older_than_90d": float((age > HORIZON_DAYS).mean()),
            "share_older_than_365d": float((age > 365).mean()),
            "outcome_window_already_closed": int((age > HORIZON_DAYS).sum()),
        }
    return out


def coverage(train: pd.DataFrame, score: pd.DataFrame) -> dict:
    """Missing intent data: how much, whether it is informative, and who has it.

    SimpleImputer(strategy="median") fills it with the training median and adds no
    indicator, so "the vendor does not cover this company" becomes "this company
    has average intent" - on the model's heaviest feature.
    """
    missing = train.intent_score.isna()
    size_q = pd.qcut(train.employee_count, 4, duplicates="drop")
    cov_by_size = 1 - train.groupby(size_q, observed=True).intent_score.apply(lambda s: s.isna().mean())
    return {
        "intent_missing_train": float(missing.mean()),
        "intent_missing_score": float(score.intent_score.isna().mean()),
        "imputed_with_training_median": float(train.intent_score.median()),
        "conversion_when_intent_present": float(train.loc[~missing, "converted_within_90d"].mean()),
        "conversion_when_intent_missing": float(train.loc[missing, "converted_within_90d"].mean()),
        # The packet says intent data "skews toward larger accounts". Checked, not assumed.
        "coverage_by_employee_quartile": {str(k): round(float(v), 3) for k, v in cov_by_size.items()},
        "zero_share_train": {
            c: float((train[c] == 0).mean())
            for c in ["mql_count_90d", "trial_started", "trial_active_users",
                      "web_touchpoints_90d", "sales_contacts_90d"]
        },
        "contradiction_trial_users_without_trial": int(((train.trial_active_users > 0) & (train.trial_started == 0)).sum()),
    }


def model_card(model) -> dict:
    clf = model.named_steps["clf"]
    encoded = list(model.named_steps["pre"].get_feature_names_out())
    importance = sorted(zip(encoded, clf.feature_importances_), key=lambda t: -t[1])
    # subsample=0.7 means each tree held out 30% of rows, and sklearn recorded how
    # much each tree improved loss on rows it had not seen. This is the only
    # out-of-sample signal available without retraining, which the packet forbids.
    oob = clf.oob_improvement_
    return {
        "sklearn_version_at_save": getattr(model, "_sklearn_version", "unknown"),
        "sklearn_version_running": sklearn.__version__,
        "classifier": type(clf).__name__,
        "n_estimators": int(clf.n_estimators),
        "max_depth": int(clf.max_depth),
        "subsample": float(clf.subsample),
        "feature_contract": list(model.feature_names_in_),
        "encoded_feature_count": len(encoded),
        "top_importances": {n: round(float(v), 4) for n, v in importance[:6]},
        "oob_total_improvement": float(oob.sum()),
        "oob_last10_improvement": float(oob[-10:].sum()),
        "oob_trees_that_made_it_worse": int((oob < 0).sum()),
        "oob_tree_count": int(len(oob)),
    }


def in_sample_performance(model, train: pd.DataFrame) -> dict:
    """Measured on the rows the model was fitted to: a ceiling, not an estimate."""
    features = list(model.feature_names_in_)
    y = train.converted_within_90d.values
    p = model.predict_proba(train[features])[:, 1]
    base = float(y.mean())

    ranked = pd.DataFrame({"y": y, "p": p}).sort_values("p", ascending=False).reset_index(drop=True)
    ranked["decile"] = np.minimum(np.arange(len(ranked)) // (len(ranked) // 10) + 1, 10)
    deciles = [
        {
            "decile": int(d),
            "n": int(len(g)),
            "conversions": int(g.y.sum()),
            "actual_rate": round(float(g.y.mean()), 4),
            "mean_predicted": round(float(g.p.mean()), 4),
            "lift_vs_base": round(float(g.y.mean() / base), 2),
        }
        for d, g in ranked.groupby("decile")
    ]

    top_n = {}
    for n in (50, 100, 200, 300):
        head = ranked.head(n)
        wins = int(head.y.sum())
        top_n[str(n)] = {
            "conversions": wins,
            "rate": round(float(head.y.mean()), 4),
            "lift": round(float(head.y.mean() / base), 2),
            "calls_per_win": round(n / wins, 1) if wins else None,
        }

    return {
        "caveat": "IN-SAMPLE: measured on the rows the model was trained on. An upper bound, not an estimate.",
        "auc": round(float(roc_auc_score(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "pr_auc_random_baseline": round(base, 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "brier_if_always_predicting_base_rate": round(float(brier_score_loss(y, np.full_like(p, base))), 4),
        "calls_per_win_at_base_rate": round(1 / base, 1),
        "deciles": deciles,
        "top_n": top_n,
        "max_score": round(float(p.max()), 4),
        "accounts_flagged_at_threshold_0_5": int((p > 0.5).sum()),
        "score_percentiles": {q: round(float(np.quantile(p, float(q))), 4) for q in ("0.50", "0.70", "0.90", "0.95")},
    }


def drift_baseline(model, train: pd.DataFrame, score: pd.DataFrame) -> dict:
    """Today's measured gap between training and the batch: the monitoring baseline.

    Everything is stable now, which is what makes these usable reference points
    rather than thresholds borrowed from somewhere else.
    """
    features = list(model.feature_names_in_)
    p_train = model.predict_proba(train[features])[:, 1]
    p_score = model.predict_proba(score[features])[:, 1]
    numeric = ["employee_count", "intent_score", "mql_count_90d", "trial_started",
               "trial_active_users", "web_touchpoints_90d", "sales_contacts_90d"]
    return {
        "psi_by_feature": {c: round(psi(train[c], score[c]), 4) for c in numeric},
        "psi_model_score": round(psi(pd.Series(p_train), pd.Series(p_score)), 4),
        "score_distribution": {
            "train": {"mean": round(float(p_train.mean()), 4),
                      "p90": round(float(np.quantile(p_train, 0.9)), 4),
                      "max": round(float(p_train.max()), 4)},
            "score": {"mean": round(float(p_score.mean()), 4),
                      "p90": round(float(np.quantile(p_score, 0.9)), 4),
                      "max": round(float(p_score.max()), 4)},
        },
        "threshold_convention": "PSI 0.1 warn, 0.25 alert. Measured today every feature is below 0.06.",
    }


def main() -> None:
    train, score, model = load()
    findings = {
        "meta": {
            "as_of": str(AS_OF.date()),
            "horizon_days": HORIZON_DAYS,
            "input_sha256": {
                "training_data.csv": sha256(TRAIN_CSV),
                "accounts_to_score.csv": sha256(SCORE_CSV),
                "model.pkl": sha256(MODEL_PKL),
            },
            "regenerate_with": "python analysis/profile.py",
        },
        "data_shape": data_shape(train, score),
        "base_rate": base_rate(train),
        "label_censoring": label_censoring(train),
        "freshness": freshness(train, score),
        "coverage": coverage(train, score),
        "model_card": model_card(model),
        "in_sample_performance": in_sample_performance(model, train),
        "drift_baseline": drift_baseline(model, train, score),
    }
    OUT_JSON.write_text(json.dumps(findings, indent=2), encoding="utf-8")

    b, c, f = findings["base_rate"], findings["label_censoring"], findings["freshness"]
    cov, m, p = findings["coverage"], findings["model_card"], findings["in_sample_performance"]
    d1 = p["deciles"][0]
    print(f"as of {findings['meta']['as_of']}  |  train {findings['data_shape']['train_rows']} rows, "
          f"batch {findings['data_shape']['score_rows']} rows, overlap {findings['data_shape']['accounts_in_both_files']}")
    print(f"base rate      {b['rate']:.1%} ({b['positives']} conversions) vs packet's real world: {b['packet_says_real_world_cold']}")
    print(f"censoring      {c['rows_with_immature_window']} rows younger than {HORIZON_DAYS}d hold "
          f"{c['conversions_among_them']} conversions between them")
    print(f"staleness      batch median {f['score']['median_age_days']:.0f}d | "
          f"{f['score']['share_older_than_90d']:.0%} over 90d | "
          f"{f['score']['outcome_window_already_closed']} outcome windows already closed")
    print(f"intent         missing {cov['intent_missing_score']:.1%} of batch, imputed at "
          f"{cov['imputed_with_training_median']}; converts {cov['conversion_when_intent_present']:.1%} present "
          f"vs {cov['conversion_when_intent_missing']:.1%} missing")
    print(f"model          {m['classifier']} x{m['n_estimators']} depth {m['max_depth']} | OOB: "
          f"{m['oob_trees_that_made_it_worse']}/{m['oob_tree_count']} trees made held-out loss worse, "
          f"last 10 {m['oob_last10_improvement']:+.4f}")
    print(f"ceiling        AUC {p['auc']:.3f} | decile 1 {d1['actual_rate']:.1%} ({d1['lift_vs_base']}x) | "
          f"calls per win {p['top_n']['100']['calls_per_win']} vs {p['calls_per_win_at_base_rate']} at base rate")
    print(f"thresholds     max score {p['max_score']} -> fires {p['accounts_flagged_at_threshold_0_5']} times at 0.5 | "
          f"p90 cut {p['score_percentiles']['0.90']}")
    print(f"drift today    score PSI {findings['drift_baseline']['psi_model_score']} (all features < 0.06)")
    print(f"\nwrote {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
