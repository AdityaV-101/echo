"""Step 8 (eval harness), part 3: run the real production scorer (not a
reimplementation - backend/scorer.py's actual score_word) over the whole
synthetic corpus and report:
- overall accuracy on the correct-vs-error decision
- a per-phoneme confusion matrix (expected -> what was reported as heard)
- false accept rate (errors scored as correct) and false reject rate
  (correct productions scored as wrong), reported separately
- the 10 worst individual cases with their GOP values

Each recording is scored under a unique, never-before-seen user_id, so
every trial is judged against the global prior only (gop_config.GLOBAL_PRIOR)
- the same "brand new speaker" condition eval/sweep.py calibrated against -
never against another eval trial's accumulated baseline.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from _shared import load_labels  # noqa: E402
from scorer import score_word  # noqa: E402

EVAL_DIR = Path(__file__).parent


def predicted_label(result: dict) -> str:
    return "correct" if result["percent_correct"] == 100 else "error"


def main():
    labels = load_labels()
    outcomes = []

    for i, entry in enumerate(labels):
        audio_path = str(EVAL_DIR / entry["audio_path"])
        user_id = f"eval_{entry['target_word']}_{entry['label']}_{i}"  # always-fresh, no calibration history
        result = score_word(
            audio_path,
            entry["target_word"],
            phonemes_override=entry["canonical"],
            user_id=user_id,
            accent_tolerance_enabled=True,
        )
        pred = predicted_label(result)
        outcomes.append({**entry, "result": result, "predicted": pred})
        print(f"[{i + 1}/{len(labels)}] {entry['target_word']:8} true={entry['label']:7} "
              f"pred={pred:7} percent={result['percent_correct']:3} pattern={entry['pattern']}")

    # --- Overall accuracy + FAR/FRR ---
    tp = fp = tn = fn = 0
    for o in outcomes:
        true, pred = o["label"], o["predicted"]
        if true == "error" and pred == "error":
            tp += 1
        elif true == "correct" and pred == "error":
            fp += 1
        elif true == "correct" and pred == "correct":
            tn += 1
        else:
            fn += 1
    n = len(outcomes)
    accuracy = (tp + tn) / n
    far = fn / (tp + fn) if (tp + fn) else 0.0
    frr = fp / (fp + tn) if (fp + tn) else 0.0

    print("\n" + "=" * 70)
    print("OVERALL RESULTS")
    print("=" * 70)
    print(f"Accuracy on correct-vs-error decision: {accuracy:.3f} ({tp + tn}/{n})")
    print(f"False accept rate (errors scored correct):   {far:.3f} ({fn}/{tp + fn})")
    print(f"False reject rate (correct scored as error):  {frr:.3f} ({fp}/{fp + tn})")

    # --- Per-phoneme confusion matrix ---
    confusion = Counter()
    for o in outcomes:
        for r in o["result"]["results"]:
            if r["status"] != "correct" and r["heard"]:
                confusion[(r["expected"], r["heard"])] += 1

    print("\n" + "=" * 70)
    print("PER-PHONEME CONFUSION MATRIX (expected -> heard, count)")
    print("=" * 70)
    for (expected, heard), count in sorted(confusion.items(), key=lambda kv: -kv[1]):
        print(f"  {expected:4} -> {heard:6}  x{count}")

    # --- 10 worst cases ---
    def severity(o):
        # False accept (error scored correct): higher percent_correct is worse.
        # False reject (correct scored error): lower percent_correct is worse.
        if o["label"] == "error" and o["predicted"] == "correct":
            return o["result"]["percent_correct"]
        if o["label"] == "correct" and o["predicted"] == "error":
            return 100 - o["result"]["percent_correct"]
        return -1  # correctly classified, not a "worst case"

    misclassified = [o for o in outcomes if o["label"] != o["predicted"]]
    worst = sorted(misclassified, key=severity, reverse=True)[:10]

    print("\n" + "=" * 70)
    print("10 WORST CASES")
    print("=" * 70)
    for o in worst:
        print(f"\n{o['target_word']} (true={o['label']}, pattern={o['pattern']}) "
              f"-> predicted={o['predicted']}, percent={o['result']['percent_correct']}")
        for r in o["result"]["results"]:
            print(f"    {r['expected']:4} status={r['status']:9} gop={r['gop']:7.3f} "
                  f"z={r['z_score']:7.3f} heard={r['heard']}")

    report = {
        "accuracy": accuracy, "far": far, "frr": frr,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "confusion_matrix": [[e, h, c] for (e, h), c in confusion.items()],
    }
    with open(EVAL_DIR / "eval_report.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"\nFull report written to {EVAL_DIR / 'eval_report.json'}")


if __name__ == "__main__":
    main()
