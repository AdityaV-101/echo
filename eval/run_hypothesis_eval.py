"""Evaluates hypothesis_scorer.py against real human speech (speechocean762,
via speechocean.py's extracted manifests) instead of the espeak synthetic
corpus. Two phases, matching hypothesis_scorer's own split between the
expensive (model inference) and cheap (prior weighting + decision) parts:

1. build_raw_cache - runs score_candidates_raw once per word (the only part
   that needs the model) and caches canonical, tagged candidates, raw
   acoustic scores, and ground truth (phones-accuracy, mispronunciations)
   to disk.
2. evaluate(...) - pure post-processing against the cache: applies a given
   (lambda_, uncertain_margin), derives per-phoneme predicted statuses via
   hypothesis_scorer.phoneme_statuses_from_decision, and compares against
   ground truth. This is what sweep_lambda / coverage_precision_curve call
   repeatedly without ever re-touching the model.

Ground truth: a phoneme with phones-accuracy >= 2.0 counts as correctly
produced; < 2.0 counts as mispronounced (matches the two-way split
run_eval.py's old GOP eval used, now against real annotated speech instead
of synthetic pairs).

Only ever run against the dev split (speechocean_train.jsonl) for tuning.
The test split (speechocean_test.jsonl) is held out - see
report_test_split() at the bottom, which is meant to be run once, last.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import hypothesis_config as cfg  # noqa: E402
from gop_scorer import align_canonical, compute_gop, compute_log_probs, get_model  # noqa: E402
from hypothesis_scorer import (  # noqa: E402
    Candidate,
    apply_prior_and_decide,
    generate_candidates,
    phoneme_statuses_from_decision,
    score_candidates_raw,
)
import model_vocab  # noqa: E402
from speechocean import WordItem, load_word_audio  # noqa: E402

EVAL_DIR = Path(__file__).parent
RAW_CACHE_PATH = EVAL_DIR / "hypothesis_raw_cache.json"


def build_raw_cache(split: str = "train", limit: int | None = None, force: bool = False) -> list[dict]:
    manifest_path = EVAL_DIR / f"speechocean_{split}.jsonl"
    cache_key_path = RAW_CACHE_PATH.with_name(f"hypothesis_raw_cache_{split}.json")
    if cache_key_path.exists() and not force:
        with open(cache_key_path) as f:
            cached = json.load(f)
        if limit is None or len(cached) >= limit:
            return cached[:limit] if limit else cached

    processor, model, vocab, id_to_symbol, blank_id = get_model()

    results = []
    with open(manifest_path) as f:
        lines = f.readlines()
    if limit:
        lines = lines[:limit]

    for i, line in enumerate(lines):
        item = WordItem(**json.loads(line))
        audio = load_word_audio(item)
        if len(audio) < 800:  # < 50ms, too short to be meaningful
            continue
        try:
            log_probs, frame_seconds = compute_log_probs(processor, model, audio)
            spans = align_canonical(log_probs, item.canonical, vocab, blank_id)
        except RuntimeError as e:
            print(f"[{i}] {item.text}: alignment failed, skipping ({e})")
            continue

        competitor_hints = []
        for expected, span in zip(item.canonical, spans):
            _, competitors = compute_gop(log_probs, span, expected, blank_id)
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
            "candidates": [asdict(c) for c in candidates],
            "raw_scores": raw_scores,
        })
        if (i + 1) % 250 == 0:
            print(f"  ...{i + 1}/{len(lines)} words scored")

    with open(cache_key_path, "w") as f:
        json.dump(results, f)
    print(f"cached {len(results)} words to {cache_key_path}")
    return results


def evaluate(raw_cache: list[dict], lambda_: float, uncertain_margin: float, children_only: bool = False) -> dict:
    tp = fp = fn = tn = 0
    n_unclear = 0
    n_total = 0

    for entry in raw_cache:
        if children_only and not entry["is_child"]:
            continue
        candidates = [Candidate(**c) for c in entry["candidates"]]
        decision = apply_prior_and_decide(candidates, entry["raw_scores"], user_id=None, lambda_=lambda_, uncertain_margin=uncertain_margin)
        statuses = phoneme_statuses_from_decision(entry["canonical"], decision)

        for status, acc in zip(statuses, entry["phones_accuracy"]):
            n_total += 1
            actual_mispronounced = acc < 2.0
            if status == "unclear":
                n_unclear += 1
                continue
            predicted_mispronounced = status == "wrong"
            if predicted_mispronounced and actual_mispronounced:
                tp += 1
            elif predicted_mispronounced and not actual_mispronounced:
                fp += 1
            elif not predicted_mispronounced and actual_mispronounced:
                fn += 1
            else:
                tn += 1

    considered = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) and precision == precision and recall == recall else float("nan")
    frr = fp / (fp + tn) if (fp + tn) else float("nan")  # correct flagged wrong
    far = fn / (fn + tp) if (fn + tp) else float("nan")  # wrong flagged correct
    coverage = considered / n_total if n_total else 0.0

    return {
        "lambda": lambda_, "uncertain_margin": uncertain_margin, "children_only": children_only,
        "n_total": n_total, "n_unclear": n_unclear, "coverage": coverage,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1, "frr": frr, "far": far,
    }


def sweep_lambda(raw_cache: list[dict], lambdas: list[float], uncertain_margin: float) -> list[dict]:
    return [evaluate(raw_cache, lam, uncertain_margin) for lam in lambdas]


def coverage_precision_curve(raw_cache: list[dict], lambda_: float, margins: list[float]) -> list[dict]:
    return [evaluate(raw_cache, lambda_, m) for m in margins]


def _fmt(r: dict) -> str:
    return (
        f"lambda={r['lambda']:.2f} margin={r['uncertain_margin']:.2f} "
        f"coverage={r['coverage']:.1%} precision={r['precision']:.1%} recall={r['recall']:.1%} "
        f"f1={r['f1']:.3f} frr={r['frr']:.1%} far={r['far']:.1%} (n={r['n_total']})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1500)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cache = build_raw_cache("train", limit=args.limit, force=args.force)

    print("\n=== baseline (lambda=0, i.e. no prior) ===")
    print(_fmt(evaluate(cache, 0.0, cfg.UNCERTAIN_MARGIN)))

    print("\n=== lambda sweep (margin fixed) ===")
    for r in sweep_lambda(cache, [0.0, 0.5, 1.0, 1.5, 2.0], cfg.UNCERTAIN_MARGIN):
        print(_fmt(r))
