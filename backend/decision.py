"""Phase 5: the operating point, deliberately abstention-heavy.

eval/phase3_protocol.md's modeling freeze (2026-09-13) found the frozen
classifier's real, usable advantage over the GOP z-score baseline
unproven on the child slice's own target phonemes (Echo-weighted
within-phoneme delta 95% CI [-0.085, +0.148] - crosses zero) - not because
the features don't work (they clearly do once there's enough data - see
the L2/all-speakers diagnostic, weighted delta +0.123 [+0.055, +0.199]),
but because there isn't enough labeled child data yet for Echo's actual
target phonemes. An unproven margin at a 2-3% base rate is exactly the
situation where the product should default to NOT naming a specific error
until the evidence is strong and corroborated across more than one
attempt - that is the correct default here, not a fallback for a model
that "should" be more confident.

Two layers:
1. Single attempt: p < T_CORRECT -> "correct"; p >= T_ERROR -> tentative
   "candidate_wrong" (strong evidence, but not yet acted on); otherwise
   "unclear" (genuinely ambiguous - practice-screen feedback stays
   encouraging and non-committal either way, per Phase 8's product rule).
2. k-of-n corroboration (backend/aggregation.py): a tentative
   "candidate_wrong" is only escalated to a CONFIRMED, named error - routed
   to the therapist review queue - once K_OF_N of the last N_WINDOW
   attempts at that phoneme are tentative "candidate_wrong". A single
   strong-evidence attempt alone never names a specific error to anyone.

T_CORRECT / T_ERROR come from eval/derive_decision_thresholds.py's
coverage-precision curve (eval/decision_thresholds.json - read off the
frozen model's already-computed out-of-fold scores, not a new sweep).
Important: the original Phase 5 rule ("lowest threshold clearing
FRR<=0.05") would pick T_ERROR=0.20 here - technically compliant
(FRR=0.0485) but right at the edge of the constraint, and it would
collapse the abstain band if T_CORRECT used the same cut. T_ERROR=0.8 is a
deliberate policy choice instead: a strong-evidence bar comfortably inside
the constraint (FRR=0.0004, precision=0.684 vs the naive cut's 0.138),
trading single-attempt recall (0.044) for k-of-n corroboration across
repeated practice attempts. T_CORRECT=0.1 keeps the abstain band wide by
design, matching the abstention-heavy default.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

import db
from aggregation import aggregate_k_of_n
from child_calibration import RELATIVE_FEATURES, speaker_relative_features, update_baselines
from features import PositionFeatures, WordFeatures

_MODEL_DIR = Path(__file__).parent / "data" / "phase3_model"
_MODEL = None
_SCALER = None
_ENCODER = None
_METADATA = None

T_CORRECT = 0.1
T_ERROR = 0.8
K_OF_N = 2
N_WINDOW = 3


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
    single_status: str  # "correct" | "candidate_wrong" | "unclear"
    probability: float
    phoneme: str
    heard: str | None
    confirmed_status: str  # "correct" | "pending_review" | "confirmed_error"
    window_size: int
    n_wrong_in_window: int


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


def classify_single_attempt(p: float) -> str:
    if p < T_CORRECT:
        return "correct"
    if p >= T_ERROR:
        return "candidate_wrong"
    return "unclear"


def decide(pos: PositionFeatures, word: WordFeatures, user_id: str) -> AttemptDecision:
    """Full Phase 5 decision for one target-phoneme attempt: single-attempt
    call, k-of-n corroboration against this user's recent history at this
    phoneme, and therapist-queue escalation on a fresh confirmation."""
    p, relative = compute_error_probability(pos, word, user_id)
    single_status = classify_single_attempt(p)
    # The specific substituted phone (if any) comes from llr_scorer's winning
    # candidate at this position, not from PositionFeatures - the caller
    # (main.py's /api/score handler) already has that candidate and attaches
    # it to the API response; this module only produces the verdict.
    heard = pos.llr_best_origin if single_status == "candidate_wrong" and pos.llr_best_origin != "canonical" else None

    # Fetch the previous window BEFORE recording this attempt, so we can
    # tell whether this attempt is what newly tips the aggregate into
    # "wrong" (queue once, on the transition) versus an already-confirmed
    # run continuing to say "wrong" (never re-queue the same confirmation).
    previous_history = db.get_recent_attempt_history(user_id, pos.expected, N_WINDOW)
    previous_agg = aggregate_k_of_n([h["status"] for h in previous_history], K_OF_N)

    db.record_attempt_history(user_id, pos.expected, single_status, p)
    update_baselines(user_id, pos.expected, _raw_relative_inputs(pos))

    history = db.get_recent_attempt_history(user_id, pos.expected, N_WINDOW)
    agg = aggregate_k_of_n([h["status"] for h in history], K_OF_N)

    confirmed_status = "correct"
    if agg.status == "wrong":
        confirmed_status = "confirmed_error"
        if previous_agg.status != "wrong":
            mean_p = sum(h["probability"] for h in history) / len(history)
            db.add_to_therapist_review_queue(user_id, pos.expected, agg.n_wrong, agg.n_total, mean_p)
    elif agg.status == "unclear":
        confirmed_status = "pending_review"

    return AttemptDecision(
        single_status=single_status, probability=p, phoneme=pos.expected, heard=heard,
        confirmed_status=confirmed_status, window_size=agg.n_total, n_wrong_in_window=agg.n_wrong,
    )
