"""cmudict lookup: the one piece of the pre-rebuild scoring pipeline that's
still needed. Everything else that used to live in this file (free-
recognition alignment, guessed time windows, confidence-window scoring) was
replaced outright by forced-alignment + GOP scoring - see DIAGNOSIS.md and
gop_scorer.py - rather than patched, per explicit instruction. This module
now only answers "what's the canonical ARPABET phoneme sequence for this
word," which the new scorer still needs (forced alignment has to be told
what sequence to align against).
"""
import cmudict

_CMU_DICT = None


def get_cmudict() -> dict:
    global _CMU_DICT
    if _CMU_DICT is None:
        _CMU_DICT = cmudict.dict()
    return _CMU_DICT


def _single_word_phonemes(word: str) -> list[str] | None:
    d = get_cmudict()
    entries = d.get(word.lower().strip())
    if not entries:
        return None
    first_variant = entries[0]
    return [p.rstrip("0123456789") for p in first_variant]


def canonical_phonemes_for_word(word: str) -> list[str] | None:
    """Look up the first pronunciation variant in cmudict, stress digits stripped.

    cmudict only has single-word entries, so a multi-word phrase (used by the
    Tier 5 practice items, e.g. "the red rabbit ran") is split on whitespace
    and each word's phonemes are looked up and concatenated. Returns None if
    none of the words resolved.
    """
    word = word.strip()
    if " " not in word:
        return _single_word_phonemes(word)

    combined: list[str] = []
    any_found = False
    for part in word.split():
        part_phonemes = _single_word_phonemes(part)
        if part_phonemes is not None:
            any_found = True
            combined.extend(part_phonemes)
    return combined if any_found else None
