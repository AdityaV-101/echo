// One inline SVG sprite sheet, one <symbol> per word, referenced via
// <use href="#word-X">. Style: simple bold flat shapes, one thick outline
// colour, 2-3 fills, readable at both 240px (practice screen hero) and
// 80px (level/track pickers). No photo-realism, no gradients, no emoji.
//
// Coverage is intentionally partial and honest, not a placeholder-for-
// everything promise: WORD_ART_COVERAGE below lists exactly which words
// have real art. Words that are inherently abstract (function words like
// "no"/"we"/"yes"/"wet"/"hop"/"yum" - nothing concrete to draw that a
// 4-year-old would recognize faster than the word itself) are left to the
// themed fallback card (WordCard.jsx) on purpose, not as a gap to fill
// later - forcing a literal icon onto an abstract word would be worse than
// a well-designed fallback. See DESIGN_NOTES.md for the running tally of
// which concrete-noun words still need art (tiers 2-4, not done this run).
//
// Palette below is the CURRENT (pre-Part-7) app palette - Part 7 swaps
// these to real per-theme CSS custom properties; each shape's fill here
// already uses var(--word-art-*) tokens so that swap doesn't require
// touching this file again.
const OUTLINE = "var(--word-art-outline, #3a2a1e)";

export const WORD_ART_COVERAGE = new Set([
  "ball", "bed", "bus", "cup", "dog", "door", "duck", "ham", "hat", "hen",
  "man", "map", "moon", "mud", "mug", "net", "nose", "pen", "pig", "pot",
  "pup", "top", "web",
]);

export function hasWordArt(word) {
  return WORD_ART_COVERAGE.has((word || "").toLowerCase());
}

