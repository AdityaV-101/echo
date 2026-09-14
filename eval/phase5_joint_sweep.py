"""Phase 5, corrected: the FRR<=0.05 budget applies to the AGGREGATED
(k-of-n corroborated) decision, because that's the only decision a child or
therapist ever sees - a single attempt no longer names anything (Phase 5's
whole design), so its own FRR is not the user-facing quantity. The earlier
version stacked a single-attempt threshold (chosen to be safe on its own
FRR) on top of k-of-n corroboration as an afterthought; this sweeps
(T_ERROR, (k, n)) JOINTLY and selects from the resulting aggregated
Pareto front, not from a single-attempt curve.

Windowing is identical to eval/measure_k_of_n.py's: group by (speaker,
canonical phone), sort by (utt_id, word_index) as the chronological proxy,
cut into non-overlapping windows of size n. A window's true label is 1 iff
>=k of its n tokens are true errors (same k-of-n rule applied to ground
truth as to the prediction - a stated modeling choice, not a given, see
measure_k_of_n.py's docstring for the reasoning). The single-attempt call
inside a window is a plain threshold at T_ERROR (no separate T_CORRECT for
this sweep - one free single-attempt knob, T_ERROR, per point, since
corroboration is what's doing the recall-recovery work here, not a
three-way single-attempt decision).

Uses the ALREADY-COMPUTED frozen-model CV (class_weight=None, per the
calibration finding) - no retraining, no new feature or hyperparameter
choices, consistent with the modeling freeze.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import build_xy, load_all_gop_records, load_pooled_rows, run_lr_cv  # noqa: E402
from harness import label_for_accuracy  # noqa: E402

EVAL_DIR = Path(__file__).parent
FRR_BUDGET = 0.05
KN_CONFIGS = [(1, 1), (2, 3), (3, 4), (2, 4), (3, 5)]
T_GRID = [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05 .. 0.95
CURRENT_STACKED_POINT = (0.80, 2, 3)  # the setting being replaced - included explicitly for comparison


def build_child_attempts(rows, kept, oof_scores, child_speakers):
    attempts = []
    for row_i, i in enumerate(kept):
        r = rows[i]
        if r["speaker"] not in child_speakers:
            continue
        label = label_for_accuracy(r["phone_accuracy"])
        if label is None:
            continue
        attempts.append({
            "speaker": r["speaker"], "phone": r["expected"],
            "utt_id": r["utt_id"], "word_index": r["word_index"],
            "label": label, "p": float(oof_scores[row_i]),
        })
    return attempts


def build_windows(attempts, n):
    groups: dict[tuple, list[dict]] = {}
    for a in attempts:
        groups.setdefault((a["speaker"], a["phone"]), []).append(a)
    windows = []
    for (speaker, phone), group in groups.items():
        group.sort(key=lambda a: (a["utt_id"], a["word_index"]))
        for start in range(0, len(group) - n + 1, n):
            windows.append({"speaker": speaker, "phone": phone, "attempts": group[start:start + n]})
    return windows


def evaluate_point(windows, t_error, k, n):
    tp = fp = fn = tn = 0
    for w in windows:
        attempts = w["attempts"]
        n_true_error = sum(a["label"] for a in attempts)
        true_wrong = n_true_error >= k
        n_flagged = sum(1 for a in attempts if a["p"] >= t_error)
        pred_wrong = n_flagged >= k
        if pred_wrong and true_wrong:
            tp += 1
        elif pred_wrong and not true_wrong:
            fp += 1
        elif not pred_wrong and true_wrong:
            fn += 1
        else:
            tn += 1
    n_pos = tp + fn
    n_neg = fp + tn
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / n_pos if n_pos else float("nan")
    frr = fp / n_neg if n_neg else float("nan")
    return {"t_error": t_error, "k": k, "n": n, "n_windows": len(windows),
            "n_pos": n_pos, "n_neg": n_neg, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "frr": frr}


def is_dominated(a, b):
    """True if b dominates a: b is at least as good on all three axes and
    strictly better on at least one (lower FRR, higher recall, higher
    precision), restricted to points with a defined precision/recall."""
    if any(v != v for v in (a["frr"], a["recall"], a["precision"], b["frr"], b["recall"], b["precision"])):
        return False
    not_worse = b["frr"] <= a["frr"] and b["recall"] >= a["recall"] and b["precision"] >= a["precision"]
    strictly_better = b["frr"] < a["frr"] or b["recall"] > a["recall"] or b["precision"] > a["precision"]
    return not_worse and strictly_better


def pareto_front(points):
    return [p for p in points if not any(is_dominated(p, q) for q in points if q is not p)]


def bootstrap_ci_for_point(attempts, t_error, k, n, n_boot=1000, seed=0):
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


def main():
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)
    is_child = np.array([rows[i]["is_child"] for i in kept])
    fold_stats, oof_scores, _ = run_lr_cv(numeric, cat_encoded, y, groups, is_child, class_weight=None)
    print(f"reproduced fold PR-AUCs: {[round(f['pr_auc'], 4) for f in fold_stats]}\n")

    all_gop_records = load_all_gop_records()
    child_speakers = {r["speaker"] for r in all_gop_records if r["is_child"]}
    attempts = build_child_attempts(rows, kept, oof_scores, child_speakers)
    print(f"child attempts available for windowing: {len(attempts)}\n")

    all_points = []
    windows_cache = {}
    for k, n in KN_CONFIGS:
        windows = build_windows(attempts, n)
        windows_cache[(k, n)] = windows
        for t in T_GRID:
            all_points.append(evaluate_point(windows, t, k, n))

    print(f"{'k-of-n':8} {'T_ERROR':>8} {'n_win':>6} {'n_pos':>6} {'precision':>10} {'recall':>8} {'FRR':>8}")
    for p in sorted(all_points, key=lambda p: (p["k"], p["n"], p["t_error"])):
        print(f"{p['k']}-of-{p['n']:<3} {p['t_error']:8.2f} {p['n_windows']:6} {p['n_pos']:6} "
              f"{p['precision']:10.3f} {p['recall']:8.3f} {p['frr']:8.4f}")

    front = pareto_front(all_points)
    print(f"\n=== Pareto front ({len(front)} points) ===")
    for p in sorted(front, key=lambda p: p["frr"]):
        print(f"  k={p['k']} n={p['n']} T={p['t_error']:.2f}  FRR={p['frr']:.4f}  recall={p['recall']:.3f}  "
              f"precision={p['precision']:.3f}  n_windows={p['n_windows']} n_pos={p['n_pos']}")

    compliant = [p for p in all_points if p["frr"] == p["frr"] and p["frr"] <= FRR_BUDGET and p["recall"] == p["recall"]]
    if compliant:
        selected = max(compliant, key=lambda p: p["recall"])
    else:
        selected = min(all_points, key=lambda p: p["frr"])
    print(f"\n=== SELECTED (max aggregated recall subject to aggregated FRR<={FRR_BUDGET}) ===")
    print(f"  k={selected['k']} n={selected['n']} T_ERROR={selected['t_error']:.2f}")
    print(f"  aggregated recall={selected['recall']:.3f}  precision={selected['precision']:.3f}  "
          f"FRR={selected['frr']:.4f}  n_windows={selected['n_windows']}  n_pos={selected['n_pos']}")

    k_sel, n_sel, t_sel = selected["k"], selected["n"], selected["t_error"]
    ci = bootstrap_ci_for_point(attempts, t_sel, k_sel, n_sel, n_boot=1000, seed=0)
    print(f"  95% CI (bootstrap by speaker): recall={ci['recall']}  precision={ci['precision']}  frr={ci['frr']}")

    # abstain rate: fraction of attempts that never end up in a complete window
    n_in_windows = sum(len(w["attempts"]) for w in windows_cache[(k_sel, n_sel)])
    abstain_rate = 1 - (n_in_windows / len(attempts)) if attempts else float("nan")
    print(f"  abstain rate (attempts not part of a complete {n_sel}-window): {abstain_rate:.1%}")

    # expected false corrections per 10-word session
    prevalence = selected["n_pos"] / (selected["n_pos"] + selected["n_neg"]) if (selected["n_pos"] + selected["n_neg"]) else float("nan")
    windows_per_10 = 10 // n_sel
    expected_false_per_10 = windows_per_10 * (1 - prevalence) * selected["frr"]
    print(f"  windows per 10-word session: {windows_per_10}  aggregate prevalence: {prevalence:.2%}")
    print(f"  EXPECTED FALSE CORRECTIONS PER 10-WORD SESSION: {expected_false_per_10:.4f}")

    # current stacked point, for explicit comparison
    t_cur, k_cur, n_cur = CURRENT_STACKED_POINT
    stacked = evaluate_point(windows_cache[(k_cur, n_cur)], t_cur, k_cur, n_cur)
    print(f"\n=== CURRENT STACKED SETTING (T_ERROR=0.80, 2-of-3), for comparison ===")
    print(f"  recall={stacked['recall']:.3f}  precision={stacked['precision']:.3f}  frr={stacked['frr']:.4f}  "
          f"n_windows={stacked['n_windows']}  n_pos={stacked['n_pos']}")

    result = {
        "all_points": all_points, "pareto_front": front,
        "selected": selected, "selected_ci_95": {k: list(v) for k, v in ci.items()},
        "selected_abstain_rate": abstain_rate, "selected_expected_false_corrections_per_10_words": expected_false_per_10,
        "current_stacked_point": stacked,
    }
    with open(EVAL_DIR / "phase5_joint_sweep.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase5_joint_sweep.json'}")


if __name__ == "__main__":
    main()
