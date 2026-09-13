"""Paired local likelihood-ratio scoring (Phase 1 of the rebuild).

Replaces hypothesis_scorer.py's whole-word candidate comparison, which had
three compounding problems (see DIAGNOSIS/the rebuild brief, all confirmed
directly against the code before this was written):

1. `score_candidates_raw`'s `-nll / target_lengths` divides the CTC
   log-likelihood by the WHOLE WORD's phoneme count. Every candidate here
   differs from canonical at exactly one position, so the real evidence is a
   handful of frames - dividing it by whole-word length crushes every
   margin toward zero, and a deletion candidate (different length) isn't
   even on the same scale as a substitution candidate.
2. `apply_prior_and_decide`'s `margin = best - second_best` over up to 40
   whole-word candidates, many near-duplicates, so the second-best is
   usually a near-clone of the best and the margin collapses into noise.
   "Which error" was being asked before "was there an error" was answered.
3. `F.ctc_loss(..., zero_infinity=True)` silently turns an infeasible
   candidate's loss into 0 - the single HIGHEST possible score - so an
   impossible candidate can win outright on a short recording.

The fix here is narrower and better-posed: for ONE target phoneme position i
in word W, build only the candidates that differ from canonical at i
(canonical itself, each clinically-plausible substitution, and deletion of
i), score each with the full CTC marginal likelihood (unchanged from
before - F.ctc_loss already computes the forward-algorithm marginal over
all alignments, not a Viterbi path; nothing to fix there), then normalize by
the LOCAL frame count around position i instead of the whole word's phoneme
count. Because every candidate at a given i is scored against the same
audio and differs from canonical only at that one position, speaker/mic/
model miscalibration is common to both sides of the comparison and mostly
cancels - this is what makes an adult-trained model usable on children's
speech at all.

`llr[s] = (LL(candidate_s) - LL(canonical)) / F` is a per-frame log-odds
against canonical: comparable across words of any length and across
different target positions, which target_lengths normalization never was.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import torch
import torch.nn.functional as F

import model_vocab
from gop_scorer import align_canonical

_DATA_DIR = Path(__file__).parent / "data"
_PROCESSES_PATH = _DATA_DIR / "phonological_processes.json"
_PROCESSES: dict | None = None


def _load_processes() -> dict:
    global _PROCESSES
    if _PROCESSES is None:
        with open(_PROCESSES_PATH) as f:
            raw = json.load(f)
        _PROCESSES = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _PROCESSES


def _substitutions_for(phone: str) -> list[tuple[str, str]]:
    """Returns [(new_phone, process_name), ...] - every documented
    phonological-process rule whose "from" matches this exact phone."""
    out = []
    for process_name, rules in _load_processes().items():
        for rule in rules:
            if rule["from"] == phone:
                out.append((rule["to"], process_name))
    return out


def _min_frames_for_ctc(seq: list[int]) -> int:
    """CTC's forced structure requires a blank between two identical
    consecutive labels (otherwise there is no way to distinguish "one long
    symbol" from "two separate occurrences" in the collapsed output) - so
    the true minimum input length for a target isn't just len(seq), it's
    len(seq) plus one extra frame per adjacent repeat. A candidate needing
    more frames than the recording has is infeasible and must never be
    scored as if zero-loss (bug 3) - it has to be excluded from ranking
    outright."""
    repeats = sum(1 for a, b in zip(seq, seq[1:]) if a == b)
    return len(seq) + repeats


@dataclass
class LocalCandidate:
    sequence: list[str]  # full-word ARPABET sequence, differs from canonical only at `index`
    origin: str  # "canonical" | process name | "deletion"


@dataclass
class PositionResult:
    index: int
    expected: str
    frame_span: tuple[int, int]  # local [a, b) used for LLR normalization
    frame_count: int  # F
    candidates: list[LocalCandidate]
    llrs: list[float]  # parallel to candidates; canonical's own entry is always 0.0
    feasible: list[bool]  # parallel to candidates - False entries are excluded from ranking

    @property
    def best_index(self) -> int:
        """Argmax LLR among feasible candidates only (bug 3's fix in
        practice: an infeasible candidate can never be returned here even
        if F.ctc_loss's zero_infinity flag internally reports it as 0)."""
        best_i, best_v = None, float("-inf")
        for i, (llr, ok) in enumerate(zip(self.llrs, self.feasible)):
            if ok and llr > best_v:
                best_i, best_v = i, llr
        return best_i if best_i is not None else 0  # canonical is always index 0 and always feasible


def generate_local_candidates(canonical: list[str], index: int) -> list[LocalCandidate]:
    """Canonical first (always index 0 in the returned list), then every
    documented substitution of canonical[index], then deletion of index
    (only if the word has more than one phoneme - deleting a word's only
    phoneme leaves nothing to align)."""
    candidates = [LocalCandidate(list(canonical), "canonical")]
    target_phone = canonical[index]
    for new_phone, process_name in _substitutions_for(target_phone):
        seq = list(canonical)
        seq[index] = new_phone
        candidates.append(LocalCandidate(seq, process_name))
    if len(canonical) > 1:
        seq = canonical[:index] + canonical[index + 1:]
        candidates.append(LocalCandidate(seq, "deletion"))
    return candidates


def _score_sequences_batched(
    log_probs: torch.Tensor, sequences: list[list[str]], vocab: dict[str, int], blank_id: int,
) -> tuple[list[float], list[bool]]:
    """One batched CTC call (the full forward-algorithm marginal, not a
    Viterbi path - torch's ctc_loss already computes this) for every unique
    sequence. Returns (log_likelihoods, feasible) parallel to `sequences` -
    feasible[i] is False (and log_likelihoods[i] is -inf) when
    _min_frames_for_ctc says this sequence cannot possibly align within the
    available frames, checked BEFORE calling ctc_loss so zero_infinity's
    silent 0-loss substitution never gets a chance to produce a winner."""
    T, V = log_probs.shape
    n = len(sequences)

    target_ids = [model_vocab.arpabet_sequence_to_vocab_ids(seq, vocab) for seq in sequences]
    feasible = [_min_frames_for_ctc(ids) <= T for ids in target_ids]

    target_seqs = [torch.tensor(ids if ids else [0], dtype=torch.long) for ids in target_ids]
    target_lengths = torch.tensor([len(ids) for ids in target_ids], dtype=torch.long)
    targets_padded = torch.nn.utils.rnn.pad_sequence(target_seqs, batch_first=True, padding_value=0)

    log_probs_batched = log_probs.unsqueeze(1).expand(T, n, V).contiguous()
    input_lengths = torch.full((n,), T, dtype=torch.long)

    nll = F.ctc_loss(
        log_probs_batched, targets_padded, input_lengths, target_lengths.clamp(min=1),
        blank=blank_id, reduction="none", zero_infinity=True,
    )
    log_likelihoods = (-nll).tolist()
    log_likelihoods = [ll if ok else float("-inf") for ll, ok in zip(log_likelihoods, feasible)]
    return log_likelihoods, feasible


def _local_frame_span(spans, index: int, n_frames: int) -> tuple[int, int]:
    """[a, b) = position i's own aligned span extended by one neighboring
    phoneme's span on each side (clipped at the word's own boundaries when
    i is initial or final - there is no neighbor to extend into)."""
    left = max(index - 1, 0)
    right = min(index + 1, len(spans) - 1)
    a = int(spans[left].start)
    b = int(spans[right].end)
    b = max(b, a + 1)
    b = min(b, n_frames)
    a = min(a, max(b - 1, 0))
    return a, b


def compute_paired_llr_for_word(
    log_probs: torch.Tensor, canonical: list[str], vocab: dict[str, int], blank_id: int,
) -> list[PositionResult]:
    """Paired LLR at every position in the word (production only ever needs
    the app's single designated target_phoneme index; eval needs every
    position since speechocean762 annotates every phoneme). Candidate
    sequences are batched across ALL positions in one CTC call - canonical
    is scored once and its log-likelihood reused everywhere, since it never
    changes position to position."""
    spans = align_canonical(log_probs, canonical, vocab, blank_id)
    n_frames = log_probs.shape[0]

    per_position_candidates = [generate_local_candidates(canonical, i) for i in range(len(canonical))]

    # Dedupe sequences across the whole word (a substitution at i can
    # coincide with canonical at some other unrelated word, though never
    # with a DIFFERENT position's candidate in the same word since they
    # differ from canonical at different indices - dedupe is mostly for
    # canonical itself, requested by every position).
    seq_to_slot: dict[tuple, int] = {}
    all_sequences: list[list[str]] = []
    slot_lookup: list[list[int]] = []  # parallel to per_position_candidates[i], gives slot per candidate
    for candidates in per_position_candidates:
        slots = []
        for cand in candidates:
            key = tuple(cand.sequence)
            if key not in seq_to_slot:
                seq_to_slot[key] = len(all_sequences)
                all_sequences.append(cand.sequence)
            slots.append(seq_to_slot[key])
        slot_lookup.append(slots)

    log_likelihoods, feasible = _score_sequences_batched(log_probs, all_sequences, vocab, blank_id)
    canonical_ll = log_likelihoods[seq_to_slot[tuple(canonical)]]

    results = []
    for i, (candidates, slots) in enumerate(zip(per_position_candidates, slot_lookup)):
        a, b = _local_frame_span(spans, i, n_frames)
        frame_count = max(b - a, 1)
        llrs = [(log_likelihoods[slot] - canonical_ll) / frame_count for slot in slots]
        cand_feasible = [feasible[slot] for slot in slots]
        results.append(PositionResult(
            index=i, expected=canonical[i], frame_span=(a, b), frame_count=frame_count,
            candidates=candidates, llrs=llrs, feasible=cand_feasible,
        ))
    return results
