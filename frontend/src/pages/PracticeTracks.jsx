import { useState } from "react";
import { useApp } from "../lib/AppContext";
import FloatingDecor from "../components/FloatingDecor";
import Doodles from "../components/Doodles";
import WordPractice from "./WordPractice";

const TRACK_EMOJIS = { R: "🐰", S: "☀️", L: "🦁", TH: "👍", Z: "🦓", SH: "🤫", CH: "🧀", K: "🐱" };

export default function PracticeTracks({ onExit, initialPhoneme = null }) {
  const { practiceTracks, phonemeErrors } = useApp();
  const [selectedPhoneme, setSelectedPhoneme] = useState(initialPhoneme);
  const [selectedTier, setSelectedTier] = useState(null);

  const errorCountFor = (phoneme) => phonemeErrors.find((p) => p.phoneme === phoneme)?.error_count ?? 0;

  if (selectedPhoneme && selectedTier !== null) {
    const track = practiceTracks[selectedPhoneme];
    const tier = track.tiers[selectedTier];
    // Tiers 1-3 are explicitly labeled "Initial/Final/Medial, ..."; later
    // tiers (consonant clusters, multisyllabic/phrases) don't map cleanly
    // to a single position, so position-based scoring validation is
    // skipped for those (score_word treats an unset position as unknown).
    const tierPosition = tier.name.toLowerCase().startsWith("initial")
      ? "initial"
      : tier.name.toLowerCase().startsWith("final")
        ? "final"
        : tier.name.toLowerCase().startsWith("medial")
          ? "medial"
          : null;
    const words = tier.words.map((w) => ({ word: w, target_phoneme: selectedPhoneme, position: tierPosition }));
    return (
      <WordPractice
        title={`${selectedPhoneme} Practice — Tier ${tier.tier}: ${tier.name}`}
        words={words}
        levelNumber={null}
        onExit={() => setSelectedTier(null)}
      />
    );
  }

  if (selectedPhoneme) {
    const track = practiceTracks[selectedPhoneme];
    return (
      <div className="screen screen-tracks">
        <div className="practice-top">
          <button className="btn-icon" onClick={() => setSelectedPhoneme(null)} aria-label="Back">
            ←
          </button>
          <h2 className="practice-title">{selectedPhoneme} Sound Track</h2>
        </div>
        <div className="tier-list">
          {track.tiers.map((tier) => (
            <button key={tier.tier} className="tier-card" onClick={() => setSelectedTier(tier.tier - 1)}>
              <span className="tier-number">Tier {tier.tier}</span>
              <span className="tier-name">{tier.name}</span>
              <span className="tier-preview">{tier.words.slice(0, 3).join(", ")}...</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="screen screen-tracks">
      <FloatingDecor variant="home" />
      <Doodles variant="home" />
      <div className="practice-top">
        <button className="btn-icon" onClick={onExit} aria-label="Back">
          ←
        </button>
        <h2 className="practice-title">Sound Practice</h2>
      </div>
      <p className="tracks-intro">
        Pick a sound to practice with dedicated word lists, from single words to full phrases.
      </p>
      <div className="track-grid">
        {Object.keys(practiceTracks).map((phoneme) => {
          const count = errorCountFor(phoneme);
          return (
            <button key={phoneme} className="track-card" onClick={() => setSelectedPhoneme(phoneme)}>
              <span className="track-emoji">{TRACK_EMOJIS[phoneme] || "🔤"}</span>
              <span className="track-letter">{phoneme}</span>
              {count > 0 && <span className="track-error-badge">{count} misses</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
