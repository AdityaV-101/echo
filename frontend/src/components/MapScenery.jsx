// A living, colorful scenic backdrop for the level map: sun, a rainbow, a
// sky-to-ground gradient, hand-drawn SVG clouds/birds/critters (no emoji -
// every shape here is an authored <svg>, not a font glyph), and a steady
// rise of colorful sparkles.
//
// The map path can be far taller than one viewport (each level is a fixed
// row height, and there can be 15+ levels), so this backdrop is sized to
// the FULL scroll height of the map, not the viewport - a `position: fixed`
// backdrop only ever covers the first screenful, which is exactly the "map
// scenery doesn't cover the full page" bug this replaces. `worldCount`
// horizon bands are spaced evenly down that full height, each shifting the
// ground tone a little (meadow -> forest -> highland) so the map reads as
// a real journey through changing terrain, not one static screenful
// repeated - this is also the visual seam Part 7's themed worlds hook into.
const SPARKLES = [
  { left: "8%", size: 10, color: "#ff8a3d", duration: 9, delay: 0 },
  { left: "18%", size: 7, color: "#22c9b8", duration: 7, delay: 1.5 },
  { left: "30%", size: 9, color: "#8b6ff0", duration: 10, delay: 3 },
  { left: "42%", size: 6, color: "#ffb84d", duration: 8, delay: 0.5 },
  { left: "55%", size: 8, color: "#ff6b9d", duration: 11, delay: 4 },
  { left: "67%", size: 7, color: "#22c9b8", duration: 8.5, delay: 2 },
  { left: "78%", size: 10, color: "#8b6ff0", duration: 9.5, delay: 5 },
  { left: "88%", size: 6, color: "#ff8a3d", duration: 7.5, delay: 1 },
  { left: "95%", size: 8, color: "#ffb84d", duration: 10.5, delay: 3.5 },
];

// One ground-tone set per Part 7 theme, so the map's terrain bands read as
// "the world you picked" rather than always the same rainbow regardless of
// theme. "default" keeps the original warm sand -> mint -> teal -> lilac ->
// pink progression.
const GROUND_TONE_SETS = {
  default: ["#ffd08f", "#a9e0b4", "#8fe0d3", "#c9c2f0", "#ffb8d4"],
  jungle: ["#cfe8a8", "#a3d98c", "#7fc98f", "#6fc0a6", "#8fd6c2"],
  space: ["#3a2f6e", "#4b3a86", "#2f5a8f", "#3a7ba8", "#5a4a9e"],
  ocean: ["#bfe8f0", "#9fdcec", "#8fd0e8", "#a0e0d8", "#c0eee8"],
  candy: ["#ffd6ea", "#ffc2e0", "#f0b8ec", "#e0c4f5", "#ffd0d8"],
};

function CloudShape() {
  return (
    <svg viewBox="0 0 64 36" width="1em" height="1em" fill="currentColor">
      <ellipse cx="18" cy="22" rx="16" ry="12" />
      <ellipse cx="34" cy="14" rx="18" ry="14" />
      <ellipse cx="50" cy="22" rx="14" ry="11" />
      <rect x="10" y="20" width="44" height="12" rx="6" />
    </svg>
  );
}

function BirdShape() {
  return (
    <svg viewBox="0 0 40 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round">
      <path d="M2 16 Q11 4 20 14 Q29 4 38 16" />
    </svg>
  );
}

function ButterflyShape() {
  return (
    <svg viewBox="0 0 40 32" width="1em" height="1em">
      <ellipse cx="12" cy="12" rx="10" ry="9" fill="#ff9dc7" />
      <ellipse cx="12" cy="23" rx="8" ry="7" fill="#8b6ff0" />
      <ellipse cx="28" cy="12" rx="10" ry="9" fill="#ff9dc7" />
      <ellipse cx="28" cy="23" rx="8" ry="7" fill="#8b6ff0" />
      <rect x="18" y="6" width="4" height="22" rx="2" fill="#4a3f6b" />
    </svg>
  );
}

function BeeShape() {
  return (
    <svg viewBox="0 0 36 26" width="1em" height="1em">
      <ellipse cx="12" cy="13" rx="7" ry="6" fill="#fff" opacity="0.7" />
      <ellipse cx="18" cy="13" rx="7" ry="6" fill="#fff" opacity="0.7" />
      <ellipse cx="22" cy="13" rx="12" ry="9" fill="#ffd23f" />
      <path d="M12 6 L14 20 M18 5 L20 21 M24 6 L26 20" stroke="#2b2b2b" strokeWidth="2.5" />
    </svg>
  );
}

