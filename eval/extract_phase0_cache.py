"""One-pass raw-signal extraction for the Phase 0 baseline comparison: for
every word in a speaker-disjoint split, runs the model exactly once and
caches everything both existing scoring paths need to be replayed without
touching the model again:

- per-phoneme GOP + top competitors (what backend/gop_scorer.score_phonemes
  produces) - what the GOP + z-score scorer (backend/scorer.py) needs.
- hypothesis-rescoring candidates + their raw (un-prior-weighted) CTC
  log-likelihoods (what backend/hypothesis_scorer.py needs) - same shape as
  eval/hypothesis_raw_cache_train.json, computed here for the dev split
  specifically (that file was built from the first 3000 lines of
  speechocean_train.jsonl by run number, which is not speaker-disjoint from
  this dev split).

Cached once to eval/phase0_raw_cache_<name>.json; eval/harness.py's
baselines replay this file for every metric, so re-running a threshold sweep
never re-touches the model.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from gop_scorer import align_canonical, compute_gop, compute_log_probs, get_model  # noqa: E402
from hypothesis_scorer import generate_candidates, score_candidates_raw  # noqa: E402
import model_vocab  # noqa: E402
from speechocean import WordItem, load_word_audio  # noqa: E402

EVAL_DIR = Path(__file__).parent
TRAIN_MANIFEST = EVAL_DIR / "speechocean_train.jsonl"
TEST_MANIFEST = EVAL_DIR / "speechocean_test.jsonl"
SPLIT_PATH = EVAL_DIR / "speaker_split.json"


def _load_split_speakers(name: str) -> set[str] | None:
    """None means "no filtering" (used for the held-out test manifest,
    which is speaker-disjoint from speechocean_train.jsonl by construction)."""
    if name == "test":
        return None
    with open(SPLIT_PATH) as f:
        assignment = json.load(f)
    return {sp for sp, group in assignment.items() if group == name}


def extract(name: str, limit: int | None = None, force: bool = False) -> list[dict]:
    """name: "dev" or "subtrain" (filters speechocean_train.jsonl by
    eval/speaker_split.json) or "test" (all of speechocean_test.jsonl,
    never touched until Phase 5's final run)."""
    out_path = EVAL_DIR / f"phase0_raw_cache_{name}.json"
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
        if len(audio) < 800:  # < 50ms, too short to be meaningful (matches run_hypothesis_eval.py)
            continue
        try:
            log_probs, frame_seconds = compute_log_probs(processor, model, audio)
            spans = align_canonical(log_probs, item.canonical, vocab, blank_id)
        except RuntimeError as e:
            print(f"[{item.utt_id}/{item.word_index}] {item.text}: alignment failed, skipping ({e})")
            continue

        phoneme_gops = []
        competitor_hints = []
        for expected, span in zip(item.canonical, spans):
            gop, competitors = compute_gop(log_probs, span, expected, blank_id)
            phoneme_gops.append({"gop": gop, "top_competitor": competitors[0][0] if competitors else None})
            competitor_hints.append([label for label, _ in competitors if label in model_vocab.ARPABET_TO_MODEL_VOCAB])

        candidates = generate_candidates(item.canonical, competitor_hints)
        raw_scores = score_candidates_raw(log_probs, candidates, vocab, blank_id)

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
            "phoneme_gops": phoneme_gops,
            "candidates": [asdict(c) for c in candidates],
            "raw_scores": raw_scores,
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
