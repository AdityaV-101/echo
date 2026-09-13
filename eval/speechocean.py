"""Real-speech eval set built from speechocean762 (mispeech/speechocean762 on
HuggingFace, also published as OpenSLR SLR101). Replaces the espeak-ng
synthetic corpus as the source of truth for accuracy numbers and calibration
priors: espeak is formant synthesis, acoustically nothing like the human
speech wav2vec2 was trained on, so thresholds fit against it don't transfer.
speechocean762 is 5000 real English utterances (half children, half adults),
every word scored 0-2 per phoneme by 5 experts, with explicit annotated
substitutions when a phoneme was mispronounced - exactly the ground truth
this app's scorer claims to produce.

Dataset schema actually observed (verified against the live dataset, not
assumed - see the coverage report this module prints when run directly):

- utterance-level fields: text, words, speaker, gender, age, audio.
  train=2500 examples, test=2500 - used here as dev/held-out, matching the
  dataset's own published split rather than an arbitrary one. Never tune
  against the test split; see run_eval usage in run_eval.py.
- per word: phones (ARPABET + stress digit, e.g. "IY0"), phones-accuracy
  (list of 0.0-2.0 expert-consensus scores, one per phone, in steps of 0.2 -
  5 raters each scoring 0/1/2), mispronunciations: a list of
  {canonical-phone, index, pronounced-phone}, present only for phones
  scored below 2.0.
- there is no word- or phone-level timing in the dataset. Word audio spans
  are recovered here by forced-aligning the *whole sentence's* canonical
  phone sequence against the whole utterance in one pass (standard CTC
  forced alignment already lets blank frames absorb inter-word pauses - no
  special handling needed), then grouping the resulting phone spans back
  into words using each word's own phone count.
- pronounced-phone ground truth uses a few dataset-specific conventions on
  top of plain ARPABET (verified across all 3403 mispronunciation
  annotations in both splits combined): "<DEL>" (846 occurrences) means the
  phone was dropped entirely; "<unk>" (820) means the annotator couldn't
  identify a specific substitute; a trailing "*" (~220 occurrences, e.g.
  "R*") marks a weakly/reduced realization of the base phone and is
  stripped; a residual 71 entries (~2%) are two-token labels ("IH R",
  "D Z", ...) whose meaning isn't self-evident from the data alone - these
  are kept as category "ambiguous" and excluded from substitution-accuracy
  scoring rather than guessed at. See _normalize_pronounced_phone.
- age ranges 6-15 for children (2440 utterances total) and 19-43 for adults
  (2560 utterances) with a clean gap between 15 and 19 - --children-only
  filters to age <= CHILD_MAX_AGE.

Canonical phones were checked against every one of the 39 keys in
model_vocab.ARPABET_TO_MODEL_VOCAB: 100% coverage, zero unmapped, across
all 31,816 words in both splits combined.
"""
import argparse
import io
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import model_vocab  # noqa: E402
from gop_scorer import align_canonical, compute_log_probs, get_model  # noqa: E402

EVAL_DIR = Path(__file__).parent
CACHE_DIR = EVAL_DIR / "speechocean_cache"
UTT_AUDIO_DIR = CACHE_DIR / "utt_audio"
ALIGN_CACHE_PATH = CACHE_DIR / "alignment_cache.json"

CHILD_MAX_AGE = 15  # verified gap in the real age distribution: 6-15 vs 19-43
WORD_MARGIN_MS = 80  # pad beyond the outer aligned phone boundary per word
TARGET_SR = 16000

_VOCAB_KEYS = set(model_vocab.ARPABET_TO_MODEL_VOCAB.keys())


def _strip_stress(phone: str) -> str:
    return re.sub(r"[0-9]+$", "", phone)


