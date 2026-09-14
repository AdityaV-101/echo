"""Diagnostic question, not a clinical one: do these features discriminate
within a fixed phoneme AT ALL, when sample size stops being the limiting
factor? Uses the ALL-SPEAKERS slice (adults included - speechocean762's
adult speakers are non-native L2 English speakers) purely because that's
where positive counts are large enough per phoneme to measure within-
phoneme PR-AUC reliably. This is explicitly NOT a clinical measurement:
L2 adult mispronunciation patterns (accent-driven, largely phonological
transfer errors) are a different population and a different error
generating process than developmental child articulation errors. It
answers one narrower methodological question: is the feature set capable
of within-phoneme discrimination at all, or is it structurally incapable
of it regardless of data volume. See RESULTS.md for which answer the data
actually gives - written there as one of two explicit, non-hedged options.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import (  # noqa: E402
    build_xy, candidate_rows_from_oof, echo_phoneme_weights,
    gop_rows_for, load_all_gop_records, load_pooled_rows, run_lr_cv,
)
from phase3_within_phoneme import bootstrap_weighted_delta, per_phoneme_table, weighted_aggregate  # noqa: E402
from harness import paired_bootstrap_delta  # noqa: E402

EVAL_DIR = Path(__file__).parent
MIN_POSITIVES = 30


def main():
    print("L2/ALL-SPEAKERS within-phoneme diagnostic - NOT a clinical measurement, see module docstring.\n")
    print("Re-running the selected model's CV (LR, per-fold scaled, class_weight=None per the calibration finding)...")
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])
    fold_stats, oof_scores, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child, class_weight=None)
    print(f"  fold PR-AUCs (child, for reference only): {[round(f['pr_auc'], 4) for f in fold_stats]}\n")

    all_gop_records = load_all_gop_records()
    candidate_rows = candidate_rows_from_oof(rows, kept, oof_scores, child_only_speakers=None)  # ALL speakers
    gop_rows = gop_rows_for(all_gop_records, child_only=False)  # ALL speakers

    weights = echo_phoneme_weights()
    table = per_phoneme_table(candidate_rows, gop_rows, min_positives=MIN_POSITIVES)

    print(f"{'phone':6} {'n':>6} {'n_pos':>6} {'prev':>7} {'cand_PR':>8} {'base_PR':>8} {'delta':>9} "
          f"{'95% CI':>22} {'echo_wt':>8}")
    qualifying = {p: t for p, t in table.items() if t["included"] and p in weights}
    for phone in sorted(qualifying, key=lambda p: -weights.get(p, 0)):
        t = table[phone]
        # speaker-clustered CI for this single phoneme
        phone_cand = [r for r in candidate_rows if r["phone"] == phone]
        phone_gop = [r for r in gop_rows if r["phone"] == phone]
        d = paired_bootstrap_delta(phone_cand, phone_gop, metric_name="pr_auc", n_boot=1000, seed=0)
        lo, hi = d["ci"]
        print(f"{phone:6} {t['n']:6} {t['n_pos']:6} {t['prevalence']:6.1%} {t['candidate_pr_auc']:8.4f} "
              f"{t['baseline_pr_auc']:8.4f} {t['delta']:+9.4f} [{lo:+8.4f},{hi:+8.4f}] {weights.get(phone, 0):8}")
        qualifying[phone]["ci"] = [lo, hi]

    requested = {"S", "L", "SH", "TH", "Z", "CH", "K", "V", "DH", "R", "T", "N"}
    not_qualifying_but_requested = sorted(p for p in requested if p not in qualifying)
    print(f"\nRequested phonemes that did NOT clear {MIN_POSITIVES} positives at the all-speakers level "
          f"(reported honestly, not forced into the table): {not_qualifying_but_requested}")
    for p in not_qualifying_but_requested:
        print(f"  {p}: n_pos={table.get(p, {}).get('n_pos', 0)}")

    extra_qualifying = sorted(set(qualifying) - requested)
    print(f"Other Echo-curriculum phonemes that DO qualify (not in the requested list): {extra_qualifying}\n")

    agg = weighted_aggregate(table, weights)
    print(f"Echo-weighted within-phoneme aggregate (L2/all-speakers, n={len(qualifying)} phonemes, "
          f"{agg['coverage_fraction']:.1%} of curriculum weight): delta PR-AUC = {agg['weighted_delta']:+.4f}")
    ci, n_valid = bootstrap_weighted_delta(candidate_rows, gop_rows, weights, n_boot=2000, seed=0, min_positives=MIN_POSITIVES)
    print(f"  95% CI (bootstrap by speaker, n_valid={n_valid}): [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    verdict = "BEATS baseline within-phoneme (L2/all-speakers)" if ci[0] > 0 else "does NOT clear baseline within-phoneme (L2/all-speakers)"
    print(f"  -> {verdict}")

    result = {
        "population": "all_speakers (L2 adults + children pooled) - NOT clinical, see module docstring",
        "min_positives": MIN_POSITIVES,
        "per_phoneme_table": {p: qualifying[p] for p in qualifying},
        "requested_not_qualifying": not_qualifying_but_requested,
        "extra_qualifying": extra_qualifying,
        "weighted_aggregate": agg, "weighted_aggregate_ci_95": list(ci),
    }
    with open(EVAL_DIR / "phase3_within_phoneme_l2.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_within_phoneme_l2.json'}")


if __name__ == "__main__":
    main()
