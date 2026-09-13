"""Phase 2: raw per-word/per-position feature quantities. Nothing here
makes a decision - per the rebuild brief, thresholding any single value
(llr included) is exactly what NOT to do. This module only computes the
inputs to Phase 3's learned classifier: local paired-LLR statistics
(delegated to llr_scorer.py), plain GOP, a log-posterior-ratio against the
single strongest competing phone over the same span, span-duration relative
to this word's own mean phone duration, posterior entropy, whole-word
canonical fit, and a free-decode "did they maybe say a different word"
signal. Speaker-relative versions of four of these (built from the running
per-speaker baseline, via calibration.py's Welford accumulator) are added
downstream in eval/build_phase2_features.py, since that needs to see
attempts in speaker order - this module is stateless, one word at a time.
"""
import math
from dataclasses import dataclass, field

import torch

import model_vocab
from gop_scorer import align_canonical
from llr_scorer import (
    PositionResult,
    _score_vocab_id_sequences_batched,
    compute_paired_llr_for_word,
)


@dataclass
class PositionFeatures:
    index: int
    expected: str
    llr_best: float
    llr_best_origin: str  # "canonical" | process name | "deletion" - categorical
    llr_deletion: float | None  # None if the word has only one phoneme (no deletion candidate)
    llr_second_best: float | None  # None if there's only one feasible candidate at all
    llr_margin: float  # llr_best - llr_second_best (0.0 when there's no second candidate)
    gop_i: float
    gop_lpr_i: float
    top_competitor: str | None  # ARPABET label of the best competing phone, None if unmappable
    dur_z: float
    entropy: float
    raw_span: tuple[int, int]
    position: str  # "initial" | "medial" | "final" | "single"
    syllable_count: int
    frame_count_word: int


@dataclass
class WordFeatures:
    canonical: list[str]
    ll_canonical_per_frame: float
    free_decode_gap: float
    frame_count: int
    positions: list[PositionFeatures] = field(default_factory=list)


_VOWELS = frozenset({
    "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY",
    "IH", "IY", "OW", "OY", "UH", "UW",
})


def _word_position(index: int, length: int) -> str:
    if length == 1:
        return "single"
    if index == 0:
        return "initial"
    if index == length - 1:
        return "final"
    return "medial"


def _mean_log_prob(log_probs: torch.Tensor, start: int, end: int, vocab_id: int) -> float:
    return log_probs[start:end, vocab_id].mean().item()


def _gop_and_lpr(
    log_probs: torch.Tensor, start: int, end: int, target_id: int,
    english_vocab_ids: set[int], blank_id: int, id_to_symbol: dict[int, str],
) -> tuple[float, float, str | None]:
    """gop_i: mean log-posterior of the target phone over [start, end).
    gop_lpr_i: gop_i minus the SAME-SPAN mean log-posterior of whichever
    other English phone has the highest mean log-posterior there (the
    single most plausible alternative reading of this span, not a
    per-frame argmax) - a standard log-posterior-ratio feature."""
    from ipa_arpabet import normalize_and_map

    gop_i = _mean_log_prob(log_probs, start, end, target_id)
    best_id, best_val = None, float("-inf")
    for vid in english_vocab_ids:
        if vid in (target_id, blank_id):
            continue
        val = _mean_log_prob(log_probs, start, end, vid)
        if val > best_val:
            best_id, best_val = vid, val
    if best_id is None:
        return gop_i, 0.0, None
    competitor_label = normalize_and_map(id_to_symbol[best_id])
    return gop_i, gop_i - best_val, competitor_label


def _entropy(log_probs: torch.Tensor, start: int, end: int) -> float:
    frame_lp = log_probs[start:end]
    probs = frame_lp.exp()
    per_frame_entropy = -(probs * frame_lp).sum(dim=-1)
    return per_frame_entropy.mean().item()


