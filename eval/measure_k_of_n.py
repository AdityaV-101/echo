"""Design change E: does k-of-n evidence aggregation actually deliver the
precision gain the independence-assumed arithmetic predicts, on real
(correlated) attempts from the same speaker?

Grouping: (speaker, canonical phone) - a speaker's repeated attempts at
producing one target phone across different words in the corpus, the same
shape as a practice level's 3-4 words sharing one target phoneme. Attempts
are ordered by (utt_id, word_index) as the best available chronological
proxy (speechocean762 carries no per-utterance timestamp) and cut into
NON-OVERLAPPING windows of size n - each window is one simulated "practice
level attempt" for that phoneme.

Ground truth for a window uses the SAME k-of-n rule applied to the true
per-token labels (>=k of the n tokens in the window are real errors) - this
is a stated modeling choice, not a given: speechocean762 rates individual
word productions, not a stable "this child has a problem with this sound"
trait, so treating "the child got it wrong on a clear majority of tries in
this window" as evidence of a real, persistent difficulty is an
approximation, made explicit here rather than left implicit.

Single-attempt operating point comes from the GOP z-score baseline (the
best-measured baseline so far) - not from a hypothetical FRR=5%/recall=50%
point, so the "does aggregation help" answer is grounded in a real,
already-measured scorer rather than an idealized one. The independence
assumption's prediction is computed from that SAME scorer's real
single-attempt FRR/recall (via backend.aggregation.binomial_at_least_k),
so the "real vs assumed" comparison isolates exactly one thing: whether
this speaker's repeated attempts behave as independent draws.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from aggregation import aggregate_k_of_n, binomial_at_least_k  # noqa: E402
from baselines import predict_gop_zscore  # noqa: E402
from harness import bootstrap_ci_by_speaker, label_for_accuracy  # noqa: E402

EVAL_DIR = Path(__file__).parent


def build_attempts(records: list[dict], slice_filter=None) -> list[dict]:
    """One row per (speaker, phone) occurrence, in (utt_id, word_index)
    order within each record - the single-attempt population everything
    else in this script groups and windows."""
    rows = []
    for record in records:
        if slice_filter is not None and not slice_filter(record):
            continue
        predictions = predict_gop_zscore(record)
        for i, (phone, acc, pred) in enumerate(zip(record["canonical"], record["phones_accuracy"], predictions)):
            label = label_for_accuracy(acc)
            if label is None:
                continue  # ambiguous band excluded, same as everywhere else
            rows.append({
                "speaker": record["speaker"], "phone": phone,
                "utt_id": record["utt_id"], "word_index": record["word_index"],
                "label": label, "status": pred["status"],
            })
    return rows


def build_windows(rows: list[dict], n: int) -> list[dict]:
    """Groups by (speaker, phone), sorts by (utt_id, word_index), cuts into
    non-overlapping windows of size n. Each window: {speaker, phone,
    attempts: [row, ...]}."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["speaker"], row["phone"]), []).append(row)

    windows = []
    for (speaker, phone), attempts in groups.items():
        attempts.sort(key=lambda r: (r["utt_id"], r["word_index"]))
        for start in range(0, len(attempts) - n + 1, n):
            windows.append({"speaker": speaker, "phone": phone, "attempts": attempts[start:start + n]})
    return windows


def windows_to_rows(windows: list[dict], k: int) -> list[dict]:
    """One row per window: aggregated predicted status vs aggregated true
    label (same k-of-n rule applied to both - see module docstring)."""
    rows = []
    for w in windows:
        statuses = [a["status"] for a in w["attempts"]]
        labels = [a["label"] for a in w["attempts"]]
        pred = aggregate_k_of_n(statuses, k)
        n_true_error = sum(labels)
        true_label = 1 if n_true_error >= k else 0
        rows.append({
            "speaker": w["speaker"], "label": true_label,
            "status": pred.status, "score": 0.0, "heard": None, "gt_sub": None,
            "phone": w["phone"], "position": "n/a",
        })
    return rows


def _confusion(rows: list[dict]) -> dict:
    tp = fp = fn = tn = 0
    for r in rows:
        predicted_error = r["status"] == "wrong"
        actual_error = r["label"] == 1
        if predicted_error and actual_error:
            tp += 1
        elif predicted_error and not actual_error:
            fp += 1
        elif not predicted_error and actual_error:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    frr = fp / (fp + tn) if (fp + tn) else float("nan")
    far = fn / (fn + tp) if (fn + tp) else float("nan")
    n_pos = tp + fn
    n_neg = fp + tn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n_positive": n_pos, "n_negative": n_neg,
            "base_rate": n_pos / (n_pos + n_neg) if (n_pos + n_neg) else float("nan"),
            "precision": precision, "recall": recall, "frr": frr, "far": far}


