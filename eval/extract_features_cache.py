"""One model pass per word, computing everything Phase 2's feature vector
needs (backend/features.compute_word_features already includes the Phase 1
paired-LLR computation internally, so this supersedes needing to run that
separately). Cached the same way as Phase 0/1's extraction scripts.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import gop_scorer  # noqa: E402
from features import compute_word_features  # noqa: E402
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


def extract(name: str, limit: int | None = None, force: bool = False) -> list[dict]:
    out_path = EVAL_DIR / f"features_raw_cache_{name}.json"
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

    processor, model, vocab, id_to_symbol, blank_id = gop_scorer.get_model()
    english_vocab_ids = gop_scorer._ENGLISH_VOCAB_IDS

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
            from gop_scorer import compute_log_probs
            log_probs, frame_seconds = compute_log_probs(processor, model, audio)
            wf = compute_word_features(log_probs, item.canonical, vocab, blank_id, id_to_symbol, english_vocab_ids)
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
            "word_features": {
                "ll_canonical_per_frame": wf.ll_canonical_per_frame,
                "free_decode_gap": wf.free_decode_gap,
                "frame_count": wf.frame_count,
            },
            "positions": [asdict(p) for p in wf.positions],
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
