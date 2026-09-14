"""Replaces the FRR<=0.05 selection rule (wrong at this base rate - it
produced a point with 13.8% precision and 0% abstention, which is not a
usable child-facing operating point) with two operating points serving two
different consumers, per review:

1. CHILD-FACING point: precision>=0.5 is a HARD constraint, then maximize
   recall subject to it. This is the only point allowed to name a specific
   substitution to the child - see the naming rule in backend/decision.py.
2. THERAPIST-QUEUE point: no precision constraint - rank every attempt by
   calibrated probability and report recall/precision at top-K. This is
   where the higher-recall, lower-precision numbers (k=1,n=1 at T=0.20,
   or higher-K queue depths) actually belong.

Fine-grained (0.01) T_ERROR grid, all (k,n) configs from the joint sweep,
so the precision>=0.5 threshold is actually located rather than read off
a coarse 0.05 grid (which is what produced the imprecise "2-of-4 at
T=0.35" read - checked directly, that point's precision is 0.200, not
>=0.5, and is corrected here rather than carried forward).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import build_xy, load_all_gop_records, load_pooled_rows, run_lr_cv  # noqa: E402
from harness import label_for_accuracy  # noqa: E402
from phase5_joint_sweep import build_child_attempts, build_windows, evaluate_point  # noqa: E402

EVAL_DIR = Path(__file__).parent
PRECISION_FLOOR = 0.5
FINE_T_GRID = [round(0.01 * i, 2) for i in range(1, 100)]
KN_CONFIGS = [(1, 1), (2, 3), (3, 4), (2, 4), (3, 5)]


def best_at_precision_floor(windows, k, n, floor=PRECISION_FLOOR):
    candidates = []
    for t in FINE_T_GRID:
        m = evaluate_point(windows, t, k, n)
        if m["precision"] == m["precision"] and m["precision"] >= floor:
            candidates.append(m)
    if not candidates:
        return None
    return max(candidates, key=lambda m: m["recall"])


def at_matched_frr(windows, k, n, target_frr, tol=0.0015):
    """Finds the point on this (k,n) config's curve closest to target_frr
    (within tol if possible), for the "same FRR, does single-attempt do as
    well or better" comparison."""
    best, best_diff = None, float("inf")
    for t in FINE_T_GRID:
        m = evaluate_point(windows, t, k, n)
        if m["frr"] != m["frr"]:
            continue
        diff = abs(m["frr"] - target_frr)
        if diff < best_diff:
            best, best_diff = m, diff
    return best


def bootstrap_ci(attempts, t_error, k, n, n_boot=1000, seed=0):
    by_speaker: dict[str, list[dict]] = {}
    for a in attempts:
        by_speaker.setdefault(a["speaker"], []).append(a)
    speakers = list(by_speaker.keys())
    n_sp = len(speakers)
    import random
    rng = random.Random(seed)
    samples = {"precision": [], "recall": [], "frr": []}
    for _ in range(n_boot):
        drawn = [speakers[rng.randrange(n_sp)] for _ in range(n_sp)]
        boot_attempts = []
        for sp in drawn:
            boot_attempts.extend(by_speaker[sp])
        boot_windows = build_windows(boot_attempts, n)
        m = evaluate_point(boot_windows, t_error, k, n)
        for key in samples:
            v = m[key]
            if v == v:
                samples[key].append(v)
    ci = {}
    for key, vals in samples.items():
        vals.sort()
        if not vals:
            ci[key] = (float("nan"), float("nan"))
            continue
        lo = vals[max(0, int(0.025 * len(vals)))]
        hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
        ci[key] = (lo, hi)
    return ci


def expected_false_per_10(m, n):
    prevalence = m["n_pos"] / (m["n_pos"] + m["n_neg"]) if (m["n_pos"] + m["n_neg"]) else float("nan")
    windows_per_10 = 10 // n
    return windows_per_10 * (1 - prevalence) * m["frr"], prevalence


