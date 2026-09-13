"""Caches backend/llr_scorer.py's paired local-LLR output for every phoneme
position in a speaker-disjoint split, in one model pass per word - same
caching pattern as extract_phase0_cache.py, so every downstream feature
sweep (Phase 2's features, Phase 3's classifier) replays this file instead
of re-touching the model.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from gop_scorer import compute_log_probs, get_model  # noqa: E402
from llr_scorer import compute_paired_llr_for_word  # noqa: E402
from speechocean import WordItem, load_word_audio  # noqa: E402

EVAL_DIR = Path(__file__).parent
TRAIN_MANIFEST = EVAL_DIR / "speechocean_train.jsonl"
TEST_MANIFEST = EVAL_DIR / "speechocean_test.jsonl"
SPLIT_PATH = EVAL_DIR / "speaker_split.json"


def _load_split_speakers(name: str) -> set[str] | None:
    if name == "test":
        return None
    with open(SPLIT_PATH) as f:
        assignment = json.load(f)
    return {sp for sp, group in assignment.items() if group == name}


def _serialize_position(pr) -> dict:
    return {
        "index": pr.index,
        "expected": pr.expected,
        "frame_span": list(pr.frame_span),
        "frame_count": pr.frame_count,
        "candidates": [asdict(c) for c in pr.candidates],
        "llrs": pr.llrs,
        "feasible": pr.feasible,
    }


def extract(name: str, limit: int | None = None, force: bool = False) -> list[dict]:
    out_path = EVAL_DIR / f"phase1_raw_cache_{name}.json"
    if out_path.exists() and not force:
        with open(out_path) as f:
            cached = json.load(f)
        if limit is None or len(cached) >= limit:
            print(f"using existing cache {out_path} ({len(cached)} words)")
            return cached[:limit] if limit else cached

    manifest_path = TEST_MANIFEST if name == "test" else TRAIN_MANIFEST
    keep_speakers = _load_split_speakers(name)

    with open(manifest_path) as f:
        lines = f.readlines()

    processor, model, vocab, id_to_symbol, blank_id = get_model()
    results = []
    n_seen = 0
    for line in lines:
        raw = json.loads(line)
        if keep_speakers is not None and raw["speaker"] not in keep_speakers:
            continue
        n_seen += 1
        if limit is not None and n_seen > limit:
            break

        item = WordItem(**raw)
        audio = load_word_audio(item)
        if len(audio) < 800:
            continue
        try:
            log_probs, frame_seconds = compute_log_probs(processor, model, audio)
            positions = compute_paired_llr_for_word(log_probs, item.canonical, vocab, blank_id)
        except RuntimeError as e:
            print(f"[{item.utt_id}/{item.word_index}] {item.text}: failed, skipping ({e})")
            continue

        results.append({
            "utt_id": item.utt_id,
            "word_index": item.word_index,
            "text": item.text,
            "canonical": item.canonical,
            "phones_accuracy": item.phones_accuracy,
            "mispronunciations": item.mispronunciations,
            "is_child": item.is_child,
            "age": item.age,
            "speaker": item.speaker,
            "positions": [_serialize_position(p) for p in positions],
        })
        if len(results) % 250 == 0:
            print(f"  ...{len(results)} words extracted (of {n_seen} seen)")

    with open(out_path, "w") as f:
        json.dump(results, f)
    print(f"cached {len(results)} words to {out_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=["dev", "subtrain", "test"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    extract(args.split, limit=args.limit, force=args.force)
