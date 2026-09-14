"""Per-child running baseline for the four speaker-relative features the
frozen Phase 3 model was trained on (llr_best, gop_i, gop_lpr_i, dur_z) -
production equivalent of eval/build_phase2_features.py's training-time
Welford accumulator, which computed each attempt's value relative to that
SAME speaker's own prior attempts. Reuses calibration.py's welford_update
(the exact same algorithm, already used for the GOP z-score path) rather
than reimplementing it.

Cold start: below MIN_SPEAKER_SAMPLES (gop_config.py's existing constant,
reused for consistency), centers on the GLOBAL per-phoneme mean from
eval/export_final_model.py's training data
(backend/data/phase3_model/global_feature_means.json) instead of this
child's own thin history - identical cold-start shape to calibration.py's
get_baseline_for_scoring.
"""
import json
from pathlib import Path

import db
from calibration import welford_update
from gop_config import MIN_SPEAKER_SAMPLES

_GLOBAL_MEANS_PATH = Path(__file__).parent / "data" / "phase3_model" / "global_feature_means.json"
_GLOBAL_MEANS: dict[str, dict[str, float]] | None = None

RELATIVE_FEATURES = ("llr_best", "gop_i", "gop_lpr_i", "dur_z")


def _load_global_means() -> dict[str, dict[str, float]]:
    global _GLOBAL_MEANS
    if _GLOBAL_MEANS is None:
        with open(_GLOBAL_MEANS_PATH) as f:
            _GLOBAL_MEANS = json.load(f)
    return _GLOBAL_MEANS


def speaker_relative_features(user_id: str, phoneme: str, raw_values: dict[str, float]) -> dict[str, float]:
    """raw_values: {feature_name: raw_value} for the four RELATIVE_FEATURES
    from this attempt. Returns {feature_name + '_speaker_rel': centered
    value}, using this child's own running mean once they have
    MIN_SPEAKER_SAMPLES for this phoneme, else the global fallback -
    computed BEFORE folding this attempt in, exactly as training did."""
    global_means = _load_global_means()
    relative = {}
    for feat in RELATIVE_FEATURES:
        existing = db.get_feature_baseline(user_id, phoneme, feat)
        if existing is not None and existing["n"] >= MIN_SPEAKER_SAMPLES:
            baseline = existing["mean_value"]
        else:
            baseline = global_means[feat].get(phoneme, global_means[feat].get("_default", 0.0))
        relative[f"{feat}_speaker_rel"] = raw_values[feat] - baseline
    return relative


def update_baselines(user_id: str, phoneme: str, raw_values: dict[str, float]) -> None:
    """Folds this attempt's raw values into the running per-(user, phoneme,
    feature) baseline - called for every attempt regardless of verdict, an
    explicit, documented simplification carried over from
    eval/build_phase2_features.py (see that module's docstring): the
    verdict-gated fold-in used by calibration.py's GOP path would create a
    circular dependency here (the verdict depends on features that depend
    on the baseline), and errors are a small minority of attempts."""
    for feat in RELATIVE_FEATURES:
        existing = db.get_feature_baseline(user_id, phoneme, feat)
        n, mean, m2 = (0, 0.0, 0.0) if existing is None else (existing["n"], existing["mean_value"], existing["m2"])
        n, mean, m2 = welford_update(n, mean, m2, raw_values[feat])
        db.upsert_feature_baseline(user_id, phoneme, feat, n, mean, m2)