def _greedy_decode_ids(log_probs: torch.Tensor, blank_id: int) -> list[int]:
    """Free CTC greedy decode: per-frame argmax, then collapse consecutive
    repeats and remove blanks - the standard CTC decoding collapse rule."""
    frame_ids = log_probs.argmax(dim=-1).tolist()
    decoded = []
    prev = None
    for vid in frame_ids:
        if vid != blank_id and vid != prev:
            decoded.append(vid)
        prev = vid
    return decoded


def compute_word_features(
    log_probs: torch.Tensor,
    canonical: list[str],
    vocab: dict[str, int],
    blank_id: int,
    id_to_symbol: dict[int, str],
    english_vocab_ids: set[int],
) -> WordFeatures:
    T = log_probs.shape[0]
    spans = align_canonical(log_probs, canonical, vocab, blank_id)
    raw_spans = [(int(s.start), int(s.end)) for s in spans]
    durations = [max(e - s, 1) for s, e in raw_spans]
    mean_dur = sum(durations) / len(durations)
    syllable_count = max(1, sum(1 for p in canonical if p in _VOWELS))

    canon_ids = model_vocab.arpabet_sequence_to_vocab_ids(canonical, vocab)
    (canon_ll,), (canon_feasible,) = _score_vocab_id_sequences_batched(log_probs, [canon_ids], blank_id)
    ll_canonical_per_frame = canon_ll / T if canon_feasible else float("-inf")

    decoded_ids = _greedy_decode_ids(log_probs, blank_id)
    if decoded_ids:
        (decoded_ll,), (decoded_feasible,) = _score_vocab_id_sequences_batched(log_probs, [decoded_ids], blank_id)
        free_decode_gap = (decoded_ll / T) - ll_canonical_per_frame if decoded_feasible else 0.0
    else:
        # Nothing survived the collapse (every frame favored blank) - no
        # alternative reading to compare against, so no evidence of a
        # different word; a 0 gap is the honest "no signal either way".
        free_decode_gap = 0.0

    llr_positions: list[PositionResult] = compute_paired_llr_for_word(log_probs, canonical, vocab, blank_id)

    positions = []
    for i, (phone, (start, end), llr_pos) in enumerate(zip(canonical, raw_spans, llr_positions)):
        target_id = model_vocab.arpabet_sequence_to_vocab_ids([phone], vocab)[0]
        gop_i, gop_lpr_i, top_competitor = _gop_and_lpr(
            log_probs, start, end, target_id, english_vocab_ids, blank_id, id_to_symbol,
        )
        entropy = _entropy(log_probs, start, end)
        dur_z = durations[i] / mean_dur

        # Rank feasible non-canonical candidates by LLR for llr_best /
        # llr_second_best / llr_margin; llr_deletion is looked up by origin
        # specifically since it's a named feature, not just "the best one".
        ranked = sorted(
            (
                (llr, cand)
                for llr, cand, ok in zip(llr_pos.llrs, llr_pos.candidates, llr_pos.feasible)
                if ok and cand.origin != "canonical"
            ),
            key=lambda pair: pair[0], reverse=True,
        )
        llr_best, best_origin = (ranked[0][0], ranked[0][1].origin) if ranked else (0.0, "canonical")
        llr_second_best = ranked[1][0] if len(ranked) > 1 else None
        llr_margin = (llr_best - llr_second_best) if llr_second_best is not None else 0.0
        llr_deletion = next((llr for llr, cand in ranked if cand.origin == "deletion"), None)

        positions.append(PositionFeatures(
            index=i, expected=phone,
            llr_best=llr_best, llr_best_origin=best_origin,
            llr_deletion=llr_deletion, llr_second_best=llr_second_best, llr_margin=llr_margin,
            gop_i=gop_i, gop_lpr_i=gop_lpr_i, top_competitor=top_competitor,
            dur_z=dur_z, entropy=entropy, raw_span=(start, end),
            position=_word_position(i, len(canonical)), syllable_count=syllable_count,
            frame_count_word=T,
        ))

    return WordFeatures(
        canonical=canonical, ll_canonical_per_frame=ll_canonical_per_frame,
        free_decode_gap=free_decode_gap, frame_count=T, positions=positions,
    )
