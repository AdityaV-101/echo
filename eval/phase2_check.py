"""Phase 2 end-of-phase checkpoint (ground rule: stop and show numbers).
Phase 2 builds features, it doesn't decide anything (Phase 3 does) - so
there's no FRR/FAR table here. What's worth checking before handing this to
a classifier: are the features actually informative (univariate separation
between the honest correct/error labels), and how complete are they
(llr_deletion/llr_second_best are undefined for some positions by
construction - a single-phoneme word has no deletion candidate, and a
position with only one feasible alternative has no second-best).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from harness import label_for_accuracy  # noqa: E402

EVAL_DIR = Path(__file__).parent

NUMERIC_FEATURES = [
    "llr_best", "llr_margin", "gop_i", "gop_lpr_i", "dur_z", "entropy",
    "ll_canonical_per_frame", "free_decode_gap",
    "llr_best_speaker_rel", "gop_i_speaker_rel", "gop_lpr_i_speaker_rel", "dur_z_speaker_rel",
]


def point_biserial(values: list[float], labels: list[int]) -> float:
    n = len(values)
    if n < 2:
        return float("nan")
    mean_v = sum(values) / n
    var_v = sum((v - mean_v) ** 2 for v in values) / n
    std_v = var_v ** 0.5
    mean_l = sum(labels) / n
    var_l = sum((l - mean_l) ** 2 for l in labels) / n
    std_l = var_l ** 0.5
    if std_v == 0 or std_l == 0:
        return float("nan")
    cov = sum((v - mean_v) * (l - mean_l) for v, l in zip(values, labels)) / n
    return cov / (std_v * std_l)


def main():
    with open(EVAL_DIR / "phase2_features_dev.json") as f:
        rows = json.load(f)

    labeled = [(r, label_for_accuracy(r["phone_accuracy"])) for r in rows]
    labeled = [(r, l) for r, l in labeled if l is not None]
    n_ambiguous = len(rows) - len(labeled)
    print(f"Total rows: {len(rows)}  ambiguous excluded: {n_ambiguous}  labeled: {len(labeled)}")
    n_pos = sum(1 for _, l in labeled if l == 1)
    print(f"  positive (error) rate among labeled: {n_pos / len(labeled):.1%} ({n_pos}/{len(labeled)})\n")

    n_no_deletion = sum(1 for r in rows if r["llr_deletion"] is None)
    n_no_second = sum(1 for r in rows if r["llr_second_best"] is None)
    print(f"llr_deletion missing (single-phoneme words): {n_no_deletion}/{len(rows)} ({n_no_deletion / len(rows):.1%})")
    print(f"llr_second_best missing (only one alternative candidate): {n_no_second}/{len(rows)} ({n_no_second / len(rows):.1%})\n")

    print(f"{'feature':28} {'r (point-biserial vs error label)':>36}  {'mean|correct':>14} {'mean|error':>12}")
    for feat in NUMERIC_FEATURES:
        values = [r[feat] for r, _ in labeled]
        labels = [l for _, l in labeled]
        r = point_biserial(values, labels)
        mean_correct = sum(v for v, l in zip(values, labels) if l == 0) / max(1, labels.count(0))
        mean_error = sum(v for v, l in zip(values, labels) if l == 1) / max(1, labels.count(1))
        print(f"{feat:28} {r:36.3f}  {mean_correct:14.4f} {mean_error:12.4f}")

    # Child slice too - the population that actually matters
    print("\n--- child slice ---")
    child_labeled = [(r, l) for r, l in labeled if r["is_child"]]
    n_pos_c = sum(1 for _, l in child_labeled if l == 1)
    print(f"labeled: {len(child_labeled)}  positive rate: {n_pos_c / len(child_labeled):.1%} ({n_pos_c}/{len(child_labeled)})")
    for feat in NUMERIC_FEATURES:
        values = [r[feat] for r, _ in child_labeled]
        labels = [l for _, l in child_labeled]
        r = point_biserial(values, labels)
        print(f"  {feat:26} r={r:7.3f}")


if __name__ == "__main__":
    main()
