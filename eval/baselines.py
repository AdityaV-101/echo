"""Phase 0: run the three mandatory baselines through eval/harness.py on the
dev split and commit the result table to eval/baselines.json. Every number
here comes from eval/phase0_raw_cache_dev.json (one model pass, cached by
eval/extract_phase0_cache.py) - no new inference happens in this script.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import hypothesis_config as hcfg  # noqa: E402
from calibration import classify_z_score  # noqa: E402
from gop_config import FLOOR_SIGMA, GLOBAL_PRIOR, GLOBAL_PRIOR_DEFAULT  # noqa: E402
from hypothesis_scorer import Candidate, apply_prior_and_decide, _levenshtein_align  # noqa: E402

from harness import evaluate, format_overall  # noqa: E402

EVAL_DIR = Path(__file__).parent


def load_dev_cache() -> list[dict]:
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        return json.load(f)


# --- Baseline 1: always-say-correct ---

def predict_always_correct(record: dict) -> list[dict]:
    return [{"status": "correct", "score": 0.0, "heard": None} for _ in record["canonical"]]


# --- Baseline 2: current GOP + z-score scorer (backend/scorer.py),
# cold-start / global-prior condition - matches every previously published
# number for this scorer, which all used a fresh user_id (no calibration
# history). Accent-variant tolerance is deliberately NOT replicated here:
# it needs the actual model-vocab IPA competitor symbol, which
# phoneme_gops's top_competitor already normalizes to ARPABET (see
# gop_scorer._competitor_label) and accent_variants.json keys are raw model
# symbols - the two aren't in the same vocabulary at this cache's level of
# detail, so this baseline is (if anything) very slightly harsher than
# production. Noted, not worth a second extraction pass for a baseline
# number that's about to be replaced. ---

def predict_gop_zscore(record: dict) -> list[dict]:
    predictions = []
    for phone, pg in zip(record["canonical"], record["phoneme_gops"]):
        mean, std = GLOBAL_PRIOR.get(phone, GLOBAL_PRIOR_DEFAULT)
        std = max(std, FLOOR_SIGMA)
        z = (pg["gop"] - mean) / std
        status, _weight = classify_z_score(z)
        # borderline is not flagged as an error in production (only "wrong"
        # feeds phoneme_error / is treated as a real error) - see
        # backend/main.py's score endpoint.
        predicted_status = "wrong" if status == "wrong" else "correct"
        predictions.append({
            "status": predicted_status,
            "score": -z,  # more negative z (worse GOP) -> higher error score
            "heard": pg["top_competitor"] if predicted_status == "wrong" else None,
        })
    return predictions


# --- Baseline 3: current hypothesis-rescoring scorer
# (backend/hypothesis_scorer.py), LAMBDA=0 / UNCERTAIN_MARGIN=0.15 (current
# hypothesis_config.py defaults - the values that produced the F1=0.329
# number this rebuild is measured against). ---

def predict_hypothesis(record: dict) -> list[dict]:
    candidates = [Candidate(**c) for c in record["candidates"]]
    canonical = record["canonical"]
    decision = apply_prior_and_decide(
        candidates, record["raw_scores"], user_id=None,
        lambda_=hcfg.LAMBDA, uncertain_margin=hcfg.UNCERTAIN_MARGIN,
    )
    word_status = decision["word_status"]
    margin = decision["margin"]

    if word_status == "unclear":
        return [{"status": "unclear", "score": -margin, "heard": None} for _ in canonical]

    if decision["is_canonical_winner"]:
        # Word-level "correct" - no localized evidence of which position (if
        # any) is most error-like, so every position gets the same
        # word-level score. Documented limitation: PR-AUC for this scorer is
        # therefore word-level discrimination broadcast onto phoneme
        # positions, not a true per-phoneme continuous score - this scorer's
        # decision procedure is word-level by design (see its module
        # docstring), so this is what "the score it actually produces" is.
        return [{"status": "correct", "score": -margin, "heard": None} for _ in canonical]

    winner = decision["winner"]
    alignment = _levenshtein_align(canonical, winner.sequence)
    predictions = []
    for op, heard in alignment:
        status = "correct" if op == "match" else "wrong"
        # heard=None for a "del" op is the correct signal for a predicted
        # deletion (see harness._ground_truth_substitution's "deleted" case).
        predictions.append({"status": status, "score": margin if status == "wrong" else -margin, "heard": heard})
    return predictions


SLICES = {
    "all_speakers": None,
    "child": lambda r: r["is_child"],
    "age_le9": lambda r: r["is_child"] and r["age"] <= 9,
}

BASELINES = {
    "always_correct": predict_always_correct,
    "gop_zscore": predict_gop_zscore,
    "hypothesis_lambda0": predict_hypothesis,
}


def main():
    records = load_dev_cache()
    print(f"Loaded {len(records)} dev-split words "
          f"({sum(1 for r in records if r['is_child'])} child, "
          f"{sum(1 for r in records if r['is_child'] and r['age'] <= 9)} age<=9)\n")

    report = {}
    for slice_name, slice_filter in SLICES.items():
        print(f"=== slice: {slice_name} ===")
        report[slice_name] = {}
        for baseline_name, predict_fn in BASELINES.items():
            result = evaluate(records, predict_fn, slice_filter=slice_filter)
            report[slice_name][baseline_name] = result
            print(format_overall(baseline_name, result["overall"]))
        print()

    out_path = EVAL_DIR / "baselines.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=1)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
