"""Hypothesis rescoring: the replacement decision procedure for the GOP +
z-score threshold approach in gop_scorer.py / calibration.py.

The old procedure asked, per phoneme, "is this GOP too many standard
deviations below a baseline." That is an open-ended anomaly-detection
question, and it is fragile: a single outlier frame can produce an
enormous z-score (z=-11.95 was observed on a clean recording), and the
threshold has no way to know whether a low score means "wrong" or just
"a slightly different but valid production."

This procedure asks a narrower, better-posed question instead: since the
target word is known in advance, which of a small set of plausible
pronunciations - the canonical one, or one produced by a documented
phonological simplification, or one suggested by what the model's own
frame posteriors actually favored - best explains this audio, end to end.
That is closed-set discrimination (an "extended recognition network" in
the pronunciation-assessment literature), not open-set anomaly detection.

On top of pure acoustic (CTC) likelihood, each candidate also carries a
prior reflecting how plausible its origin is - canonical highest, a
documented phonological process next (weighted by how commonly that
process is attested in children's speech), a purely data-driven acoustic
competitor with no linguistic backing lowest. This exists because acoustic
likelihood alone lets a clinically implausible neighbour (e.g. G->NG, a
substitution no developmental-phonology reference documents) win by a
razor-thin margin on ambiguous audio. See data/hypothesis_priors.json and
hypothesis_config.LAMBDA. The prior is a hypothesis to be measured, not
trusted by construction - eval/run_hypothesis_eval.py sweeps LAMBDA
against real dev-split data and reports whether it actually helps.

Pipeline:
1. generate_candidates - canonical + rule-based variants (data/
   phonological_processes.json, applied 1-2 at a time, plus final-consonant
   deletion / cluster reduction / weak-syllable deletion) + data-driven
   variants (each phoneme's top competitors from the canonical forced
   alignment). Each candidate is tagged with its origin (canonical /
   process name(s) / data_driven) for prior lookup.
2. score_candidates_raw - one batched torch.nn.functional.ctc_loss call
   scores every candidate's pure acoustic likelihood against the same
   cached emission matrix. This is the expensive, model-inference part and
   is what eval/run_hypothesis_eval.py caches per word.
3. apply_prior_and_decide - final_score = acoustic + LAMBDA * log_prior
   (log_prior boosted per-user for a process with a confirmed history -
   see get_user_process_boost). Softmax + margin between best and
   second-best candidate; low margin returns "unclear" rather than forcing
   a verdict. This step is cheap (no model inference), which is what lets
   LAMBDA and UNCERTAIN_MARGIN be swept against cached raw scores.
4. Levenshtein-align the winning candidate back to canonical to report
   exactly which positions changed - the error report is grounded in a
   hypothesis that actually explained the audio better, not a threshold.
5. Per-phoneme display confidence - max-pooled (not mean-pooled) posterior
   over each phoneme's own aligned frame span, so a handful of coarticulated
   edge frames can't dominate the number the therapist sees.
"""
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import torch
import torch.nn.functional as F

import hypothesis_config as cfg
import model_vocab
from gop_scorer import align_canonical, compute_gop, compute_log_probs, get_model

logger = logging.getLogger("speechpal.hypothesis_scorer")

_DATA_DIR = Path(__file__).parent / "data"
_PROCESSES_PATH = _DATA_DIR / "phonological_processes.json"
_PRIORS_PATH = _DATA_DIR / "hypothesis_priors.json"
_PROCESSES: dict | None = None
_PRIORS: dict | None = None

VOWELS = frozenset({
    "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY",
    "IH", "IY", "OW", "OY", "UH", "UW",
})


def _is_consonant(phone: str) -> bool:
    return phone not in VOWELS


def _load_processes() -> dict:
    global _PROCESSES
    if _PROCESSES is None:
        with open(_PROCESSES_PATH) as f:
            raw = json.load(f)
        _PROCESSES = {k: v for k, v in raw.items() if not k.startswith("_")}
        n_rules = sum(len(v) for v in _PROCESSES.values())
        logger.info("hypothesis_scorer: loaded %d phonological rules across %d processes", n_rules, len(_PROCESSES))
    return _PROCESSES


def _load_priors() -> dict:
    global _PRIORS
    if _PRIORS is None:
        with open(_PRIORS_PATH) as f:
            raw = json.load(f)
        _PRIORS = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _PRIORS


