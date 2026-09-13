"""Maps cmudict ARPABET phonemes to facebook/wav2vec2-lv-60-espeak-cv-ft's
own tokenizer vocabulary, for forced alignment (torchaudio.functional.
forced_align needs the target sequence expressed as this model's vocab ids,
not generic IPA and not ARPABET).

Every symbol below was obtained empirically, not guessed: phonemizer's
espeak-ng backend (en-us, the same phonemizer configuration this model's
training data - CommonVoice transcripts - was labeled with) was run on a
word chosen to isolate each ARPABET phoneme, and the resulting IPA symbol
is what's recorded here. See the "ARPABET -> espeak-ng ground truth" table
in SETUP_NOTES.md for the exact word used for each phoneme and the
phonemizer output that produced it.

Every symbol was then checked directly against
Wav2Vec2Processor.from_pretrained(...).tokenizer.get_vocab() - see
verify_vocab_coverage() below, which is called at startup (in
_get_model()) specifically so a bad or stale mapping fails loudly instead
of silently producing garbage alignments.

A few phonemes need a documented judgment call because cmudict collapses a
distinction espeak's phonemizer preserves:
- AH: cmudict uses this for both the stressed vowel in "sun"/"thumb" (ʌ)
  and the unstressed schwa in "sofa" (ə) or "about" (ɐ) - stress digits are
  stripped before this app ever sees the phoneme (see
  canonical_phonemes_for_word), so there is no signal left to pick between
  them. ʌ (the stressed/citation form) is used as the representative.
- ER: same issue - cmudict's ER covers both the stressed rhotic vowel in
  "bird" (ɜː) and the unstressed one in "measure"/"butter" (ɚ). ɜː is used,
  since this app's Vocalic R practice track targets are mostly stressed
  ("bird"-type words).
Neither judgment call affects a CLINICAL_TARGET_PHONEMES consonant (see
scorer_common.py) - AH and ER are only ever context vowels here, and this
app never targets a vowel.
"""
import logging

logger = logging.getLogger("speechpal.model_vocab")

ARPABET_TO_MODEL_VOCAB: dict[str, str] = {
    "AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "EH": "ɛ", "ER": "ɜː",
    "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h", "IH": "ɪ", "IY": "iː",
    "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ",
    "T": "t", "TH": "θ", "UH": "ʊ", "UW": "uː", "V": "v", "W": "w",
    "Y": "j", "Z": "z", "ZH": "ʒ",
}

# Every ARPABET phoneme cmudict can produce (post stress-stripping), used
# only to make verify_vocab_coverage's completeness check explicit rather
# than implicitly trusting ARPABET_TO_MODEL_VOCAB's own key set.
ALL_ENGLISH_ARPABET_PHONEMES = frozenset(ARPABET_TO_MODEL_VOCAB.keys())


def verify_vocab_coverage(vocab: dict[str, int]) -> None:
    """Fail loudly at startup if any English phoneme's mapped symbol isn't
    actually in the model's vocabulary. A silent bad mapping here would
    mean forced_align silently aligns against the wrong sound - the whole
    point of this rebuild was to stop tolerating exactly that kind of
    silent failure, so this raises rather than logs."""
    missing = [
        (arpabet, symbol)
        for arpabet, symbol in ARPABET_TO_MODEL_VOCAB.items()
        if symbol not in vocab
    ]
    if missing:
        raise RuntimeError(
            "model_vocab.ARPABET_TO_MODEL_VOCAB has entries not present in "
            f"the loaded model's tokenizer vocabulary: {missing}. Refusing "
            "to start the real scorer - forced alignment against a symbol "
            "the model doesn't have would silently misalign every word "
            "containing that phoneme."
        )
    logger.info("model_vocab: all %d ARPABET phonemes verified present in model vocab.", len(ARPABET_TO_MODEL_VOCAB))


def arpabet_sequence_to_vocab_ids(canonical: list[str], vocab: dict[str, int]) -> list[int]:
    """Map a canonical ARPABET phoneme sequence (from cmudict) to this
    model's vocab ids, for forced_align's `targets` argument. Raises with a
    clear message on an unmapped phoneme rather than silently dropping it -
    dropping a phoneme here would desync the alignment from the canonical
    sequence's indices, silently corrupting every phoneme after the drop."""
    ids = []
    for phoneme in canonical:
        symbol = ARPABET_TO_MODEL_VOCAB.get(phoneme)
        if symbol is None:
            raise ValueError(f"No model-vocab mapping for ARPABET phoneme {phoneme!r}")
        vocab_id = vocab.get(symbol)
        if vocab_id is None:
            raise ValueError(f"Mapped symbol {symbol!r} for {phoneme!r} not found in model vocab")
        ids.append(vocab_id)
    return ids
