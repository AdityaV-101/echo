"""Shared eval infrastructure: extracting raw (phoneme, GOP, competitors)
data for the whole synthetic corpus is the expensive part (loading the
model, running inference on 80 recordings), so it's done once and cached
here - both sweep.py (which needs to try many threshold values against the
same underlying data) and run_eval.py reuse the cache instead of re-running
inference per script invocation.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from audio_preprocess import preprocess_audio  # noqa: E402
from gop_scorer import score_phonemes  # noqa: E402

EVAL_DIR = Path(__file__).parent
LABELS_PATH = EVAL_DIR / "labels.json"
RAW_GOP_CACHE_PATH = EVAL_DIR / "raw_gop_cache.json"


def load_labels() -> list[dict]:
    with open(LABELS_PATH) as f:
        return json.load(f)


def extract_raw_gop(force: bool = False) -> list[dict]:
    """Runs forced-alignment + GOP (Steps 1-3 only, no calibration) on
    every recording in labels.json. Returns a list of entries, one per
    recording, each with its per-phoneme [{expected, gop, start_ms, end_ms,
    competitors}, ...]. Cached to RAW_GOP_CACHE_PATH; pass force=True to
    recompute (e.g. after changing gop_scorer.py)."""
    if RAW_GOP_CACHE_PATH.exists() and not force:
        with open(RAW_GOP_CACHE_PATH) as f:
            return json.load(f)

    labels = load_labels()
    results = []
    for i, entry in enumerate(labels):
        audio_path = str(EVAL_DIR / entry["audio_path"])
        audio = preprocess_audio(audio_path)
        phoneme_results = score_phonemes(entry["canonical"], audio)
        results.append({
            **entry,
            "phonemes": [
                {
                    "index": p.index,
                    "expected": p.expected,
                    "gop": p.gop,
                    "start_ms": p.start_ms,
                    "end_ms": p.end_ms,
                    "competitors": p.competitors,
                }
                for p in phoneme_results
            ],
        })
        print(f"[{i + 1}/{len(labels)}] {entry['target_word']} ({entry['label']}): "
              f"{[(p.expected, round(p.gop, 2)) for p in phoneme_results]}")

    with open(RAW_GOP_CACHE_PATH, "w") as f:
        json.dump(results, f, indent=1)
    return results
