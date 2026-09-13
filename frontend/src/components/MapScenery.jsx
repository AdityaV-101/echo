// A living, colorful scenic backdrop for the level map: sun, a rainbow,
// three tinted hill layers for depth, a tree line, drifting clouds and
// birds, a couple of critters peeking out of the grass, and a steady rise
// of colorful sparkles. Fixed behind the level path so the map reads as a
// world to walk through instead of a bare list of circles.
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

// Trees sit on a shared ground line (y=140 in the tree layer's own
// viewBox) so mixing pine and round canopies still reads as one tree line.
const TREES = [
  { x: 22, scale: 0.8, type: "pine", tone: "#8fd6a8" },
  { x: 60, scale: 1.05, type: "round", tone: "#5fb87e" },
  { x: 105, scale: 0.7, type: "pine", tone: "#79c996" },
  { x: 200, scale: 0.65, type: "round", tone: "#8fd6a8" },
  { x: 245, scale: 1.0, type: "pine", tone: "#5fb87e" },
  { x: 300, scale: 0.75, type: "round", tone: "#79c996" },
  { x: 345, scale: 0.9, type: "pine", tone: "#8fd6a8" },
  { x: 385, scale: 0.6, type: "pine", tone: "#5fb87e" },
];

function PineTree() {
  return (
    <>
      <path d="M-26 0 L0 -40 L26 0 Z" />
      <path d="M-20 -22 L0 -58 L20 -22 Z" />
      <path d="M-14 -42 L0 -78 L14 -42 Z" />
      <rect x="-4" y="0" width="8" height="14" fill="#a9773f" />
    </>
  );
}

function RoundTree() {
  return (
    <>
      <circle cx="-14" cy="-38" r="19" />
      <circle cx="14" cy="-38" r="19" />
      <circle cx="0" cy="-54" r="21" />
      <rect x="-4" y="0" width="8" height="16" fill="#a9773f" />
    </>
  );
}

export default function MapScenery() {
  return (
    <div className="map-scenery" aria-hidden="true">
      <div className="map-sun" />
      <svg className="map-rainbow" viewBox="0 0 200 100" preserveAspectRatio="none">
        <path d="M0 100 A 100 100 0 0 1 200 100" fill="none" stroke="#ff6b6b" strokeWidth="6" />
        <path d="M12 100 A 88 88 0 0 1 188 100" fill="none" stroke="#ffb84d" strokeWidth="6" />
        <path d="M24 100 A 76 76 0 0 1 176 100" fill="none" stroke="#ffe066" strokeWidth="6" />
        <path d="M36 100 A 64 64 0 0 1 164 100" fill="none" stroke="#22c9b8" strokeWidth="6" />
        <path d="M48 100 A 52 52 0 0 1 152 100" fill="none" stroke="#8b6ff0" strokeWidth="6" />
      </svg>

      <svg className="map-hills map-hills-far" viewBox="0 0 400 120" preserveAspectRatio="none">
        <path d="M0 120 L0 78 Q60 50 120 68 T240 60 T400 72 L400 120 Z" fill="#a9e0b4" />
      </svg>
      <svg className="map-hills map-hills-back" viewBox="0 0 400 120" preserveAspectRatio="none">
        <path d="M0 120 L0 70 Q50 30 100 55 T200 50 T300 60 T400 45 L400 120 Z" fill="#8fe0d3" />
      </svg>

      <svg className="map-trees" viewBox="0 0 400 140" preserveAspectRatio="none">
        {TREES.map((t, i) => (
          <g key={i} fill={t.tone} transform={`translate(${t.x} 140) scale(${t.scale})`}>
            {t.type === "pine" ? <PineTree /> : <RoundTree />}
          </g>
        ))}
      </svg>

      <svg className="map-hills map-hills-front" viewBox="0 0 400 100" preserveAspectRatio="none">
        <path d="M0 100 L0 60 Q60 20 130 50 T260 40 T400 55 L400 100 Z" fill="#ffd08f" />
      </svg>

      <span className="map-cloud map-cloud-1">☁️</span>
      <span className="map-cloud map-cloud-2">☁️</span>
      <span className="map-cloud map-cloud-3">☁️</span>
      <span className="map-bird map-bird-1">🐦</span>
      <span className="map-bird map-bird-2">🕊️</span>
      <span className="map-bird map-bird-3">🦋</span>
      <span className="map-bird map-bird-4">🐝</span>

      <span className="map-critter map-critter-1">🐿️</span>
      <span className="map-critter map-critter-2">🐇</span>
      <span className="map-critter map-critter-3">🦊</span>

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
