"""Check C: does extract_phase0_cache.py's <800-sample audio filter and
forced-alignment failure handling silently make the dev set easier than the
population it's drawn from?

Both filters run BEFORE any label is looked at, so there's no way they
could deliberately target error tokens - but that doesn't mean they can't
correlate with them. A mispronounced word is more likely to be short,
mumbled, or acoustically ambiguous, all of which are exactly the conditions
that make forced_align more likely to raise (gop_scorer.align_canonical
raises RuntimeError rather than silently mis-aligning - see its docstring)
and more likely to produce short/quiet audio that trips the <800-sample
floor. If error tokens drop out at a higher rate than correct tokens, every
baseline number measured on the survivors is optimistic - it was computed
on the easier-to-process subset of the errors that exist.

This compares the FULL set of phoneme tokens belonging to the 31 speakers
speaker_split.json originally assigned to "dev" (before any filtering)
against the tokens that actually survived into phase0_raw_cache_dev.json,
broken down by the same label bands harness.py uses (correct / ambiguous /
error) - not just "did the word survive" but "did tokens in each label
band survive at the same rate."
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from harness import label_for_accuracy  # noqa: E402

EVAL_DIR = Path(__file__).parent


def main():
    with open(EVAL_DIR / "speaker_split.json") as f:
        split = json.load(f)
    dev_speakers = {sp for sp, g in split.items() if g == "dev"}
    print(f"Originally assigned dev speakers: {len(dev_speakers)}")

    original_words = []
    with open(EVAL_DIR / "speechocean_train.jsonl") as f:
        for line in f:
            d = json.loads(line)
            if d["speaker"] in dev_speakers:
                original_words.append(d)
    print(f"Originally assigned dev words (before any filtering): {len(original_words)}")

    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        survived = json.load(f)
    survived_keys = {(r["utt_id"], r["word_index"]) for r in survived}
    survived_speakers = {r["speaker"] for r in survived}
    print(f"Words that survived extraction: {len(survived)}")
    print(f"Speakers that survived (produced >=1 usable word): {len(survived_speakers)}")
    dropped_speakers = dev_speakers - survived_speakers
    print(f"Speakers with ZERO surviving words: {sorted(dropped_speakers)}\n")

    # Per-TOKEN drop rate by label band - the actual question.
    bands = {"correct (2.0)": lambda a: a >= 2.0, "ambiguous (1.0-2.0)": lambda a: 1.0 < a < 2.0, "error (<=1.0)": lambda a: a <= 1.0}
    counts = {b: {"original": 0, "survived": 0} for b in bands}

    for w in original_words:
        key = (w["utt_id"], w["word_index"])
        word_survived = key in survived_keys
        for acc in w["phones_accuracy"]:
            for band, pred in bands.items():
                if pred(acc):
                    counts[band]["original"] += 1
                    if word_survived:
                        counts[band]["survived"] += 1
                    break

    print(f"{'band':22} {'original':>10} {'survived':>10} {'dropped':>9} {'drop rate':>10}")
    for band, c in counts.items():
        dropped = c["original"] - c["survived"]
        rate = dropped / c["original"] if c["original"] else float("nan")
        print(f"{band:22} {c['original']:10} {c['survived']:10} {dropped:9} {rate:9.1%}")

    error_rate = (counts["error (<=1.0)"]["original"] - counts["error (<=1.0)"]["survived"]) / counts["error (<=1.0)"]["original"]
    correct_rate = (counts["correct (2.0)"]["original"] - counts["correct (2.0)"]["survived"]) / counts["correct (2.0)"]["original"]
    print(f"\nerror-token drop rate {error_rate:.1%} vs correct-token drop rate {correct_rate:.1%} "
          f"(ratio {error_rate / correct_rate if correct_rate else float('nan'):.2f}x)")

    result = {
        "n_original_dev_speakers": len(dev_speakers),
        "n_survived_dev_speakers": len(survived_speakers),
        "dropped_speakers": sorted(dropped_speakers),
        "n_original_words": len(original_words),
        "n_survived_words": len(survived),
        "band_counts": {b: c for b, c in counts.items()},
        "error_token_drop_rate": error_rate,
        "correct_token_drop_rate": correct_rate,
    }
    with open(EVAL_DIR / "extraction_bias_check.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'extraction_bias_check.json'}")


if __name__ == "__main__":
    main()
