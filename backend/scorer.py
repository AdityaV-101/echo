"""Real phoneme scorer: forced alignment + Goodness of Pronunciation (GOP),
calibrated per-speaker. See DIAGNOSIS.md for what was wrong with the
previous (free-recognition + guessed-window) approach, and the "Forced
alignment + GOP rebuild" section of SETUP_NOTES.md for the full design.

Pipeline, per request:
1. audio_preprocess.preprocess_audio - decode, peak-normalize, trim
   silence, pad if short, reject if silent.
2. gop_scorer.score_phonemes - frame log-probs, forced-align the known
   canonical sequence, per-phoneme GOP + top competitors.
3. calibration - z-score each phoneme's GOP against this speaker's own
   running baseline (falling back to a global prior for a new speaker),
   classify correct/borderline/wrong, and fold correct/accent_variant
   results back into that speaker's baseline for next time.
4. accent variant tolerance - a "wrong" phoneme whose top competitor is a
   documented accent variant of the target is downgraded to
   accent_variant and counted as correct.
5. percent_correct + feedback text.

Same function signature as scorer_stub.py's score_word so main.py can
switch between them with the USE_REAL_SCORER env var.
"""
import logging

import calibration
from audio_preprocess import SilentRecordingError, preprocess_audio
from gop_scorer import PhonemeResult, score_phonemes
from scorer_common import canonical_phonemes_for_word

logger = logging.getLogger("speechpal.scorer")


def _classify_phoneme(user_id: str, phoneme: PhonemeResult, accent_tolerance_enabled: bool) -> dict:
    z, mean_used, std_used, n_speaker_samples = calibration.compute_z_score(phoneme.gop, user_id, phoneme.expected)
    status, weight = calibration.classify_z_score(z)

    accent_variant_of = None
    if status == "wrong" and accent_tolerance_enabled:
        variants = calibration.get_accent_variants().get(phoneme.expected, [])
        if phoneme.top_competitor in variants:
            status, weight = "accent_variant", 1.0
            accent_variant_of = phoneme.top_competitor

    if status in ("correct", "accent_variant"):
        calibration.update_speaker_baseline(user_id, phoneme.expected, phoneme.gop)

    return {
        "index": phoneme.index,
        "expected": phoneme.expected,
        "status": status,
        "weight": weight,
        "heard": phoneme.top_competitor if status != "correct" else None,
        "accent_variant_of": accent_variant_of,
        "gop": round(phoneme.gop, 4),
        "z_score": round(z, 3),
        "baseline_mean": round(mean_used, 4),
        "baseline_std": round(std_used, 4),
        "baseline_n": n_speaker_samples,
        "start_ms": round(phoneme.start_ms, 1),
        "end_ms": round(phoneme.end_ms, 1),
        "competitors": [[label, round(p, 4)] for label, p in phoneme.competitors],
    }


def _pick_worst(results: list[dict], target_phoneme: str | None) -> dict | None:
    """The phoneme feedback should center on: the target phoneme's own
    result if the target isn't correct (that's what the word is actually
    screening for), otherwise the single lowest-weight result anywhere in
    the word, if any."""
    if target_phoneme:
        target_hits = [r for r in results if r["expected"] == target_phoneme.upper() and r["status"] != "correct"]
        if target_hits:
            return min(target_hits, key=lambda r: r["weight"])
    non_correct = [r for r in results if r["status"] != "correct"]
    if not non_correct:
        return None
    return min(non_correct, key=lambda r: r["weight"])


def _generate_feedback(word: str, percent_correct: int, worst: dict | None) -> str:
    if percent_correct == 100:
        return f"Perfect! You said \"{word}\" exactly right."
    if worst is None:
        return f"Nice try on \"{word}\"! Keep practicing."
    phoneme = worst["expected"]
    if worst["status"] == "accent_variant":
        return f"The {phoneme} sound was a little different, but that's just a normal accent variation, not an error."
    heard = worst["heard"]
    if worst["status"] == "borderline":
        if heard:
            return f"So close! The {phoneme} sound was borderline - it leaned toward {heard}. Try it once more."
        return f"So close! The {phoneme} sound was borderline. Try it once more."
    if heard:
        return f"Almost! The {phoneme} sound came out like {heard}. Let's practice {phoneme}."
    return f"Good try! The {phoneme} sound needs some work. Let's practice {phoneme}."


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

    try:
        audio = preprocess_audio(audio_path)
    except SilentRecordingError as e:
        raise ValueError(str(e))

    phoneme_gops = score_phonemes(canonical, audio)
    results = [_classify_phoneme(user_id, p, accent_tolerance_enabled) for p in phoneme_gops]

    percent_correct = round(100 * sum(r["weight"] for r in results) / len(results))
    worst = _pick_worst(results, target_phoneme)
    worst_phoneme = worst["expected"] if worst else None
    feedback = _generate_feedback(word, percent_correct, worst)

    return {
        "word": word,
        "percent_correct": percent_correct,
        "canonical": canonical,
        "results": results,
        "worst_phoneme": worst_phoneme,
        "feedback": feedback,
        "target_phoneme": target_phoneme,
    }
