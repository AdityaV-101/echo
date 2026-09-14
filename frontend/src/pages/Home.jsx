import { useState } from "react";
import Mascot from "../components/Mascot";
import FloatingDecor from "../components/FloatingDecor";
import MapScenery from "../components/MapScenery";
import Doodles from "../components/Doodles";
import SpeechModeToggle from "../components/SpeechModeToggle";
import { useApp } from "../lib/AppContext";
import { THEMES, getTheme, setTheme } from "../lib/theme";

// A gentle winding-path effect for the level bubbles, Duolingo-style.
const PATH_OFFSETS = [15, 45, 75, 60, 30, 10, 40, 70];

// A small themed sticker per level so the map reads as a playful trail
// instead of a bare row of numbers. Purely decorative.
const LEVEL_EMOJIS = ["👩", "🐶", "🎈", "🔑", "🐸", "🚐", "🦁", "☀️", "🐝", "🐚", "🌹", "🐻", "👍", "⭐", "🌈"];

// The path is chaptered into named "worlds" every WORLD_SIZE levels - both
// a wayfinding aid on a long path (15+ levels) and the visual seam
// MapScenery's ground-color bands and Part 7's themes key off of.
const WORLD_SIZE = 5;
const WORLD_NAMES = ["Meadow Trail", "Forest Path", "Mountain Peak", "Cloud Kingdom", "Starlight Bay"];
const WORLD_ICONS = ["🌼", "🌲", "⛰️", "☁️", "✨"];

// Height (in the SVG's own units, one "row" per level) each level occupies.
// Matches --level-row-height in index.css so the trail threads exactly
// through each bubble's center regardless of how many levels there are.
const ROW_UNIT = 100;

// Builds a smooth curved trail through the bubble centers so the map reads
// as an actual path to walk, not just a zig-zag list.
function buildTrailPath(offsets) {
  const points = offsets.map((offset, i) => [offset + 8, i * ROW_UNIT + ROW_UNIT / 2]);
  if (points.length < 2) return "";
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const midY = (y0 + y1) / 2;
    d += ` C ${x0} ${midY}, ${x1} ${midY}, ${x1} ${y1}`;
  }
  return d;
}

