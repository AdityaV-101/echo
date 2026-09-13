import "./mascot.css";

// "Echo" as a logo mark, not a character: a flat, geometric bird silhouette
// with concentric sound-wave rings radiating from its beak. The rings are
// the actual concept - sound (and the app's name) bouncing back outward -
// and are what makes this read as a speech app's mark instead of a generic
// animal icon. Built from a small number of bold flat shapes (no gradients,
// no shading, no articulated eyes) so it stays crisp down to favicon size
// and reads as designed rather than illustrated. `state` only tints the
// glow behind it and gates the listening ring / celebration confetti - the
// mark itself never animates.
export default function Mascot({ state = "idle", size = 160 }) {
  return (
    <div className={`mascot-wrap mascot-wrap--${state}`} style={{ width: size, height: size }}>
      <svg
        className="mascot"
        viewBox="0 0 200 200"
        width={size}
        height={size}
        role="img"
        aria-label="Echo"
      >
        {/* tail: two swept points, drawn behind the body */}
        <path
          d="M58 108 L10 88 L52 126 L12 156 L60 140 Z"
          fill="var(--mascot-green-dark)"
          stroke="var(--mascot-outline)"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* body + head: one continuous silhouette */}
        <ellipse
          cx="90" cy="128" rx="50" ry="44"
          fill="var(--mascot-green)"
          stroke="var(--mascot-outline)"
          strokeWidth="2"
        />
        <circle
          cx="132" cy="80" r="30"
          fill="var(--mascot-green)"
          stroke="var(--mascot-outline)"
          strokeWidth="2"
        />

        {/* wing: a second flat tone layered on the body for dimension
            without any gradient shading */}
        <path
          d="M108 98 C 82 104, 60 126, 66 160 C 92 156, 118 138, 120 104 Z"
          fill="var(--mascot-green-light)"
        />

        {/* beak */}
        <path
          d="M158 68 L172 84 L158 100 Z"
          fill="var(--mascot-beak)"
          stroke="var(--mascot-outline)"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* eye: a single flat dot, no iris/highlight/blink rig */}
        <circle cx="124" cy="68" r="8" fill="var(--mascot-eye-white)" />
        <circle cx="126" cy="68" r="4" fill="var(--mascot-outline)" />

        {/* echo rings: sound radiating from the beak - the literal "Echo" */}
        <g fill="none" strokeLinecap="round">
          <path d="M182.3 71.7 A16 16 0 0 1 182.3 96.3" stroke="var(--mascot-ring)" strokeWidth="5" opacity="0.9" />
          <path d="M190.0 62.6 A28 28 0 0 1 190.0 105.4" stroke="var(--mascot-ring)" strokeWidth="4" opacity="0.55" />
          <path d="M197.7 53.4 A40 40 0 0 1 197.7 114.6" stroke="var(--mascot-ring)" strokeWidth="3" opacity="0.3" />
        </g>

        {state === "celebrating" && (
          <g className="confetti">
            {Array.from({ length: 14 }).map((_, i) => (
              <rect
                key={i}
                className={`confetti-piece confetti-piece-${i}`}
                x="140"
                y="70"
                width="8"
                height="8"
                fill={["#ff6b6b", "#4ecdc4", "#ffd166", "#7bdff2", "#c9a4ff"][i % 5]}
              />
            ))}
          </g>
        )}
      </svg>
      {state === "listening" && <div className="mascot-listening-ring" aria-hidden="true" />}
    </div>
  );
}
