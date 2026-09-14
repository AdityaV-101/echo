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

from harness import bootstrap_ci_by_speaker, evaluate_from_rows, flatten_rows, format_overall  # noqa: E402

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


CI_METRICS = ("precision", "recall", "pr_auc", "frr", "far")


def _fmt_ci(name: str, point: float, ci: tuple[float, float]) -> str:
    return f"{name}={point:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"


def _row_key(r: dict) -> tuple:
    return (r["utt_id"], r["word_index"], r["index"])


def _coerce_unclear_to_correct(rows: list[dict]) -> list[dict]:
    """"Abstentions counted as misses": an unclear call on a true error
    becomes a miss (FN); an unclear call on a true correct is harmless
    (TN) - both are what treating "unclear" as a non-flag ("correct") for
    confusion-matrix purposes produces. Only hypothesis_lambda0 ever emits
    "unclear" - this is a no-op for the other two baselines."""
    return [dict(r, status="correct") if r["status"] == "unclear" else r for r in rows]


def _report_table(rows_by_baseline: dict[str, list[dict]], label: str, n_boot: int) -> dict:
    print(f"  --- {label} ---")
    table = {}
    for baseline_name, rows in rows_by_baseline.items():
        labeled_rows = [r for r in rows if r["label"] is not None]
        result = evaluate_from_rows(rows)
        ci = bootstrap_ci_by_speaker(labeled_rows, metric_names=CI_METRICS, n_boot=n_boot, seed=0)
        result["ci_by_speaker_95"] = {k: list(v) for k, v in ci.items()}
        table[baseline_name] = result
        print(f"  {format_overall(baseline_name, result['overall'])}")
        ci_str = "  ".join(_fmt_ci(m, result["overall"][m], ci[m]) for m in CI_METRICS)
        print(f"     95% CI (bootstrap by speaker, n_boot={n_boot}): {ci_str}")
    return table


def main(n_boot: int = 2000):
    records = load_dev_cache()
    print(f"Loaded {len(records)} dev-split words "
          f"({sum(1 for r in records if r['is_child'])} child, "
          f"{sum(1 for r in records if r['is_child'] and r['age'] <= 9)} age<=9)\n")

    report = {}
    for slice_name, slice_filter in SLICES.items():
        print(f"=== slice: {slice_name} ===")

        full_rows = {name: flatten_rows(records, fn, slice_filter=slice_filter) for name, fn in BASELINES.items()}

        # hypothesis_lambda0 is the only baseline that abstains - the
        # "common coverage" population is wherever IT has a definitive
        # call, applied identically to every baseline so the denominator
        # (70/2321 on the child slice, not 92/3016) is the same for all three.
        covered_keys = {_row_key(r) for r in full_rows["hypothesis_lambda0"] if r["status"] != "unclear"}
        common_rows = {name: [r for r in rows if _row_key(r) in covered_keys] for name, rows in full_rows.items()}

        # PR-AUC/precision/recall across different denominators is not
        # comparable - report both tables explicitly, never just one.
        common_table = _report_table(common_rows, f"common coverage subset (n={len(covered_keys)}, all 3 scorers give a definitive call)", n_boot)

        full_coerced_rows = {name: _coerce_unclear_to_correct(rows) for name, rows in full_rows.items()}
        full_table = _report_table(full_coerced_rows, "full set, abstentions counted as misses (same denominator for all 3)", n_boot)

        report[slice_name] = {"common_coverage_subset": common_table, "full_set_abstentions_as_miss": full_table}
        print()

    out_path = EVAL_DIR / "baselines.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=1)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
