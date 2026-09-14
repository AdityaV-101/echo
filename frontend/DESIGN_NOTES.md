# Echo frontend rebuild: running design log

Overnight run, backend closeout + frontend rebuild. This file is updated as
each part completes - see the top for a rolling summary once more parts land.

## Part 3: Mascot (3 rounds, as required)

Deleted the old flat geometric bird-logo mark entirely (per the brief - not
evolved). Rebuilt as a rigged SVG: named groups `#ear-l #ear-r #eye-l #eye-r
#lid-l #lid-r #pupil-l #pupil-r #mouth #body #arm-l #arm-r #shadow`, each
with an explicit transform-origin, states driven by CSS classes on
`.mascot-wrap--{state}`.

**Round 1 finding (self-critique, not polish):** the ear tips converged to a
sharp point - read as horns, not "soft and slightly floppy" fur. Also found
a real functional bug while reviewing the celebrating/encouraging states:
the arm rendered as a detached blob nowhere near the body. Root cause:
`transform-box: fill-box` in CSS combined with inline pixel
`transform-origin` values (e.g. `"64px 222px"`) - with `fill-box`, a pixel
transform-origin is interpreted as an OFFSET FROM THE ELEMENT'S OWN
BOUNDING BOX, not an absolute SVG coordinate, so every rotate/scale on a
rigged part was pivoting around the wrong point. Fixed by switching to
`transform-box: view-box` everywhere, which makes the same inline values
mean what they look like they mean.

**Round 2 finding:** re-drew both ears as a rounder, leaf/paisley silhouette
with a genuine asymmetry (left ear droops lower, wider tip curl) instead of
a mirrored pair - confirmed via screenshot the arm-detachment bug was gone
and the ear shape read noticeably softer. Still standing fairly upright
rather than truly "flopping" - logged as remaining polish, not re-drawn a
third time given the overnight time budget.

**Round 3 finding:** confetti wasn't visible in any celebrating screenshot
at any wait time, including 100-400ms into an 850ms+1.3s animation.
Instrumented the live page directly (`getComputedStyle` on a
`.confetti-piece` at 100ms) rather than guessing: opacity was already
~0.10, ten times faster than the 1.3s duration should allow. Cause: the
single `animation: confetti-fall 1.3s ease-out forwards` shorthand applied
the SAME `ease-out` timing curve to the opacity keyframe as to the
position/rotation keyframes - ease-out front-loads motion, which also
front-loaded the opacity fade almost to invisible within the first tenth of
the animation. Fixed by giving opacity its own keyframe stop (stays at 1
until 70%, only fades in the last 30%), decoupling it from the position
easing. Confirmed present (small falling dots near the feet) in the round-3
screenshot, though subtle in a static composite where every state is
mounted at once rather than fired live on an actual attempt.

**Honest state of the mascot after 3 rounds:**
- Large, low-set eyes with real iris/pupil/highlight - not a flat dot. Reads well.
- Warm coral/amber body pops clearly against both light and dark backgrounds -
  directly fixes the old green-on-green invisibility problem.
- Ears are the dominant visual feature and asymmetric, as intended - but
  stand more upright than truly "floppy." Would push further with more time.
- All 7 states are visually distinct at a glance. Verified structurally
  (not just by eye) that no sad/red/frown/X state exists anywhere in the
  CSS or JSX - the hard "no failure state" rule has nothing to accidentally
  trigger.
- 4 celebrate variants exist (differing arm spread, jump height, tilt) and
  cycle via a `celebrateVariant` prop - caller (WordPractice, Part 5) needs
  to increment this per attempt so it doesn't repeat identically every time.
- Not yet tested against real theme palettes (Part 7 builds the actual
  Jungle/Space/Ocean/Candy themes) - only placeholder light/dark swatches
  shown in `/mascot-lab` so far. Re-check once themes exist.
- `prefers-reduced-motion: reduce` stops every loop/transition; verified the
  rule exists for every animated state, not spot-checked per-state.

Screenshots from all 3 rounds are in the session scratchpad, not committed
(they're throwaway debug artifacts, not product assets).
