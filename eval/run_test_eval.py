"""Overnight run, Part 1 step 1: runs the held-out speechocean762 TEST split
ONCE through the exact production pipeline - backend/recording_gate.py's
usable-recording gate, then the frozen Phase 3 classifier
(backend/data/phase3_model/, loaded exactly as backend/decision.py loads
it) at the shipped thresholds (T_CORRECT=0.10, T_ERROR=0.71). This split
has not been touched by any prior phase (no tuning, no threshold search,
no feature selection was ever run against it) - see eval/phase3_protocol.md's
modeling freeze.

Feature values come from eval/phase2_features_test.json (the same offline,
per-speaker Welford relative-feature computation used for every other split
in this project - a fresh accumulator per test speaker, no leakage from
subtrain/dev), not from backend/child_calibration.py's live per-user db,
since there is no live app session for speechocean762 utterances. This is
the same convention eval/phase3_common.py and every dev-split number in
RESULTS.md already uses.

Reports FRR/precision/recall/PR-AUC/abstain rate/naming accuracy/expected
false corrections per 10-word session for three slices (all speakers,
child, age<=9), plus a per-phoneme breakdown (harness.py's own by_phoneme
accumulation - a within-phoneme table of this single frozen scorer's
results, not a repeat of Phase 3's phoneme-identity-control methodology,
which was already answered on dev data)."""
import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from recording_gate import check_recording_usable  # noqa: E402
from harness import bootstrap_ci_by_speaker, evaluate_from_rows, flatten_rows, format_overall  # noqa: E402

EVAL_DIR = Path(__file__).parent
MODEL_DIR = Path(__file__).parent.parent / "backend" / "data" / "phase3_model"
T_CORRECT = 0.10
T_ERROR = 0.71
MISSING_SENTINEL = -5.0


def load_frozen_model():
    model = joblib.load(MODEL_DIR / "model.joblib")
    scaler = joblib.load(MODEL_DIR / "scaler.joblib")
    encoder = joblib.load(MODEL_DIR / "encoder.joblib")
    with open(MODEL_DIR / "metadata.json") as f:
        metadata = json.load(f)
    return model, scaler, encoder, metadata


def classify(p: float) -> str:
    if p < T_CORRECT:
        return "correct"
    if p >= T_ERROR:
        return "wrong"
    return "unclear"


def numeric_value(row: dict, feat: str) -> float:
    if feat == "llr_deletion":
        return row["llr_deletion"] if row["llr_deletion"] is not None else MISSING_SENTINEL
    if feat == "llr_second_best":
        return row["llr_second_best"] if row["llr_second_best"] is not None else MISSING_SENTINEL
    if feat == "has_deletion_candidate":
        return 1.0 if row["llr_deletion"] is not None else 0.0
    if feat == "has_second_best_candidate":
        return 1.0 if row["llr_second_best"] is not None else 0.0
    return row[feat]


def expected_false_per_10(overall: dict) -> float:
    prevalence = overall["base_rate"]
    frr = overall["frr"]
    if prevalence != prevalence or frr != frr:
        return float("nan")
    return 10 * (1 - prevalence) * frr


def main():
    with open(EVAL_DIR / "features_raw_cache_test.json") as f:
        raw_records = json.load(f)
    with open(EVAL_DIR / "phase2_features_test.json") as f:
        phase2_rows = json.load(f)

    model, scaler, encoder, metadata = load_frozen_model()
    numeric_features = metadata["numeric_features"]
    categorical_features = metadata["categorical_features"]
    row_by_key = {(r["utt_id"], r["word_index"], r["index"]): r for r in phase2_rows}

    gate_passed, gate_rejected = [], []
    for r in raw_records:
        gap = r["word_features"]["free_decode_gap"]
        (gate_passed if check_recording_usable(gap).usable else gate_rejected).append(r)

    print(f"recording gate: {len(gate_rejected)}/{len(raw_records)} words rejected as "
          f"unclear_recording ({len(gate_rejected) / len(raw_records):.1%})\n")

    def predict_fn(record):
        preds = []
        for i, _phone in enumerate(record["canonical"]):
            row = row_by_key[(record["utt_id"], record["word_index"], i)]
            numeric_vec = np.array([[numeric_value(row, f) for f in numeric_features]])
            numeric_scaled = scaler.transform(numeric_vec)
            cat_raw = np.array([[str(row[f]) for f in categorical_features]])
            cat_encoded = encoder.transform(cat_raw)
            X = np.hstack([numeric_scaled, cat_encoded])
            p = float(model.predict_proba(X)[0, 1])
            status = classify(p)
            # Mirrors backend/decision.py's (bug-fixed) naming rule exactly:
            # top_competitor is the ARPABET label of the model's best
            # alternative reading of this span - llr_best_origin is a
            # category (canonical/process-name/deletion), never a phoneme.
            if status != "wrong" or row["llr_best_origin"] == "canonical":
                heard = None
            elif row["llr_best_origin"] == "deletion":
                heard = None
            else:
                heard = row["top_competitor"]
            preds.append({"status": status, "score": p, "heard": heard})
        return preds

    def report_slice(name, records, slice_filter=None):
        rows = flatten_rows(records, predict_fn, slice_filter)
        result = evaluate_from_rows(rows)
        overall = result["overall"]
        ci = bootstrap_ci_by_speaker(
            rows, metric_names=("precision", "recall", "pr_auc", "frr", "far", "f1", "substitution_naming_accuracy"),
        )
        efp10 = expected_false_per_10(overall)
        print(format_overall(name, overall))
        print(f"  95% CI: precision={ci['precision']} recall={ci['recall']} frr={ci['frr']} pr_auc={ci['pr_auc']}")
        print(f"  naming accuracy 95% CI: {ci['substitution_naming_accuracy']}")
        print(f"  expected false corrections per 10-word session: {efp10:.4f}\n")
        return {
            "n_speakers": len({row["speaker"] for row in rows}),
            "metrics": overall,
            "ci_95": {k: list(v) for k, v in ci.items()},
            "expected_false_per_10": efp10,
            "by_phoneme": result["by_phoneme"],
        }

    out = {
        "t_correct": T_CORRECT, "t_error": T_ERROR,
        "recording_gate": {
            "n_total_words": len(raw_records),
            "n_rejected": len(gate_rejected),
            "rejection_rate": len(gate_rejected) / len(raw_records),
        },
    }
    out["all_speakers"] = report_slice("ALL SPEAKERS (test, gate-passed)", gate_passed)
    out["child"] = report_slice("CHILD (test, gate-passed)", gate_passed, lambda r: r["is_child"])
    out["age_le_9"] = report_slice(
        "AGE<=9 (test, gate-passed)", gate_passed,
        lambda r: r["is_child"] and r["age"] is not None and r["age"] <= 9,
    )

    out_path = EVAL_DIR / "test_eval_final.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