def main():
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])
    fold_stats, oof_scores, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child, class_weight=None)

    all_gop_records = load_all_gop_records()
    child_speakers = {r["speaker"] for r in all_gop_records if r["is_child"]}
    attempts = build_child_attempts(rows, kept, oof_scores, child_speakers)
    print(f"child attempts: {len(attempts)}\n")

    print(f"=== Best point per (k,n) config at precision >= {PRECISION_FLOOR} (fine grid, step 0.01) ===")
    per_config_best = {}
    for k, n in KN_CONFIGS:
        windows = build_windows(attempts, n)
        best = best_at_precision_floor(windows, k, n)
        per_config_best[(k, n)] = best
        if best is None:
            print(f"  k={k} n={n}: NO threshold on this config clears precision>={PRECISION_FLOOR} "
                  f"(n_windows={len(windows)}) - too few positives to support this constraint")
        else:
            print(f"  k={k} n={n}: T={best['t_error']:.2f}  recall={best['recall']:.3f}  "
                  f"precision={best['precision']:.3f}  FRR={best['frr']:.4f}  "
                  f"n_windows={best['n_windows']} n_pos={best['n_pos']}")

    # single-attempt config is the reference; compare at ITS matched FRR
    # against every k>1 config that DID clear the precision floor
    single_windows = build_windows(attempts, 1)
    child_point = per_config_best[(1, 1)]
    print(f"\n=== Child-facing selection: single-attempt (k=1,n=1) at precision>={PRECISION_FLOOR} ===")
    print(f"  T_ERROR={child_point['t_error']:.2f}  recall={child_point['recall']:.3f}  "
          f"precision={child_point['precision']:.3f}  FRR={child_point['frr']:.4f}")

    print(f"\n=== Cross-check: does single-attempt at the SAME FRR as each qualifying k>1 config do as well or better? ===")
    for (k, n), best in per_config_best.items():
        if k == 1 and n == 1:
            continue
        if best is None:
            continue
        matched = at_matched_frr(single_windows, 1, 1, best["frr"])
        print(f"  {k}-of-{n} @ T={best['t_error']:.2f}: recall={best['recall']:.3f} precision={best['precision']:.3f} FRR={best['frr']:.4f}")
        print(f"  single-attempt @ matched FRR={matched['frr']:.4f}: recall={matched['recall']:.3f} precision={matched['precision']:.3f} (T={matched['t_error']:.2f})")
        verdict = "single-attempt matches or beats" if matched["recall"] >= best["recall"] else f"{k}-of-{n} wins"
        print(f"  -> {verdict}\n")

    ci = bootstrap_ci(attempts, child_point["t_error"], 1, 1, n_boot=1000, seed=0)
    print(f"95% CI (bootstrap by speaker) at selected child-facing point: "
          f"recall={ci['recall']}  precision={ci['precision']}  frr={ci['frr']}")

    false_per_10, prevalence = expected_false_per_10(child_point, 1)
    print(f"expected false corrections per 10-word session: {false_per_10:.4f}")

    # --- abstain band: T_CORRECT chosen, report actual width (fraction of attempts) ---
    T_CORRECT = 0.10
    T_ERROR_CHILD = child_point["t_error"]
    n_abstain = sum(1 for a in attempts if T_CORRECT <= a["p"] < T_ERROR_CHILD)
    abstain_rate = n_abstain / len(attempts)
    print(f"\nAbstain band [T_CORRECT={T_CORRECT}, T_ERROR={T_ERROR_CHILD:.2f}): "
          f"{n_abstain}/{len(attempts)} attempts = {abstain_rate:.1%} abstain rate")

    # --- therapist queue point: recall/precision at top-K ---
    print(f"\n=== Therapist-queue point: recall/precision at top-K (pooled child attempts, ranked by p) ===")
    ranked = sorted(attempts, key=lambda a: -a["p"])
    n_total_pos = sum(a["label"] for a in attempts)
    queue_result = {}
    for K in (10, 25, 50):
        top_k = ranked[:K]
        tp_k = sum(a["label"] for a in top_k)
        recall_k = tp_k / n_total_pos
        precision_k = tp_k / K
        queue_result[K] = {"recall": recall_k, "precision": precision_k, "tp": tp_k}
        print(f"  top-{K}: recall={recall_k:.3f}  precision={precision_k:.3f}  ({tp_k}/{K} true positives)")

    # for reference: the k=1,n=1 T=0.20 point from last turn also belongs here, not child-facing
    prior_point = evaluate_point(single_windows, 0.20, 1, 1)
    false_per_10_prior, prevalence_prior = expected_false_per_10(prior_point, 1)
    print(f"\nFor reference, last turn's selected point (T=0.20, recall={prior_point['recall']:.3f}, "
          f"precision={prior_point['precision']:.3f}) belongs at the THERAPIST-QUEUE point, not child-facing.")
    print(f"  its expected false corrections per 10-word session: {false_per_10_prior:.4f}")

    result = {
        "precision_floor": PRECISION_FLOOR,
        "per_config_best_at_precision_floor": {f"{k}-of-{n}": v for (k, n), v in per_config_best.items()},
        "child_facing_point": child_point, "child_facing_ci_95": {k: list(v) for k, v in ci.items()},
        "child_facing_expected_false_per_10": false_per_10, "child_facing_prevalence": prevalence,
        "abstain_band": {"t_correct": T_CORRECT, "t_error": T_ERROR_CHILD, "n_abstain": n_abstain,
                          "n_total": len(attempts), "abstain_rate": abstain_rate},
        "therapist_queue_top_k": queue_result,
        "reference_prior_point": {"metrics": prior_point, "expected_false_per_10": false_per_10_prior},
    }
    with open(EVAL_DIR / "phase5_two_points.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase5_two_points.json'}")


if __name__ == "__main__":
    main()
