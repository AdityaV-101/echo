"""Phase 3: learn the decision instead of hand-setting it.

Trains on the POOLED subtrain+dev population (125 speakers), grouped
5-fold CV by speaker (per eval/phase3_protocol.md - a single 24-speaker
dev split is too small to trust for model/hyperparameter selection at this
positive rate). Model/hyperparameter selection uses mean+spread of
child-slice PR-AUC across folds, never F1 (the threshold isn't set until
Phase 5).

"Beat the GOP z-score baseline" specifically is tested on the dev-speaker
subset of the pooled CV's out-of-fold predictions - each dev speaker's
prediction comes from a fold that never trained on them, so this is a
legitimate out-of-fold estimate on the exact same population
eval/baselines.json's GOP z-score number was computed on (no leakage, and
no need to re-extract GOP values for subtrain, which use a different raw
quantity than Phase 2's gop_i - see backend/gop_scorer.compute_gop vs
backend/features.py's plain mean-log-posterior gop_i, not interchangeable).
The paired bootstrap (harness.paired_bootstrap_delta) is run on exactly
this dev-speaker population against GOP z-score's existing predictions.
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder

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
MISSING_SENTINEL = -5.0  # far below the observed llr range (-1..+1ish) - "no such candidate"
CATEGORICAL_FEATURES = ["expected", "position", "llr_best_origin", "top_competitor"]


def load_pooled_rows() -> list[dict]:
    rows = []
    for split in ("subtrain", "dev"):
        with open(EVAL_DIR / f"phase2_features_{split}.json") as f:
            rows.extend(json.load(f))
    return rows


def build_xy(rows: list[dict], encoder: OneHotEncoder | None = None):
    """Returns (X, y, groups, encoder, kept_row_indices). Rows with an
    ambiguous ground-truth label (1.0 < accuracy < 2.0) are excluded from
    fitting entirely, per the label scheme - not just from eval."""
    kept = [i for i, r in enumerate(rows) if label_for_accuracy(r["phone_accuracy"]) is not None]
    y = np.array([label_for_accuracy(rows[i]["phone_accuracy"]) for i in kept])
    groups = np.array([rows[i]["speaker"] for i in kept])

    numeric = np.zeros((len(kept), len(NUMERIC_FEATURES) + 2), dtype=np.float64)
    for j, feat in enumerate(NUMERIC_FEATURES):
        for row_i, i in enumerate(kept):
            numeric[row_i, j] = rows[i][feat]
    # has_deletion / has_second_best indicators + sentinel-filled llr_deletion/llr_second_best
    extra = np.zeros((len(kept), 2), dtype=np.float64)
    llr_del = np.full(len(kept), MISSING_SENTINEL)
    llr_2nd = np.full(len(kept), MISSING_SENTINEL)
    for row_i, i in enumerate(kept):
        r = rows[i]
        if r["llr_deletion"] is not None:
            llr_del[row_i] = r["llr_deletion"]
            extra[row_i, 0] = 1.0
        if r["llr_second_best"] is not None:
            llr_2nd[row_i] = r["llr_second_best"]
            extra[row_i, 1] = 1.0

    cat_raw = np.array([[str(rows[i][feat]) for feat in CATEGORICAL_FEATURES] for i in kept])
    if encoder is None:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        cat_encoded = encoder.fit_transform(cat_raw)
    else:
        cat_encoded = encoder.transform(cat_raw)

    X = np.hstack([numeric, llr_del.reshape(-1, 1), llr_2nd.reshape(-1, 1), extra, cat_encoded])
    return X, y, groups, encoder, kept


def child_pr_auc(y_true, y_score, is_child_mask) -> float:
    if is_child_mask.sum() == 0 or len(set(y_true[is_child_mask])) < 2:
        return float("nan")
    return float(average_precision_score(y_true[is_child_mask], y_score[is_child_mask]))


def run_cv(rows: list[dict], make_model, n_splits: int = 5, seed: int = 0):
    """Returns (fold_pr_aucs, out_of_fold_scores, kept_indices) - scores are
    P(error) for every kept row, each from a fold that never trained on it."""
    X_full, y_full, groups_full, encoder, kept = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])

    gkf = GroupKFold(n_splits=n_splits)
    oof_scores = np.full(len(kept), np.nan)
    fold_pr_aucs = []

    for fold_i, (train_idx, val_idx) in enumerate(gkf.split(X_full, y_full, groups_full)):
        model = make_model(seed + fold_i)
        model.fit(X_full[train_idx], y_full[train_idx])
        proba = model.predict_proba(X_full[val_idx])[:, 1]
        oof_scores[val_idx] = proba
        pr_auc = child_pr_auc(y_full[val_idx], proba, is_child[val_idx])
        fold_pr_aucs.append(pr_auc)
        n_child_pos = int(y_full[val_idx][is_child[val_idx]].sum())
        print(f"    fold {fold_i}: n_val={len(val_idx)} n_child_val={int(is_child[val_idx].sum())} "
              f"n_child_pos={n_child_pos} child_pr_auc={pr_auc:.4f}")

    return fold_pr_aucs, oof_scores, kept, y_full, is_child


def summarize_folds(name: str, fold_pr_aucs: list[float]):
    vals = [v for v in fold_pr_aucs if v == v]
    if not vals:
        print(f"  {name}: no valid folds (child PR-AUC undefined in every fold)")
        return
    arr = np.array(vals)
    print(f"  {name}: child PR-AUC mean={arr.mean():.4f} std={arr.std():.4f} "
          f"min={arr.min():.4f} max={arr.max():.4f} (n_folds={len(vals)}/{len(fold_pr_aucs)})")


def main():
    print("Loading pooled subtrain+dev features...")
    rows = load_pooled_rows()
    speakers = {r["speaker"] for r in rows}
    print(f"{len(rows)} phoneme-attempt rows, {len(speakers)} speakers\n")

    models = {
        "logistic_regression": lambda seed: LogisticRegression(
            class_weight="balanced", max_iter=2000, random_state=seed,
        ),
        "hist_gradient_boosting": lambda seed: HistGradientBoostingClassifier(
            class_weight="balanced", random_state=seed, max_iter=200,
        ),
    }

    results = {}
    for name, make_model in models.items():
        print(f"=== {name}: grouped 5-fold CV over pooled subtrain+dev ===")
        fold_pr_aucs, oof_scores, kept, y_full, is_child = run_cv(rows, make_model)
        summarize_folds(name, fold_pr_aucs)
        results[name] = {
            "fold_pr_aucs": fold_pr_aucs, "oof_scores": oof_scores, "kept": kept,
            "y": y_full, "is_child": is_child,
        }
        print()

    with open(EVAL_DIR / "phase3_cv_results.json", "w") as f:
        json.dump({
            name: {"fold_pr_aucs": r["fold_pr_aucs"]}
            for name, r in results.items()
        }, f, indent=1)

    # --- model selection: prefer logistic regression unless HGB clearly wins ---
    lr_vals = np.array([v for v in results["logistic_regression"]["fold_pr_aucs"] if v == v])
    hgb_vals = np.array([v for v in results["hist_gradient_boosting"]["fold_pr_aucs"] if v == v])
    print(f"logistic_regression: mean={lr_vals.mean():.4f}  hist_gradient_boosting: mean={hgb_vals.mean():.4f}")
    winner = "hist_gradient_boosting" if hgb_vals.mean() > lr_vals.mean() + lr_vals.std() else "logistic_regression"
    print(f"Selected model (prefer LR unless HGB clearly wins beyond 1 std): {winner}\n")

    # --- beat-baseline test: dev-speaker subset of the winner's out-of-fold predictions ---
    print(f"=== beat-baseline test ({winner}, dev-speaker subset of out-of-fold predictions) ===")
    winner_r = results[winner]
    kept = winner_r["kept"]
    oof_scores = winner_r["oof_scores"]

    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        dev_records = json.load(f)
    dev_speaker_is_child = {r["speaker"]: r["is_child"] for r in dev_records}

    candidate_rows_child = []
    for row_i, i in enumerate(kept):
        r = rows[i]
        if not dev_speaker_is_child.get(r["speaker"], False):
            continue
        candidate_rows_child.append({
            "utt_id": r["utt_id"], "word_index": r["word_index"], "index": r["index"],
            "speaker": r["speaker"], "phone": r["expected"], "position": r["position"],
            "label": label_for_accuracy(r["phone_accuracy"]),
            "status": "wrong" if oof_scores[row_i] >= 0.5 else "correct",
            "score": float(oof_scores[row_i]), "heard": None, "gt_sub": None,
        })

    gop_rows_child = [r for r in flatten_rows(dev_records, predict_gop_zscore, slice_filter=lambda rec: rec["is_child"]) if r["label"] is not None]

    print(f"candidate (dev-speaker out-of-fold) child rows: {len(candidate_rows_child)}, gop_zscore child rows: {len(gop_rows_child)}")
    delta_result = paired_bootstrap_delta(candidate_rows_child, gop_rows_child, metric_name="pr_auc", n_boot=2000, seed=0)
    lo, hi = delta_result["ci"]
    verdict = "BEATS baseline" if lo > 0 else "does NOT beat baseline"
    print(f"delta PR-AUC (candidate - gop_zscore) = {delta_result['point_delta']:+.4f}  "
          f"95% CI [{lo:+.4f}, {hi:+.4f}]  P(delta>0)={delta_result['frac_positive']:.1%}")
    print(f"-> {verdict}")

    with open(EVAL_DIR / "phase3_beat_baseline_test.json", "w") as f:
        json.dump({
            "winner_model": winner,
            "point_delta": delta_result["point_delta"], "ci": list(delta_result["ci"]),
            "frac_positive": delta_result["frac_positive"],
        }, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_cv_results.json'} and {EVAL_DIR / 'phase3_beat_baseline_test.json'}")


if __name__ == "__main__":
    main()