function SquirrelShape({ flip }) {
  return (
    <svg viewBox="0 0 44 38" width="1em" height="1em" transform={flip ? "scale(-1,1)" : undefined}>
      <path d="M30 30 C42 26 42 8 28 6 C34 14 30 22 22 22 Z" fill="#c9773f" />
      <circle cx="16" cy="22" r="12" fill="#e0975c" />
      <circle cx="9" cy="14" r="4" fill="#e0975c" />
      <circle cx="12" cy="19" r="1.6" fill="#2b2b2b" />
    </svg>
  );
}

function RabbitShape() {
  return (
    <svg viewBox="0 0 36 40" width="1em" height="1em">
      <ellipse cx="18" cy="26" rx="13" ry="11" fill="#f2efe6" />
      <ellipse cx="10" cy="8" rx="4" ry="12" fill="#f2efe6" />
      <ellipse cx="20" cy="6" rx="4" ry="12" fill="#f2efe6" />
      <circle cx="13" cy="24" r="1.6" fill="#2b2b2b" />
      <circle cx="22" cy="24" r="1.6" fill="#2b2b2b" />
    </svg>
  );
}

function FoxShape() {
  return (
    <svg viewBox="0 0 40 36" width="1em" height="1em">
      <path d="M20 34 C6 34 4 20 10 12 L2 6 L14 8 C17 6 23 6 26 8 L38 6 L30 12 C36 20 34 34 20 34 Z" fill="#e6763f" />
      <path d="M18 30 L22 30 L20 24 Z" fill="#fff" opacity="0.85" />
      <circle cx="15" cy="18" r="1.6" fill="#2b2b2b" />
      <circle cx="25" cy="18" r="1.6" fill="#2b2b2b" />
    </svg>
  );
}

// Builds one smooth vertical gradient across the whole map instead of flat
// stacked color blocks, so world-to-world transitions read as a soft
// terrain change rather than a hard seam.
function buildGroundGradient(worldCount, tones) {
  const n = Math.max(1, worldCount);
  const bandPct = 100 / n;
  const blend = Math.min(bandPct * 0.4, 6);
  const stops = [];
  for (let i = 0; i < n; i++) {
    const color = tones[i % tones.length];
    const start = i * bandPct;
    const end = (i + 1) * bandPct;
    stops.push(`${color} ${start}%`);
    stops.push(`${color} ${Math.max(start, end - blend)}%`);
  }
  return `linear-gradient(180deg, ${stops.join(", ")})`;
}

export default function MapScenery({ worldCount = 3, theme = "default" }) {
  const tones = GROUND_TONE_SETS[theme] || GROUND_TONE_SETS.default;
  return (
    <div className="map-scenery" aria-hidden="true">
      <div className="map-ground-gradient" style={{ background: buildGroundGradient(worldCount, tones) }} />

      <div className="map-sun" />
      <svg className="map-rainbow" viewBox="0 0 200 100" preserveAspectRatio="none">
        <path d="M0 100 A 100 100 0 0 1 200 100" fill="none" stroke="#ff6b6b" strokeWidth="6" />
        <path d="M12 100 A 88 88 0 0 1 188 100" fill="none" stroke="#ffb84d" strokeWidth="6" />
        <path d="M24 100 A 76 76 0 0 1 176 100" fill="none" stroke="#ffe066" strokeWidth="6" />
        <path d="M36 100 A 64 64 0 0 1 164 100" fill="none" stroke="#22c9b8" strokeWidth="6" />
        <path d="M48 100 A 52 52 0 0 1 152 100" fill="none" stroke="#8b6ff0" strokeWidth="6" />
      </svg>

      <span className="map-cloud map-cloud-1"><CloudShape /></span>
      <span className="map-cloud map-cloud-2"><CloudShape /></span>
      <span className="map-cloud map-cloud-3"><CloudShape /></span>
      <span className="map-cloud map-cloud-4"><CloudShape /></span>
      <span className="map-cloud map-cloud-5"><CloudShape /></span>

      <span className="map-bird map-bird-1"><BirdShape /></span>
      <span className="map-bird map-bird-2"><BirdShape /></span>
      <span className="map-bird map-bird-3"><ButterflyShape /></span>
      <span className="map-bird map-bird-4"><BeeShape /></span>
      <span className="map-bird map-bird-5"><ButterflyShape /></span>

      <span className="map-critter map-critter-1"><SquirrelShape /></span>
      <span className="map-critter map-critter-2"><RabbitShape /></span>
      <span className="map-critter map-critter-3"><FoxShape /></span>
      <span className="map-critter map-critter-4"><SquirrelShape flip /></span>

      <div className="map-sparkles">
        {SPARKLES.map((s, i) => (
          <span
            key={i}
            className="map-sparkle"
            style={{
              left: s.left,
              width: s.size,
              height: s.size,
              background: s.color,
              animationDuration: `${s.duration}s`,
              animationDelay: `${s.delay}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
