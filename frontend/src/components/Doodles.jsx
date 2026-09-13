// Hand-drawn-style doodles (star, scribble, heart, spiral, sound-wave,
// cloud) that drift and spin gently across a screen — the "kid's crayon
// drawing" layer that sits alongside FloatingDecor's emoji. Drawn as loose,
// slightly uneven strokes on purpose, so they read as sketched rather than
// as clean vector icons.
const DOODLES = {
  star: (color) => (
    <path
      d="M20 2 L24.5 15 38 16 27 25 31 38 20 30 9 38 13 25 2 16 15.5 15 Z"
      fill="none"
      stroke={color}
      strokeWidth="3.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  scribble: (color) => (
    <path
      d="M3 20 Q10 4 18 18 T33 15 Q38 22 30 28 T15 32"
      fill="none"
      stroke={color}
      strokeWidth="3.2"
      strokeLinecap="round"
    />
  ),
  heart: (color) => (
    <path
      d="M20 34 C4 22 3 10 12 7 C17 5 20 10 20 13 C20 10 23 5 28 7 C37 10 36 22 20 34 Z"
      fill="none"
      stroke={color}
      strokeWidth="3.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  spiral: (color) => (
    <path
      d="M20 20 Q22 14 16 13 Q6 12 8 24 Q10 36 24 34 Q38 32 34 18 Q31 6 18 8"
      fill="none"
      stroke={color}
      strokeWidth="3.2"
      strokeLinecap="round"
    />
  ),
  soundwave: (color) => (
    <g stroke={color} strokeWidth="4" strokeLinecap="round">
      <line x1="6" y1="14" x2="6" y2="26" />
      <line x1="16" y1="6" x2="16" y2="34" />
      <line x1="26" y1="10" x2="26" y2="30" />
      <line x1="36" y1="16" x2="36" y2="24" />
    </g>
  ),
  cloud: (color) => (
    <path
      d="M8 26 Q2 26 3 20 Q4 14 11 15 Q12 6 22 7 Q32 6 33 15 Q40 15 39 22 Q39 27 32 26 Z"
      fill="none"
      stroke={color}
      strokeWidth="3.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
};

const DOODLE_SETS = {
  login: [
    { shape: "star", color: "#ff8a3d", top: "10%", left: "10%", size: 34, duration: 7, spin: true },
    { shape: "soundwave", color: "#22c9b8", top: "76%", left: "12%", size: 40, duration: 6 },
    { shape: "spiral", color: "#8b6ff0", top: "16%", left: "82%", size: 36, duration: 8, spin: true },
    { shape: "heart", color: "#ff6b9d", top: "70%", left: "84%", size: 32, duration: 6.5 },
    { shape: "scribble", color: "#ffb84d", top: "44%", left: "4%", size: 30, duration: 7.5 },
  ],
  home: [
    { shape: "star", color: "#8b6ff0", top: "18%", left: "6%", size: 26, duration: 6.5, spin: true },
    { shape: "soundwave", color: "#22c9b8", top: "58%", left: "90%", size: 32, duration: 7 },
    { shape: "scribble", color: "#ff8a3d", top: "8%", left: "58%", size: 28, duration: 8 },
    { shape: "heart", color: "#ff6b9d", top: "36%", left: "88%", size: 24, duration: 6 },
    { shape: "spiral", color: "#ffb84d", top: "68%", left: "8%", size: 26, duration: 7.5, spin: true },
    { shape: "cloud", color: "#8b6ff0", top: "4%", left: "30%", size: 30, duration: 9 },
    { shape: "star", color: "#22c9b8", top: "82%", left: "94%", size: 20, duration: 5.5, spin: true },
    { shape: "scribble", color: "#ff6b9d", top: "50%", left: "3%", size: 22, duration: 7 },
    { shape: "soundwave", color: "#ffb84d", top: "26%", left: "72%", size: 26, duration: 6.8 },
  ],
  practice: [
    { shape: "spiral", color: "#8b6ff0", top: "78%", left: "88%", size: 28, duration: 7, spin: true },
    { shape: "soundwave", color: "#22c9b8", top: "16%", left: "6%", size: 30, duration: 6.5 },
  ],
  celebration: [
    { shape: "star", color: "#ffb84d", top: "20%", left: "18%", size: 36, duration: 4, spin: true },
    { shape: "heart", color: "#ff6b9d", top: "60%", left: "20%", size: 32, duration: 4.5 },
    { shape: "star", color: "#8b6ff0", top: "22%", left: "76%", size: 30, duration: 4.2, spin: true },
    { shape: "spiral", color: "#22c9b8", top: "62%", left: "78%", size: 30, duration: 5, spin: true },
  ],
};

export default function Doodles({ variant = "home" }) {
  const items = DOODLE_SETS[variant] || [];
  return (
    <div className="doodle-layer" aria-hidden="true">
      {items.map((item, i) => (
        <svg
          key={i}
          className={`doodle-item ${item.spin ? "doodle-item--spin" : ""}`}
          style={{
            top: item.top,
            left: item.left,
            width: item.size,
            height: item.size,
            animationDuration: `${item.duration}s`,
            animationDelay: `${i * 0.4}s`,
          }}
          viewBox="0 0 40 40"
        >
          {DOODLES[item.shape](item.color)}
        </svg>
      ))}
    </div>
  );
}