export default function Home({ onSelectLevel, onOpenPracticeTracks, onOpenTherapist, onPracticePhoneme }) {
  const { user, levels, levelProgress, recommendations, logout, saveSettings } = useApp();
  const [themePickerOpen, setThemePickerOpen] = useState(false);
  const [activeTheme, setActiveTheme] = useState(getTheme());

  const currentLevel = user?.current_level ?? 1;
  const appSpeechEnabled = user ? !!user.app_speech_enabled : true;
  const handleToggleAppSpeech = (value) => {
    saveSettings(!!user?.speak_aloud, user?.speech_rate ?? 0.8, value).catch(() => {});
  };
  const trailOffsets = levels.map((_, i) => PATH_OFFSETS[i % PATH_OFFSETS.length]);
  const worldCount = Math.max(1, Math.ceil(levels.length / WORLD_SIZE));

  // Chapter the path into per-world sections, each with its OWN trail SVG
  // scoped to just that world's rows. A single global trail synced to
  // `levels.length * ROW_UNIT` would drift out of alignment with the
  // bubbles as soon as a world-banner divider added height the trail math
  // didn't know about - per-world sections sidestep that entirely.
  const worldGroups = [];
  for (let i = 0; i < levels.length; i += WORLD_SIZE) {
    const chunkLevels = levels.slice(i, i + WORLD_SIZE);
    const chunkOffsets = trailOffsets.slice(i, i + WORLD_SIZE);
    worldGroups.push({ startIndex: i, levels: chunkLevels, trailPath: buildTrailPath(chunkOffsets) });
  }

  return (
    <div className="screen screen-home">
      <MapScenery worldCount={worldCount} theme={activeTheme} />
      <FloatingDecor variant="home" />
      <Doodles variant="home" />
      <header className="home-header">
        <div className="home-header-left">
          <Mascot state="idle" size={64} />
          <div>
            <div className="home-greeting">Hi, {user?.id}!</div>
            <div className="home-level-label">Level {currentLevel}</div>
          </div>
        </div>
        <div className="home-header-right">
          <SpeechModeToggle enabled={appSpeechEnabled} onChange={handleToggleAppSpeech} />
          <button className="btn-icon" onClick={onOpenPracticeTracks} title="Sound Practice" aria-label="Sound Practice">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none">
              <path
                d="M12 3v10.5a3.5 3.5 0 1 1-2-3.16V3h2Z"
                fill="var(--color-primary)"
              />
              <path d="M12 3h6a2 2 0 0 1 2 2v2" stroke="var(--color-primary)" strokeWidth="1.6" fill="none" />
            </svg>
          </button>
          <button className="btn-icon" onClick={onOpenTherapist} title="Therapist Mode" aria-label="Therapist Mode">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none">
              <path
                d="M12 8a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z"
                stroke="var(--color-text)"
                strokeWidth="1.7"
              />
              <path
                d="M19.4 13a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V19a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 17.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 13 1.65 1.65 0 0 0 3.17 12H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 6.98a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 2.66c.61.25 1 .85 1 1.51V4.3a2 2 0 1 1 4 0v.09c0 .66.39 1.26 1 1.51.62.26 1.34.13 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06c-.46.48-.59 1.2-.33 1.82.25.61.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09c-.66 0-1.26.39-1.51 1Z"
                stroke="var(--color-text)"
                strokeWidth="1.4"
              />
            </svg>
          </button>
          <button
            className="btn-icon"
            onClick={() => setThemePickerOpen((v) => !v)}
            title="Change theme"
            aria-label="Change theme"
            aria-expanded={themePickerOpen}
          >
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none">
              <path
                d="M12 2a10 10 0 1 0 0 20c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4c2 0 3.6-1.6 3.6-3.6C21 6.6 17 2 12 2Z"
                stroke="var(--color-text)"
                strokeWidth="1.5"
              />
              <circle cx="7" cy="12" r="1.4" fill="var(--color-primary)" />
              <circle cx="9" cy="7.5" r="1.4" fill="var(--color-secondary)" />
              <circle cx="15" cy="7.5" r="1.4" fill="var(--color-accent)" />
              <circle cx="17" cy="12" r="1.4" fill="var(--color-warning)" />
            </svg>
          </button>
        </div>
      </header>

      {themePickerOpen && (
        <div className="theme-picker">
          {THEMES.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`theme-swatch ${activeTheme === t.id ? "theme-swatch--active" : ""}`}
              style={{ background: t.swatch }}
              onClick={() => {
                setTheme(t.id);
                setActiveTheme(t.id);
              }}
              title={t.label}
              aria-label={`${t.label} theme`}
              aria-pressed={activeTheme === t.id}
            />
          ))}
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="recommendation-card">
          <Mascot state="encouraging" size={56} />
          <div className="recommendation-text">
            <strong>You've had trouble with the {recommendations[0].phoneme} sound</strong>
            <span>{recommendations[0].error_count} times recently. Want to practice it?</span>
          </div>
          <button className="btn btn-secondary" onClick={() => onPracticePhoneme(recommendations[0].phoneme)}>
            Practice {recommendations[0].phoneme}
          </button>
        </div>
      )}

      {worldGroups.map((group, gi) => (
        <section key={gi} className="world-section">
          <div className="world-banner">
            <span className="world-banner-icon">{WORLD_ICONS[gi % WORLD_ICONS.length]}</span>
            <span className="world-banner-name">{WORLD_NAMES[gi % WORLD_NAMES.length]}</span>
          </div>
          <div className="level-path" style={{ "--level-count": group.levels.length }}>
            <svg
              className="level-trail"
              viewBox={`0 0 100 ${group.levels.length * ROW_UNIT}`}
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path className="level-trail-path" d={group.trailPath} />
            </svg>
            {group.levels.map((lvl, gi2) => {
              const i = group.startIndex + gi2;
              const progress = levelProgress[String(lvl.level)];
              const completed = progress?.completed === 1;
              const isCurrent = lvl.level === currentLevel;
              // A level is locked until the path has actually reached it -
              // it hasn't been completed AND it's further along than the
              // level the child is currently on. Without this every
              // not-yet-completed level (2 through the very last one)
              // rendered identically, with no way to tell "next up" from
              // "14 levels away."
              const locked = !completed && lvl.level > currentLevel;
              const offset = trailOffsets[i];
              return (
                <div key={lvl.level} className="level-path-row">
                  <button
                    type="button"
                    className={`level-bubble ${completed ? "level-bubble--completed" : ""} ${isCurrent ? "level-bubble--current" : ""} ${locked ? "level-bubble--locked" : ""}`}
                    style={{ marginLeft: `${offset}%` }}
                    onClick={() => !locked && onSelectLevel(lvl.level)}
                    disabled={locked}
                    aria-disabled={locked}
                    title={locked ? "Locked - finish earlier levels first" : lvl.name}
                  >
                    {isCurrent && <span className="level-bubble-flag">🚩</span>}
                    {!locked && <span className="level-bubble-sticker">{LEVEL_EMOJIS[i % LEVEL_EMOJIS.length]}</span>}
                    {locked ? (
                      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="white" strokeWidth="2">
                        <rect x="5" y="11" width="14" height="10" rx="2" />
                        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                      </svg>
                    ) : completed ? (
                      <svg viewBox="0 0 24 24" width="26" height="26" fill="gold" stroke="#c9930a" strokeWidth="1">
                        <path d="M12 2l2.9 6.26L22 9.27l-5 4.87L18.2 21 12 17.5 5.8 21 7 14.14 2 9.27l7.1-1.01L12 2z" />
                      </svg>
                    ) : (
                      lvl.level
                    )}
                  </button>
                  {!completed && (
                    <span className={`level-path-name ${locked ? "level-path-name--locked" : ""}`} style={{ marginLeft: `${offset}%` }}>
                      {lvl.name}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <button className="logout-link" onClick={logout}>
        Not you? Switch user
      </button>
    </div>
  );
}