def log_prior_for(category: str, processes: list[str]) -> float:
    """Base (pre-per-user-boost) log prior for a candidate. "process" with
    two entries (a two-rule-application variant) averages their individual
    priors - still process-backed, but stacking two simplifications is
    intuitively a bit less likely than either alone."""
    priors = _load_priors()
    if category == "canonical":
        return priors["canonical"]
    if category == "data_driven":
        return priors["data_driven"]
    process_priors = priors["processes"]
    vals = [process_priors.get(p, process_priors["_default"]) for p in processes]
    return sum(vals) / len(vals) if vals else process_priors["_default"]


def get_user_process_boost(user_id: str | None, processes: list[str]) -> float:
    """Saturating boost from this user's confirmed history of each process
    in `processes` (0 if user_id is None or the process has no history).
    See hypothesis_config.PROCESS_BOOST_RATE / MAX_PROCESS_BOOST."""
    if not user_id or not processes:
        return 0.0
    import db

    counts = db.get_user_process_counts(user_id)
    if not counts:
        return 0.0
    boosts = [
        min(cfg.MAX_PROCESS_BOOST, cfg.PROCESS_BOOST_RATE * math.log1p(counts.get(p, 0)))
        for p in processes
    ]
    return sum(boosts) / len(boosts) if boosts else 0.0


def record_confirmed_process(user_id: str | None, category: str, processes: list[str]):
    """Called after a definitive ("wrong", not "unclear") verdict whose
    winning candidate was process-backed - increments that user's count for
    each process involved, so future attempts trust that hypothesis more
    for them specifically. No-op for canonical/data_driven winners or
    without a user_id."""
    if not user_id or category != "process" or not processes:
        return
    import db

    for p in processes:
        db.increment_user_process_count(user_id, p)


def _single_rule_variants(seq: list[str]) -> list[tuple[list[str], str]]:
    """Returns (variant, process_name) pairs."""
    processes = _load_processes()
    variants = []
    for i, phone in enumerate(seq):
        for process_name, rules in processes.items():
            for rule in rules:
                if rule["from"] == phone:
                    variant = list(seq)
                    variant[i] = rule["to"]
                    variants.append((variant, process_name))
    return variants


def _find_consonant_clusters(seq: list[str]) -> list[tuple[int, int]]:
    clusters = []
    i, n = 0, len(seq)
    while i < n:
        if _is_consonant(seq[i]):
            j = i
            while j < n and _is_consonant(seq[j]):
                j += 1
            if j - i >= 2:
                clusters.append((i, j))
            i = j
        else:
            i += 1
    return clusters


def _structural_variants(seq: list[str]) -> list[tuple[list[str], str]]:
    """Returns (variant, process_name) pairs."""
    variants = []

    if len(seq) > 1 and _is_consonant(seq[-1]):
        variants.append((seq[:-1], "final_consonant_deletion"))

    for start, end in _find_consonant_clusters(seq):
        for drop_idx in range(start, end):
            variants.append((seq[:drop_idx] + seq[drop_idx + 1:], "cluster_reduction"))

    vowel_positions = [i for i, p in enumerate(seq) if not _is_consonant(p)]
    if len(vowel_positions) >= 3:
        for vi in vowel_positions[1:-1]:
            variants.append((seq[:vi] + seq[vi + 1:], "weak_syllable_deletion"))

    return [(v, p) for v, p in variants if v]


@dataclass
class Candidate:
    sequence: list[str]
    category: str  # canonical | process | data_driven
    processes: list[str] = field(default_factory=list)


def generate_candidates(
    canonical: list[str],
    competitor_hints: list[list[str]] | None = None,
    max_candidates: int = cfg.MAX_CANDIDATES,
) -> list[Candidate]:
    """Returns tagged candidates, canonical always first, deduped, capped
    at max_candidates. When the same sequence is reachable multiple ways,
    the most specific tag wins: canonical > process > data_driven, since a
    rule match is strictly more informative than "some frame favored this."
    Priority when over budget mirrors this: canonical > data-driven (most
    directly grounded in this audio) > single-rule > structural > two-rule
    combinations, which are dropped first."""
    by_key: dict[tuple, Candidate] = {tuple(canonical): Candidate(list(canonical), "canonical")}
    order: list[tuple] = [tuple(canonical)]

    def add(seq: list[str], category: str, processes: list[str]):
        key = tuple(seq)
        if key in by_key:
            return
        by_key[key] = Candidate(seq, category, processes)
        order.append(key)

    data_driven = []
    if competitor_hints:
        for i, competitors in enumerate(competitor_hints):
            for comp in competitors[:2]:
                if comp in model_vocab.ARPABET_TO_MODEL_VOCAB and comp != canonical[i]:
                    variant = list(canonical)
                    variant[i] = comp
                    data_driven.append(variant)
    for v in data_driven:
        add(v, "data_driven", [])

    single = _single_rule_variants(canonical)
    for v, process in single:
        add(v, "process", [process])

    for v, process in _structural_variants(canonical):
        add(v, "process", [process])

    if len(order) < max_candidates:
        two_rule = []
        for v, process1 in single:
            for v2, process2 in _single_rule_variants(v):
                two_rule.append((v2, process1, process2))
            if len(order) + len(two_rule) > max_candidates * 4:
                break
        for v2, process1, process2 in two_rule:
            add(v2, "process", [process1, process2])

    return [by_key[k] for k in order[:max_candidates]]