def _bootstrap_confusion_ci(rows: list[dict], n_boot: int = 2000, seed: int = 0) -> dict:
    import random
    by_speaker: dict[str, list[dict]] = {}
    for r in rows:
        by_speaker.setdefault(r["speaker"], []).append(r)
    speakers = list(by_speaker.keys())
    n_sp = len(speakers)
    rng = random.Random(seed)
    samples = {"precision": [], "recall": [], "frr": [], "far": []}
    for _ in range(n_boot):
        drawn = [speakers[rng.randrange(n_sp)] for _ in range(n_sp)]
        boot_rows = []
        for sp in drawn:
            boot_rows.extend(by_speaker[sp])
        m = _confusion(boot_rows)
        for k in samples:
            v = m[k]
            if v == v:
                samples[k].append(v)
    ci = {}
    for k, vals in samples.items():
        vals.sort()
        if not vals:
            ci[k] = (float("nan"), float("nan"))
            continue
        lo = vals[max(0, int(0.025 * len(vals)))]
        hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
        ci[k] = (lo, hi)
    return ci


SLICES = {
    "all_speakers": None,
    "child": lambda r: r["is_child"],
    "age_le9": lambda r: r["is_child"] and r["age"] <= 9,
}


def main():
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        records = json.load(f)

    report = {}
    for slice_name, slice_filter in SLICES.items():
        print(f"=== slice: {slice_name} ===")
        attempts = build_attempts(records, slice_filter)

        # single-attempt confusion, restricted to attempts that end up in a
        # window (fair comparison population - see module docstring)
        n_window = 3
        k = 2
        windows = build_windows(attempts, n_window)
        windowed_attempt_rows = [
            {"speaker": w["speaker"], "label": a["label"], "status": a["status"]}
            for w in windows for a in w["attempts"]
        ]
        single_m = _confusion(windowed_attempt_rows)
        single_ci = _bootstrap_confusion_ci(windowed_attempt_rows)

        agg_rows = windows_to_rows(windows, k)
        agg_m = _confusion(agg_rows)
        agg_ci = _bootstrap_confusion_ci(agg_rows)

        theoretical_frr = binomial_at_least_k(n_window, k, single_m["frr"]) if single_m["frr"] == single_m["frr"] else float("nan")
        theoretical_recall = binomial_at_least_k(n_window, k, single_m["recall"]) if single_m["recall"] == single_m["recall"] else float("nan")

        print(f"  windows (n={n_window}, k={k}): {len(windows)}  (from {len(attempts)} attempts, "
              f"{sum(1 for r in windowed_attempt_rows if True)} in a window)")
        print(f"  SINGLE-ATTEMPT: n_pos={single_m['n_positive']} n_neg={single_m['n_negative']} "
              f"base_rate={single_m['base_rate']:.1%} precision={single_m['precision']:.1%} "
              f"[{single_ci['precision'][0]:.1%},{single_ci['precision'][1]:.1%}] "
              f"recall={single_m['recall']:.1%} [{single_ci['recall'][0]:.1%},{single_ci['recall'][1]:.1%}] "
              f"FRR={single_m['frr']:.1%} [{single_ci['frr'][0]:.1%},{single_ci['frr'][1]:.1%}] "
              f"FAR={single_m['far']:.1%} [{single_ci['far'][0]:.1%},{single_ci['far'][1]:.1%}]")
        print(f"  {k}-of-{n_window} REAL:   n_pos={agg_m['n_positive']} n_neg={agg_m['n_negative']} "
              f"base_rate={agg_m['base_rate']:.1%} precision={agg_m['precision']:.1%} "
              f"[{agg_ci['precision'][0]:.1%},{agg_ci['precision'][1]:.1%}] "
              f"recall={agg_m['recall']:.1%} [{agg_ci['recall'][0]:.1%},{agg_ci['recall'][1]:.1%}] "
              f"FRR={agg_m['frr']:.1%} [{agg_ci['frr'][0]:.1%},{agg_ci['frr'][1]:.1%}] "
              f"FAR={agg_m['far']:.1%} [{agg_ci['far'][0]:.1%},{agg_ci['far'][1]:.1%}]")
        print(f"  {k}-of-{n_window} THEORY (independence, from this slice's single-attempt FRR/recall): "
              f"FRR={theoretical_frr:.1%}  recall={theoretical_recall:.1%}")
        print()

        report[slice_name] = {
            "n_windows": len(windows), "n_attempts_total": len(attempts),
            "single_attempt": {"metrics": single_m, "ci": single_ci},
            f"{k}_of_{n_window}_real": {"metrics": agg_m, "ci": agg_ci},
            f"{k}_of_{n_window}_theoretical_independence": {"frr": theoretical_frr, "recall": theoretical_recall},
        }

    with open(EVAL_DIR / "k_of_n_results.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"Wrote {EVAL_DIR / 'k_of_n_results.json'}")


if __name__ == "__main__":
    main()
