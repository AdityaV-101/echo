"""Forced-alignment + Goodness-of-Pronunciation (GOP) phoneme scorer.

Replaces the old free-recognition-plus-diffing approach entirely (see
DIAGNOSIS.md for exactly what was wrong with it). The word the child was
asked to say is always known in advance, so this never guesses at what
sequence of phones was produced or where in the recording each one landed:
torchaudio's CTC forced_align computes the actual optimal frame boundaries
for the *known* target sequence, and GOP measures how much the model's own
posterior at those frames favored the intended phone over every alternative.
"""
import logging
from dataclasses import dataclass, field

import torch
from torchaudio.functional import forced_align, merge_tokens

import model_vocab
from ipa_arpabet import normalize_and_map

logger = logging.getLogger("speechpal.gop_scorer")

_MODEL_NAME = "facebook/wav2vec2-lv-60-espeak-cv-ft"
_TOP_COMPETITORS_KEPT = 3

_PROCESSOR = None
_MODEL = None
_VOCAB: dict[str, int] | None = None
_ID_TO_SYMBOL: dict[int, str] | None = None
_BLANK_ID: int | None = None
_ENGLISH_VOCAB_IDS: set[int] | None = None
_FRAME_SECONDS = 0.02  # wav2vec2's standard stride: 320 samples at 16kHz


def get_model():
    """Lazily load the processor/model once per process, then verify the
    ARPABET->vocab mapping against this exact model's tokenizer before
    ever serving a request - a bad mapping here would silently align every
    word against the wrong target, which is precisely the class of bug
    this rebuild exists to eliminate. See model_vocab.verify_vocab_coverage."""
    global _PROCESSOR, _MODEL, _VOCAB, _ID_TO_SYMBOL, _BLANK_ID, _ENGLISH_VOCAB_IDS
    if _MODEL is None:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        logger.info("Loading wav2vec2 phoneme recognizer (first request only, may download weights)...")
        _PROCESSOR = Wav2Vec2Processor.from_pretrained(_MODEL_NAME)
        _MODEL = Wav2Vec2ForCTC.from_pretrained(_MODEL_NAME)
        _MODEL.eval()
        _VOCAB = _PROCESSOR.tokenizer.get_vocab()
        _ID_TO_SYMBOL = {v: k for k, v in _VOCAB.items()}
        _BLANK_ID = _PROCESSOR.tokenizer.pad_token_id
        model_vocab.verify_vocab_coverage(_VOCAB)
        # This model's vocabulary spans ~60 languages (see model_vocab.py's
        # module docstring); only ~39 of its ~388 symbols are English
        # phonemes. Restricting competitor ranking to this subset is what
        # keeps "you said X instead of Y" meaningful - without it, the top
        # "competitor" for a frame is frequently a Mandarin tone-marked
        # vowel or similar (confirmed directly during eval: symbols like
        # "iɛ5" and "ts." topped the competitor list for ordinary English
        # words), which is useless as a therapist-facing explanation and
        # was never a real alternative interpretation of the child's speech.
        _ENGLISH_VOCAB_IDS = {
            vid for symbol, vid in _VOCAB.items() if normalize_and_map(symbol) is not None
        }
        logger.info(
            "wav2vec2 phoneme recognizer loaded; vocab verified; blank_id=%d; %d/%d vocab symbols are English-mappable",
            _BLANK_ID, len(_ENGLISH_VOCAB_IDS), len(_VOCAB),
        )
    return _PROCESSOR, _MODEL, _VOCAB, _ID_TO_SYMBOL, _BLANK_ID


@dataclass
class PhonemeResult:
    index: int
    expected: str  # ARPABET
    start_ms: float
    end_ms: float
    gop: float
    competitors: list[tuple[str, float]] = field(default_factory=list)  # [(ARPABET or raw IPA, mean_posterior), ...]

    @property
    def top_competitor(self) -> str | None:
        return self.competitors[0][0] if self.competitors else None


def compute_log_probs(processor, model, audio) -> tuple[torch.Tensor, float]:
    """Step 1: frame-level log-probabilities, not the decoded string.
    Returns (log_probs [T, V], frame_seconds)."""
    inputs = processor(audio, sampling_rate=16000, return_tensors="pt")
    with torch.inference_mode():
        logits = model(inputs.input_values).logits  # [1, T, V]
        log_probs = torch.log_softmax(logits, dim=-1)[0]  # [T, V]
    num_frames = log_probs.shape[0]
    frame_seconds = (len(audio) / 16000) / num_frames if num_frames else 0.0
    logger.info(
        "compute_log_probs: audio=%.3fs frames=%d frame_seconds=%.4f (nominal %.4f)",
        len(audio) / 16000, num_frames, frame_seconds, _FRAME_SECONDS,
    )
    return log_probs, frame_seconds