def score_candidates_raw(
    log_probs: torch.Tensor,
    candidates: list[Candidate],
    vocab: dict[str, int],
    blank_id: int,
) -> list[float]:
    """One batched CTC call scores every candidate's pure acoustic
    likelihood against the same cached emission matrix - no prior applied
    here, deliberately, so this (the expensive, model-inference-derived
    part) can be cached and prior-weighting swept independently. Returns
    length-normalized log-likelihoods, higher = better explains the audio."""
    T, V = log_probs.shape
    n = len(candidates)

    target_seqs = [
        torch.tensor(model_vocab.arpabet_sequence_to_vocab_ids(c.sequence, vocab), dtype=torch.long)
        for c in candidates
    ]
    target_lengths = torch.tensor([len(s) for s in target_seqs], dtype=torch.long)
    targets_padded = torch.nn.utils.rnn.pad_sequence(target_seqs, batch_first=True, padding_value=0)

    log_probs_batched = log_probs.unsqueeze(1).expand(T, n, V).contiguous()
    input_lengths = torch.full((n,), T, dtype=torch.long)

    nll = F.ctc_loss(
        log_probs_batched, targets_padded, input_lengths, target_lengths,
        blank=blank_id, reduction="none", zero_infinity=True,
    )
    scores = (-nll / target_lengths.clamp(min=1).float()).tolist()
    return scores


def apply_prior_and_decide(
    candidates: list[Candidate],
    raw_scores: list[float],
    user_id: str | None = None,
    lambda_: float = cfg.LAMBDA,
    uncertain_margin: float = cfg.UNCERTAIN_MARGIN,
) -> dict:
    """Pure post-processing, no model inference - this is what
    eval/run_hypothesis_eval.py sweeps lambda_ and uncertain_margin
    against, reusing the same cached raw_scores for every setting tried.
    Returns {final_scores, best_idx, second_idx, margin, winner, word_status}."""
    final_scores = []
    for cand, raw in zip(candidates, raw_scores):
        base_prior = log_prior_for(cand.category, cand.processes)
        boost = get_user_process_boost(user_id, cand.processes) if cand.category == "process" else 0.0
        final_scores.append(raw + lambda_ * (base_prior + boost))

    ranked = sorted(range(len(candidates)), key=lambda i: final_scores[i], reverse=True)
    best_idx = ranked[0]
    second_idx = ranked[1] if len(ranked) > 1 else best_idx
    margin = final_scores[best_idx] - final_scores[second_idx]
    winner = candidates[best_idx]
    is_canonical_winner = winner.category == "canonical"

    if margin < uncertain_margin:
        word_status = "unclear"
    elif is_canonical_winner:
        word_status = "correct"
    else:
        word_status = "wrong"

    return {
        "final_scores": final_scores,
        "best_idx": best_idx,
        "second_idx": second_idx,
        "margin": margin,
        "winner": winner,
        "is_canonical_winner": is_canonical_winner,
        "word_status": word_status,
    }


