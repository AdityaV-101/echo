"""Turns eval/features_raw_cache_<split>.json into one feature-vector row
per phoneme-attempt, adding the four speaker-relative features Phase 2
calls for (llr_best, gop_i, gop_lpr_i, dur_z, each minus that speaker's own
running mean) using calibration.py's actual Welford accumulator - not a
reimplementation of it.

Processing order matters: a speaker's running mean must only ever reflect
attempts that came BEFORE the one being featurized (never the attempt
itself, and never a later one - that would leak the answer). Records are
grouped by speaker and sorted by (utt_id, word_index) as the best available
proxy for recording order (speechocean762 carries no per-utterance
timestamp; utt_id order matches the dataset's own file order, which is the
order utterances were exported in).

Simplification, stated plainly: backend/scorer.py's real calibration only
folds a phoneme's GOP into the speaker baseline when the system's own
verdict was "correct" or "accent_variant" (folding in a wrong production
would drag the baseline toward tolerating that same error). This script has
no verdict yet - producing one is Phase 3's job - so it folds in every
attempt's raw value unconditionally. Errors are the minority class (~9.5%
of phones, ~2.5-3.6% for children - see Phase 0's label distribution), so
this should shift a running mean only slightly; Phase 3 can revisit if
feature importance suggests otherwise.

Cold start: a speaker's first few attempts at a given phoneme have no
personal history. Below MIN_SPEAKER_SAMPLES (gop_config.py's existing
constant, reused rather than inventing a new one), the "speaker's running
mean" used for centering is that phoneme's GLOBAL mean over the whole
split instead of the speaker's own (thin, unreliable) mean - the same
cold-start-falls-back-to-global-prior shape as calibration.py's real
get_baseline_for_scoring, just applied to four raw features instead of one.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from calibration import welford_update  # noqa: E402
from gop_config import MIN_SPEAKER_SAMPLES  # noqa: E402

EVAL_DIR = Path(__file__).parent
RELATIVE_FEATURES = ["llr_best", "gop_i", "gop_lpr_i", "dur_z"]


def _ground_truth_substitution(record: dict, index: int):
    for m in record["mispronunciations"]:
        if m["index"] == index:
            return m["category"], m["pronounced_phone"]
    return None


def _global_means(records: list[dict]) -> dict[str, dict[str, float]]:
    """global_means[feature][phoneme] = mean of that raw feature over every
    occurrence of that phoneme in the whole split - the cold-start fallback."""
    sums: dict[str, dict[str, float]] = {f: {} for f in RELATIVE_FEATURES}
    counts: dict[str, dict[str, int]] = {f: {} for f in RELATIVE_FEATURES}
    for record in records:
        for pos in record["positions"]:
            phone = pos["expected"]
            for feat in RELATIVE_FEATURES:
                val = pos[feat]
                sums[feat].setdefault(phone, 0.0)
                counts[feat].setdefault(phone, 0)
                sums[feat][phone] += val
                counts[feat][phone] += 1
    return {
        feat: {phone: sums[feat][phone] / counts[feat][phone] for phone in sums[feat]}
        for feat in RELATIVE_FEATURES
    }


def build_rows(records: list[dict]) -> list[dict]:
    global_means = _global_means(records)

    by_speaker: dict[str, list[dict]] = {}
    for record in records:
        by_speaker.setdefault(record["speaker"], []).append(record)
    for speaker_records in by_speaker.values():
        speaker_records.sort(key=lambda r: (r["utt_id"], r["word_index"]))

    rows = []
    for speaker, speaker_records in by_speaker.items():
        # accumulator[feature][phoneme] = (n, mean, m2)
        accumulator: dict[str, dict[str, tuple[int, float, float]]] = {f: {} for f in RELATIVE_FEATURES}

        for record in speaker_records:
            length = len(record["canonical"])
            for pos in record["positions"]:
                phone = pos["expected"]
                gt_sub = _ground_truth_substitution(record, pos["index"])

                rel_values = {}
                for feat in RELATIVE_FEATURES:
                    n, mean, m2 = accumulator[feat].get(phone, (0, 0.0, 0.0))
                    baseline = mean if n >= MIN_SPEAKER_SAMPLES else global_means[feat][phone]
                    rel_values[f"{feat}_speaker_rel"] = pos[feat] - baseline
                    n, mean, m2 = welford_update(n, mean, m2, pos[feat])
                    accumulator[feat][phone] = (n, mean, m2)

                row = {
                    "utt_id": record["utt_id"], "word_index": record["word_index"], "index": pos["index"],
                    "text": record["text"], "speaker": speaker,
                    "is_child": record["is_child"], "age": record["age"],
                    "phone_accuracy": record["phones_accuracy"][pos["index"]],
                    "gt_category": gt_sub[0] if gt_sub else None,
                    "gt_pronounced_phone": gt_sub[1] if gt_sub else None,
                    "expected": phone,
                    "llr_best": pos["llr_best"], "llr_best_origin": pos["llr_best_origin"],
                    "llr_deletion": pos["llr_deletion"], "llr_second_best": pos["llr_second_best"],
                    "llr_margin": pos["llr_margin"],
                    "gop_i": pos["gop_i"], "gop_lpr_i": pos["gop_lpr_i"], "top_competitor": pos["top_competitor"],
                    "dur_z": pos["dur_z"], "entropy": pos["entropy"],
                    "position": pos["position"], "syllable_count": pos["syllable_count"],
                    "frame_count_word": pos["frame_count_word"],
                    "ll_canonical_per_frame": record["word_features"]["ll_canonical_per_frame"],
                    "free_decode_gap": record["word_features"]["free_decode_gap"],
                    **rel_values,
                }
                rows.append(row)

    rows.sort(key=lambda r: (r["utt_id"], r["word_index"], r["index"]))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=["dev", "subtrain", "test"])
    args = parser.parse_args()

    with open(EVAL_DIR / f"features_raw_cache_{args.split}.json") as f:
        records = json.load(f)
    rows = build_rows(records)
    out_path = EVAL_DIR / f"phase2_features_{args.split}.json"
    with open(out_path, "w") as f:
        json.dump(rows, f)
    print(f"wrote {len(rows)} phoneme-attempt rows to {out_path}")
