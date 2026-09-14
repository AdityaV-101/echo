// Finds the substring in a word most likely to correspond to its target
// ARPABET phoneme, for highlighting "the m in mug" inside the word itself.
// A heuristic (real grapheme-to-phoneme alignment is a much bigger problem)
// - good enough for this app's mostly-simple, mostly-initial-consonant
// curriculum words, not claimed to be phonetically rigorous.
const PHONEME_TO_GRAPHEME = {
  HH: "h", NG: "ng", SH: "sh", CH: "ch", TH: "th", DH: "th", JH: "j",
  WH: "wh", QU: "qu",
};

function graphemeFor(phoneme) {
  if (!phoneme) return null;
  const upper = phoneme.toUpperCase();
  if (PHONEME_TO_GRAPHEME[upper]) return PHONEME_TO_GRAPHEME[upper];
  return upper[0]?.toLowerCase() || null;
}

// Returns [{text, highlight}] segments to render - highlight=true for the
// matched grapheme's first occurrence, false otherwise. Falls back to no
// highlight (single non-highlighted segment) if nothing matches.
export function highlightSegments(word, targetPhoneme) {
  const grapheme = graphemeFor(targetPhoneme);
  if (!word || !grapheme) return [{ text: word || "", highlight: false }];
  const idx = word.toLowerCase().indexOf(grapheme);
  if (idx === -1) return [{ text: word, highlight: false }];
  const segments = [];
  if (idx > 0) segments.push({ text: word.slice(0, idx), highlight: false });
  segments.push({ text: word.slice(idx, idx + grapheme.length), highlight: true });
  if (idx + grapheme.length < word.length) segments.push({ text: word.slice(idx + grapheme.length), highlight: false });
  return segments;
}
