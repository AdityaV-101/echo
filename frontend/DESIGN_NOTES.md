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

## Part 4: Word illustrations

Built the real system (`frontend/src/assets/wordArt.jsx`: one inline SVG
sprite, `<symbol>` per word, `<use>` to reference; `frontend/src/components/
WordCard.jsx`: real art or a themed initial-letter fallback, never bare
text) and illustrated **23 words** for real - the Level 1-3 concrete nouns
(ball, bed, bus, cup, dog, door, duck, ham, hat, hen, man, map, moon, mud,
mug, net, nose, pen, pig, pot, pup, top, web).

**Deliberately not illustrated, and not a gap**: Level 1-3's abstract/
function words (no, we, yes, wet, hop, yum) - there's nothing concrete to
draw for these that a 4-year-old would recognize faster than the printed
word itself; a forced literal icon would be worse than the themed fallback
card. Tiers 2-4 (R/S practice tracks, levels 4-8, everything else) were not
started this run - 291 of 314 total distinct words across `levels.json` +
`practice_tracks.json` currently render the fallback card
(`node mock-server/check_word_art.mjs` to regenerate this count/list).

**Two real bugs caught by building `/word-art-lab` and actually looking**,
not just described from writing the code:
1. `mud` was listed in `WORD_ART_COVERAGE` but I never wrote its `<symbol>`
   - rendered as a blank card. Added the missing symbol (a puddle + splash
   dots).
2. The fallback letter was nearly invisible - `font-size: 40%` in CSS
   resolves against the INHERITED font-size, not the card's own pixel
   size, so a 140px card's letter was rendering at ~6px. Fixed by sizing
   the letter from the actual `size` prop in JS instead of a CSS percentage.

**Honest quality note, not smoothed over**: reviewing the composite image,
`dog` reads more like a monkey (ear shape/brown tone), `pup` is a bit
indistinct, `net` doesn't clearly read as a fishing/butterfly net (comes
across as a striped funnel), and `top` (the spinning toy) reads more like a
carrot than a toy. `ham` is recognizable but weak. These are the icons I'd
redraw first if continuing - listed here rather than left for someone else
to discover. `ball, bed, bus, cup, door, duck, hat, hen, pen, pig, man, map,
moon, mug, nose, web` read clearly and are the icons I'd point to as the
actual target quality bar.