def align_canonical(log_probs: torch.Tensor, canonical: list[str], vocab: dict[str, int], blank_id: int):
    """Step 2: forced-align the *known* canonical ARPABET sequence against
    log_probs. Because forced_align is constrained to exactly this target
    sequence, there is no free recognition, no guessed windows, and no
    possibility of the aligner substituting or reordering phones - every
    span corresponds 1:1, in order, to canonical's phonemes."""
    target_ids = model_vocab.arpabet_sequence_to_vocab_ids(canonical, vocab)
    targets = torch.tensor([target_ids], dtype=torch.int32)
    log_probs_batched = log_probs.unsqueeze(0)  # [1, T, V]
    aligned_labels, aligned_scores = forced_align(log_probs_batched, targets, blank=blank_id)
    spans = merge_tokens(aligned_labels[0], aligned_scores[0], blank=blank_id)
    if len(spans) != len(canonical):
        # Should never happen - forced_align is constrained to place every
        # target token somewhere. Fail loudly rather than silently
        # mis-indexing the rest of the pipeline against canonical.
        raise RuntimeError(
            f"forced_align produced {len(spans)} spans for {len(canonical)} canonical phonemes "
            f"({canonical}); refusing to score with a desynced alignment."
        )
    for i, (span, expected_id) in enumerate(zip(spans, target_ids)):
        if span.token != expected_id:
            raise RuntimeError(
                f"forced_align span {i} token {span.token} != expected {expected_id} for {canonical[i]!r}; "
                "alignment order assumption violated, refusing to score."
            )
    return spans


def _competitor_label(vocab_id: int) -> str:
    """Prefer the ARPABET label (consistent with the rest of the app's
    display vocabulary) when this model's symbol maps cleanly to one;
    otherwise fall back to the raw IPA symbol rather than hiding the
    competitor."""
    symbol = _ID_TO_SYMBOL[vocab_id]
    arpabet = normalize_and_map(symbol)
    return arpabet if arpabet is not None else symbol


def compute_gop(log_probs: torch.Tensor, span, expected_arpabet: str, blank_id: int) -> tuple[float, list[tuple[str, float]]]:
    """Step 3: GOP(p) = mean over frames in [start, end) of
    [log P(p|x_t) - max_q log P(q|x_t)]. Always <= 0 (the target's own
    log-prob can never exceed the max over everything including itself).

    Frames where blank dominates are excluded from the mean (a blank-
    dominant frame reflects the model finding no clear speech there, not
    evidence about how well this specific phone was produced), but at
    least one frame is always used - a span that collapses to entirely
    blank-dominated frames falls back to its single least-blank-dominant
    frame rather than producing no signal at all.

    Also returns the top _TOP_COMPETITORS_KEPT non-blank, non-target
    symbols by mean posterior probability across the kept frames - the
    named "you said X instead of Y" explanation for anything not scored
    correct.
    """
    start, end = int(span.start), int(span.end)
    if end <= start:
        end = start + 1
    end = min(end, log_probs.shape[0])
    start = min(start, max(end - 1, 0))

    target_id = span.token
    competitor_ids = _ENGLISH_VOCAB_IDS - {blank_id, target_id}

    frame_gops = []
    competitor_sum: dict[int, float] = {}
    kept_count = 0

    frame_indices = list(range(start, end))
    for t in frame_indices:
        frame_lp = log_probs[t]
        max_val, max_id = torch.max(frame_lp, dim=-1)
        if max_id.item() == blank_id:
            continue
        kept_count += 1
        frame_gops.append((frame_lp[target_id] - max_val).item())
        frame_probs = torch.exp(frame_lp)
        for vid in competitor_ids:
            competitor_sum[vid] = competitor_sum.get(vid, 0.0) + frame_probs[vid].item()

    if kept_count == 0:
        # Fallback: single best (least blank-dominant) frame in the span,
        # per GOP_MIN_FRAMES_FOR_MEAN - never return "no signal" for a
        # phoneme the aligner did place somewhere.
        t = start
        frame_lp = log_probs[t]
        max_val, max_id = torch.max(frame_lp, dim=-1)
        frame_gops = [(frame_lp[target_id] - max_val).item()]
        frame_probs = torch.exp(frame_lp)
        for vid in competitor_ids:
            competitor_sum[vid] = frame_probs[vid].item()
        kept_count = 1

    gop = sum(frame_gops) / len(frame_gops)

    ranked = sorted(competitor_sum.items(), key=lambda kv: kv[1], reverse=True)[:_TOP_COMPETITORS_KEPT]
    competitors = [(_competitor_label(vid), mean_sum / kept_count) for vid, mean_sum in ranked]

    return gop, competitors


def score_phonemes(canonical: list[str], audio) -> list[PhonemeResult]:
    """Full Steps 1-3 for one recording against one known canonical
    sequence: emissions, forced alignment, per-phoneme GOP + competitors."""
    processor, model, vocab, id_to_symbol, blank_id = get_model()
    log_probs, frame_seconds = compute_log_probs(processor, model, audio)
    spans = align_canonical(log_probs, canonical, vocab, blank_id)

    results = []
    for i, (expected, span) in enumerate(zip(canonical, spans)):
        gop, competitors = compute_gop(log_probs, span, expected, blank_id)
        results.append(
            PhonemeResult(
                index=i,
                expected=expected,
                start_ms=span.start * frame_seconds * 1000,
                end_ms=span.end * frame_seconds * 1000,
                gop=gop,
                competitors=competitors,
            )
        )
        logger.info(
            "phoneme[%d] %-4s [%.0f-%.0fms] gop=%.3f top_competitor=%s",
            i, expected, results[-1].start_ms, results[-1].end_ms, gop,
            competitors[0] if competitors else None,
        )
    return results
