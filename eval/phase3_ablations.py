"""Two ablations, both direct follow-ups to the within-phoneme result:

1. Drop the target-phoneme-identity dummies (expected_*) entirely and
   re-run the same CV + paired-baseline test. If pooled PR-AUC barely
   moves, the dummies were decorative. If it collapses, the model was
   substantially leaning on corpus-specific phoneme priors - which the
   within-phoneme test already suggested (N alone showed the baseline
   winning once phoneme identity stopped varying).
2. Feature-family ablation (llr-only / gop-only / duration-entropy-only /
   all-numeric, no categoricals at all) - answers which numeric family
   actually carries the signal, the question the llr_best sign flip was
   standing in for without answering it.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import (  # noqa: E402
    CATEGORICAL_FEATURES, FEATURE_FAMILIES, build_xy, candidate_rows_from_oof,
    gop_rows_for, load_all_gop_records, load_pooled_rows, run_lr_cv, summarize_folds,
)
from harness import paired_bootstrap_delta  # noqa: E402

EVAL_DIR = Path(__file__).parent


def run_variant(rows, numeric_features, categorical_features, all_gop_records):
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(
        rows, numeric_features=numeric_features, categorical_features=categorical_features,
    )
    is_child = np.array([rows[i]["is_child"] for i in kept])
    fold_stats, oof_scores, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child)
    summary = summarize_folds(fold_stats)

    speaker_is_child = {r["speaker"]: r["is_child"] for r in all_gop_records}
    child_speakers = {sp for sp, c in speaker_is_child.items() if c}
    candidate_rows = candidate_rows_from_oof(rows, kept, oof_scores, child_only_speakers=child_speakers)
    gop_rows = gop_rows_for(all_gop_records, child_only=True)
    delta = paired_bootstrap_delta(candidate_rows, gop_rows, metric_name="pr_auc", n_boot=1000, seed=0)
    return summary, delta, fold_stats


def main():
    rows = load_pooled_rows()
    all_gop_records = load_all_gop_records()

    print("=== Ablation 1: target-phoneme-identity dummies ===")
    full_categorical = CATEGORICAL_FEATURES  # includes "expected"
    no_phoneme_categorical = [c for c in CATEGORICAL_FEATURES if c != "expected"]
    full_numeric = FEATURE_FAMILIES["all_numeric"]

    print("  with expected_* dummies (replicates the committed Phase 3 model):")
    summary_with, delta_with, _ = run_variant(rows, full_numeric, full_categorical, all_gop_records)
    print(f"    CV child PR-AUC mean={summary_with['mean']:.4f} std={summary_with['std']:.4f}")
    print(f"    pooled beat-baseline delta={delta_with['point_delta']:+.4f} 95% CI {delta_with['ci']}")

    print("  WITHOUT expected_* dummies:")
    summary_without, delta_without, _ = run_variant(rows, full_numeric, no_phoneme_categorical, all_gop_records)
    print(f"    CV child PR-AUC mean={summary_without['mean']:.4f} std={summary_without['std']:.4f}")
    print(f"    pooled beat-baseline delta={delta_without['point_delta']:+.4f} 95% CI {delta_without['ci']}")

    pct_change = (summary_without["mean"] - summary_with["mean"]) / summary_with["mean"] * 100
    print(f"\n  CV mean PR-AUC change from dropping phoneme dummies: {pct_change:+.1f}%")
    verdict1 = (
        "COLLAPSED - the model was substantially leaning on corpus-specific phoneme priors"
        if pct_change < -25 else
        "barely moved - phoneme dummies were decorative, not load-bearing"
        if abs(pct_change) < 10 else
        "moved moderately - phoneme identity contributes real but not dominant signal"
    )
    print(f"  Verdict: {verdict1}\n")

    print("=== Ablation 2: feature-family (numeric only, no categoricals at all) ===")
    family_results = {}
    for family_name, features in FEATURE_FAMILIES.items():
        summary, delta, fold_stats = run_variant(rows, features, [], all_gop_records)
        family_results[family_name] = {"summary": summary, "delta": delta, "fold_stats": fold_stats}
        print(f"  {family_name:24} n_features={len(features):3} CV_PR_AUC_mean={summary['mean']:.4f} "
              f"std={summary['std']:.4f}  pooled_delta={delta['point_delta']:+.4f} CI={delta['ci']}")

    result = {
        "ablation_1_phoneme_dummies": {
            "with_dummies": {"cv_summary": summary_with, "beat_baseline_delta": delta_with["point_delta"], "ci": list(delta_with["ci"])},
            "without_dummies": {"cv_summary": summary_without, "beat_baseline_delta": delta_without["point_delta"], "ci": list(delta_without["ci"])},
            "pct_change_in_cv_mean": pct_change, "verdict": verdict1,
        },
        "ablation_2_feature_families": {
            name: {"cv_summary": r["summary"], "beat_baseline_delta": r["delta"]["point_delta"], "ci": list(r["delta"]["ci"])}
            for name, r in family_results.items()
        },
    }
    with open(EVAL_DIR / "phase3_ablations.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_ablations.json'}")


if __name__ == "__main__":
    main()
