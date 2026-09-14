"""Phase 5: two operating points for two consumers, replacing the
FRR<=0.05 selection rule (wrong at this base rate - it produced a point
with 13.8% precision and 0% abstention, not usable as a child-facing
decision) and the k-of-n corroboration layer (eval/phase5_joint_sweep.py
and eval/phase5_two_points.py both found no k-of-n configuration beats
plain single-attempt thresholding at any operating point tested - a direct
consequence of the dispersion diagnostic in RESULTS.md: false alarms are
speaker-systematic, not independent, so requiring repeat crossings doesn't
isolate signal the way k-of-n's independence assumption needs).

1. CHILD-FACING point (T_ERROR, naming-capable): precision>=0.5 is a HARD
   constraint on the child slice, then maximize recall subject to it.
   Measured (eval/phase5_two_points.py, single-attempt is the only
   configuration that clears the floor at all - every k-of-n config
   tested tops out below 0.5 precision regardless of threshold):
   T_ERROR=0.71, recall=0.061, precision=0.500, FRR=0.0011. This is far
   more conservative than a first guess based on a misread FRR (the
   2-of-4 point in RESULTS.md's superseded table has precision=0.200, not
   >=0.5 - checked directly, not assumed).
2. THERAPIST-QUEUE point (no precision floor): every attempt's calibrated
   probability is retained (backend/db.py's attempt_history); the queue is
   a ranking query, not a fixed threshold - see db.get_top_k_by_probability
   and RESULTS.md's recall/precision-at-top-K table. This is where the
   higher-recall, lower-precision behavior belongs.

NAMING RULE: a specific substitution/process is only ever named to the
child when p >= T_ERROR (the child-facing point). Below that but at or
above T_CORRECT, the response is a non-naming nudge ("let's try that one
more time") - no claim about which sound was wrong. Naming a substitution
that's wrong most of the time it fires teaches the wrong thing; at the
therapist-queue point's ~13.8-56% precision (depending on K), that's
exactly what would happen if it were child-facing.

T_CORRECT=0.10 sets the abstain band's lower edge - a policy choice (UX,
not a safety measurement), giving a measured 13.2% abstain rate (attempts
in [0.10, 0.71)) on the child dev population. An abstain rate of 0%, which
the previous FRR-budget point produced, is a design failure, not
efficiency - every attempt resolving immediately means no room for "I'm
not sure yet."
"""
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

import db
from child_calibration import RELATIVE_FEATURES, speaker_relative_features, update_baselines
from features import PositionFeatures, WordFeatures

_MODEL_DIR = Path(__file__).parent / "data" / "phase3_model"
_MODEL = None
_SCALER = None
_ENCODER = None
_METADATA = None

T_CORRECT = 0.10
T_ERROR = 0.71  # child-facing, naming-capable threshold - precision=0.500 at this point


def _load():
    global _MODEL, _SCALER, _ENCODER, _METADATA
    if _MODEL is None:
        _MODEL = joblib.load(_MODEL_DIR / "model.joblib")
        _SCALER = joblib.load(_MODEL_DIR / "scaler.joblib")
        _ENCODER = joblib.load(_MODEL_DIR / "encoder.joblib")
        with open(_MODEL_DIR / "metadata.json") as f:
            _METADATA = json.load(f)
    return _MODEL, _SCALER, _ENCODER, _METADATA


@dataclass
class AttemptDecision:
    status: str  # "correct" | "unclear" | "wrong"
    probability: float
    phoneme: str
    heard: str | None  # only ever set when status == "wrong" - the naming rule


def _raw_relative_inputs(pos: PositionFeatures) -> dict[str, float]:
    return {feat: getattr(pos, feat) for feat in RELATIVE_FEATURES}


