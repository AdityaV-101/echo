"""Per-speaker GOP calibration: Welford's online algorithm for updating a
running mean/variance per (user, phoneme), and the z-score decision that
turns a raw GOP into correct/borderline/wrong/accent_variant.

This is what makes the scorer judge a child against their own voice instead
of a fixed American-adult reference - the actual fix for the accent
complaint, not a workaround for it. See "Speaker calibration" in
SETUP_NOTES.md.
"""
import json
import math
from pathlib import Path

import db
from gop_config import (
    BORDERLINE_WEIGHT,
    FLOOR_SIGMA,
    GLOBAL_PRIOR,
    GLOBAL_PRIOR_DEFAULT,
    MIN_SPEAKER_SAMPLES,
    Z_CORRECT_THRESHOLD,
    Z_WRONG_THRESHOLD,
)

_ACCENT_VARIANTS_PATH = Path(__file__).parent / "data" / "accent_variants.json"
_ACCENT_VARIANTS: dict[str, list[str]] | None = None


def get_accent_variants() -> dict[str, list[str]]:
    global _ACCENT_VARIANTS
    if _ACCENT_VARIANTS is None:
        with open(_ACCENT_VARIANTS_PATH) as f:
            raw = json.load(f)
        _ACCENT_VARIANTS = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _ACCENT_VARIANTS


def welford_update(n: int, mean: float, m2: float, new_value: float) -> tuple[int, float, float]:
    """One step of Welford's online algorithm. Returns the updated
    (n, mean, m2). Numerically stable for a long-running per-speaker
    history, unlike re-averaging from stored raw values each time."""
    n += 1
    delta = new_value - mean
    mean += delta / n
    delta2 = new_value - mean
    m2 += delta * delta2
    return n, mean, m2


def std_from_m2(n: int, m2: float) -> float:
    if n < 2:
        return 0.0
    return math.sqrt(m2 / n)


def update_speaker_baseline(user_id: str, phoneme: str, gop_value: float) -> None:
    """Fold one new GOP observation into this speaker's running baseline
    for this phoneme. Called for every phoneme judged correct or
    accent_variant in normal use (Step 4: "every time a phoneme is judged
    correct in normal use, fold its GOP into that speaker's running
    mean/std") - not for phonemes judged wrong, since a wrong production's
    GOP describes the error, not the speaker's normal voice, and folding it
    in would drag their own baseline toward tolerating that same error."""
    existing = db.get_speaker_baseline(user_id, phoneme)
    if existing is None:
        n, mean, m2 = 0, 0.0, 0.0
    else:
        n, mean, m2 = existing["n"], existing["mean_gop"], existing["m2"]
    n, mean, m2 = welford_update(n, mean, m2, gop_value)
    db.upsert_speaker_baseline(user_id, phoneme, mean, std_from_m2(n, m2), n, m2)


def get_baseline_for_scoring(user_id: str, phoneme: str) -> tuple[float, float, int]:
    """(mean, std, n) to score against: the speaker's own baseline once
    they have enough samples (Step 4's MIN_SPEAKER_SAMPLES), otherwise the
    global per-phoneme prior. std is never returned below FLOOR_SIGMA."""
    existing = db.get_speaker_baseline(user_id, phoneme)
    if existing is not None and existing["n"] >= MIN_SPEAKER_SAMPLES:
        return existing["mean_gop"], max(existing["std_gop"], FLOOR_SIGMA), existing["n"]
    mean, std = GLOBAL_PRIOR.get(phoneme, GLOBAL_PRIOR_DEFAULT)
    return mean, max(std, FLOOR_SIGMA), existing["n"] if existing else 0


def compute_z_score(gop_value: float, user_id: str, phoneme: str) -> tuple[float, float, float, int]:
    """Returns (z, mean_used, std_used, n_speaker_samples)."""
    mean, std, n = get_baseline_for_scoring(user_id, phoneme)
    z = (gop_value - mean) / std
    return z, mean, std, n


def classify_z_score(z: float) -> tuple[str, float]:
    """(status, weight) from a z-score alone, per the decision bands in
    gop_config.py. Does not know about accent variants - that's a separate
    downgrade applied by the caller (see scorer.py) using the top
    competitor phone, since it needs information this function doesn't
    have."""
    if z > Z_CORRECT_THRESHOLD:
        return "correct", 1.0
    if z > Z_WRONG_THRESHOLD:
        return "borderline", BORDERLINE_WEIGHT
    return "wrong", 0.0
