"""IPA (as produced by the phone recognizer) <-> ARPABET (as produced by
cmudict) mapping.

Originally written for allosaurus and now shared by scorer.py's wav2vec2
model too (see SETUP_NOTES.md for why the recognizer changed) - both are
*phone* recognizers rather than English-specific ones (allosaurus is
explicitly multilingual; the wav2vec2 model here was fine-tuned across ~60
languages), so either can emit narrow-transcription symbols (aspiration,
length marks, syllabic consonants, flaps, glottal stops) or even non-English
phones that never appear in cmudict's ARPABET inventory. This module
normalizes those down to the closest ARPABET phoneme so a recognized
sequence can be aligned against and compared with the canonical one.

See SETUP_NOTES.md for the reasoning behind the harder allophone decisions
(flap, glottal stop, dark L, nasalized vowels) and which symbols could not be
mapped cleanly.
"""
import logging
import unicodedata

logger = logging.getLogger("speechpal.ipa_arpabet")

# Combining diacritics we strip before lookup: aspiration, length, nasalization,
# palatalization, velarization, syllabicity, stress/tone marks that allosaurus
# sometimes emits attached to a base symbol.
_STRIP_CHARS = {
    "ʰ",  # ʰ aspiration
    "ː",  # ː length
    "ˑ",  # ˑ half-length
    "̃",  # ̃ combining tilde (nasalization)
    "ʲ",  # ʲ palatalization
    "ˠ",  # ˠ velarization
    "̩",  # ̩ combining syllabic mark
    "̝",  # ̝ raised
    "̞",  # ̞ lowered
    "̤",  # ̤ breathy voice
    "˞",  # ˞ rhotacization (handled separately for ɚ/ɝ but strip if trailing on others)
}


def _strip_diacritics(symbol: str) -> str:
    normalized = unicodedata.normalize("NFD", symbol)
    return "".join(ch for ch in normalized if ch not in _STRIP_CHARS)


# Core mapping: one IPA symbol (as it appears in allosaurus's eng inventory,
# post diacritic-stripping) -> one ARPABET phoneme (stress-free).
IPA_TO_ARPABET: dict[str, str] = {
    # --- Vowels ---
    "i": "IY",
    "ɪ": "IH",
    "ɪ̈": "IH",
    "e": "EY",
    "eɪ": "EY",
    "ɛ": "EH",
    "æ": "AE",
    "a": "AA",
    "ɑ": "AA",
    "ɒ": "AA",  # British "hot" vowel, closest ARPABET is AA
    "ʌ": "AH",
    "ə": "AH",  # unstressed schwa collapses to AH once stress digits are stripped
    "ɐ": "AH",
    "ɔ": "AO",
    "o": "OW",
    "oʊ": "OW",
    "u": "UW",
    "ʉ": "UW",
    "ʊ": "UH",
    "aʊ": "AW",
    "aɪ": "AY",
    "ɔɪ": "OY",
    "ɝ": "ER",  # stressed rhotacized schwa ("bird")
    "ɚ": "ER",  # unstressed rhotacized schwa ("butter")
    "ɜ": "ER",  # British open-mid central, closest to ER
    "ɹ̩": "ER",  # syllabic r
    "n̩": "N",  # syllabic n ("button")
    "l̩": "L",  # syllabic l ("bottle")
    "əl": "L",  # syllabic l, alternate transcription some recognizers emit
    "m̩": "M",  # syllabic m ("rhythm")
    "ᵻ": "IH",  # near-close central unrounded vowel: common American allophone of unstressed I
    # --- Stops ---
    "p": "P",
    "b": "B",
    "t": "T",
    "d": "D",
    "k": "K",
    "ɡ": "G",
    "g": "G",  # ASCII g, some tools emit this instead of U+0261
    "ʔ": "T",  # glottal stop: common allophone of /t/ in American English ("kitten")
    "ɾ": "T",  # alveolar flap: common allophone of /t/ or /d/ ("butter", "ladder")
    # --- Fricatives ---
    "f": "F",
    "v": "V",
    "θ": "TH",
    "ð": "DH",
    "s": "S",
    "z": "Z",
    "ʃ": "SH",
    "ʒ": "ZH",
    "h": "HH",
    "ɦ": "HH",  # breathy-voiced h allophone
    "x": "K",  # voiceless velar fricative (loanwords like "loch"); no ARPABET equivalent, nearest is K
    # --- Affricates ---
    "tʃ": "CH",
    "dʒ": "JH",
    # --- Nasals ---
    "m": "M",
    "n": "N",
    "ŋ": "NG",
    # --- Liquids & glides ---
    "l": "L",
    "ɫ": "L",  # dark/velarized l allophone ("full")
    "ɹ": "R",
    "r": "R",  # trilled r symbol, allosaurus rarely emits it for English but map it defensively
    "ɻ": "R",  # retroflex r allophone
    "w": "W",
    "ʍ": "W",  # voiceless w ("wh-"), collapses to W since ARPABET has no separate symbol
    "j": "Y",
}


def normalize_and_map(ipa_symbol: str) -> str | None:
    """Map one raw IPA symbol to ARPABET, or None if it cannot be mapped.

    Logs a warning (not an exception) for anything unmapped so a single odd
    symbol from the recognizer never crashes a scoring request.
    """
    stripped = _strip_diacritics(ipa_symbol).strip()
    if not stripped:
        return None
    if stripped in IPA_TO_ARPABET:
        return IPA_TO_ARPABET[stripped]
    # Retry without stripping, in case the raw symbol (not the NFD-stripped one)
    # is already a direct key (covers precomposed symbols like "ɡ").
    if ipa_symbol in IPA_TO_ARPABET:
        return IPA_TO_ARPABET[ipa_symbol]
    logger.warning("Unmapped IPA symbol from recognizer: %r (stripped: %r)", ipa_symbol, stripped)
    return None


def map_ipa_sequence(ipa_symbols: list[str]) -> list[str]:
    """Map a full recognized IPA sequence to ARPABET, dropping unmapped symbols."""
    mapped = []
    for sym in ipa_symbols:
        arpabet = normalize_and_map(sym)
        if arpabet is not None:
            mapped.append(arpabet)
    return mapped


def strip_stress(arpabet_phonemes: list[str]) -> list[str]:
    """Strip stress digits from cmudict ARPABET phonemes: 'AE1' -> 'AE'."""
    return [p.rstrip("0123456789") for p in arpabet_phonemes]
