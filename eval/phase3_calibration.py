"""Calibration, done right: Platt scaling and isotonic regression are each
fit on out-of-fold predictions via a SECOND, nested grouped split - a
calibrator is only ever applied to a speaker it was not fit on, exactly
the same discipline as the base model's own out-of-fold discipline. Fitting
and evaluating a calibrator on the identical out-of-fold scores it was
fit on would understate its true calibration error the same way fitting
and evaluating a classifier on its own training fold would.

Also tests dropping class_weight="balanced" (the likely source of the
ECE=0.233 overconfidence - balanced weighting reweights the loss, which
distorts predict_proba away from true class-conditional probabilities even
though it can still preserve ranking).
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import build_xy, load_pooled_rows, run_lr_cv, summarize_folds  # noqa: E402
from train_phase3 import reliability_diagram  # noqa: E402

EVAL_DIR = Path(__file__).parent


def nested_calibrate(oof_scores, y, groups, method: str, n_splits=5, seed=0):
    """Returns calibrated scores, same length as oof_scores, each produced
    by a calibrator fit on OTHER speakers' out-of-fold scores only."""
    calibrated = np.full(len(oof_scores), np.nan)
    gkf = GroupKFold(n_splits=n_splits)
    for fold_i, (fit_idx, apply_idx) in enumerate(gkf.split(oof_scores.reshape(-1, 1), y, groups)):
        if method == "platt":
            platt = LogisticRegression()
            platt.fit(oof_scores[fit_idx].reshape(-1, 1), y[fit_idx])
            calibrated[apply_idx] = platt.predict_proba(oof_scores[apply_idx].reshape(-1, 1))[:, 1]
        elif method == "isotonic":
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(oof_scores[fit_idx], y[fit_idx])
            calibrated[apply_idx] = iso.predict(oof_scores[apply_idx])
        else:
            raise ValueError(method)
    return calibrated


def main():
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])

    print("=== Base model (class_weight='balanced', as committed) ===")
    fold_stats_balanced, oof_balanced, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child, class_weight="balanced")
    summary_balanced = summarize_folds(fold_stats_balanced)
    print(f"  CV child PR-AUC mean={summary_balanced['mean']:.4f} std={summary_balanced['std']:.4f}")

    print("=== Base model, class_weight=None (imbalance handled by threshold only) ===")
    fold_stats_none, oof_none, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child, class_weight=None)
    summary_none = summarize_folds(fold_stats_none)
    print(f"  CV child PR-AUC mean={summary_none['mean']:.4f} std={summary_none['std']:.4f}")
    pct = (summary_none["mean"] - summary_balanced["mean"]) / summary_balanced["mean"] * 100
    print(f"  PR-AUC change from dropping class_weight: {pct:+.1f}% (ranking should barely move if this is purely a calibration distortion)\n")

    def ece_for(scores, mask, label):
        y_sub = y[mask]
        s_sub = scores[mask]
        valid = ~np.isnan(s_sub)
        _, ece = reliability_diagram(y_sub[valid], s_sub[valid], n_bins=10)
        print(f"  ECE ({label}): {ece:.4f}  (n={valid.sum()})")
        return ece

    print("=== ECE before calibration ===")
    print("balanced model:")
    ece_pooled_before = ece_for(oof_balanced, np.ones(len(y), dtype=bool), "pooled, all rows")
    ece_child_before = ece_for(oof_balanced, is_child, "child slice only")
    print("class_weight=None model:")
    ece_pooled_none = ece_for(oof_none, np.ones(len(y), dtype=bool), "pooled, all rows")
    ece_child_none = ece_for(oof_none, is_child, "child slice only")
    print()

    print("=== Nested calibration (balanced model's out-of-fold scores, recalibrated on OTHER speakers) ===")
    platt_scores = nested_calibrate(oof_balanced, y, groups, "platt")
    iso_scores = nested_calibrate(oof_balanced, y, groups, "isotonic")

    print("Platt:")
    ece_pooled_platt = ece_for(platt_scores, np.ones(len(y), dtype=bool), "pooled, all rows")
    ece_child_platt = ece_for(platt_scores, is_child, "child slice only")
    print("Isotonic:")
    ece_pooled_iso = ece_for(iso_scores, np.ones(len(y), dtype=bool), "pooled, all rows")
    ece_child_iso = ece_for(iso_scores, is_child, "child slice only")

    # Ranking (PR-AUC) is invariant to any monotonic calibration transform in theory - verify empirically.
    from sklearn.metrics import average_precision_score
    child_mask = is_child
    pr_before = average_precision_score(y[child_mask], oof_balanced[child_mask])
    pr_platt = average_precision_score(y[child_mask], platt_scores[child_mask])
    pr_iso = average_precision_score(y[child_mask], iso_scores[child_mask])
    print(f"\nChild-slice PR-AUC: uncalibrated={pr_before:.4f}  platt={pr_platt:.4f}  isotonic={pr_iso:.4f} "
          f"(should be ~identical - calibration is monotonic on average, small differences from the nested-fold structure are expected)")

    result = {
        "class_weight_comparison": {
            "balanced": summary_balanced, "none": summary_none, "pct_change": pct,
        },
        "ece": {
            "balanced_uncalibrated": {"pooled": ece_pooled_before, "child": ece_child_before},
            "class_weight_none_uncalibrated": {"pooled": ece_pooled_none, "child": ece_child_none},
            "platt_nested": {"pooled": ece_pooled_platt, "child": ece_child_platt},
            "isotonic_nested": {"pooled": ece_pooled_iso, "child": ece_child_iso},
        },
        "pr_auc_invariance_check": {"uncalibrated": pr_before, "platt": pr_platt, "isotonic": pr_iso},
    }
    with open(EVAL_DIR / "phase3_calibration.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_calibration.json'}")


if __name__ == "__main__":
    main()
