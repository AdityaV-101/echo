"""Phase 5 operating-point derivation. Not a sweep for "best" performance -
the frozen model's own already-computed out-of-fold scores (no new fitting)
are read off at a few candidate thresholds to document the operating point,
not to optimize it.

Important correction made while writing this: the ORIGINAL Phase 5 spec's
"lowest threshold that clears FRR<=0.05" rule (maximize recall subject to
the hard constraint) picks t=0.20 here (frr=0.0485, right at the edge of
the constraint, recall=0.427) - technically compliant, but that is NOT the
abstention-heavy operating point that was explicitly requested once the
within-phoneme margin came back unproven. Using 0.20 as both the "error"
and "correct" cut would collapse the abstain band to nothing. Per the
explicit instruction, T_ERROR is instead set as a genuine STRONG-EVIDENCE
bar - comfortably inside the FRR constraint, not just barely inside it -
and single-attempt recall is deliberately traded away in favor of
k-of-n corroboration across a child's repeated practice attempts at the
same phoneme recovering usable sensitivity over a session instead. This is
a policy choice, recorded here rather than derived by the "maximize
recall" rule, precisely because that rule's own natural answer (0.20)
doesn't match the requested default.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import build_xy, load_pooled_rows, run_lr_cv  # noqa: E402

EVAL_DIR = Path(__file__).parent
FRR_CONSTRAINT = 0.05


def main():
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])
    fold_stats, oof_scores, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child, class_weight=None)

    child_y = y[is_child]
    child_scores = oof_scores[is_child]

    curve = []
    for t in [0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        flagged = child_scores >= t
        n_flagged = int(flagged.sum())
        tp = int((flagged & (child_y == 1)).sum())
        fp = int((flagged & (child_y == 0)).sum())
        precision = tp / n_flagged if n_flagged else float("nan")
        recall = tp / (child_y == 1).sum()
        frr = fp / (child_y == 0).sum()
        curve.append({"threshold": t, "n_flagged": n_flagged, "precision": precision, "recall": recall, "frr": frr})
        print(f"t={t:.2f}  n_flagged={n_flagged:5}  precision={precision:.3f}  recall={recall:.3f}  frr={frr:.4f}")

    compliant = [c for c in curve if c["frr"] <= FRR_CONSTRAINT]
    min_compliant = min(c["threshold"] for c in compliant) if compliant else 0.95
    min_compliant_point = next(c for c in curve if c["threshold"] == min_compliant)
    print(f"\n'Maximize recall subject to FRR<=0.05' would pick t={min_compliant} "
          f"(frr={min_compliant_point['frr']:.4f}, precision={min_compliant_point['precision']:.3f}, "
          f"recall={min_compliant_point['recall']:.3f}) - right at the edge of the constraint, and it collapses "
          f"the abstain band if also used as T_CORRECT. NOT used as the default - see module docstring.")

    # Policy choice: T_ERROR is a strong-evidence bar, comfortably inside
    # the FRR constraint (not just barely inside it), so a single flagged
    # attempt is rarely wrong even before k-of-n corroboration.
    t_error = 0.80
    t_error_point = next(c for c in curve if c["threshold"] == t_error)
    t_correct = 0.10
    print(f"\nCHOSEN (abstention-heavy policy, not derived from 'maximize recall'): "
          f"T_ERROR={t_error} (frr={t_error_point['frr']:.4f}, precision={t_error_point['precision']:.3f}, "
          f"recall={t_error_point['recall']:.3f}), T_CORRECT={t_correct} (wide abstain band by design)")

    result = {
        "frr_constraint": FRR_CONSTRAINT,
        "coverage_precision_curve": curve,
        "maximize_recall_subject_to_frr_constraint": min_compliant_point,
        "t_error": t_error, "t_correct": t_correct,
        "chosen_operating_point": t_error_point,
        "note": "T_ERROR is a policy choice (strong-evidence bar, comfortably inside FRR<=0.05, not the bare "
                "minimum-compliant threshold) made explicit because the 'maximize recall subject to FRR<=0.05' "
                "rule's own answer (see maximize_recall_subject_to_frr_constraint) would collapse the abstain "
                "band - single-attempt recall is deliberately traded for k-of-n corroboration across repeated "
                "practice attempts. T_CORRECT is a wide-abstain-band policy choice, not derived from this curve.",
    }
    with open(EVAL_DIR / "decision_thresholds.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'decision_thresholds.json'}")


if __name__ == "__main__":
    main()
