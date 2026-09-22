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
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np

import db
from child_calibration import RELATIVE_FEATURES, speaker_relative_features, update_baselines
from features import PositionFeatures, WordFeatures

logger = logging.getLogger("speechpal.decision")

_MODEL_DIR = Path(__file__).parent / "data" / "phase3_model"
_MODEL = None
_SCALER = None
_ENCODER = None
_METADATA = None

T_CORRECT = 0.10
T_ERROR = 0.71  # child-facing, naming-capable threshold - precision=0.500 at this point


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def warm_up() -> None:
    """Public entry point for main.py to force the artifact-load logging to
    happen at process boot rather than lazily on the first /api/score
    request - Part 1c found the load itself was correct but silent, and a
    load silently deferred to first-request is still effectively silent for
    anyone watching boot logs to confirm the service came up cleanly."""
    _load()


def _load():
    """Loads the four frozen Phase 3 artifacts once per process. Part 1c
    (2026-09-15 diagnosis) found these load correctly but silently - nothing
    confirmed it, which is exactly how a future silent fallback to an
    untrained/default object would go unnoticed. Every load is now logged
    with its file path, a content hash, and a one-line shape summary, so a
    version mismatch or corrupted artifact is visible at boot, not inferred
    later from bad scores."""
    global _MODEL, _SCALER, _ENCODER, _METADATA
    if _MODEL is None:
        model_path = _MODEL_DIR / "model.joblib"
        scaler_path = _MODEL_DIR / "scaler.joblib"
        encoder_path = _MODEL_DIR / "encoder.joblib"
        metadata_path = _MODEL_DIR / "metadata.json"

        _MODEL = joblib.load(model_path)
        _SCALER = joblib.load(scaler_path)
        _ENCODER = joblib.load(encoder_path)
        with open(metadata_path) as f:
            _METADATA = json.load(f)

        logger.info(
            "phase3 classifier loaded: path=%s sha256=%s type=%s n_features_in_=%s classes_=%s",
            model_path, _file_hash(model_path), type(_MODEL).__name__,
            getattr(_MODEL, "n_features_in_", None), getattr(_MODEL, "classes_", None),
        )
        logger.info(
            "phase3 scaler loaded: path=%s sha256=%s n_features_in_=%s",
            scaler_path, _file_hash(scaler_path), getattr(_SCALER, "n_features_in_", None),
        )
        logger.info(
            "phase3 encoder loaded: path=%s sha256=%s category_counts=%s (order=%s)",
            encoder_path, _file_hash(encoder_path),
            [len(c) for c in _ENCODER.categories_], _METADATA.get("categorical_features"),
        )
        logger.info(
            "phase3 metadata loaded: path=%s sha256=%s frozen_date=%s n_training_rows=%s n_training_speakers=%s",
            metadata_path, _file_hash(metadata_path), _METADATA.get("frozen_date"),
            _METADATA.get("n_training_rows"), _METADATA.get("n_training_speakers"),
        )
    return _MODEL, _SCALER, _ENCODER, _METADATA


@dataclass
class AttemptDecision:
    status: str  # "correct" | "unclear" | "wrong"
    probability: float
    phoneme: str
    heard: str | None  # only ever set when status == "wrong" - the naming rule
    explanation: "FeatureExplanation | None" = None


@dataclass
class FeatureExplanation:
    """Everything Part 2 Step 1 needs logged about how one p was computed:
    the raw feature values fed in, the same numeric block after the frozen
    StandardScaler, the raw categorical values, and which calibration source
    (this speaker's own running mean vs. the global fallback, with n) backed
    each of the four speaker-relative features."""
    raw: dict[str, float] = field(default_factory=dict)
    scaled_numeric: dict[str, float] = field(default_factory=dict)
    categorical: dict[str, str] = field(default_factory=dict)
    calibration_sources: dict[str, dict] = field(default_factory=dict)


def _raw_relative_inputs(pos: PositionFeatures) -> dict[str, float]:
    return {feat: getattr(pos, feat) for feat in RELATIVE_FEATURES}


def compute_error_probability(
    pos: PositionFeatures, word: WordFeatures, user_id: str
) -> tuple[float, FeatureExplanation]:
    """Returns (P(error), FeatureExplanation) for this one target position.
    Does NOT update the child's running baseline - call update_baselines
    separately, after the verdict is recorded, so a replay/retry of the same
    attempt doesn't double-count it."""
    model, scaler, encoder, metadata = _load()
    raw_relative = _raw_relative_inputs(pos)
    relative, calibration_sources = speaker_relative_features(user_id, pos.expected, raw_relative)

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

    cat_raw_values = [
        pos.expected, pos.position, pos.llr_best_origin, pos.top_competitor if pos.top_competitor else "None",
    ]
    cat_raw = np.array([cat_raw_values])
    cat_encoded = encoder.transform(cat_raw)

    X = np.hstack([numeric_scaled, cat_encoded])
    p = float(model.predict_proba(X)[0, 1])

    explanation = FeatureExplanation(
        raw={feat: round(values[feat], 6) for feat in metadata["numeric_features"]},
        scaled_numeric={
            feat: round(float(v), 6) for feat, v in zip(metadata["numeric_features"], numeric_scaled[0])
        },
        categorical=dict(zip(metadata["categorical_features"], cat_raw_values)),
        calibration_sources=calibration_sources,
    )
    return p, explanation


def classify(p: float) -> str:
    if p < T_CORRECT:
        return "correct"
    if p >= T_ERROR:
        return "wrong"
    return "unclear"


def decide(pos: PositionFeatures, word: WordFeatures, user_id: str, target_word: str | None = None) -> AttemptDecision:
    """Single-attempt decision at the child-facing operating point. Every
    attempt (regardless of status) is recorded to attempt_history with its
    probability - that history is the therapist-queue's ranking source
    (db.get_top_k_by_probability), independent of this function's verdict.
    target_word is the literal word text (e.g. "cat") purely for the
    therapist review queue's display - it plays no part in scoring."""
    p, explanation = compute_error_probability(pos, word, user_id)
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

    db.record_attempt_history(user_id, pos.expected, status, p, word=target_word)
    update_baselines(user_id, pos.expected, _raw_relative_inputs(pos))

    if status == "wrong":
        db.add_to_therapist_review_queue(user_id, pos.expected, n_wrong=1, n_window=1, mean_probability=p, word=target_word)

    logger.info(
        "decide user_id=%s phoneme=%s verdict=%s p=%.6f heard=%s calibration_sources=%s raw=%s scaled_numeric=%s categorical=%s",
        user_id, pos.expected, status, p, heard,
        json.dumps(explanation.calibration_sources), json.dumps(explanation.raw),
        json.dumps(explanation.scaled_numeric), json.dumps(explanation.categorical),
    )

    return AttemptDecision(status=status, probability=p, phoneme=pos.expected, heard=heard, explanation=explanation)
