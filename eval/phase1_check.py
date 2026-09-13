"""Phase 1 end-of-phase checkpoint (ground rule: stop and show numbers
before continuing). This is NOT the final decision procedure - Phase 2
builds real features from the LLR values and Phase 3 learns the weighting;
thresholding llr directly is exactly what Phase 2's docstring says not to
ship. This script exists only to answer one narrower question: now that the
three bugs are fixed (length normalization, best-vs-second margin, silent
zero-loss on infeasible candidates), does the simplest possible decision
rule built on top of the paired LLR - "does any alternative beat canonical
at this position at all" - already move the needle versus the old
hypothesis scorer's F1 on the honest dev-split labels from Phase 0?

Decision rule: for each position, score = max LLR among feasible
non-canonical candidates (a per-frame log-odds against canonical - positive
means some alternative explains the audio better). Predicted "wrong" iff
that max is > 0; the winning candidate's substituted phone (or None for a
deletion) is the naming guess. No abstain band yet (uncertain_margin is a
Phase 5 concern, chosen from a real sweep, not a guess here).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from harness import evaluate, format_overall  # noqa: E402

EVAL_DIR = Path(__file__).parent


def load_dev_cache() -> list[dict]:
    with open(EVAL_DIR / "phase1_raw_cache_dev.json") as f:
        return json.load(f)


def predict_phase1_naive(record: dict) -> list[dict]:
    predictions = []
    for pos in record["positions"]:
        best_llr = float("-inf")
        best_cand = None
        for cand, llr, ok in zip(pos["candidates"], pos["llrs"], pos["feasible"]):
            if cand["origin"] == "canonical" or not ok:
                continue
            if llr > best_llr:
                best_llr, best_cand = llr, cand

        if best_cand is None:
            predictions.append({"status": "correct", "score": -10.0, "heard": None})
            continue

        status = "wrong" if best_llr > 0 else "correct"
        if status == "wrong" and best_cand["origin"] != "deletion":
            heard = best_cand["sequence"][pos["index"]]
        else:
            heard = None
        predictions.append({"status": status, "score": best_llr, "heard": heard})
    return predictions


SLICES = {
    "all_speakers": None,
    "child": lambda r: r["is_child"],
    "age_le9": lambda r: r["is_child"] and r["age"] <= 9,
}


def main():
    records = load_dev_cache()
    print(f"Loaded {len(records)} dev-split words\n")

    report = {}
    for slice_name, slice_filter in SLICES.items():
        result = evaluate(records, predict_phase1_naive, slice_filter=slice_filter)
        report[slice_name] = result
        print(format_overall(f"phase1_naive ({slice_name})", result["overall"]))

    with open(EVAL_DIR / "phase1_check.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase1_check.json'}")


if __name__ == "__main__":
    main()
