# Echo frontend rebuild: running design log

Overnight run, backend closeout + frontend rebuild. This file is updated as
each part completes.

## Summary (read this first)

All 9 parts of the overnight run are complete and committed (branch
`rebuild`, one commit per part). What shipped, what's honestly still
missing, and what needs a human decision:

**Backend (Part 1):** the frozen model ran once against speechocean762's
held-out test split (125 speakers, genuinely never touched by any prior
phase) through the real production pipeline. Headline: precision=0.667,
recall=0.216, FRR=0.002 on the child slice - full numbers and a real bug
fix (the naming rule was reporting a category string instead of a
phoneme; fixed) are in `RESULTS.md`. Data-access requests for three
external clinical corpora are drafted (`eval/corpora.md`, not sent).

**Frontend (Parts 2-9):** a zero-dependency mock server for dev-time
review; the mascot rebuilt from scratch (3 real critique rounds); word
illustrations for the 23 highest-priority curriculum words (291 of 314
total words still use the themed-letter fallback - real, not hidden);
a redesigned practice screen (word-card hero, grapheme highlighting,
attempt-driven progress, distinct non-punitive treatment for each of the
4 verdict states); a redesigned home map (fixed two real layout bugs,
added locked/current/completed level states, chaptered into named
worlds); four selectable themes with programmatically-verified contrast
and app-wide reduced-motion support; and a therapist view with a review
queue, per-phoneme stats, and a calibration tab (the last of which is
mock-only pending a backend route that doesn't exist yet).

**Two real bugs found by testing rather than assumed away, left
unfixed and documented rather than silently patched around, because
fixing them means touching `backend/` after Part 1's freeze:**
1. `backend/db.get_or_create_user` has a TOCTOU race condition - two
   concurrent requests for the same brand-new user_id (which React
   StrictMode's double-effect-invocation triggers on literally every
   first login in dev, and which a double-tap or multi-tab open could
   trigger in production) crash one of the two requests with a 500
   (`sqlite3.IntegrityError: UNIQUE constraint failed: users.id`).
   Reproduced cleanly with two concurrent curls. The app recovers - the
   second request's data still renders correctly - so this is a
   background error, not a visible break, but it's real and worth a
   `SELECT ... ON CONFLICT DO NOTHING`-style fix.
2. No API route exposes `backend/db.get_all_speaker_baselines()` - the
   Calibration tab is built and works against a mock-only route; against
   the real backend it degrades gracefully to "not available yet"
   instead of erroring, but the real data isn't reachable until someone
   adds the route.

**Verified, not assumed:** zero console/page errors across every screen
against the mock server; zero horizontal scroll at both 360px and 390px
on every screen (Home, Practice in all 4 verdict states, Practice Tracks,
Level Complete, Therapist Mode's 4 tabs); all 5 themes pass WCAG contrast
at the threshold that actually applies to each pair (programmatic check,
not eyeballed); `prefers-reduced-motion` verified to actually collapse
every animation app-wide via computed-style inspection, not just "the CSS
rule exists"; the full flow (login -> home -> practice -> word display)
verified against the REAL backend, not just the mock, which is what
surfaced bug #1 above.

**Honestly still missing / deprioritized, not silently dropped:** 291 of
314 curriculum words on the themed-letter fallback (tiers 2-4 word art,
never started - time budget); mascot ear "floppiness" (logged in Part 3,
not revisited); a texture/grain overlay (Part 7, deprioritized behind two
real correctness bugs); per-theme rainbow colors on the home map (minor
mismatch in the Space theme specifically); recording playback in the
therapist queue (no audio is stored anywhere in this system, mock or
real - shown as an honest disabled state).

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

## Part 5: Practice screen redesign

Full rewrite of `WordPractice.jsx` plus a large new CSS block
(`.screen-practice--v2` and children) in `index.css`, and a new
`graphemeHighlight.js` heuristic that highlights the letter(s) most likely
to correspond to the target ARPABET phoneme inside the word itself (e.g.
the "m" in "mug" for target `/M/`), with a sound chip (`/M/`) next to the
word as a second, unambiguous channel for kids who can't yet map letters to
sounds. Settings (speak-aloud toggle, rate slider) moved behind a gear
button instead of sitting permanently on screen. Mic button recolored from
red to teal (red reads as an error/stop color, wrong for an action that's
never itself a failure). Progress (word-attempt counter driving the flame
streak) increments on any scored attempt except `unclear_recording` -
deliberately driven by effort, not by the model's verdict, since measured
recall on real errors is only a few percent (RESULTS.md) and can't carry an
honest reward economy on its own.

**Two real screenshot-driven layout rounds, not a single pass:**

Round 1 (`practice-r1.png`, 1280x900): word-card hero, grapheme highlight,
sound chip, and teal mic button all worked, but at wide viewport there was
significant dead space on the left and right of the centered column, and
Echo (the mascot) sat below the word row rather than genuinely "beside" the
card as the brief asked for - the same complaint as the original brief,
just relocated from top/bottom to the sides.

Round 2 fix: restructured the JSX into `.practice-hero-row` wrapping the
word-card and a new `.practice-info-col` (word row + sound chip + mascot),
with CSS making that a `flex-direction: row` pairing at ≥760px and
collapsing to a stacked column below. Verified via fresh screenshots at
both 1280x900 (`practice-r2-wide.png`) and 390x844 (`practice-r2-mobile.png`):
at wide viewport the word card now sits on the left with the word/chip/Echo
genuinely beside it as a pair, dead space substantially reduced; at mobile
width everything stacks cleanly in a single column with no horizontal
overflow and the mic bar stays anchored at the bottom.

**Verdict-state review**: built `mock-server/screenshot_verdicts.mjs`,
which stubs `getUserMedia`/`MediaRecorder` in-page (headless Chromium's
fake-media-device flags hung rather than resolving in this environment, so
rather than fight that, the script substitutes a real-but-silent
`MediaStream`/`Blob` so the actual `handleMicClick` record → score code
path runs for real) and drives the mock status bar's force buttons to
capture `wrong`, `unclear`, and `unclear_recording` as one composite image.
Confirmed the three non-"correct" states are clearly differentiated by
copy and color, not by mascot pose alone: `wrong` shows warm orange
corrective text naming the target sound and models the word aloud at a
slower rate; `unclear` shows calm gray "let's try that one more time"
phrasing with no naming (avoids teaching a wrong sound when the model
itself isn't confident); `unclear_recording` is explicitly framed as a mic
problem ("can you try again a bit closer to the microphone?") rather than
a pronunciation judgment, with a mic emoji reinforcing that framing. All
three offer "Try again" plus "Next word" so a child is never stuck.

**Honest quality note**: the mascot's per-state pose differences for
`demonstrating`/`encouraging`/`thinking` (small ear-rotation and head-tilt
transforms, a few degrees each) are real in the CSS but read as subtle at
110px in a static screenshot - the text/color channel is doing most of the
differentiation work right now, not the mascot's body language. Given this
is the second design pass over the mascot itself (3 critique rounds already
spent in Part 3) and the text/color signal is unambiguous on its own, this
is logged as a polish gap rather than reworked further this run.

Not yet verified in this pass: the `MAX_WRONG_RETRIES` (3) and
`MAX_UNCLEAR_IN_ROW` (2) auto-advance behavior over a full multi-attempt
sequence, and the settings panel's open/closed visual state - both are
implemented but only exercised via code read, not screenshotted.

## Part 6: Home map

Screenshotted Home directly (`mock-server/screenshot_home.mjs`) for the
first time this run - it had only been passed through on the way into
practice before, never actually reviewed on its own - and found the three
bugs the brief named, plus two more real ones caught by testing at mobile
width, which nothing up to this point had done for this specific screen.

**Greeting bug: could not reproduce as described.** `Hi, {user?.id}!`
rendered correctly ("Hi, Jamie!") in every screenshot, including a fresh
page load with only a `localStorage`-seeded user id and no prior session -
`App.jsx` already gates on `loading` before rendering `Home`, and `user` is
set in the same state-update pass that clears `loading`, so there's no
render frame where `user` is set but empty. Logged as not reproduced rather
than silently "fixed" - if this still shows up against the real backend, it
points at that fetch path specifically, not this component.

**MapScenery not covering full height: real bug, root cause confirmed.**
`.map-scenery` was `position: fixed; inset: 0` - which pins a layer to the
current viewport rectangle, not the page's actual scrollable height. A
15-level path is far taller than one screen, so the sun/rainbow/hills only
ever rendered in the first ~900px and everything below level 5 or so sat on
bare white. Fixed by making it `position: absolute` sized to the full
height of `.screen-home` (already `position: relative`) instead of the
viewport, and rebuilding the ground as one continuous vertical gradient
(not viewport-anchored hill art) so it scales to any number of levels.

**Level nodes not showing state: real bug, also now fixed.** Every
not-completed, not-current level (2 through 15) rendered as an identical
solid-orange numbered circle - there was no notion of "locked" at all, only
completed vs. not. Added a `locked` state (`lvl.level > currentLevel &&
!completed`) with a distinct muted-gray bubble, a padlock icon in place of
the level number, and a disabled/non-clickable button - so "the level right
after where you are" and "a level 14 steps away" finally look different,
and locked levels can't be jumped to out of order.

**Redesigned into worlds**, addressing the brief's "4-5 themed worlds" and
solving the height problem at the same time rather than as two unrelated
patches: the path is chaptered every 5 levels into a named world (Meadow
Trail / Forest Path / Mountain Peak / Cloud Kingdom / Starlight Bay, cycling
if there are more), each with its own banner divider and its own
independently-sized trail SVG (so a banner's height never desyncs the
dashed trail from the bubble positions - the two are computed separately
per world section instead of one global calculation). The ground gradient
shifts tone per world. This is intentionally a light version: the actual
Jungle/Space/Ocean/Candy palette *system* as CSS custom properties is
Part 7's job, and these world sections are the seam it hooks into, not a
finished theme.

**Deleted the emoji decoration system in MapScenery specifically** (clouds,
birds, butterflies, bees, squirrel/rabbit/fox critters) and replaced every
one with an authored inline SVG shape, matching the brief's instruction.
Scope note, stated plainly: `FloatingDecor` and `Doodles` (used on Login,
Practice, and layered on Home too) are a separate, more broadly-shared
emoji-based decoration system and were deliberately left alone this pass -
replacing those is a larger, riskier change spanning every screen, better
suited to Part 7's "visual language" pass than bundled into a Home-specific
bug-fix part. Small functional icon-labels elsewhere (the level sticker
emoji, the world banner icon, the 🚩 current-level flag, the 🎤/🔥 icons
used in Practice) were also kept, consistent with how the rest of the app
already uses emoji as compact icons rather than ambient decoration.

## Part 7: Visual language - themes, motion rules, contrast

**Four themes, as CSS custom properties, switchable per-device.** Added
`[data-theme="jungle|space|ocean|candy"]` blocks in `index.css` overriding
the brand/background palette (`--color-bg*`, `--color-primary*`,
`--color-secondary*`, `--color-accent*`, `--color-text*`, `--color-card`,
`--color-ring-track`). Deliberately did NOT theme `--color-success`/
`--color-warning`/`--color-danger` - those carry a fixed semantic meaning
(green=good, amber=caution) that shouldn't shift with the skin. A new
`src/lib/theme.js` persists the choice to `localStorage`
(`speechpal_theme`, independent of the backend's per-user settings - a
color skin isn't a clinical setting and has nowhere to live server-side)
and applies it via a `data-theme` attribute set at module load in
`App.jsx`, before the first paint (a `useEffect` would apply it one frame
late and flash the default theme first). A palette-icon button in Home's
header opens a 5-swatch picker (Sunny/Jungle/Space/Ocean/Candy).
MapScenery's ground-gradient bands also read a per-theme tone set now
(`GROUND_TONE_SETS`), so the map's terrain actually looks like the chosen
world instead of always the same fixed rainbow of bands regardless of
theme. Screenshotted all three new themes side by side
(`mock-server/screenshot_themes.mjs`) - Space (a dark navy/purple theme)
in particular needed checking since it's the one most different in kind
from the rest, and text/mascot/buttons all read cleanly against it.

**Contrast verified programmatically, not by eye**
(`mock-server/check_contrast.mjs`) - it parses colors straight out of
`index.css` (not hand-copied into the script, so it can't silently drift
from what's shipped) and checks every theme's text/background pairs
against the WCAG threshold that actually applies: 4.5:1 for normal text,
3:1 for large bold text (every button/bubble label in this app is >=18px
and font-weight 700, which qualifies). First run found real failures -
not just in the new themes, but in the pre-existing default palette that's
been live since Part 3: white button text on `--color-primary`/
`--color-secondary` was as low as 2.14:1 and 2.52:1 (both fail even the
relaxed 3:1 large-text bar), and secondary body text
(`--color-text-soft`) was just under 4.5:1 on two backgrounds. Fixed by
darkening the specific failing tokens (`--color-primary`,
`--color-secondary`, and `--color-text-soft` in the default and ocean
themes; `--color-secondary` in jungle and space) by the minimum amount
needed to clear the bar - all values recomputed via the actual contrast
formula, not guessed. Re-ran: all 5 themes pass all checks now. This was a
real, previously-unverified accessibility gap in code that predates this
part, caught only because the brief asked for the check to be automated
rather than eyeballed.

**Reduced motion: extended from mascot-only to the whole app.** Before
this part, `prefers-reduced-motion` was only handled inside `mascot.css` -
every other animation (the map's sun/rainbow/clouds/birds/critters/
sparkles, the level trail's marching dashes, the current-level pulse
ring, the flag wave, FloatingDecor's drifting emoji, confetti, the mic
button's idle pulse) had no reduced-motion handling at all. Added one
global rule in `index.css` that collapses every animation/transition
duration to near-zero under `prefers-reduced-motion: reduce`, checked to
confirm it doesn't fight mascot.css's own scoped block (that one also
sets static per-state pose transforms so a state stays visually
distinguishable with motion off - a different CSS property, so the two
rules don't conflict).

**Sticker aesthetic: audited, not rebuilt.** Checked every interactive
element's `box-shadow` for the "solid offset, not blur" pattern the brief
asked for - primary/secondary buttons, the mic button, and level bubbles
already consistently use it (`0 Npx 0 <dark-color>`, established in
earlier parts), so this was a verification pass rather than a rework.
Static content cards (recommendation card, settings panel) intentionally
keep a soft ambient shadow (`--shadow-sm/md/lg`) rather than a hard
sticker edge - a common and deliberate mix (Duolingo does the same:
sticker-style interactive elements, soft-elevation static surfaces), not
an oversight.

**Not done this part, logged honestly:** a paper-grain/texture overlay
(the brief's "texture") was deprioritized in favor of the contrast fix and
motion-rule gap, both of which are real correctness issues rather than
polish; the rainbow decoration in MapScenery still uses fixed rainbow
colors rather than a per-theme palette (a minor mismatch in the Space
theme specifically - a rainbow in a night sky - acceptable but noted); and
themes are currently a Home-screen-triggered, app-wide device preference,
not scoped per-world-section as Part 6's world banners might suggest -
that would be a bigger, separate design decision (does the app's whole
chrome change as you scroll into a new world, or does the player choose
one skin for the whole app?) and picking the simpler, more standard
"user picks an app skin" interpretation was a deliberate scope call, not
an oversight.

## Part 8: Therapist view

Added three tabs to `TherapistMode.jsx` alongside the existing Custom Sets
tab (which was already fully built - custom word lists, dictionary lookup,
manual phoneme override for out-of-dictionary words - and needed no
changes): **Review Queue**, **Phoneme Stats**, **Calibration**.

**Review Queue** is where Phase 5's therapist-queue operating point (no
precision floor, ranked by calibrated probability - RESULTS.md's
recall/precision-at-top-K table) finally has somewhere to live in the
product, not just in an eval script. Shows word, phoneme, probability,
naming status ("named" vs "abstained (not named)" - the same naming rule
from `backend/decision.py`, surfaced honestly rather than re-explained),
and top competitor phoneme. `attempt_history` already stored everything
needed for this except `top_competitor` and an explicit `has_recording`
flag - added both to the mock server's attempt records; the real backend
doesn't persist per-attempt `top_competitor` at all today (only uses it
transiently inside `decision.py`'s naming logic), which is a real,
honestly-logged gap - would need a `backend/` schema change to close, out
of scope after Part 1's freeze.

**Recording playback**, which the brief asked for, does not exist anywhere
in this system - `scorer_phase3.py` scores audio in memory and discards
it, nothing persists a recording to disk or object storage. Rather than
fake it, the row shows a disabled, clearly-labeled 🔇 button ("Recording
not saved - audio is scored in memory and discarded") - an honest
placeholder, not a missing feature pretending to work.

**Phoneme Stats** reuses `phoneme_errors` from `useApp()` (already fetched
by `AppContext` for Home's recommendation card - no new API call needed) as
a simple horizontal bar chart of wrong-verdict counts per phoneme.

**Calibration** surfaces the per-child running baseline
(`backend/db.py`'s `speaker_baseline` table / `get_all_speaker_baselines`)
- mean/std GOP per phoneme, the numbers `child_calibration.py`'s
speaker-relative features are computed against. Real problem: **no route
exposes this over HTTP** - `main.py` never wraps
`get_all_speaker_baselines()` in an endpoint. Since backend/ is frozen
after Part 1, this run can't add one. Handled honestly rather than
skipped or faked: added a mock-only `/api/therapist/calibration/:userId`
route (clearly commented as mock-only in `server.js`) so the UI could be
designed and reviewed now, and `api.getTherapistCalibration()` calls it
with a try/catch that degrades to `null` on any failure - against the
real (frozen) backend this 404s today and the tab shows "Calibration
state isn't available yet" instead of crashing, so Part 9's "works
against real backend" check still passes; wiring the real route is a
one-line addition for a future backend-touching session.

**Real bug caught while testing:** the mock server process running for
this whole session was started before these changes and Node doesn't
hot-reload - screenshotting the review queue against the live dev server
returned attempt records with no `top_competitor`/`has_recording` fields
at all (the OLD code, still in memory) until the process was manually
restarted. Worth remembering for any future part of this run: a `server.js`
edit needs a restart, not just a save.

**Two bugs caught only by testing at 390px, not visible at desktop width:**
1. `.home-header` (greeting + mascot vs. the speech-toggle/practice/
   therapist icon buttons) had no `flex-wrap`, so at 390px the right-hand
   button group ran 50px past the viewport edge - real, silent horizontal
   overflow, never caught because every prior screenshot of this session
   was either desktop-width or of a different screen. Fixed by wrapping
   the header and giving the button group `flex-shrink: 0` so it drops to
   its own row instead of overflowing.
2. Smaller residual overflow: `.level-path-name` labels at a high trail
   offset (up to 75% of row width) had too little room left beside the
   bubble on a narrow screen regardless of their own max-width, since the
   bubble alone already consumed most of the row. Rather than fight the
   trail's horizontal offset system on mobile, the labels are hidden below
   480px - the level name is still reachable via the bubble's title
   tooltip and is shown prominently once a level is actually opened.
   Verified `document.documentElement.scrollWidth === innerWidth` (no
   horizontal scroll at all) at both 390px and the brief's stated 360px
   minimum, for both Home and Practice.

## Part 9: Final pass

**Composite screenshots** across every screen at 1280px and 390px (Home,
Practice, Practice Tracks, Therapist Mode's 4 tabs, Level Complete,
Mascot Lab, Word Art Lab) - most were already captured and reviewed
individually as each part landed; this pass added the ones that hadn't
been looked at yet this session (Practice Tracks, Level Complete) and one
final side-by-side grid of Home+Practice at both widths together, which
incidentally confirmed the locked/current/completed level states still
read correctly as progress advances past level 1 (level 2 now shows
unlocked-and-current with the flag, levels 3+ still locked) - not just in
the fresh-user state every other screenshot this session happened to
capture.

**Verification checklist, each one actually run, not assumed:**
- *Horizontal scroll at 360px/390px*: `document.documentElement.
  scrollWidth === innerWidth` checked on every screen (Home, Practice in
  all 4 verdict states, Practice Tracks, Level Complete, Therapist Mode's
  4 tabs). All clean now - see Parts 5, 6, and 8 for the real overflow
  bugs this caught and fixed along the way (none new this pass).
- *Contrast*: `mock-server/check_contrast.mjs` (Part 7) - all 5 themes
  pass the WCAG threshold that applies to each text/background pair.
- *Reduced motion*: didn't just confirm the CSS rule exists - launched a
  Playwright context with `reducedMotion: "reduce"` and read back
  `getComputedStyle().animationDuration` on live elements (the map sun,
  a sparkle, the current-level pulse): all collapse to ~0.01ms as
  intended. Separately confirmed the mascot's own per-state reduced-motion
  poses (Part 3) still resolve to distinct static transforms per state
  under the same emulated setting - the app-wide kill switch added in
  Part 7 doesn't fight the mascot's more nuanced per-state handling.
- *Console errors*: zero `console.error`/`pageerror` events across every
  screen and interaction path tested, against the mock server.
- *Works against the real backend*: actually started `backend/main.py`
  with `uvicorn` (not assumed from reading the code) and ran the frontend
  against it. Login, Home (real level data, greeting, locked states),
  Practice (real word/phonemes loading), and Therapist Mode all rendered
  correctly. This is what surfaced the two real bugs in the summary at
  the top of this file - a login race condition in `backend/db.py` and
  the missing calibration route - both logged there rather than fixed,
  since fixing either means editing `backend/` after Part 1's freeze.

**Honest final critique, not smoothed over:**
- The single biggest gap is real-word-art coverage: 291 of 314 curriculum
  words still render a themed-letter fallback card, not an illustration.
  This is the most visible unfinished piece of the whole run.
- The mascot's ears read as upright rather than "floppy" as originally
  asked (Part 3, not revisited since).
- Part 7's "texture" (a paper-grain overlay) was never built - two real
  correctness bugs (contrast failures, missing reduced-motion coverage)
  took priority over that polish item, which was the right call given
  limited time, but the texture itself is still just not there.
- The Space theme's rainbow decoration uses fixed (non-themed) colors, a
  minor visual mismatch (a bright rainbow in a night sky) not worth a
  special-case fix given everything else that theme gets right.
- Two real, reproduced-not-assumed backend bugs are documented but
  intentionally NOT fixed (see the top-of-file summary) - this is a
  deliberate scope decision under the brief's "don't touch backend/ after
  Part 1" rule, not an oversight, but it means the app has one narrow,
  real failure mode (a first-login race) that a human should decide
  whether to fix before this ships anywhere real users would hit it.

All 9 parts are committed (branch `rebuild`). This is the final commit of
the overnight run.

## Post-run: both documented backend bugs fixed

Corrected after review: the "don't touch backend/" freeze covers the
frozen model/features/thresholds (`eval/phase3_protocol.md`'s modeling
freeze), not the entire `backend/` directory - neither bug below touches
any of that, so both were fixed rather than left as documented-but-broken.

**Login race condition**, `backend/db.get_or_create_user`: was a plain
SELECT-then-INSERT, racy under two concurrent requests for the same
brand-new user_id. Fixed with `INSERT ... ON CONFLICT (id) DO NOTHING`
(atomic, idempotent) followed by the SELECT. Also added
`PRAGMA busy_timeout = 5000` to `get_conn()` so any concurrent-write path
in this file waits briefly instead of raising `database is locked`
immediately. Verified by firing 5 pairs of genuinely concurrent first-
login requests (10 requests total, 5 brand-new user_ids) at the real
backend: 10/10 returned 200, zero errors in the server log - the same
test that produced a 500 before the fix.

**Missing calibration route**: added `GET /api/therapist/calibration/
{user_id}` to `backend/main.py`, wrapping the `db.get_all_speaker_
baselines()` that already existed. Verified against the real backend:
the Therapist Mode Calibration tab now renders "No calibration data yet"
(the correct empty state) instead of the old "not available yet" 404
fallback. Updated the stale "doesn't exist yet" comments in `api.js`,
`TherapistMode.jsx`, and the mock server (which keeps its own simulated
route for dev/screenshot review - fabricating plausible baseline numbers
for phonemes a mock user has never really attempted, which the real
route correctly won't do).