def _normalize_pronounced_phone(raw: str) -> tuple[str, str | None]:
    """Returns (category, value). category is one of:
    "phone" (value is a real ARPABET phone in our vocab),
    "deleted" (the phone was dropped, dataset's own "<DEL>"),
    "unknown" (annotator couldn't identify it, "<unk>"),
    "ambiguous" (a dataset convention we don't confidently interpret -
    logged by the caller, excluded from substitution-accuracy scoring)."""
    if raw == "<DEL>":
        return "deleted", None
    if raw == "<unk>":
        return "unknown", None
    candidate = raw.rstrip("*")
    candidate = _strip_stress(candidate)
    if candidate in _VOCAB_KEYS:
        return "phone", candidate
    return "ambiguous", raw


@dataclass
class WordItem:
    utt_id: str
    split: str
    word_index: int
    text: str
    canonical: list[str]
    phones_accuracy: list[float]
    mispronunciations: list[dict] = field(default_factory=list)
    is_child: bool = False
    age: int = 0
    gender: str = ""
    speaker: str = ""
    start_ms: float = 0.0
    end_ms: float = 0.0
    utt_audio_path: str = ""


def _load_raw_dataset():
    from datasets import Audio, load_dataset

    ds = load_dataset("mispeech/speechocean762")
    return ds.cast_column("audio", Audio(decode=False))


def _decode_audio_bytes(raw_bytes: bytes) -> tuple[np.ndarray, int]:
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(raw_bytes), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != TARGET_SR:
        import torch
        import torchaudio

        audio = torchaudio.functional.resample(
            torch.from_numpy(audio), sr, TARGET_SR
        ).numpy()
        sr = TARGET_SR
    return audio, sr


def _peak_normalize(audio: np.ndarray) -> np.ndarray:
    peak = np.abs(audio).max()
    if peak < 1e-6:
        return audio
    return audio / peak * 0.95


def _load_align_cache() -> dict:
    if ALIGN_CACHE_PATH.exists():
        with open(ALIGN_CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_align_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALIGN_CACHE_PATH, "w") as f:
        json.dump(cache, f)


def _align_utterance(utt_id: str, audio: np.ndarray, canonical: list[str], cache: dict) -> list[tuple[int, int]]:
    """Forced-aligns the whole sentence's canonical phone sequence against
    the whole utterance in one pass. Returns [(start_frame, end_frame), ...]
    parallel to canonical. Cached by utt_id since this is the expensive
    (model inference) step and Step 4 will need to re-run it per candidate
    recognizer model."""
    if utt_id in cache:
        return [tuple(span) for span in cache[utt_id]]

    processor, model, vocab, id_to_symbol, blank_id = get_model()
    log_probs, frame_seconds = compute_log_probs(processor, model, audio)
    spans = align_canonical(log_probs, canonical, vocab, blank_id)
    result = [(int(s.start), int(s.end)) for s in spans]
    cache[utt_id] = result
    cache["_frame_seconds__" + utt_id] = frame_seconds
    return result