def _levenshtein_align(canonical: list[str], hypothesis: list[str]) -> list[tuple[str, str | None]]:
    """Aligns hypothesis back to canonical (edit distance, unit costs).
    Returns one entry per canonical position: ("match", None) if kept,
    ("sub", heard_phone) if substituted, ("del", None) if dropped."""
    n, m = len(canonical), len(hypothesis)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if canonical[i - 1] == hypothesis[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and canonical[i - 1] == hypothesis[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            ops.append(("match", None))
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(("sub", hypothesis[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", None))
            i -= 1
        else:
            j -= 1
    ops.reverse()
    return ops


def phoneme_statuses_from_decision(canonical: list[str], decision: dict) -> list[str]:
    """Per-canonical-position status list (correct/wrong/unclear) from an
    apply_prior_and_decide result, without needing spans/confidence -
    exposed standalone so eval/run_hypothesis_eval.py can re-derive
    statuses for many (lambda_, uncertain_margin) settings against the
    same cached raw scores without recomputing model inference or the
    display-only confidence numbers."""
    word_status = decision["word_status"]
    if word_status == "unclear":
        return ["unclear"] * len(canonical)
    winner = decision["winner"]
    if decision["is_canonical_winner"]:
        return ["correct"] * len(canonical)
    alignment = _levenshtein_align(canonical, winner.sequence)
    return ["correct" if op == "match" else "wrong" for op, _ in alignment]


def _max_pool_confidence(log_probs: torch.Tensor, span, target_id: int, top_k: int) -> float:
    start, end = int(span.start), int(span.end)
    end = min(max(end, start + 1), log_probs.shape[0])
    start = min(start, max(end - 1, 0))
    frame_probs = torch.exp(log_probs[start:end, target_id])
    k = min(top_k, frame_probs.numel())
    top_vals, _ = torch.topk(frame_probs, k)
    return top_vals.mean().item()


@dataclass
class PhonemeVerdict:
    index: int
    expected: str
    status: str  # correct | wrong | unclear
    heard: str | None
    confidence: float
    start_ms: float
    end_ms: float


@dataclass
class HypothesisResult:
    canonical: list[str]
    winner: list[str]
    is_canonical_winner: bool
    word_status: str  # correct | wrong | unclear
    margin: float
    n_candidates: int
    winner_category: str = "canonical"
    winner_processes: list[str] = field(default_factory=list)
    phonemes: list[PhonemeVerdict] = field(default_factory=list)


def score_word_hypothesis(canonical: list[str], audio, user_id: str | None = None) -> HypothesisResult:
    processor, model, vocab, id_to_symbol, blank_id = get_model()
    log_probs, frame_seconds = compute_log_probs(processor, model, audio)
    spans = align_canonical(log_probs, canonical, vocab, blank_id)

    competitor_hints = []
    for expected, span in zip(canonical, spans):
        _, competitors = compute_gop(log_probs, span, expected, blank_id)
        competitor_hints.append([label for label, _ in competitors if label in model_vocab.ARPABET_TO_MODEL_VOCAB])

    candidates = generate_candidates(canonical, competitor_hints)
    raw_scores = score_candidates_raw(log_probs, candidates, vocab, blank_id)
    decision = apply_prior_and_decide(candidates, raw_scores, user_id=user_id)

    winner = decision["winner"]
    word_status = decision["word_status"]
    if word_status == "wrong":
        record_confirmed_process(user_id, winner.category, winner.processes)

    confidences = [
        _max_pool_confidence(log_probs, span, model_vocab.arpabet_sequence_to_vocab_ids([expected], vocab)[0], cfg.CONFIDENCE_TOP_K_FRAMES)
        for expected, span in zip(canonical, spans)
    ]

    statuses = phoneme_statuses_from_decision(canonical, decision)
    heard_per_position = [None] * len(canonical)
    if word_status == "wrong" and not decision["is_canonical_winner"]:
        for i, (op, heard) in enumerate(_levenshtein_align(canonical, winner.sequence)):
            heard_per_position[i] = heard if op == "sub" else None

    phonemes = []
    for i, (expected, span, conf, status) in enumerate(zip(canonical, spans, confidences, statuses)):
        phonemes.append(PhonemeVerdict(
            index=i, expected=expected, status=status, heard=heard_per_position[i], confidence=conf,
            start_ms=span.start * frame_seconds * 1000, end_ms=span.end * frame_seconds * 1000,
        ))

    logger.info(
        "score_word_hypothesis: canonical=%s winner=%s (%s/%s) margin=%.3f status=%s n_candidates=%d",
        canonical, winner.sequence, winner.category, winner.processes, decision["margin"], word_status, len(candidates),
    )

    return HypothesisResult(
        canonical=canonical,
        winner=winner.sequence,
        is_canonical_winner=decision["is_canonical_winner"],
        word_status=word_status,
        margin=decision["margin"],
        n_candidates=len(candidates),
        winner_category=winner.category,
        winner_processes=winner.processes,
        phonemes=phonemes,
    )
