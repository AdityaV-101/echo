"""Production entry point for the Phase 1-5 rebuild pipeline: paired LLR +
GOP/entropy features (backend/features.py) -> frozen classifier
(backend/decision.py) -> Phase 4's usable-recording gate
(backend/recording_gate.py) -> Phase 5's two-operating-point decision.

Same score_word(...) signature as scorer.py/scorer_stub.py so main.py can
select this path the same way it already selects between those two (see
USE_PHASE3_SCORER below) - nothing else about main.py's request handling
needs to change to wire this in.

Per eval/phase3_protocol.md's modeling freeze: this module consumes the
frozen model/thresholds, it does not tune anything.

NAMING RULE (decision.py's docstring has the full derivation): a specific
substitution is only ever named when decision.decide() returns
status="wrong" (the child-facing, precision>=0.5 operating point,
T_ERROR=0.71). "unclear" is a non-naming nudge - no claim about which
sound was wrong, because at any lower threshold the claim would be wrong
most of the time it fired.
"""
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from audio_preprocess import SilentRecordingError, describe_array, describe_received, preprocess_audio
import decision
from features import compute_word_features
from gop_config import TARGET_SAMPLE_RATE
from gop_scorer import compute_log_probs, get_model
import gop_scorer as _gop_scorer_module
from recording_gate import check_recording_usable
from scorer_common import canonical_phonemes_for_word

logger = logging.getLogger("speechpal.scorer_phase3")

# Off by default (see Part 2 Step 1): persists both the raw upload and the
# converted wav, plus a JSON of everything logged for that request, under
# debug_audio/<user_id>/<timestamp>_<request_id>/ - for capturing real
# failing recordings to diagnose against, not for routine operation.
DEBUG_KEEP_AUDIO = os.environ.get("DEBUG_KEEP_AUDIO") == "1"
_DEBUG_AUDIO_DIR = Path(__file__).parent / "debug_audio"


def _persist_debug_audio(request_id: str, user_id: str, original_path: str, converted, record: dict) -> None:
    import soundfile as sf

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    out_dir = _DEBUG_AUDIO_DIR / (user_id or "unknown_user") / f"{ts}_{request_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        suffix = Path(original_path).suffix or ".bin"
        shutil.copy(original_path, out_dir / f"received{suffix}")
        if converted is not None and len(converted):
            sf.write(str(out_dir / "converted.wav"), converted, TARGET_SAMPLE_RATE)
        with open(out_dir / "record.json", "w") as f:
            json.dump(record, f, indent=1, default=str)
        logger.info("DEBUG_KEEP_AUDIO: wrote %s", out_dir)
    except OSError as e:
        logger.warning("DEBUG_KEEP_AUDIO: failed to persist %s: %s", out_dir, e)


def _generate_feedback(word: str, status: str, phoneme: str | None) -> str:
    """Per Phase 8's product rule (Prompt 1) and the naming rule above:
    "unclear" never names a sound, even though the model's raw score
    crossed some threshold to get there - only "wrong" (precision=0.500 at
    this operating point) does."""
    if status == "correct":
        return f"Nice work on \"{word}\"!"
    if status == "unclear":
        return f"Good try on \"{word}\" - let's try that one more time."
    # status == "wrong": the only status allowed to name a specific sound
    return f"So close! Let's practice the {phoneme} sound in \"{word}\"."