def iter_words(split: str, children_only: bool = False, limit: int | None = None, verbose: bool = True):
    """Yields WordItem records for one split ("train" or "test"). Decodes
    and caches each utterance's audio once (as a wav under
    speechocean_cache/utt_audio/) and its forced-alignment spans once (in
    alignment_cache.json), then slices word audio from those cached spans
    on the fly - no per-word audio files are materialized."""
    import soundfile as sf

    ds = _load_raw_dataset()
    split_ds = ds[split]
    align_cache = _load_align_cache()
    UTT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    n_yielded = 0
    unmapped_pronounced = {}
    for idx in range(len(split_ds)):
        ex = split_ds[idx]
        age = ex["age"]
        is_child = age <= CHILD_MAX_AGE
        if children_only and not is_child:
            continue

        utt_id = f"{split}_{idx:05d}"
        words = ex["words"]
        canonical_all = []
        word_phone_counts = []
        for w in words:
            phones = [_strip_stress(p) for p in w["phones"]]
            canonical_all.extend(phones)
            word_phone_counts.append(len(phones))

        if not canonical_all:
            continue

        audio, sr = _decode_audio_bytes(ex["audio"]["bytes"])
        audio = _peak_normalize(audio)

        utt_wav_path = UTT_AUDIO_DIR / f"{utt_id}.wav"
        if not utt_wav_path.exists():
            sf.write(str(utt_wav_path), audio, sr)

        try:
            spans = _align_utterance(utt_id, audio, canonical_all, align_cache)
        except RuntimeError as e:
            if verbose:
                print(f"[{utt_id}] alignment failed, skipping utterance: {e}")
            continue
        frame_seconds = align_cache["_frame_seconds__" + utt_id]

        cursor = 0
        for w_idx, (w, n_phones) in enumerate(zip(words, word_phone_counts)):
            word_spans = spans[cursor:cursor + n_phones]
            cursor += n_phones
            if not word_spans:
                continue
            start_ms = max(0.0, word_spans[0][0] * frame_seconds * 1000 - WORD_MARGIN_MS)
            end_ms = word_spans[-1][1] * frame_seconds * 1000 + WORD_MARGIN_MS

            mispron = []
            for m in w["mispronunciations"]:
                category, value = _normalize_pronounced_phone(m["pronounced-phone"])
                if category == "ambiguous":
                    unmapped_pronounced[m["pronounced-phone"]] = unmapped_pronounced.get(m["pronounced-phone"], 0) + 1
                mispron.append({
                    "index": m["index"],
                    "canonical_phone": _strip_stress(m["canonical-phone"]),
                    "category": category,
                    "pronounced_phone": value,
                    "raw": m["pronounced-phone"],
                })

            yield WordItem(
                utt_id=utt_id,
                split=split,
                word_index=w_idx,
                text=w["text"],
                canonical=[_strip_stress(p) for p in w["phones"]],
                phones_accuracy=list(w["phones-accuracy"]),
                mispronunciations=mispron,
                is_child=is_child,
                age=age,
                gender=ex["gender"],
                speaker=ex["speaker"],
                start_ms=start_ms,
                end_ms=end_ms,
                utt_audio_path=str(utt_wav_path.relative_to(EVAL_DIR)),
            )
            n_yielded += 1

        if limit is not None and n_yielded >= limit:
            break

    _save_align_cache(align_cache)
    if verbose and unmapped_pronounced:
        print(f"[speechocean] {sum(unmapped_pronounced.values())} ambiguous pronounced-phone labels "
              f"excluded from substitution scoring: {unmapped_pronounced}")


def load_word_audio(item: WordItem) -> np.ndarray:
    """Slices one word's audio out of its cached utterance wav, using the
    start/end ms already computed (with margin) during alignment."""
    import soundfile as sf

    audio, sr = sf.read(str(EVAL_DIR / item.utt_audio_path), dtype="float32")
    start = int(item.start_ms / 1000 * sr)
    end = int(item.end_ms / 1000 * sr)
    return audio[max(0, start):min(len(audio), end)]


def build_manifest(split: str, children_only: bool = False, limit: int | None = None) -> Path:
    suffix = "_children" if children_only else ""
    out_path = EVAL_DIR / f"speechocean_{split}{suffix}.jsonl"
    n = 0
    n_mispron = 0
    with open(out_path, "w") as f:
        for item in iter_words(split, children_only=children_only, limit=limit):
            f.write(json.dumps(asdict(item)) + "\n")
            n += 1
            n_mispron += sum(1 for pa in item.phones_accuracy if pa < 2.0)
            if n % 500 == 0:
                print(f"  ...{n} words written")
    print(f"wrote {n} words ({n_mispron} phones scored <2.0) to {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev", help="dev=train split, test=held-out split (never tune against it)")
    parser.add_argument("--children-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="cap on number of words (for a quick smoke run)")
    args = parser.parse_args()

    split = "train" if args.split == "dev" else "test"
    build_manifest(split, children_only=args.children_only, limit=args.limit)
