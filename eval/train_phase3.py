"""Phase 3: learn the decision instead of hand-setting it.

Trains on the POOLED subtrain+dev population (125 speakers), grouped
5-fold CV by speaker (per eval/phase3_protocol.md - a single 24-speaker
dev split is too small to trust for model/hyperparameter selection at this
positive rate). Model/hyperparameter selection uses mean+spread of
child-slice PR-AUC across folds, never F1 (the threshold isn't set until
Phase 5).

Numeric preprocessing audit (explicit per review request): logistic
regression's numeric features are standardized with a StandardScaler
fit ONLY on each fold's training rows (never on the validation fold, never
on the pooled set) - see _fit_fold_pipeline. The only imputation is a fixed
constant sentinel (MISSING_SENTINEL = -5.0) for llr_deletion/llr_second_best
when no such candidate exists; that constant does not depend on any data
statistic, pooled or per-fold, so there is nothing to leak. No
feature-selection step is used. Speaker-relative features
(*_speaker_rel) were computed upstream in eval/build_phase2_features.py
using ONLY each speaker's own prior attempts (Welford accumulator,
processed in per-speaker chronological order) - never another speaker's
data and never a future attempt of the same speaker's.

The headline "beats GOP z-score" comparison is now computed over ALL 125
pooled speakers' out-of-fold child rows (candidate never trained on the
speaker it predicts, in either case), not just the 24 dev speakers - a
prior version used dev-only and turned out to be dominated by a handful of
unusually easy dev speakers that happened to land in one CV fold (see
eval/fold_diagnostics.json). The dev-only number is kept as a secondary,
clearly-labeled line, not the headline.
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from baselines import predict_gop_zscore  # noqa: E402
from harness import flatten_rows, label_for_accuracy, paired_bootstrap_delta  # noqa: E402

EVAL_DIR = Path(__file__).parent

NUMERIC_FEATURES = [
    "llr_best", "llr_margin", "gop_i", "gop_lpr_i", "dur_z", "entropy",
    "ll_canonical_per_frame", "free_decode_gap",
    "llr_best_speaker_rel", "gop_i_speaker_rel", "gop_lpr_i_speaker_rel", "dur_z_speaker_rel",
    "syllable_count", "frame_count_word",
]
EXTRA_NUMERIC_NAMES = ["llr_deletion", "llr_second_best", "has_deletion_candidate", "has_second_best_candidate"]
MISSING_SENTINEL = -5.0  # far below the observed llr range (-1..+1ish) - "no such candidate"; a fixed constant, not a data statistic
CATEGORICAL_FEATURES = ["expected", "position", "llr_best_origin", "top_competitor"]


def load_pooled_rows() -> list[dict]:
    rows = []
    for split in ("subtrain", "dev"):
        with open(EVAL_DIR / f"phase2_features_{split}.json") as f:
            rows.extend(json.load(f))
    return rows


def build_xy(rows: list[dict], encoder: OneHotEncoder | None = None):
    """Returns (X_numeric, X_categorical_encoded, y, groups, encoder,
    kept_row_indices, feature_names). Numeric and categorical blocks are
    kept separate so a StandardScaler can be fit on the numeric block only,
    per fold - one-hot columns are already 0/1 and scaling them is neither
    necessary nor standard practice. Rows with an ambiguous ground-truth
    label are excluded from fitting entirely, per the label scheme."""
    kept = [i for i, r in enumerate(rows) if label_for_accuracy(r["phone_accuracy"]) is not None]
    y = np.array([label_for_accuracy(rows[i]["phone_accuracy"]) for i in kept])
    groups = np.array([rows[i]["speaker"] for i in kept])

    numeric = np.zeros((len(kept), len(NUMERIC_FEATURES) + 4), dtype=np.float64)
    for j, feat in enumerate(NUMERIC_FEATURES):
        for row_i, i in enumerate(kept):
            numeric[row_i, j] = rows[i][feat]
    base = len(NUMERIC_FEATURES)
    for row_i, i in enumerate(kept):
        r = rows[i]
        numeric[row_i, base + 0] = r["llr_deletion"] if r["llr_deletion"] is not None else MISSING_SENTINEL
        numeric[row_i, base + 1] = r["llr_second_best"] if r["llr_second_best"] is not None else MISSING_SENTINEL
        numeric[row_i, base + 2] = 1.0 if r["llr_deletion"] is not None else 0.0
        numeric[row_i, base + 3] = 1.0 if r["llr_second_best"] is not None else 0.0
    numeric_names = NUMERIC_FEATURES + EXTRA_NUMERIC_NAMES

    cat_raw = np.array([[str(rows[i][feat]) for feat in CATEGORICAL_FEATURES] for i in kept])
    if encoder is None:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        cat_encoded = encoder.fit_transform(cat_raw)
    else:
        cat_encoded = encoder.transform(cat_raw)
    cat_names = list(encoder.get_feature_names_out(CATEGORICAL_FEATURES))

    return numeric, cat_encoded, y, groups, encoder, kept, numeric_names + cat_names


def child_pr_auc(y_true, y_score, is_child_mask) -> float:
    if is_child_mask.sum() == 0 or len(set(y_true[is_child_mask])) < 2:
        return float("nan")
    return float(average_precision_score(y_true[is_child_mask], y_score[is_child_mask]))


def lift(pr_auc: float, prevalence: float) -> float:
    if pr_auc != pr_auc or not prevalence:
        return float("nan")
    return pr_auc / prevalence


def make_lr(seed):
    return LogisticRegression(class_weight="balanced", max_iter=2000, random_state=seed)


def make_hgb(seed):
    return HistGradientBoostingClassifier(class_weight="balanced", random_state=seed, max_iter=200)


def run_cv(numeric, cat_encoded, y, groups, is_child, model_name: str, n_splits: int = 5, seed: int = 0):
    """Fits a fresh StandardScaler PER FOLD on that fold's training numeric
    rows only (HGB gets the raw numeric block - tree splits are invariant
    to monotonic per-feature scaling, so scaling would be a no-op for it
    and isn't applied). Returns (fold_stats, oof_scores, speaker_to_fold)."""
    gkf = GroupKFold(n_splits=n_splits)
    oof_scores = np.full(len(y), np.nan)
    fold_stats = []
    speaker_to_fold = {}

    for fold_i, (train_idx, val_idx) in enumerate(gkf.split(numeric, y, groups)):
        for sp in set(groups[val_idx]):
            speaker_to_fold[sp] = fold_i

        if model_name == "logistic_regression":
            scaler = StandardScaler()
            num_train = scaler.fit_transform(numeric[train_idx])
            num_val = scaler.transform(numeric[val_idx])
            model = make_lr(seed + fold_i)
        else:
            num_train, num_val = numeric[train_idx], numeric[val_idx]
            model = make_hgb(seed + fold_i)

        X_train = np.hstack([num_train, cat_encoded[train_idx]])
        X_val = np.hstack([num_val, cat_encoded[val_idx]])
        model.fit(X_train, y[train_idx])
        proba = model.predict_proba(X_val)[:, 1]
        oof_scores[val_idx] = proba

        val_child = is_child[val_idx]
        n_child = int(val_child.sum())
        n_child_pos = int(y[val_idx][val_child].sum())
        prevalence = n_child_pos / n_child if n_child else float("nan")
        pr_auc = child_pr_auc(y[val_idx], proba, val_child)
        fold_stats.append({
            "fold": fold_i, "n_val": len(val_idx), "n_child": n_child, "n_child_pos": n_child_pos,
            "prevalence": prevalence, "pr_auc": pr_auc, "lift": lift(pr_auc, prevalence),
        })
        print(f"    fold {fold_i}: n_val={len(val_idx):5} n_child={n_child:5} n_child_pos={n_child_pos:3} "
              f"prevalence={prevalence:.2%} pr_auc={pr_auc:.4f} lift={lift(pr_auc, prevalence):.2f}x")

    return fold_stats, oof_scores, speaker_to_fold


def summarize_folds(name: str, fold_stats: list[dict]):
    vals = np.array([f["pr_auc"] for f in fold_stats if f["pr_auc"] == f["pr_auc"]])
    lifts = np.array([f["lift"] for f in fold_stats if f["lift"] == f["lift"]])
    print(f"  {name}: child PR-AUC mean={vals.mean():.4f} std={vals.std():.4f} "
          f"min={vals.min():.4f} max={vals.max():.4f}  |  lift mean={lifts.mean():.2f}x "
          f"min={lifts.min():.2f}x max={lifts.max():.2f}x")


def _accumulate_pr(rows: list[dict]) -> float:
    labels = [r["label"] for r in rows]
    scores = [r["score"] for r in rows]
    if len(set(labels)) < 2:
        return float("nan")
    return float(average_precision_score(labels, scores))


def _row_key(r: dict) -> tuple:
    return (r["utt_id"], r["word_index"], r["index"])


def per_speaker_delta(candidate_rows: list[dict], baseline_rows: list[dict]) -> dict:
    """Per-speaker PR-AUC(candidate) - PR-AUC(baseline), joined by
    (utt_id, word_index, index) so both scorers are compared on the exact
    same set of phoneme attempts per speaker (not just "same speaker",
    which could silently compare mismatched populations if the two row
    lists were built by different code paths). A speaker is included only
    if they have both classes present among their own labeled attempts -
    PR-AUC is undefined for a single speaker with all-one-class data, and
    at the child slice's ~3% base rate many individual speakers will have
    zero or one positive token."""
    cand_by_key = {_row_key(r): r for r in candidate_rows}
    base_by_key = {_row_key(r): r for r in baseline_rows}
    shared_keys = set(cand_by_key) & set(base_by_key)
    assert len(shared_keys) == len(cand_by_key) == len(baseline_rows), (
        f"candidate/baseline row sets must match exactly for a per-speaker comparison - "
        f"candidate={len(cand_by_key)} baseline={len(base_by_key)} shared={len(shared_keys)}"
    )

    by_speaker: dict[str, list[tuple]] = {}
    for key in shared_keys:
        c, b = cand_by_key[key], base_by_key[key]
        assert c["label"] == b["label"], f"label mismatch at {key}: {c['label']} vs {b['label']}"
        by_speaker.setdefault(c["speaker"], []).append((c["label"], c["score"], b["score"]))

    per_speaker = []
    excluded_single_class = 0
    for speaker, triples in by_speaker.items():
        labels = [t[0] for t in triples]
        if len(set(labels)) < 2:
            excluded_single_class += 1
            continue
        c_scores = [t[1] for t in triples]
        b_scores = [t[2] for t in triples]
        c_pr = float(average_precision_score(labels, c_scores))
        b_pr = float(average_precision_score(labels, b_scores))
        per_speaker.append({"speaker": speaker, "n": len(triples), "n_pos": sum(labels),
                             "candidate_pr_auc": c_pr, "baseline_pr_auc": b_pr, "delta": c_pr - b_pr})

    deltas = [p["delta"] for p in per_speaker]
    n_beats = sum(1 for d in deltas if d > 0)
    n_loses = sum(1 for d in deltas if d < 0)
    n_ties = sum(1 for d in deltas if d == 0)

    from scipy.stats import binomtest, wilcoxon
    sign_test = binomtest(n_beats, n_beats + n_loses, p=0.5) if (n_beats + n_loses) > 0 else None
    try:
        wilcoxon_result = wilcoxon(deltas) if len(deltas) >= 1 and any(d != 0 for d in deltas) else None
    except ValueError:
        wilcoxon_result = None

    return {
        "n_speakers_included": len(per_speaker), "n_speakers_excluded_single_class": excluded_single_class,
        "n_beats": n_beats, "n_loses": n_loses, "n_ties": n_ties,
        "sign_test_p_value": sign_test.pvalue if sign_test else float("nan"),
        "wilcoxon_p_value": wilcoxon_result.pvalue if wilcoxon_result else float("nan"),
        "mean_delta": float(np.mean(deltas)) if deltas else float("nan"),
        "median_delta": float(np.median(deltas)) if deltas else float("nan"),
        "per_speaker": per_speaker,
    }


def lift_report(pr_auc: float, prevalence: float) -> str:
    return f"{lift(pr_auc, prevalence):.2f}x (PR-AUC={pr_auc:.4f} / prevalence={prevalence:.2%})"


def reliability_diagram(y_true, y_score, n_bins=10):
    """Equal-width bins on [0,1]. Returns per-bin (mean predicted prob,
    empirical frequency, count) plus expected calibration error (ECE) -
    the count-weighted mean absolute gap between the two."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.digitize(y_score, bins) - 1, 0, n_bins - 1)
    rows = []
    ece = 0.0
    n = len(y_true)
    for b in range(n_bins):
        mask = bin_idx == b
        count = int(mask.sum())
        if count == 0:
            rows.append({"bin_lo": float(bins[b]), "bin_hi": float(bins[b + 1]), "count": 0,
                         "mean_predicted": float("nan"), "empirical_frequency": float("nan")})
            continue
        mean_pred = float(y_score[mask].mean())
        emp_freq = float(y_true[mask].mean())
        rows.append({"bin_lo": float(bins[b]), "bin_hi": float(bins[b + 1]), "count": count,
                     "mean_predicted": mean_pred, "empirical_frequency": emp_freq})
        ece += (count / n) * abs(mean_pred - emp_freq)
    return rows, ece


def main():
    print("Loading pooled subtrain+dev features...")
    rows = load_pooled_rows()
    print(f"{len(rows)} phoneme-attempt rows, {len({r['speaker'] for r in rows})} speakers\n")

    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])

    with open(EVAL_DIR / "speaker_split.json") as f:
        split = json.load(f)
    dev_speakers = {sp for sp, g in split.items() if g == "dev"}
    is_dev = np.array([groups[i] in dev_speakers for i in range(len(groups))])

    results = {}
    for model_name in ("logistic_regression", "hist_gradient_boosting"):
        print(f"=== {model_name}: grouped 5-fold CV over pooled subtrain+dev ===")
        fold_stats, oof_scores, speaker_to_fold = run_cv(numeric, cat_encoded, y, groups, is_child, model_name)
        summarize_folds(model_name, fold_stats)
        results[model_name] = {"fold_stats": fold_stats, "oof_scores": oof_scores, "speaker_to_fold": speaker_to_fold}
        print()

    # --- dev-speaker fold-assignment distribution (are they concentrated in one fold?) ---
    from collections import Counter
    dev_fold_dist = Counter(results["logistic_regression"]["speaker_to_fold"][sp] for sp in dev_speakers)
    print(f"Dev-speaker (24) fold assignment: {dict(sorted(dev_fold_dist.items()))}")
    print("(fold assignment is identical across models - same GroupKFold split, same groups)\n")

    # --- model selection ---
    lr_vals = np.array([f["pr_auc"] for f in results["logistic_regression"]["fold_stats"] if f["pr_auc"] == f["pr_auc"]])
    hgb_vals = np.array([f["pr_auc"] for f in results["hist_gradient_boosting"]["fold_stats"] if f["pr_auc"] == f["pr_auc"]])
    winner = "hist_gradient_boosting" if hgb_vals.mean() > lr_vals.mean() + lr_vals.std() else "logistic_regression"
    print(f"logistic_regression mean={lr_vals.mean():.4f}  hist_gradient_boosting mean={hgb_vals.mean():.4f}  -> selected: {winner}\n")

    winner_oof = results[winner]["oof_scores"]

    # --- headline: ALL 125 pooled speakers' child out-of-fold rows vs GOP z-score on the same 125 ---
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        dev_gop_records = json.load(f)
    with open(EVAL_DIR / "phase0_raw_cache_subtrain.json") as f:
        subtrain_gop_records = json.load(f)
    all_gop_records = dev_gop_records + subtrain_gop_records
    speaker_is_child = {r["speaker"]: r["is_child"] for r in all_gop_records}

    candidate_rows_all = []
    for row_i, i in enumerate(kept):
        r = rows[i]
        if not speaker_is_child.get(r["speaker"], False):
            continue
        candidate_rows_all.append({
            "utt_id": r["utt_id"], "word_index": r["word_index"], "index": r["index"],
            "speaker": r["speaker"], "phone": r["expected"], "position": r["position"],
            "label": label_for_accuracy(r["phone_accuracy"]),
            "status": "wrong" if winner_oof[row_i] >= 0.5 else "correct",
            "score": float(winner_oof[row_i]), "heard": None, "gt_sub": None,
        })
    gop_rows_all_child = [r for r in flatten_rows(all_gop_records, predict_gop_zscore, slice_filter=lambda rec: rec["is_child"]) if r["label"] is not None]

    n_pos = sum(1 for r in gop_rows_all_child if r["label"] == 1)
    prevalence_all = n_pos / len(gop_rows_all_child)
    print(f"=== HEADLINE beat-baseline test ({winner}, ALL 125 pooled speakers' out-of-fold child rows) ===")
    print(f"candidate rows: {len(candidate_rows_all)}, gop_zscore rows: {len(gop_rows_all_child)}, prevalence={prevalence_all:.2%}")
    headline = paired_bootstrap_delta(candidate_rows_all, gop_rows_all_child, metric_name="pr_auc", n_boot=2000, seed=0)
    lo, hi = headline["ci"]
    cand_pr_all = headline["point_delta"] + _accumulate_pr(gop_rows_all_child)
    print(f"delta PR-AUC = {headline['point_delta']:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  P(delta>0)={headline['frac_positive']:.1%}")
    print(f"delta in LIFT units: candidate={lift_report(cand_pr_all, prevalence_all)}  baseline={lift_report(_accumulate_pr(gop_rows_all_child), prevalence_all)}  "
          f"delta_lift={headline['point_delta'] / prevalence_all:+.2f}x")
    print(f"-> {'BEATS baseline' if lo > 0 else 'does NOT beat baseline'}\n")

    print("=== Per-speaker robustness (125 pooled speakers, all - not just child) ===")
    candidate_rows_all_speakers = []
    for row_i, i in enumerate(kept):
        r = rows[i]
        candidate_rows_all_speakers.append({
            "utt_id": r["utt_id"], "word_index": r["word_index"], "index": r["index"],
            "speaker": r["speaker"], "label": label_for_accuracy(r["phone_accuracy"]),
            "score": float(winner_oof[row_i]),
        })
    gop_rows_all_speakers = [r for r in flatten_rows(all_gop_records, predict_gop_zscore) if r["label"] is not None]
    per_speaker_all = per_speaker_delta(candidate_rows_all_speakers, gop_rows_all_speakers)
    print(f"  All 125 speakers: {winner} beats GOP on {per_speaker_all['n_beats']} of "
          f"{per_speaker_all['n_beats'] + per_speaker_all['n_loses']} speakers with a defined PR-AUC "
          f"({per_speaker_all['n_ties']} ties, {per_speaker_all['n_speakers_excluded_single_class']} excluded - single class)")
    print(f"  sign test p={per_speaker_all['sign_test_p_value']:.2e}  wilcoxon p={per_speaker_all['wilcoxon_p_value']:.2e}  "
          f"mean_delta={per_speaker_all['mean_delta']:+.4f}  median_delta={per_speaker_all['median_delta']:+.4f}")

    per_speaker_child = per_speaker_delta(candidate_rows_all, gop_rows_all_child)
    print(f"  Child speakers only: {winner} beats GOP on {per_speaker_child['n_beats']} of "
          f"{per_speaker_child['n_beats'] + per_speaker_child['n_loses']} speakers with a defined PR-AUC "
          f"({per_speaker_child['n_ties']} ties, {per_speaker_child['n_speakers_excluded_single_class']} excluded - single class)")
    print(f"  sign test p={per_speaker_child['sign_test_p_value']:.2e}  wilcoxon p={per_speaker_child['wilcoxon_p_value']:.2e}  "
          f"mean_delta={per_speaker_child['mean_delta']:+.4f}  median_delta={per_speaker_child['median_delta']:+.4f}\n")

    # --- secondary: dev-only (kept for comparison, explicitly not the headline) ---
    dev_speaker_is_child = {r["speaker"]: r["is_child"] for r in dev_gop_records}
    candidate_rows_dev = [r for r in candidate_rows_all if r["speaker"] in dev_speakers]
    gop_rows_dev_child = [r for r in flatten_rows(dev_gop_records, predict_gop_zscore, slice_filter=lambda rec: rec["is_child"]) if r["label"] is not None]
    n_pos_dev = sum(1 for r in gop_rows_dev_child if r["label"] == 1)
    prevalence_dev = n_pos_dev / len(gop_rows_dev_child)
    print(f"=== SECONDARY beat-baseline test (dev-only, 24 speakers) ===")
    print(f"candidate rows: {len(candidate_rows_dev)}, gop_zscore rows: {len(gop_rows_dev_child)}, prevalence={prevalence_dev:.2%}")
    dev_only = paired_bootstrap_delta(candidate_rows_dev, gop_rows_dev_child, metric_name="pr_auc", n_boot=2000, seed=0)
    lo2, hi2 = dev_only["ci"]
    print(f"delta PR-AUC = {dev_only['point_delta']:+.4f}  95% CI [{lo2:+.4f}, {hi2:+.4f}]  P(delta>0)={dev_only['frac_positive']:.1%}")
    print(f"delta in LIFT units: delta_lift={dev_only['point_delta'] / prevalence_dev:+.2f}x\n")

    # --- reliability diagram + ECE, on the headline out-of-fold child population ---
    candidate_y = np.array([r["label"] for r in candidate_rows_all])
    candidate_score = np.array([r["score"] for r in candidate_rows_all])
    diagram, ece = reliability_diagram(candidate_y, candidate_score, n_bins=10)
    print(f"=== Reliability diagram ({winner}, out-of-fold, all pooled child rows) ===")
    print(f"{'bin':14} {'count':>6} {'mean_pred':>10} {'emp_freq':>9}")
    for b in diagram:
        if b["count"] == 0:
            continue
        print(f"[{b['bin_lo']:.1f},{b['bin_hi']:.1f})  {b['count']:6} {b['mean_predicted']:10.3f} {b['empirical_frequency']:9.3f}")
    print(f"Expected Calibration Error (ECE) = {ece:.4f}\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "k--", label="perfect calibration")
    valid = [b for b in diagram if b["count"] > 0]
    ax.plot([b["mean_predicted"] for b in valid], [b["empirical_frequency"] for b in valid], "o-", label=winner)
    ax.set_xlabel("mean predicted P(error)")
    ax.set_ylabel("empirical error frequency")
    ax.set_title(f"Reliability diagram - child slice, out-of-fold (ECE={ece:.3f})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(EVAL_DIR / "reliability_diagram.png", dpi=150)
    print(f"Wrote {EVAL_DIR / 'reliability_diagram.png'}\n")

    # --- ranked LR coefficients: final model fit on ALL pooled data (not for
    # performance claims - for inspecting what the model actually learned) ---
    final_scaler = StandardScaler()
    num_scaled = final_scaler.fit_transform(numeric)
    X_final = np.hstack([num_scaled, cat_encoded])
    final_model = LogisticRegression(class_weight="balanced", max_iter=2000, random_state=0)
    final_model.fit(X_final, y)
    coefs = list(zip(feature_names, final_model.coef_[0]))
    coefs.sort(key=lambda kv: -abs(kv[1]))
    print("=== Logistic regression coefficients (standardized features, final model on all pooled data) ===")
    for name, coef in coefs:
        print(f"  {name:34} {coef:+.4f}")

    result = {
        "cv": {name: {"fold_stats": r["fold_stats"]} for name, r in results.items()},
        "dev_speaker_fold_distribution": dict(sorted(dev_fold_dist.items())),
        "selected_model": winner,
        "headline_beat_baseline_125_speakers": {
            "point_delta": headline["point_delta"], "ci": list(headline["ci"]), "frac_positive": headline["frac_positive"],
            "n_candidate": len(candidate_rows_all), "n_baseline": len(gop_rows_all_child),
            "prevalence": prevalence_all, "delta_lift": headline["point_delta"] / prevalence_all,
            "candidate_pr_auc": cand_pr_all, "baseline_pr_auc": _accumulate_pr(gop_rows_all_child),
        },
        "per_speaker_robustness_all_125": per_speaker_all,
        "per_speaker_robustness_child_only": per_speaker_child,
        "secondary_beat_baseline_dev_only": {
            "point_delta": dev_only["point_delta"], "ci": list(dev_only["ci"]), "frac_positive": dev_only["frac_positive"],
            "n_candidate": len(candidate_rows_dev), "n_baseline": len(gop_rows_dev_child),
            "prevalence": prevalence_dev, "delta_lift": dev_only["point_delta"] / prevalence_dev,
        },
        "reliability_diagram": diagram, "ece": ece,
        "lr_coefficients_standardized": [{"feature": n, "coef": float(c)} for n, c in coefs],
    }
    with open(EVAL_DIR / "phase3_results.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_results.json'}")


if __name__ == "__main__":
    main()