def compute_error_probability(pos: PositionFeatures, word: WordFeatures, user_id: str) -> tuple[float, dict]:
    """Returns (P(error), speaker_relative_features_used) for this one
    target position. Does NOT update the child's running baseline - call
    update_baselines separately, after the verdict is recorded, so a
    replay/retry of the same attempt doesn't double-count it."""
    model, scaler, encoder, metadata = _load()
    raw_relative = _raw_relative_inputs(pos)
    relative = speaker_relative_features(user_id, pos.expected, raw_relative)

    MISSING_SENTINEL = -5.0
    values = {
        "llr_best": pos.llr_best, "llr_margin": pos.llr_margin,
        "gop_i": pos.gop_i, "gop_lpr_i": pos.gop_lpr_i,
        "dur_z": pos.dur_z, "entropy": pos.entropy,
        "ll_canonical_per_frame": word.ll_canonical_per_frame, "free_decode_gap": word.free_decode_gap,
        "syllable_count": pos.syllable_count, "frame_count_word": pos.frame_count_word,
        "llr_deletion": pos.llr_deletion if pos.llr_deletion is not None else MISSING_SENTINEL,
        "llr_second_best": pos.llr_second_best if pos.llr_second_best is not None else MISSING_SENTINEL,
        "has_deletion_candidate": 1.0 if pos.llr_deletion is not None else 0.0,
        "has_second_best_candidate": 1.0 if pos.llr_second_best is not None else 0.0,
        **relative,
    }
    numeric_vec = np.array([[values[feat] for feat in metadata["numeric_features"]]])
    numeric_scaled = scaler.transform(numeric_vec)

    cat_raw = np.array([[
        pos.expected, pos.position, pos.llr_best_origin, pos.top_competitor if pos.top_competitor else "None",
    ]])
    cat_encoded = encoder.transform(cat_raw)

    X = np.hstack([numeric_scaled, cat_encoded])
    p = float(model.predict_proba(X)[0, 1])
    return p, relative


def classify(p: float) -> str:
    if p < T_CORRECT:
        return "correct"
    if p >= T_ERROR:
        return "wrong"
    return "unclear"


def decide(pos: PositionFeatures, word: WordFeatures, user_id: str) -> AttemptDecision:
    """Single-attempt decision at the child-facing operating point. Every
    attempt (regardless of status) is recorded to attempt_history with its
    probability - that history is the therapist-queue's ranking source
    (db.get_top_k_by_probability), independent of this function's verdict."""
    p, relative = compute_error_probability(pos, word, user_id)
    status = classify(p)
    # Naming rule: heard is only ever populated for "wrong" - never for
    # "unclear", which must stay a non-naming nudge.
    #
    # BUG FIX (found while building eval/run_test_eval.py for the overnight
    # run's Part 1): this used to be
    #   heard = pos.llr_best_origin if status == "wrong" and pos.llr_best_origin != "canonical" else None
    # but llr_best_origin is a CATEGORY - "canonical", a phonological-
    # process name ("stopping"/"fronting"/etc, see llr_scorer.py's
    # _substitutions_for), or "deletion" - never an ARPABET phoneme. It can
    # never equal a ground-truth pronounced_phone, so substitution_naming_
    # accuracy was measuring something that was structurally ~0% by
    # construction, not a real result - see RESULTS.md. top_competitor
    # (features.py's _gop_and_lpr: "the single most plausible alternative
    # reading of this span") is the field that actually names a phoneme.
    if status != "wrong" or pos.llr_best_origin == "canonical":
        heard = None  # no naming: either not "wrong", or no local alternative-candidate evidence
    elif pos.llr_best_origin == "deletion":
        heard = None  # predicted an omission, not a specific substitution
    else:
        heard = pos.top_competitor

    db.record_attempt_history(user_id, pos.expected, status, p)
    update_baselines(user_id, pos.expected, _raw_relative_inputs(pos))

    if status == "wrong":
        db.add_to_therapist_review_queue(user_id, pos.expected, n_wrong=1, n_window=1, mean_probability=p)

    return AttemptDecision(status=status, probability=p, phoneme=pos.expected, heard=heard)
