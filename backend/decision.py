"""Phase 5: the operating point, corrected to a joint sweep.

eval/phase5_joint_sweep.py fixed two problems with the first version of
this module:

1. The FRR<=0.05 budget must apply to the AGGREGATED (what a child/
   therapist actually sees) decision, not the single attempt - a single
   attempt no longer names anything on its own, so its own FRR isn't the
   user-facing quantity.
2. (T_ERROR, k-of-n) must be swept JOINTLY, not stacked (pick T_ERROR from
   a single-attempt curve, then bolt k-of-n on top).

The joint sweep's answer is not what was expected going in: the point that
maximizes AGGREGATED recall subject to AGGREGATED FRR<=0.05 is **k=1, n=1
(no corroboration at all), T_ERROR=0.20** - not a looser T_ERROR with
2-of-3 or 3-of-4 doing the work. Every k-of-n configuration tested (2-of-3,
3-of-4, 2-of-4, 3-of-5) has LOWER recall at FRR<=0.05 than plain
single-attempt thresholding, and the previous stacked setting
(T_ERROR=0.80, 2-of-3) has recall=0.000 on the 11 available positive
windows - it was catching nothing. This is not noise: it's the direct,
predicted consequence of eval/phase3_multicollinearity.py's ... no, of
RESULTS.md's dispersion diagnostic (X^2/df=4.31 on GOP z-score's false
alarms) - false alarms are speaker-systematic, so requiring the SAME
speaker to cross threshold multiple times doesn't discriminate signal
from that speaker's persistent tendency the way independence would
predict; if anything it rewards speakers who are consistently over- or
under-flagged rather than washing that out.

Bug fixed while rebuilding this: classify_single_attempt previously
returned "candidate_wrong", which backend/aggregation.py's
aggregate_k_of_n never matches (it counts the literal string "wrong") -
the k-of-n layer was silently a no-op in the first version of this module.
Fixed by using "wrong" as the stored/compared value; moot for the k=1,n=1
operating point (aggregation is bypassed either way) but real for anyone
using aggregation.py directly at k>1.

T_ERROR=0.20, T_CORRECT=0.10: at T_ERROR=0.20, aggregated (=single-attempt,
since n=1) FRR=0.0485, recall=0.427, precision=0.138 (measured on pooled
child speakers' out-of-fold scores - eval/phase5_joint_sweep.json).
T_CORRECT is a UX-only cut below T_ERROR (doesn't affect the measured
safety numbers, which depend only on the T_ERROR cut) - kept low so most
attempts read as confidently "correct" rather than "unclear", consistent
with the low base rate.

Precision at this point (13.8%) is low - most flags are false alarms, an
unavoidable consequence of a ~1.8% base rate (see RESULTS.md's precision-
ceiling section), not a defect of this operating point specifically. What
FRR<=0.05 guarantees is that a truly-correct child is rarely told they're
wrong (<5% of the time) - it does not guarantee that a flag, when it
fires, is usually right. A k=2,n=4 alternative (T=0.35: recall=0.263,
FRR=0.006, comfortably under budget) is available in
eval/phase5_joint_sweep.json for anyone who wants SOME corroboration
before ever queuing a case, at a real recall cost - not used as the
default here because the explicit selection rule (max recall subject to
the FRR budget) does not choose it, but recorded because reasonable people
could prefer it for the "never act on one attempt" property k=1,n=1 gives
up.
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

T_CORRECT = 0.10
T_ERROR = 0.20
K_OF_N = 1
N_WINDOW = 1


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
    single_status: str  # "correct" | "wrong" | "unclear"
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
        return "wrong"
    return "unclear"


def decide(pos: PositionFeatures, word: WordFeatures, user_id: str) -> AttemptDecision:
    """Full Phase 5 decision for one target-phoneme attempt: single-attempt
    call, k-of-n corroboration against this user's recent history at this
    phoneme (a no-op at the current K_OF_N=1/N_WINDOW=1 operating point -
    see module docstring for why - but left in place, correctly wired
    against aggregation.py's actual vocabulary, for anyone who switches to
    a k>1 configuration), and therapist-queue escalation on a fresh
    confirmation."""
    p, relative = compute_error_probability(pos, word, user_id)
    single_status = classify_single_attempt(p)
    # The specific substituted phone (if any) comes from llr_scorer's winning
    # candidate at this position, not from PositionFeatures - the caller
    # (main.py's /api/score handler) already has that candidate and attaches
    # it to the API response; this module only produces the verdict.
    heard = pos.llr_best_origin if single_status == "wrong" and pos.llr_best_origin != "canonical" else None

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
