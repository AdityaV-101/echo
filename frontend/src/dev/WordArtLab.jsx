import WordArtSprite, { WORD_ART_COVERAGE } from "../assets/wordArt";
import WordCard from "../components/WordCard";

// Dev route (#word-art-lab) to review every illustrated word plus a
// fallback-card sample, in one composite image.
export default function WordArtLab() {
  const words = [...WORD_ART_COVERAGE].sort();
  return (
    <div style={{ padding: 24, background: "#f5f1ea", fontFamily: "sans-serif" }}>
      <WordArtSprite />
      <h1>Word Art Lab ({words.length} illustrated)</h1>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        {words.map((w) => (
          <div key={w} style={{ textAlign: "center" }}>
            <WordCard word={w} size={140} />
            <div style={{ marginTop: 6, fontSize: 13 }}>{w}</div>
          </div>
        ))}
      </div>
      <h2>Fallback card sample (words without art)</h2>
      <div style={{ display: "flex", gap: 16 }}>
        {["rabbit", "sun", "tree", "umbrella"].map((w) => (
          <div key={w} style={{ textAlign: "center" }}>
            <WordCard word={w} size={140} />
            <div style={{ marginTop: 6, fontSize: 13 }}>{w}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
