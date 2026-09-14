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
import logging

from audio_preprocess import SilentRecordingError, preprocess_audio
import decision
from features import compute_word_features
from gop_scorer import compute_log_probs, get_model
import gop_scorer as _gop_scorer_module
from recording_gate import check_recording_usable
from scorer_common import canonical_phonemes_for_word

logger = logging.getLogger("speechpal.scorer_phase3")


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

    try:
        audio = preprocess_audio(audio_path)
    except SilentRecordingError as e:
        raise ValueError(str(e))

    processor, model, vocab, id_to_symbol, blank_id = get_model()
    english_vocab_ids = _gop_scorer_module._ENGLISH_VOCAB_IDS
    log_probs, frame_seconds = compute_log_probs(processor, model, audio)
    word_features = compute_word_features(log_probs, canonical, vocab, blank_id, id_to_symbol, english_vocab_ids)

    gate = check_recording_usable(word_features.free_decode_gap)
    if not gate.usable:
        logger.info("scorer_phase3: recording rejected for %r: %s", word, gate.reason)
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
