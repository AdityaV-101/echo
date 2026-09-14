"""The most important test in the project so far: does the classifier
carry acoustic skill, or is a chunk of its pooled advantage just "some
phonemes are rarer/easier in this corpus"? Within one target phoneme,
phoneme identity is constant for every row and carries zero information -
any remaining PR-AUC advantage inside a phoneme has to come from something
that actually varies attempt to attempt (GOP, LLR, entropy, duration),
which is exactly the acoustic signal the product needs.

The weighted aggregate uses ECHO'S OWN phoneme distribution (levels.json +
practice_tracks.json word counts per target phoneme), not speechocean762's
- the pooled/pan-corpus number describes what this dataset looks like, the
within-phoneme-weighted-by-Echo's-curriculum number describes what the
product actually does, which is the number that should be trusted as the
headline from here on.
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import (  # noqa: E402
    build_xy, candidate_rows_from_oof, child_pr_auc, echo_phoneme_weights,
    gop_rows_for, lift, load_all_gop_records, load_pooled_rows, run_lr_cv,
)
from harness import paired_bootstrap_delta  # noqa: E402

EVAL_DIR = Path(__file__).parent
MIN_POSITIVES = 10  # minimum true-error tokens (candidate side) for a phoneme to be reported


def _row_key(r):
    return (r["utt_id"], r["word_index"], r["index"])


def per_phoneme_table(candidate_rows, baseline_rows, min_positives=MIN_POSITIVES):
    cand_by_key = {_row_key(r): r for r in candidate_rows}
    base_by_key = {_row_key(r): r for r in baseline_rows}
    shared = set(cand_by_key) & set(base_by_key)
    by_phone: dict[str, list[tuple]] = {}
    for key in shared:
        c, b = cand_by_key[key], base_by_key[key]
        by_phone.setdefault(c["phone"], []).append((c["label"], c["score"], b["score"]))

    table = {}
    for phone, triples in by_phone.items():
        labels = [t[0] for t in triples]
        n_pos = sum(labels)
        n = len(triples)
        if n_pos < min_positives or n_pos == n:
            table[phone] = {"n": n, "n_pos": n_pos, "prevalence": n_pos / n if n else float("nan"),
                            "candidate_pr_auc": float("nan"), "baseline_pr_auc": float("nan"),
                            "delta": float("nan"), "candidate_lift": float("nan"), "baseline_lift": float("nan"),
                            "delta_lift": float("nan"), "included": False}
            continue
        c_scores = [t[1] for t in triples]
        b_scores = [t[2] for t in triples]
        c_pr = float(average_precision_score(labels, c_scores))
        b_pr = float(average_precision_score(labels, b_scores))
        prevalence = n_pos / n
        table[phone] = {
            "n": n, "n_pos": n_pos, "prevalence": prevalence,
            "candidate_pr_auc": c_pr, "baseline_pr_auc": b_pr, "delta": c_pr - b_pr,
            "candidate_lift": lift(c_pr, prevalence), "baseline_lift": lift(b_pr, prevalence),
            "delta_lift": (c_pr - b_pr) / prevalence, "included": True,
        }
    return table


def weighted_aggregate(table: dict, weights: dict[str, int]) -> dict:
    included = {p: t for p, t in table.items() if t["included"] and p in weights}
    total_weight = sum(weights[p] for p in included)
    if total_weight == 0:
        return {"weighted_delta": float("nan"), "weighted_delta_lift": float("nan"), "total_weight_covered": 0,
                "phonemes_used": [], "phonemes_missing_from_data": []}
    weighted_delta = sum(weights[p] * t["delta"] for p, t in included.items()) / total_weight
    weighted_delta_lift = sum(weights[p] * t["delta_lift"] for p, t in included.items()) / total_weight
    missing = sorted(set(weights) - set(included), key=lambda p: -weights[p])
    return {
        "weighted_delta": weighted_delta, "weighted_delta_lift": weighted_delta_lift,
        "total_weight_covered": total_weight, "total_weight_all": sum(weights.values()),
        "coverage_fraction": total_weight / sum(weights.values()),
        "phonemes_used": sorted(included.keys()), "phonemes_missing_from_data": missing,
    }


def bootstrap_weighted_delta(candidate_rows, baseline_rows, weights, n_boot=2000, seed=0, min_positives=MIN_POSITIVES):
    cand_by_key = {_row_key(r): r for r in candidate_rows}
    base_by_key = {_row_key(r): r for r in baseline_rows}
    shared = set(cand_by_key) & set(base_by_key)
    by_speaker: dict[str, list[tuple]] = {}
    for key in shared:
        c, b = cand_by_key[key], base_by_key[key]
        by_speaker.setdefault(c["speaker"], []).append((c["phone"], c["label"], c["score"], b["score"]))
    speakers = list(by_speaker.keys())
    n_sp = len(speakers)

    import random
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        drawn = [speakers[rng.randrange(n_sp)] for _ in range(n_sp)]
        by_phone: dict[str, list[tuple]] = {}
        for sp in drawn:
            for phone, label, c_score, b_score in by_speaker[sp]:
                by_phone.setdefault(phone, []).append((label, c_score, b_score))
        included = {}
        for phone, triples in by_phone.items():
            if phone not in weights:
                continue
            labels = [t[0] for t in triples]
            n_pos = sum(labels)
            if n_pos < min_positives or n_pos == len(triples):
                continue
            c_pr = average_precision_score(labels, [t[1] for t in triples])
            b_pr = average_precision_score(labels, [t[2] for t in triples])
            included[phone] = c_pr - b_pr
        total_w = sum(weights[p] for p in included)
        if total_w == 0:
            continue
        deltas.append(sum(weights[p] * d for p, d in included.items()) / total_w)

    deltas.sort()
    if not deltas:
        return (float("nan"), float("nan")), 0
    lo = deltas[max(0, int(0.025 * len(deltas)))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return (lo, hi), len(deltas)


def main():
    print("Loading pooled features and re-running the selected model's CV (LR, per-fold scaled, balanced)...")
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])
    fold_stats, oof_scores, speaker_to_fold = run_lr_cv(numeric, cat_encoded, y, groups, is_child)
    print(f"  reproduced fold PR-AUCs: {[round(f['pr_auc'], 4) for f in fold_stats]} (should match the committed run)\n")

    all_gop_records = load_all_gop_records()
    speaker_is_child = {r["speaker"]: r["is_child"] for r in all_gop_records}
    child_speakers = {sp for sp, c in speaker_is_child.items() if c}

    candidate_rows = candidate_rows_from_oof(rows, kept, oof_scores, child_only_speakers=child_speakers)
    gop_rows = gop_rows_for(all_gop_records, child_only=True)

    weights = echo_phoneme_weights()
    print(f"Echo's own phoneme weights (levels.json + practice_tracks.json): {weights}\n")

    table = per_phoneme_table(candidate_rows, gop_rows)
    print(f"{'phone':6} {'n':>6} {'n_pos':>6} {'prev':>7} {'cand_PR':>8} {'base_PR':>8} {'delta':>8} "
          f"{'cand_lift':>10} {'base_lift':>10} {'delta_lift':>11} {'echo_wt':>8} {'included':>9}")
    for phone in sorted(table, key=lambda p: -weights.get(p, 0)):
        t = table[phone]
        w = weights.get(phone, 0)
        if t["included"]:
            print(f"{phone:6} {t['n']:6} {t['n_pos']:6} {t['prevalence']:6.1%} {t['candidate_pr_auc']:8.4f} "
                  f"{t['baseline_pr_auc']:8.4f} {t['delta']:+8.4f} {t['candidate_lift']:9.2f}x {t['baseline_lift']:9.2f}x "
                  f"{t['delta_lift']:+10.2f}x {w:8} {'yes':>9}")
        else:
            print(f"{phone:6} {t['n']:6} {t['n_pos']:6} {'--':>7} {'--':>8} {'--':>8} {'--':>8} "
                  f"{'--':>10} {'--':>10} {'--':>11} {w:8} {'NO (n_pos<'+str(MIN_POSITIVES)+')':>9}")

    agg = weighted_aggregate(table, weights)
    print(f"\nEcho-weighted within-phoneme aggregate: covers {agg['coverage_fraction']:.1%} of Echo's curriculum "
          f"weight ({agg['total_weight_covered']}/{agg['total_weight_all']} words)")
    print(f"  phonemes used: {agg['phonemes_used']}")
    print(f"  phonemes in Echo's curriculum with insufficient dev data: {agg['phonemes_missing_from_data']}")
    print(f"  WEIGHTED WITHIN-PHONEME DELTA PR-AUC = {agg['weighted_delta']:+.4f}")
    print(f"  WEIGHTED WITHIN-PHONEME DELTA LIFT    = {agg['weighted_delta_lift']:+.2f}x")

    ci, n_valid = bootstrap_weighted_delta(candidate_rows, gop_rows, weights, n_boot=2000, seed=0)
    print(f"  95% CI (bootstrap by speaker, n_valid_resamples={n_valid}): [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    print(f"  -> {'BEATS baseline within-phoneme' if ci[0] > 0 else 'does NOT clear baseline within-phoneme'}\n")

    # pooled (between-phoneme-inclusive) delta, kept as secondary reference
    pooled = paired_bootstrap_delta(candidate_rows, gop_rows, metric_name="pr_auc", n_boot=2000, seed=0)
    print(f"SECONDARY - pooled delta (includes between-phoneme discrimination the app cannot use): "
          f"{pooled['point_delta']:+.4f} 95% CI [{pooled['ci'][0]:+.4f}, {pooled['ci'][1]:+.4f}]")

    result = {
        "echo_phoneme_weights": weights,
        "per_phoneme_table": table,
        "weighted_aggregate": agg,
        "weighted_aggregate_ci_95": list(ci),
        "pooled_secondary": {"point_delta": pooled["point_delta"], "ci": list(pooled["ci"])},
    }
    with open(EVAL_DIR / "phase3_within_phoneme.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_within_phoneme.json'}")


if __name__ == "__main__":
    main()
