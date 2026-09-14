import "./mascot.css";
import { useEffect, useRef, useState } from "react";

// Echo, rebuilt from scratch per the brief: a small round fuzzy creature
// with enormous ears - a creature that listens, where the ears carry most
// of the personality. Kinderschema proportions (large low-set eyes, head
// far larger than body-implied-by-a-neck, no neck at all, soft pear body,
// tiny limbs) - the actual principle behind why children find a character
// appealing, applied literally rather than as a vibe.
//
// The previous version of this file was a flat geometric bird-logo mark
// with a single pupil-less dot eye and concentric sound-wave rings as its
// entire "personality" - explicitly NOT what a therapy app for 4-9 year
// olds should look like. Deleted outright rather than evolved; nothing
// here reuses its shapes.
//
// Rig: every part that needs to move independently is its own named group
// with an explicit transform-origin (in SVG user units, set via the
// `transform-box: fill-box` + CSS custom property pattern below, since
// plain SVG transform-origin in % is relative to each element's own
// bounding box, which is what we want per-part). States are plain CSS
// classes on .mascot-wrap; see mascot.css for the actual animation rules.
//
// One deliberate asymmetry: the left ear's droop/tip curve is not a mirror
// of the right ear's (see the two path `d` strings below) - hand-made
// things are never perfectly symmetric, and perfect mirror symmetry is
// exactly what makes a mark read as a manufactured logo.

const CELEBRATE_VARIANTS = [
  { armSpread: 34, jumpHeight: 22, tilt: -4 },
  { armSpread: 30, jumpHeight: 26, tilt: 3 },
  { armSpread: 38, jumpHeight: 20, tilt: -2 },
  { armSpread: 28, jumpHeight: 24, tilt: 5 },
];

