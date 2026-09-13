"""Step 8 (eval harness), part 2: derive the global per-phoneme GOP prior
from the synthetic corpus's "correct" recordings, then sweep
Z_CORRECT_THRESHOLD / Z_WRONG_THRESHOLD to find the operating point that
best separates "correct" from "error" recordings. Prints the values to put
in gop_config.py - it does not edit that file itself, since these are
meant-to-be-reviewed calibration constants, not something to silently
overwrite on every run.
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from _shared import extract_raw_gop  # noqa: E402
from gop_config import FLOOR_SIGMA  # noqa: E402


def derive_global_prior(raw_data: list[dict]) -> dict[str, tuple[float, float]]:
    """Mean/std GOP per phoneme, from every occurrence of that phoneme in
    every "correct"-labeled recording (not "error" ones - the prior
    describes what a correct production looks like)."""
    by_phoneme: dict[str, list[float]] = {}
    for entry in raw_data:
        if entry["label"] != "correct":
            continue
        for p in entry["phonemes"]:
            by_phoneme.setdefault(p["expected"], []).append(p["gop"])

    prior = {}
    for phoneme, values in by_phoneme.items():
        mean = statistics.mean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        prior[phoneme] = (mean, max(std, FLOOR_SIGMA))
    return prior


def word_prediction(entry: dict, prior: dict[str, tuple[float, float]], z_wrong: float) -> str:
    """"error" if any phoneme's z-score falls at/below z_wrong, else "correct"."""
    for p in entry["phonemes"]:
        mean, std = prior.get(p["expected"], (-0.6, FLOOR_SIGMA))
        std = max(std, FLOOR_SIGMA)
        z = (p["gop"] - mean) / std
        if z <= z_wrong:
            return "error"
    return "correct"


def evaluate(raw_data: list[dict], prior: dict[str, tuple[float, float]], z_wrong: float) -> dict:
    tp = fp = tn = fn = 0  # "error" is the positive class
    for entry in raw_data:
        predicted = word_prediction(entry, prior, z_wrong)
        true = entry["label"]
        if true == "error" and predicted == "error":
            tp += 1
        elif true == "correct" and predicted == "error":
            fp += 1  # false reject (correct flagged as error)
        elif true == "correct" and predicted == "correct":
            tn += 1
        else:
            fn += 1  # false accept (error flagged as correct)
    n = tp + fp + tn + fn
    accuracy = (tp + tn) / n if n else 0.0
    far = fn / (tp + fn) if (tp + fn) else 0.0  # of true errors, fraction missed (accepted)
    frr = fp / (fp + tn) if (fp + tn) else 0.0  # of true corrects, fraction wrongly rejected
    return {"accuracy": accuracy, "far": far, "frr": frr, "tp": tp, "fp": fp, "tn": tn, "fn": fn}


def main():
    raw_data = extract_raw_gop()
    prior = derive_global_prior(raw_data)

    print("\n=== Derived global per-phoneme prior (from 'correct' recordings) ===")
    for phoneme in sorted(prior):
        mean, std = prior[phoneme]
        n = sum(1 for e in raw_data if e["label"] == "correct" for p in e["phonemes"] if p["expected"] == phoneme)
        print(f"  {phoneme:4} mean={mean:7.3f}  std={std:6.3f}  n={n}")

    print("\n=== Sweeping Z_WRONG_THRESHOLD ===")
    candidates = [-3.5, -3.0, -2.5, -2.0, -1.75, -1.5, -1.25, -1.0, -0.75, -0.5]
    best = None
    for z_wrong in candidates:
        result = evaluate(raw_data, prior, z_wrong)
        print(
            f"  z_wrong={z_wrong:+.2f}  accuracy={result['accuracy']:.3f}  "
            f"FAR(missed errors)={result['far']:.3f}  FRR(false-flagged correct)={result['frr']:.3f}  "
            f"[tp={result['tp']} fp={result['fp']} tn={result['tn']} fn={result['fn']}]"
        )
        # Prefer higher accuracy; break ties by lower FAR (missing a real
        # articulation error matters more in a therapy context than being
        # slightly over-cautious).
        key = (result["accuracy"], -result["far"])
        if best is None or key > best[0]:
            best = (key, z_wrong, result)

    _, best_z_wrong, best_result = best
    print(f"\n=== Best operating point: Z_WRONG_THRESHOLD = {best_z_wrong} ===")
    print(f"    accuracy={best_result['accuracy']:.3f} FAR={best_result['far']:.3f} FRR={best_result['frr']:.3f}")
    print("\nZ_CORRECT_THRESHOLD is kept above Z_WRONG_THRESHOLD to leave a borderline band;")
    print(f"recommended: Z_CORRECT_THRESHOLD = {best_z_wrong / 2:.2f} (midpoint toward 0), Z_WRONG_THRESHOLD = {best_z_wrong}")
    print("\nCopy GLOBAL_PRIOR and these two thresholds into backend/gop_config.py.")

    print("\n=== GLOBAL_PRIOR as a Python dict literal ===")
    print("GLOBAL_PRIOR: dict[str, tuple[float, float]] = {")
    for phoneme in sorted(prior):
        mean, std = prior[phoneme]
        print(f'    "{phoneme}": ({mean:.4f}, {std:.4f}),')
    print("}")


if __name__ == "__main__":
    main()
