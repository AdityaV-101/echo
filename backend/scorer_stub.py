"""Stub phoneme scorer: returns realistic-looking fake results without
touching the audio at all, in the exact response shape the real
forced-alignment + GOP scorer (scorer.py) produces, so the UI can be built
and tested without loading the real model. Same function signature as
scorer.py's score_word so main.py can swap between them with the
USE_REAL_SCORER env var and nothing else changes.
"""
import random

from scorer_common import canonical_phonemes_for_word

# A handful of plausible child-speech substitutions, used only to make the
# stub's fake "heard" phoneme look like a real articulation error instead
# of arbitrary noise. Not used by the real scorer - see accent_variants.json
# and gop_scorer.py for the real system's equivalents.
_CONFUSION_MAP = {
    "R": ["W", "L"], "L": ["W", "Y"], "S": ["TH", "T"], "Z": ["D", "TH"],
    "TH": ["F", "T", "S"], "DH": ["D", "V"], "SH": ["S", "CH"], "CH": ["T", "SH"],
    "JH": ["D", "Y"], "K": ["T"], "G": ["D"], "V": ["B", "F"], "F": ["P"], "NG": ["N"],
}
_ALL_ARPABET = [
    "AA", "AE", "AH", "AO", "AW", "AY", "B", "CH", "D", "DH", "EH", "ER",
    "EY", "F", "G", "HH", "IH", "IY", "JH", "K", "L", "M", "N", "NG", "OW",
    "OY", "P", "R", "S", "SH", "T", "TH", "UH", "UW", "V", "W", "Y", "Z", "ZH",
]


def _fake_competitor(expected: str) -> str:
    options = _CONFUSION_MAP.get(expected)
    if options:
        return random.choice(options)
    return random.choice([p for p in _ALL_ARPABET if p != expected])


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

    results = []
    for i, expected in enumerate(canonical):
        roll = random.random()
        start_ms = i * 90.0
        end_ms = start_ms + 80.0
        if roll < 0.72:
            status, weight, gop, z, heard, accent_of = "correct", 1.0, round(random.uniform(-0.3, -0.02), 4), round(random.uniform(-0.8, 0.5), 3), None, None
        elif roll < 0.82:
            status, weight, gop, z = "borderline", 0.5, round(random.uniform(-0.9, -0.5), 4), round(random.uniform(-1.9, -1.1), 3)
            heard, accent_of = _fake_competitor(expected), None
        elif roll < 0.88:
            status, weight, gop, z = "accent_variant", 1.0, round(random.uniform(-1.2, -0.6), 4), round(random.uniform(-2.5, -1.8), 3)
            heard = accent_of = _fake_competitor(expected)
        else:
            status, weight, gop, z = "wrong", 0.0, round(random.uniform(-2.2, -1.0), 4), round(random.uniform(-3.5, -2.0), 3)
            heard, accent_of = _fake_competitor(expected), None

        competitors = [[heard or _fake_competitor(expected), round(random.uniform(0.2, 0.6), 4)]]
        for _ in range(2):
            competitors.append([_fake_competitor(expected), round(random.uniform(0.02, 0.15), 4)])

        results.append({
            "index": i,
            "expected": expected,
            "status": status,
            "weight": weight,
            "heard": heard,
            "accent_variant_of": accent_of,
            "gop": gop,
            "z_score": z,
            "baseline_mean": round(random.uniform(-0.5, -0.1), 4),
            "baseline_std": round(random.uniform(0.2, 0.5), 4),
            "baseline_n": random.randint(0, 20),
            "start_ms": round(start_ms, 1),
            "end_ms": round(end_ms, 1),
            "competitors": competitors,
        })

    percent_correct = round(100 * sum(r["weight"] for r in results) / len(results))
    non_correct = [r for r in results if r["status"] != "correct"]
    worst = min(non_correct, key=lambda r: r["weight"]) if non_correct else None
    worst_phoneme = worst["expected"] if worst else None

    if percent_correct == 100:
        feedback = f"Perfect! You said \"{word}\" exactly right."
    elif worst is None:
        feedback = f"Nice try on \"{word}\"! Keep practicing."
    elif worst["status"] == "accent_variant":
        feedback = f"The {worst['expected']} sound was a little different, but that's just a normal accent variation, not an error."
    elif worst["status"] == "borderline":
        feedback = f"So close! The {worst['expected']} sound was borderline - it leaned toward {worst['heard']}. Try it once more."
    else:
        feedback = f"Almost! The {worst['expected']} sound came out like {worst['heard']}. Let's practice {worst['expected']}."

    return {
        "word": word,
        "percent_correct": percent_correct,
        "canonical": canonical,
        "results": results,
        "worst_phoneme": worst_phoneme,
        "feedback": feedback,
        "target_phoneme": target_phoneme,
    }