export default function Mascot({ state = "idle", size = 160, micLevel = 0, celebrateVariant = 0 }) {
  const [blinking, setBlinking] = useState(false);
  const blinkTimer = useRef(null);

  // Randomized blink every 4-7s while idle/listening/thinking, so it never
  // reads as a metronomic loop - a single fixed-interval blink is one of
  // the fastest ways an animated face reads as mechanical.
  useEffect(() => {
    function scheduleBlink() {
      const delay = 4000 + Math.random() * 3000;
      blinkTimer.current = setTimeout(() => {
        setBlinking(true);
        setTimeout(() => setBlinking(false), 140);
        scheduleBlink();
      }, delay);
    }
    scheduleBlink();
    return () => clearTimeout(blinkTimer.current);
  }, []);

  const variant = CELEBRATE_VARIANTS[celebrateVariant % CELEBRATE_VARIANTS.length];
  const ringScale = 1 + Math.min(micLevel, 1) * 0.7;

  return (
    <div
      className={`mascot-wrap mascot-wrap--${state} ${blinking ? "mascot-wrap--blink" : ""}`}
      style={{
        width: size,
        height: size * (320 / 240),
        "--celebrate-arm-spread": `${variant.armSpread}deg`,
        "--celebrate-jump": `${variant.jumpHeight}px`,
        "--celebrate-tilt": `${variant.tilt}deg`,
      }}
    >
      {state === "listening" && (
        <div className="mascot-amplitude-ring" style={{ transform: `scale(${ringScale})` }} aria-hidden="true" />
      )}

      <svg className="mascot" viewBox="0 0 240 320" width={size} height={size * (320 / 240)} role="img" aria-label="Echo">
        {/* contact shadow - floats a few px above it, never touches */}
        <ellipse id="shadow" cx="120" cy="286" rx="58" ry="11" fill="var(--mascot-shadow)" />

        <g id="mascot-rig">
          {/* right ear behind the head, drawn first so the head overlaps its base.
              Soft leaf/paisley silhouette (round tip, gentle S-curve droop) -
              round 1's sharper convergent tip read as a horn, not floppy fur;
              this version never lets two curves meet at a sharp vertex. */}
          <g id="ear-r" style={{ transformOrigin: "168px 132px" }}>
            <path
              d="M164 134
                 C 148 128, 138 108, 142 84
                 C 145 64, 156 48, 158 30
                 C 159 16, 168 6, 180 8
                 C 188 10, 190 22, 186 34
                 C 180 52, 184 74, 196 90
                 C 206 104, 204 122, 190 130
                 C 182 135, 172 136, 164 134 Z"
              fill="var(--mascot-body)"
              stroke="var(--mascot-outline)"
              strokeWidth="4"
              strokeLinejoin="round"
            />
            <path
              d="M166 122 C 156 104, 152 82, 160 58 C 166 42, 172 28, 172 16"
              fill="none"
              stroke="var(--mascot-ear-inner)"
              strokeWidth="9"
              strokeLinecap="round"
              opacity="0.5"
            />
          </g>

          {/* left ear - deliberately NOT a mirror of the right (droops lower,
              wider tip curl, sits slightly further out) so the character
              doesn't read as machine-mirrored. */}
          <g id="ear-l" style={{ transformOrigin: "72px 132px" }}>
            <path
              d="M76 136
                 C 58 132, 46 114, 48 90
                 C 50 68, 62 52, 60 32
                 C 59 18, 48 6, 36 10
                 C 27 13, 26 26, 31 38
                 C 38 56, 35 78, 24 96
                 C 15 111, 18 128, 33 134
                 C 44 138, 62 139, 76 136 Z"
              fill="var(--mascot-body)"
              stroke="var(--mascot-outline)"
              strokeWidth="4"
              strokeLinejoin="round"
            />
            <path
              d="M70 122 C 56 108, 50 86, 56 62 C 60 46, 52 30, 46 20"
              fill="none"
              stroke="var(--mascot-ear-inner)"
              strokeWidth="9"
              strokeLinecap="round"
              opacity="0.5"
            />
          </g>

          {/* body: soft pear, no neck - overlaps directly under the head */}
          <g id="body" style={{ transformOrigin: "120px 230px" }}>
            <path
              d="M120 150
                 C 160 150, 186 182, 182 222
                 C 179 258, 154 282, 120 282
                 C 86 282, 61 258, 58 222
                 C 54 182, 80 150, 120 150 Z"
              fill="var(--mascot-body)"
              stroke="var(--mascot-outline)"
              strokeWidth="4.5"
            />
            {/* soft lighter belly patch for depth without a gradient */}
            <ellipse cx="120" cy="240" rx="38" ry="30" fill="var(--mascot-belly)" opacity="0.6" />

            {/* feet */}
            <ellipse cx="94" cy="280" rx="16" ry="9" fill="var(--mascot-belly)" stroke="var(--mascot-outline)" strokeWidth="3" />
            <ellipse cx="146" cy="280" rx="16" ry="9" fill="var(--mascot-belly)" stroke="var(--mascot-outline)" strokeWidth="3" />
          </g>

          {/* arms: tiny and stubby, animate independently for encouraging/celebrating */}
          <g id="arm-r" style={{ transformOrigin: "176px 222px" }}>
            <path
              d="M176 222 C 194 220, 204 232, 200 248 C 197 260, 186 262, 178 254"
              fill="none"
              stroke="var(--mascot-body)"
              strokeWidth="20"
              strokeLinecap="round"
            />
          </g>
          <g id="arm-l" style={{ transformOrigin: "64px 222px" }}>
            <path
              d="M64 222 C 46 220, 36 232, 40 248 C 43 260, 54 262, 62 254"
              fill="none"
              stroke="var(--mascot-body)"
              strokeWidth="20"
              strokeLinecap="round"
            />
          </g>

          {/* head: large circle, low-set eyes live in its lower half */}
          <g id="head" style={{ transformOrigin: "120px 148px" }}>
            <circle cx="120" cy="148" r="76" fill="var(--mascot-body)" stroke="var(--mascot-outline)" strokeWidth="4.5" />
            {/* muzzle/cheek patch, warm lighter tone, sits low - reinforces
                the low eye placement and gives the face a soft focal center */}
            <ellipse cx="120" cy="188" rx="46" ry="34" fill="var(--mascot-belly)" opacity="0.55" />

            {/* eyes: large, low, wide-set, with iris + pupil + specular highlight + lids.
                Lids are full-eye-sized circles clipped to their own eye and
                scaled vertically from a transform-origin at the eye's TOP -
                scaleY(0.04) reads as open (a thin line), scaleY(1) as fully
                closed. Far more reliable to animate accurately than a
                hand-drawn lid shape would be. */}
            <g id="eye-l">
              <clipPath id="eye-l-clip"><circle cx="92" cy="166" r="22" /></clipPath>
              <circle cx="92" cy="166" r="22" fill="var(--mascot-eye-white)" stroke="var(--mascot-outline)" strokeWidth="2.5" />
              <g id="pupil-l" style={{ transformOrigin: "92px 166px" }}>
                <circle cx="92" cy="169" r="13" fill="var(--mascot-iris)" />
                <circle cx="92" cy="169" r="6.5" fill="var(--mascot-pupil)" />
                <circle cx="88" cy="164" r="3.2" fill="#fff" />
              </g>
              <g clipPath="url(#eye-l-clip)">
                <circle id="lid-l" cx="92" cy="166" r="22" fill="var(--mascot-body)" style={{ transformOrigin: "92px 144px" }} />
              </g>
              <path className="happy-arc happy-arc-l" d="M76 164 Q92 148 108 164" fill="none" stroke="var(--mascot-outline)" strokeWidth="4.5" strokeLinecap="round" />
            </g>
            <g id="eye-r">
              <clipPath id="eye-r-clip"><circle cx="148" cy="166" r="22" /></clipPath>
              <circle cx="148" cy="166" r="22" fill="var(--mascot-eye-white)" stroke="var(--mascot-outline)" strokeWidth="2.5" />
              <g id="pupil-r" style={{ transformOrigin: "148px 166px" }}>
                <circle cx="148" cy="169" r="13" fill="var(--mascot-iris)" />
                <circle cx="148" cy="169" r="6.5" fill="var(--mascot-pupil)" />
                <circle cx="144" cy="164" r="3.2" fill="#fff" />
              </g>
              <g clipPath="url(#eye-r-clip)">
                <circle id="lid-r" cx="148" cy="166" r="22" fill="var(--mascot-body)" style={{ transformOrigin: "148px 144px" }} />
              </g>
              <path className="happy-arc happy-arc-r" d="M132 164 Q148 148 164 164" fill="none" stroke="var(--mascot-outline)" strokeWidth="4.5" strokeLinecap="round" />
            </g>

            {/* mouth: single path, restyled per state in CSS via d overrides
                on state-specific classes is unreliable across browsers, so
                mouth shape changes are handled with sibling paths toggled
                by state class instead (see the four variants below). */}
            <g id="mouth" style={{ transformOrigin: "120px 200px" }}>
              <path className="mouth-shape mouth-shape--idle" d="M104 200 Q120 210 136 200" fill="none" stroke="var(--mascot-outline)" strokeWidth="4" strokeLinecap="round" />
              <path className="mouth-shape mouth-shape--o" d="M120 194 a9 9 0 1 0 0.1 0 Z" fill="var(--mascot-mouth-inner)" stroke="var(--mascot-outline)" strokeWidth="3" />
              <path className="mouth-shape mouth-shape--smile" d="M100 198 Q120 218 140 198" fill="none" stroke="var(--mascot-outline)" strokeWidth="4.5" strokeLinecap="round" />
              <path className="mouth-shape mouth-shape--demonstrate" d="M106 196 Q120 222 134 196 Q120 208 106 196 Z" fill="var(--mascot-mouth-inner)" stroke="var(--mascot-outline)" strokeWidth="3" />
            </g>

            {/* cheek blush - small warmth, not a design element that moves */}
            <ellipse cx="66" cy="190" rx="10" ry="6" fill="var(--mascot-blush)" opacity="0.5" />
            <ellipse cx="174" cy="190" rx="10" ry="6" fill="var(--mascot-blush)" opacity="0.5" />
          </g>
        </g>

        {state === "celebrating" && (
          <g className="confetti" aria-hidden="true">
            {Array.from({ length: 16 }).map((_, i) => (
              <rect
                key={i}
                className={`confetti-piece confetti-piece-${i}`}
                x={60 + (i * 11) % 120}
                y="140"
                width="9"
                height="9"
                fill={["#ff6b6b", "#22c9b8", "#ffd166", "#7bdff2", "#c9a4ff", "#ff9f5a"][i % 6]}
              />
            ))}
          </g>
        )}
      </svg>
    </div>
  );
}