export default function WordArtSprite() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <defs>
        <symbol id="word-mug" viewBox="0 0 100 100">
          <path d="M20 30 h44 v42 a10 10 0 0 1 -10 10 h-24 a10 10 0 0 1 -10 -10 Z" fill="var(--word-art-1, #ff9d6c)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <path d="M64 40 q18 0 18 16 t-18 16" fill="none" stroke={OUTLINE} strokeWidth="5" strokeLinecap="round" />
          <ellipse cx="42" cy="30" rx="22" ry="6" fill="var(--word-art-2, #ffcda3)" stroke={OUTLINE} strokeWidth="4" />
        </symbol>

        <symbol id="word-moon" viewBox="0 0 100 100">
          <path d="M62 15 A38 38 0 1 0 62 85 A30 30 0 0 1 62 15 Z" fill="var(--word-art-1, #ffd166)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <circle cx="45" cy="35" r="4" fill="var(--word-art-2, #fff3c4)" />
          <circle cx="38" cy="52" r="3" fill="var(--word-art-2, #fff3c4)" />
        </symbol>

        <symbol id="word-map" viewBox="0 0 100 100">
          <path d="M15 22 L38 15 L62 22 L85 15 V78 L62 85 L38 78 L15 85 Z" fill="var(--word-art-1, #a8e0b4)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <line x1="38" y1="15" x2="38" y2="78" stroke={OUTLINE} strokeWidth="3.5" strokeDasharray="3 5" />
          <line x1="62" y1="22" x2="62" y2="85" stroke={OUTLINE} strokeWidth="3.5" strokeDasharray="3 5" />
          <path d="M50 38 q0 14 -10 20 q10 6 10 18 q0 -12 10 -18 q-10 -6 -10 -20 Z" fill="var(--word-art-2, #ff6b6b)" stroke={OUTLINE} strokeWidth="3" />
        </symbol>

        <symbol id="word-man" viewBox="0 0 100 100">
          <circle cx="50" cy="28" r="16" fill="var(--word-art-1, #ffcda3)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M28 88 Q28 55 50 55 Q72 55 72 88 Z" fill="var(--word-art-2, #7bb0e0)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
        </symbol>

        <symbol id="word-ball" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="36" fill="var(--word-art-1, #ff6b6b)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M50 14 V86 M18 50 H82 M26 26 Q50 50 74 26 M26 74 Q50 50 74 74" fill="none" stroke={OUTLINE} strokeWidth="3.5" strokeLinecap="round" />
        </symbol>

        <symbol id="word-bed" viewBox="0 0 100 100">
          <rect x="12" y="55" width="76" height="12" rx="4" fill="var(--word-art-1, #c9a4ff)" stroke={OUTLINE} strokeWidth="5" />
          <rect x="16" y="30" width="30" height="26" rx="6" fill="var(--word-art-2, #ffffff)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M16 67 L20 85 M84 67 L80 85" stroke={OUTLINE} strokeWidth="6" strokeLinecap="round" />
          <rect x="12" y="45" width="76" height="10" fill="var(--word-art-1, #c9a4ff)" stroke={OUTLINE} strokeWidth="4" />
        </symbol>

        <symbol id="word-bus" viewBox="0 0 100 100">
          <rect x="10" y="28" width="80" height="42" rx="8" fill="var(--word-art-1, #ffd166)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <rect x="18" y="36" width="18" height="14" rx="2" fill="var(--word-art-2, #7bdff2)" stroke={OUTLINE} strokeWidth="3" />
          <rect x="42" y="36" width="18" height="14" rx="2" fill="var(--word-art-2, #7bdff2)" stroke={OUTLINE} strokeWidth="3" />
          <rect x="66" y="36" width="16" height="14" rx="2" fill="var(--word-art-2, #7bdff2)" stroke={OUTLINE} strokeWidth="3" />
          <circle cx="28" cy="76" r="8" fill="var(--word-art-3, #3a2a1e)" stroke={OUTLINE} strokeWidth="3" />
          <circle cx="72" cy="76" r="8" fill="var(--word-art-3, #3a2a1e)" stroke={OUTLINE} strokeWidth="3" />
        </symbol>

        <symbol id="word-pig" viewBox="0 0 100 100">
          <ellipse cx="50" cy="55" rx="34" ry="26" fill="var(--word-art-1, #ffb3c6)" stroke={OUTLINE} strokeWidth="5" />
          <circle cx="30" cy="34" r="9" fill="var(--word-art-1, #ffb3c6)" stroke={OUTLINE} strokeWidth="4" />
          <circle cx="60" cy="30" r="10" fill="var(--word-art-1, #ffb3c6)" stroke={OUTLINE} strokeWidth="4" />
          <ellipse cx="66" cy="52" rx="13" ry="10" fill="var(--word-art-2, #ff8aa8)" stroke={OUTLINE} strokeWidth="4" />
          <circle cx="70" cy="50" r="2.4" fill={OUTLINE} />
          <circle cx="62" cy="50" r="2.4" fill={OUTLINE} />
        </symbol>

        <symbol id="word-pen" viewBox="0 0 100 100">
          <path d="M20 80 L65 35 L78 48 L33 93 Z" fill="var(--word-art-1, #7bdff2)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <path d="M65 35 L78 48 L86 40 L73 27 Z" fill="var(--word-art-2, #ffd166)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <path d="M20 80 L14 92 L26 86 Z" fill={OUTLINE} />
        </symbol>

        <symbol id="word-pot" viewBox="0 0 100 100">
          <path d="M22 42 h56 l-6 38 a8 8 0 0 1 -8 7 H36 a8 8 0 0 1 -8 -7 Z" fill="var(--word-art-1, #7a3a1e)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <rect x="16" y="36" width="68" height="10" rx="4" fill="var(--word-art-2, #ffb84d)" stroke={OUTLINE} strokeWidth="4" />
          <path d="M12 40 q-8 0 -8 -10 q0 -8 8 -8 M88 40 q8 0 8 -10 q0 -8 -8 -8" fill="none" stroke={OUTLINE} strokeWidth="5" strokeLinecap="round" />
        </symbol>

        <symbol id="word-nose" viewBox="0 0 100 100">
          <path d="M50 15 Q35 45 30 62 Q28 78 50 78 Q72 78 70 62 Q65 45 50 15 Z" fill="var(--word-art-1, #ffcda3)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <ellipse cx="40" cy="66" rx="5" ry="7" fill={OUTLINE} />
          <ellipse cx="60" cy="66" rx="5" ry="7" fill={OUTLINE} />
        </symbol>

        <symbol id="word-mud" viewBox="0 0 100 100">
          <ellipse cx="50" cy="66" rx="38" ry="16" fill="var(--word-art-1, #a9773f)" stroke={OUTLINE} strokeWidth="5" />
          <ellipse cx="50" cy="62" rx="30" ry="11" fill="var(--word-art-2, #c9946a)" opacity="0.7" />
          <circle cx="30" cy="40" r="4" fill="var(--word-art-1, #a9773f)" stroke={OUTLINE} strokeWidth="2.5" />
          <circle cx="66" cy="34" r="5.5" fill="var(--word-art-1, #a9773f)" stroke={OUTLINE} strokeWidth="2.5" />
          <circle cx="50" cy="26" r="3.5" fill="var(--word-art-1, #a9773f)" stroke={OUTLINE} strokeWidth="2.5" />
        </symbol>

        <symbol id="word-net" viewBox="0 0 100 100">
          <path d="M22 20 L78 20 L64 60 A16 16 0 0 1 36 60 Z" fill="none" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <path d="M30 20 L70 20 M26 30 L74 30 M31 40 L69 40 M35 50 L65 50" stroke="var(--word-art-1, #22c9b8)" strokeWidth="3.5" />
          <path d="M22 20 L36 20 M64 20 L78 20 M28 26 L72 26" stroke={OUTLINE} strokeWidth="3" />
          <line x1="50" y1="60" x2="50" y2="88" stroke={OUTLINE} strokeWidth="6" strokeLinecap="round" />
        </symbol>

        <symbol id="word-dog" viewBox="0 0 100 100">
          <circle cx="50" cy="55" r="28" fill="var(--word-art-1, #c9a06b)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M28 40 Q10 30 16 55 Q22 62 32 52 Z" fill="var(--word-art-2, #a97a4a)" stroke={OUTLINE} strokeWidth="4" strokeLinejoin="round" />
          <path d="M72 40 Q90 30 84 55 Q78 62 68 52 Z" fill="var(--word-art-2, #a97a4a)" stroke={OUTLINE} strokeWidth="4" strokeLinejoin="round" />
          <ellipse cx="50" cy="66" rx="10" ry="7" fill="var(--word-art-2, #a97a4a)" stroke={OUTLINE} strokeWidth="3" />
          <circle cx="40" cy="50" r="3" fill={OUTLINE} />
          <circle cx="60" cy="50" r="3" fill={OUTLINE} />
        </symbol>

        <symbol id="word-door" viewBox="0 0 100 100">
          <rect x="26" y="12" width="48" height="78" rx="4" fill="var(--word-art-1, #8b6ff0)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <circle cx="62" cy="52" r="4" fill="var(--word-art-2, #ffd166)" stroke={OUTLINE} strokeWidth="2.5" />
          <rect x="26" y="12" width="48" height="78" rx="4" fill="none" stroke={OUTLINE} strokeWidth="3" strokeDasharray="0" transform="translate(6,6) scale(0.86)" />
        </symbol>

        <symbol id="word-duck" viewBox="0 0 100 100">
          <ellipse cx="46" cy="58" rx="30" ry="24" fill="var(--word-art-1, #ffd166)" stroke={OUTLINE} strokeWidth="5" />
          <circle cx="68" cy="36" r="16" fill="var(--word-art-1, #ffd166)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M80 36 q12 0 12 6 q0 6 -12 6 Z" fill="var(--word-art-2, #ff9d6c)" stroke={OUTLINE} strokeWidth="4" strokeLinejoin="round" />
          <circle cx="72" cy="32" r="2.6" fill={OUTLINE} />
        </symbol>

        <symbol id="word-hat" viewBox="0 0 100 100">
          <ellipse cx="50" cy="68" rx="42" ry="10" fill="var(--word-art-1, #ff6b6b)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M32 68 Q32 28 50 28 Q68 28 68 68 Z" fill="var(--word-art-2, #ff9d9d)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <rect x="32" y="60" width="36" height="9" fill="var(--word-art-3, #ffd166)" stroke={OUTLINE} strokeWidth="3" />
        </symbol>

        <symbol id="word-web" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="38" fill="none" stroke={OUTLINE} strokeWidth="3.5" />
          <circle cx="50" cy="50" r="24" fill="none" stroke={OUTLINE} strokeWidth="3" />
          <circle cx="50" cy="50" r="10" fill="var(--word-art-1, #c9a4ff)" stroke={OUTLINE} strokeWidth="3" />
          <path d="M50 12 V88 M12 50 H88 M22 22 L78 78 M22 78 L78 22" stroke={OUTLINE} strokeWidth="3" />
        </symbol>

        <symbol id="word-cup" viewBox="0 0 100 100">
          <path d="M25 30 h36 l-4 44 a8 8 0 0 1 -8 7 H37 a8 8 0 0 1 -8 -7 Z" fill="var(--word-art-1, #7bdff2)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <path d="M61 36 q16 0 16 14 t-16 14" fill="none" stroke={OUTLINE} strokeWidth="5" strokeLinecap="round" />
        </symbol>

        <symbol id="word-top" viewBox="0 0 100 100">
          <path d="M28 22 h44 v20 l-22 46 l-22 -46 Z" fill="var(--word-art-1, #ff9d6c)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <rect x="45" y="10" width="10" height="14" fill="var(--word-art-2, #7a3a1e)" stroke={OUTLINE} strokeWidth="3" />
          <ellipse cx="50" cy="36" rx="22" ry="6" fill="var(--word-art-2, #ffcda3)" opacity="0.7" />
        </symbol>

        <symbol id="word-ham" viewBox="0 0 100 100">
          <path d="M25 40 Q20 20 45 18 Q75 16 80 45 Q82 70 55 78 Q28 84 22 62 Q18 50 25 40 Z" fill="var(--word-art-1, #ff9d9d)" stroke={OUTLINE} strokeWidth="5" strokeLinejoin="round" />
          <circle cx="45" cy="42" r="3" fill="var(--word-art-2, #ffffff)" opacity="0.8" />
          <circle cx="58" cy="55" r="3" fill="var(--word-art-2, #ffffff)" opacity="0.8" />
          <path d="M78 40 L92 32 M79 50 L94 46" stroke={OUTLINE} strokeWidth="3.5" strokeLinecap="round" />
        </symbol>

        <symbol id="word-hen" viewBox="0 0 100 100">
          <ellipse cx="46" cy="60" rx="28" ry="22" fill="var(--word-art-1, #ff9d6c)" stroke={OUTLINE} strokeWidth="5" />
          <circle cx="66" cy="38" r="14" fill="var(--word-art-1, #ff9d6c)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M60 26 q-4 -10 4 -12 q6 8 2 14 Z M70 24 q0 -10 8 -10 q4 9 -2 14 Z" fill="var(--word-art-2, #ff6b6b)" stroke={OUTLINE} strokeWidth="3" strokeLinejoin="round" />
          <path d="M80 38 q10 2 10 6 q0 4 -10 4 Z" fill="var(--word-art-3, #ffd166)" stroke={OUTLINE} strokeWidth="3" strokeLinejoin="round" />
          <circle cx="70" cy="35" r="2.4" fill={OUTLINE} />
        </symbol>

        <symbol id="word-pup" viewBox="0 0 100 100">
          <circle cx="50" cy="58" r="24" fill="var(--word-art-1, #ffcda3)" stroke={OUTLINE} strokeWidth="5" />
          <path d="M30 44 Q16 36 20 56 Q26 62 34 54 Z" fill="var(--word-art-2, #ff9d6c)" stroke={OUTLINE} strokeWidth="4" strokeLinejoin="round" />
          <path d="M70 44 Q84 36 80 56 Q74 62 66 54 Z" fill="var(--word-art-2, #ff9d6c)" stroke={OUTLINE} strokeWidth="4" strokeLinejoin="round" />
          <ellipse cx="50" cy="66" rx="8" ry="6" fill="var(--word-art-2, #ff9d6c)" stroke={OUTLINE} strokeWidth="3" />
          <circle cx="42" cy="54" r="2.6" fill={OUTLINE} />
          <circle cx="58" cy="54" r="2.6" fill={OUTLINE} />
        </symbol>
      </defs>
    </svg>
  );
}

export function WordIllustration({ word, size = 200, className = "" }) {
  const key = (word || "").toLowerCase();
  if (!WORD_ART_COVERAGE.has(key)) return null;
  return (
    <svg width={size} height={size} className={`word-illustration ${className}`} aria-hidden="true">
      <use href={`#word-${key}`} />
    </svg>
  );
}