def score_word(
    audio_path: str,
    word: str,
    phonemes_override: list[str] | None = None,
    target_phoneme: str | None = None,
    position: str | None = None,
    user_id: str | None = None,
    accent_tolerance_enabled: bool = True,
) -> dict:
    canonical = phonemes_override if phonemes_override else canonical_phonemes_for_word(word)
    if canonical is None:
        raise ValueError(f"'{word}' is not in cmudict and no phoneme override was provided.")
    if not user_id:
        raise ValueError("user_id is required for speaker-calibrated scoring.")
    if not target_phoneme:
        raise ValueError("target_phoneme is required - this pipeline scores one designated target sound per word.")

    target_phoneme = target_phoneme.upper()
    if target_phoneme not in canonical:
        raise ValueError(f"target_phoneme {target_phoneme!r} does not appear in canonical sequence {canonical} for {word!r}.")
    target_index = canonical.index(target_phoneme)

    request_id = uuid.uuid4().hex[:12]
    received_stats = describe_received(audio_path)
    request_context = {
        "request_id": request_id, "user_id": user_id, "word": word,
        "target_phoneme": target_phoneme, "position": position, "received": received_stats,
    }

    try:
        audio = preprocess_audio(audio_path)
    except SilentRecordingError as e:
        logger.info("score_word request=%s REJECTED (SilentRecordingError) reason=%s context=%s",
                     request_id, e, json.dumps(request_context, default=str))
        if DEBUG_KEEP_AUDIO:
            _persist_debug_audio(request_id, user_id, audio_path, None,
                                  {**request_context, "rejected": True, "reject_reason": str(e)})
        raise ValueError(str(e))

    converted_stats = describe_array(audio)
    request_context["converted"] = converted_stats

    processor, model, vocab, id_to_symbol, blank_id = get_model()
    english_vocab_ids = _gop_scorer_module._ENGLISH_VOCAB_IDS
    log_probs, frame_seconds = compute_log_probs(processor, model, audio)
    word_features = compute_word_features(log_probs, canonical, vocab, blank_id, id_to_symbol, english_vocab_ids)

    gate = check_recording_usable(word_features.free_decode_gap)
    if not gate.usable:
        logger.info("scorer_phase3: recording rejected for %r: %s", word, gate.reason)
        logger.info("score_word request=%s REJECTED (recording_gate) free_decode_gap=%.4f context=%s",
                     request_id, word_features.free_decode_gap, json.dumps(request_context, default=str))
        if DEBUG_KEEP_AUDIO:
            _persist_debug_audio(request_id, user_id, audio_path, audio,
                                  {**request_context, "rejected": True, "reject_reason": gate.reason,
                                   "free_decode_gap": word_features.free_decode_gap})
        return {
            "word": word, "canonical": canonical, "target_phoneme": target_phoneme,
            "status": "unclear_recording",
            "percent_correct": None, "results": [], "worst_phoneme": None,
            "feedback": "I didn't quite hear that - can you try again a bit closer to the microphone?",
        }

    pos = word_features.positions[target_index]
    result = decision.decide(pos, word_features, user_id)
    feedback = _generate_feedback(word, result.status, target_phoneme)

    # main.py's phoneme-error-count/recommendation-card logic keys off
    # results[i]["status"] == "wrong" and db.record_attempt requires a
    # non-null integer percent_correct - both predate this scorer, kept
    # compatible rather than changed mid-migration. "wrong" here IS the
    # child-facing, precision>=0.5 threshold - not a lower-confidence flag,
    # so firing the recommendation card on it is the intended semantics.
    percent_correct = {"correct": 100, "unclear": 50, "wrong": 0}[result.status]

    explanation = result.explanation
    full_record = {
        **request_context,
        "verdict": result.status, "probability": result.probability, "heard": result.heard,
        "raw_features": explanation.raw if explanation else None,
        "scaled_features": explanation.scaled_numeric if explanation else None,
        "categorical_features": explanation.categorical if explanation else None,
        "calibration_sources": explanation.calibration_sources if explanation else None,
    }
    logger.info("score_word request=%s RESULT %s", request_id, json.dumps(full_record, default=str))
    if DEBUG_KEEP_AUDIO:
        _persist_debug_audio(request_id, user_id, audio_path, audio, full_record)

    return {
        "word": word, "canonical": canonical, "target_phoneme": target_phoneme,
        "status": result.status,  # "correct" | "unclear" | "wrong" - see decision.py's naming rule
        "probability": round(result.probability, 4),
        "heard": result.heard,  # only ever set when status == "wrong"
        "percent_correct": percent_correct,
        "results": [{
            "index": target_index, "expected": target_phoneme,
            "status": result.status, "heard": result.heard, "probability": round(result.probability, 4),
        }],
        "worst_phoneme": target_phoneme if result.status != "correct" else None,
        "feedback": feedback,
    }
