import { WordIllustration, hasWordArt } from "../assets/wordArt";

// Always renders SOMETHING designed - never bare text. Real art when
// wordArt.jsx has it; otherwise a themed card with the word's initial in
// the display face inside a decorated frame, per the brief's explicit
// fallback rule.
export default function WordCard({ word, size = 200 }) {
  if (hasWordArt(word)) {
    return (
      <div className="word-card word-card--art" style={{ width: size, height: size }}>
        <WordIllustration word={word} size={size * 0.72} />
      </div>
    );
  }
  const initial = (word || "?").trim().charAt(0).toUpperCase();
  return (
    <div className="word-card word-card--fallback" style={{ width: size, height: size }}>
      <span className="word-card-fallback-ring" aria-hidden="true" />
      {/* CSS `font-size: 40%` resolves against the INHERITED font-size, not
          this element's own box - caught directly in the word-art-lab
          screenshot (letters were nearly invisible at 140px cards). Sized
          from the actual pixel size instead. */}
      <span className="word-card-fallback-letter" style={{ fontSize: size * 0.42 }}>{initial}</span>
    </div>
  );
}
