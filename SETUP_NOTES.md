# Setup notes: IPA/ARPABET mapping and scoring calibration

**The scoring architecture described in most of this file (everything from
here down to "Alignment scoring") was replaced, not patched, by forced
alignment + GOP scoring - see DIAGNOSIS.md for exactly what was wrong with
it and "Forced alignment + GOP rebuild" below for the replacement.** The
sections below "Forced alignment + GOP rebuild" are kept as history (some
of the IPA-mapping reasoning, and the reason the recognizer itself was
switched to wav2vec2, are still accurate and still apply), but none of the
target-phoneme-focus / confidence-window / whole-word-alignment scoring
logic they describe exists in the code anymore. Jump to "Forced alignment +
GOP rebuild" for how scoring actually works now.

## Why a mapping is needed at all

`cmudict` (the canonical/expected phoneme source) uses ARPABET, a fixed
39-symbol American English inventory. `allosaurus` (the recognizer) is a
*universal phone* model: even restricted to `--lang eng` it can emit narrow
IPA symbols that never appear in ARPABET at all (aspiration marks, flaps,
glottal stops, syllabic consonants, nasalized vowels). Comparing the two
sequences requires collapsing the recognizer's narrow output down to the
same 39-symbol space cmudict uses. That mapping lives in
`backend/ipa_arpabet.py`.

## Mapping approach

1. Strip combining diacritics (aspiration `ʰ`, length `ː`, nasalization
   `̃`, palatalization `ʲ`, velarization `ˠ`, syllabicity marks) before
   lookup, since these modify a base phone without changing its ARPABET
   identity for this app's purposes.
2. Look up the stripped symbol in `IPA_TO_ARPABET`, a hand-built dictionary
   covering the ~39 core English phonemes plus the allophones allosaurus is
   likely to emit for English speech.
3. Anything still unmapped is logged as a warning and dropped from the
   recognized sequence rather than crashing the request. In testing this
   dictionary covered every symbol allosaurus produced for both synthesized
   (macOS `say`) and live speech; the warning path exists as a safety net for
   the two edge cases below and any narrow-transcription output that wasn't
   exercised (e.g. a heavier r-coloring or breathiness marker).

## Allophone decisions that aren't clean 1:1 mappings

These needed a judgment call because ARPABET has no dedicated symbol for
them:

- **Alveolar flap `ɾ`** (American "butter", "ladder") → mapped to `T`. This
  is the standard allophone of intervocalic /t/ (and often /d/) in American
  English, so treating it as `T` is correct far more often than not, at the
  cost of occasionally under-flagging a true /d/-for-/t/ substitution in
  that specific phonetic environment.
- **Glottal stop `ʔ`** (American "kitten") → mapped to `T`, same reasoning.
- **Voiceless velar fricative `x`** (loanwords like "loch") → mapped to `K`,
  the nearest ARPABET consonant. This essentially never appears in the
  app's word lists, so it's a defensive mapping rather than one that matters
  in practice.
- **Voiceless w `ʍ`** ("wh-" for some speakers) → collapsed to `W`, since
  ARPABET doesn't distinguish them.
- **Syllabic consonants** (`n̩`, `l̩`, `m̩`, `ɹ̩` — "button", "bottle",
  "rhythm") → mapped to their non-syllabic counterpart (`N`, `L`, `M`, `ER`).
- **Rhotacized vowels** `ɝ`/`ɚ` and the British-leaning `ɜ` → all mapped to
  `ER`, since ARPABET doesn't separate stressed/unstressed rhotic vowels.
- **British/regional vowels** `ɒ` ("hot") → `AA`; `ɜ` → `ER`. These matter
  more for non-American recordings and are approximate by nature.

None of these allophone choices affect the app's core diagnostic targets
(R, S, L, TH, Z, SH, CH, K remain fully distinct symbols throughout).

## Target-phoneme-focused scoring (the main scoring philosophy)

Early testing surfaced two related problems: an adult fluent English
speaker with a non-American accent got flagged for "errors" that were
really just ordinary dialectal vowel variation, and separately, ordinary
phone-recognizer noise on an unrelated sound in the word (a mis-heard vowel,
a garbled context consonant) was enough to tank the score even when the
sound actually being drilled was said correctly. Neither is an articulation
error, and scoring every phoneme in the word made the app feel like it
demanded flawless adult pronunciation of the whole word rather than
screening the one sound therapy actually cares about.

The fix, in `backend/scorer_common.py`'s `apply_target_focus`: every level
word and practice-track word carries a `target_phoneme` (the sound that
specific word is drilling — e.g. "mom" targets `M`, "red" targets `R`). The
frontend sends that phoneme along with each `/api/score` call, and scoring
only judges occurrences of *that* phoneme:

- A wrong or missing occurrence of the target phoneme is still flagged in
  full, and `percent_correct` is computed only over how many times the
  target phoneme appears in the word (e.g. "mom" targeting `M` has 2
  occurrences; getting one right is 50%, not diluted by the vowel in
  between).
- Every other phoneme in the word — vowels, and any non-target consonant —
  is never counted as an error, no matter what the recognizer heard for it.
  This mirrors how a speech-language pathologist actually scores a
  probe word: production of the target sound in context, not a
  transcription-perfect match of the whole word.

This is a deliberate design choice, not just noise reduction: it means the
tool can never flag a wrong sound the level/track isn't actually testing,
so accent variation and recognizer noise on untested sounds simply can't
produce a false "error" anymore. `apply_accent_leniency` (vowel-group
tolerance) remains as a lighter-touch fallback used only when a word has no
declared target phoneme at all — currently just therapist-added custom
words, which don't carry a single designated target sound in this app's
data model.

## Balancing sensitivity vs. accent false-positives on the target sound

Three failure modes showed up in testing, in this order:

1. An early version scored the whole word and flagged normal accent
   variation (on any sound in the word, not just the one being drilled) as
   an error.
2. Once `apply_target_focus` narrowed judging to only the target phoneme,
   a version of it counted *any* substitution on the target sound as wrong,
   which brought back the same false-positive problem in a smaller form:
   an accented production of just the target sound itself could still be
   flagged.
3. The fix attempted for #2 — only flag a substitution when the heard
   phoneme matches a curated list of "known" developmental error patterns
   (R→W, S→TH, etc.), otherwise treat it as recognizer noise — backfired
   into a false *negative*. A recorded case: a child said "bus" for the
   target word "sub" (target phoneme S). The recognizer correctly heard a
   B where the S should have been, but B wasn't on the curated pattern list
   for S, so it was waved through as correct — even though a stop
   consonant with a totally different place and manner of articulation
   than a fricative is essentially never an accent variant, and this was a
   real, obvious miss.

The current rule, `VOICING_COGNATES` in `backend/scorer_common.py` applied
inside `apply_target_focus`, is deliberately narrower than #3's approach: a
target-phoneme substitution is tolerated only when the heard sound is that
target's voiced/voiceless cognate (S↔Z, T↔D, P↔B, K↔G, F↔V, TH↔DH, SH↔ZH,
CH↔JH). Devoicing or voicing a consonant is one of the most common
accent-driven pronunciation differences across languages and isn't, on its
own, evidence of a disorder — but because the tolerance is scoped to a
single, symmetric, phonologically-defined relationship instead of an
open-ended "not on the known-error list" rule, it can no longer accidentally
forgive a heard sound that bears no phonetic relationship to the target.
Everything else on the target phoneme — including an omission, which is
reliable evidence either way — stays flagged. `PLAUSIBLE_SUBSTITUTIONS` (the
old curated list) still exists but is now used only by `scorer_stub.py`, to
make its fake "heard" phoneme look like a plausible child error instead of
arbitrary noise; it's no longer used to judge real recordings.

## Short recordings silently returning no recognition at all

Separately from the scoring-logic issues above, direct testing turned up a
real bug in the recognition pipeline itself: allosaurus can return an
**empty** result for a short clip with no error raised. Confirmed directly —
a 0.41-second recording of the word "red" (synthesized with macOS `say`,
converted the same way the app converts a browser recording) produced `''`
from `recognizer.recognize()`. Padding that exact same audio with silence
before and after made the recognizer work normally and correctly return the
R sound. This matters a lot for this app specifically: single-syllable
therapy target words ("red", "sub", "sun"...) are very often well under a
second when actually spoken, so this wasn't a rare edge case, it was likely
firing routinely.

The practical effect was invisible in the API response: a missing
recognizer result gets aligned as the target phoneme having been omitted,
which reads exactly like the child skipped the sound — there was no signal
anywhere distinguishing "recognizer found nothing to work with" from "the
child didn't make this sound." This is a second, independent source of the
"flags correct pronunciation as wrong" complaint, unrelated to the
substitution-tolerance logic above.

The fix, in `backend/scorer.py`'s `_convert_to_wav`: every recording is
padded with 0.3s of silence at both the start and end (via ffmpeg's
`adelay`/`apad`) before being handed to allosaurus. This is unconditional
and cheap - it never removes information from the recording, and it gives
the recognizer's feature frontend enough lead-in/lead-out room to work with
regardless of how short the actual speech is.

## Graded percent scores instead of only 0% or 100%

Because `apply_target_focus` scores only the word's target phoneme, and
that phoneme almost always appears exactly once per word ("red" targets R
once, "sub" targets S once), a plain right/wrong count has no third value
to land on - every attempt was necessarily either 0% or 100%. That's not a
bug in the sense of returning a wrong number, but it throws away real
information: a near-miss production (say, a slightly fronted S that comes
out sounding like TH) and a totally unrelated sound are clinically very
different results, and the score should be able to say so.

The fix is `_phonetic_closeness` in `backend/scorer_common.py`, applied
through `_result_score` inside `compute_percent_correct`: instead of
correct = 100 / wrong = 0, a substitution is scored by how much of the
target's articulatory identity survived in the heard sound, using standard
place/manner/voicing features (`_PLACE`, `_MANNER`, `_VOICED`) - manner
match worth 45 points, place match worth 40, voicing match worth 15, so a
near-miss like S→SH (same manner and voicing, different place) lands around
60%, while a wildly different sound like S→B (nothing shared) still lands
at a hard 0%, same as before. An omission still gets no partial credit
either way, since the target sound being entirely absent is reliable
evidence regardless of how close a *production* might otherwise have been.
This only changes the *texture* of the score, not its sensitivity: the
voicing-cognate tolerance and phonetic-noise filtering described above still
decide correct-vs-not first; grading only kicks in for what's left over.

## A word's first sound scoring worse than the rest of it

Reported pattern: a word's first sound was flagged wrong noticeably more
often than the rest of the word, even said carefully, and waiting a beat
after starting the recording before speaking didn't help.

That last detail rules out a simple "recording started late and clipped
the first sound" explanation - that would be fixed by waiting. What
waiting can't fix is browser mic processing: `getUserMedia({ audio: true
})` defaults to echo cancellation, noise suppression, and auto gain
control all on, and all three are *adaptive* - they calibrate against
whatever signal they're currently seeing. The moment they have the least
data to calibrate from is exactly the moment speech starts (going from
room noise to a voice signal), regardless of how long that room-noise
period lasted beforehand. So the first sound of an utterance is
systematically the part most likely to get run through a still-adapting
filter, while the rest of the word benefits from processing that's since
settled down. These modes are also tuned for perceptual quality on human
phone/video calls, not for feeding a phone recognizer, so they're not
even helping the app's actual use case.

The fix, in `frontend/src/lib/useRecorder.js`'s `start()`: request the mic
with `echoCancellation: false`, `noiseSuppression: false`,
`autoGainControl: false`. Confirmed directly that Chrome honors all three
(checked via `track.getSettings()` after acquiring the stream - all three
report `false`), so the recognizer now sees the same raw signal quality
across the whole word instead of a processed-and-settled tail following a
still-calibrating head.

## A wrong word passing because the right symbol showed up somewhere

The most serious accuracy bug found in this app: reported directly as "I
said 'gip' for 'pig' and it said correct." Confirmed and root-caused, not
just patched on faith.

`align.py`'s Needleman-Wunsch alignment works purely on the phone *symbol*
sequence - it has no idea when in the recording anything actually happened,
only what order things came in relative to each other. That's fine for a
clean recognition, but it breaks down under real-world noisy recognition:
if a recording of "gip" gets badly garbled and only a trailing P survives
(G and the vowel both drop out of recognition entirely, which is a
completely ordinary failure mode for a short, quiet, or fast recording),
the aligner has exactly one P in the canonical sequence (`P IH G`, the
initial sound of "pig") and exactly one P in what it recognized - so it
matches them, and calls the initial P "correct." The child said a
different, nearly-reversed word, and the target sound was actually at the
*end* of what they said, not the start - but nothing in a symbol-only
alignment can tell the difference between "the initial sound was produced
correctly" and "some P showed up somewhere in the recording."

The fix uses information the app already collects but never used for
scoring: each word's `position` field (initial/medial/final - already in
`levels.json` per word, and derivable from each practice-track tier's name,
e.g. "Initial, 1 syllable"). `_validate_target_position` in
`backend/scorer_common.py`, called from `apply_target_focus`, cross-checks
a target-phoneme match against where it actually falls among everything
else that got recognized: an initial-position target's match must be the
*first* phone actually heard in the recording; a final-position target's
match must be the *last*. A match that fails this gets downgraded to
"omitted" (no reliable evidence), not left as a false "correct."

The subtle part: a single surviving recognized phone is *never* enough to
confirm position on its own, even if it happens to be the target. With
nothing else recognized to compare against, "it's the only thing heard"
trivially satisfies both "first" and "last" at once - which is exactly the
degenerate case the reported bug reduces to (only the trailing P survived,
full stop). So `_validate_target_position` requires at least one other
independently-recognized phone before relative order means anything;
otherwise it demotes too, regardless of the position check passing
trivially. Verified against a full matrix of cases (both directions -
real errors that must stay flagged, and genuinely correct productions,
including short/sparse ones, that must still pass) before and after this
change; see the test matrix used during development for the exact cases.
Medial-position targets and practice-track tiers with no clean single
position (consonant clusters, multisyllabic/phrases) are left unvalidated,
since there's no single "must be first/last" expectation for them to check
against - the existing target-focus and voicing-cognate logic is all that
applies there, same as before.

`position` is now threaded end-to-end: `WordPractice.jsx` sends the
word's `position` alongside `target_phoneme` to `/api/score`, `main.py`
forwards it to `score_word()`, and both `scorer.py` (real) and
`scorer_stub.py` (fake) pass it through to `build_response` /
`apply_target_focus`.

## An omission isn't as confident a signal as it was assumed to be

Reported directly: "I said 'pic' for 'pig'" - functionally identical to
"pig" for the purposes of the target sound (P, initial; "pic" and "pig"
differ only in their final consonant, which isn't the target) - "and it
said the P sound got left out." That's a recognizer miss on a sound that,
by the app's own design, should be judged the same whether the rest of
the word was "pic" or "pig".

Investigating this surfaced a wrong assumption in earlier scoring design.
`compute_percent_correct` originally gave an omission a flat 0, reasoned
as: the target sound being entirely absent from the recognizer's output is
reliable evidence either way, so (unlike a substitution, where grading how
close the wrong sound was is the valuable signal) there's nothing to grade.
Direct testing didn't support that. Stress-testing the recognizer against
deliberately quiet audio (down to -45dB, an extreme test) showed it's
fairly robust to volume alone - so a plain loudness explanation doesn't
fully account for this - but the underlying point stands regardless of the
exact mechanism: a universal phone recognizer can fail to detect a real,
correctly-produced sound, for reasons (accent, mic/room characteristics,
a given voice's acoustic profile) this app has no way to rule out per
recording. "The recognizer heard nothing" is weaker evidence than "the
recognizer heard something clearly different," and scoring it with the
same flat-0 confidence as a gross substitution risked exactly the failure
mode this app must never have: a genuinely correct, possibly just
atypically-produced or accented attempt read back as a confident wrong.

The fix, `_OMISSION_BASELINE_SCORE` in `backend/scorer_common.py`: an
omission now scores 25 instead of 0. It still reads clearly as "needs
practice" (well below any graded substitution's typical range, and far
below a real match's 100), and a word whose target was genuinely never
produced still comes through as a low score - this isn't about hiding real
omissions. It's about not asserting near-certainty on evidence that isn't
actually that certain. Two smaller, complementary changes landed alongside
this: `frontend/src/lib/useRecorder.js` re-enables `autoGainControl` in
the mic capture (it doesn't reshape the signal's spectral content the way
echo cancellation and noise suppression do, so it stays off-by-default-safe
while helping a quiet recording reach an audible level at all), and
`backend/scorer.py`'s `_convert_to_wav` adds `dynaudnorm` loudness
normalization as a server-side backstop, independent of whatever a given
browser/device's AGC actually does. Neither is proven to be *the*
mechanism behind this specific report (the volume stress test above didn't
reproduce a failure to fix), but both are low-risk, defensible robustness
improvements against the broader category of "quiet or atypical recording,
same correct sound" - the omission-scoring change is the one with direct
evidence behind it.

## Switching the recognizer: allosaurus -> wav2vec2

Every fix above this point improved how the app *judges* what the
recognizer heard. None of them can fix the recognizer itself being wrong -
and direct A/B testing on ordinary, correctly-pronounced English words
showed allosaurus (the original recognizer) doing exactly that, confidently:

| word | target | allosaurus top guess | actual |
|---|---|---|---|
| "bus" | B | **V**, 97.5% confidence | B never above 1.4% |
| "jam" | JH | (JH not in top-5 at all) | closest candidate: ʃ at 24% |
| "chip" | CH | (CH not in top-5 at all) | top guess: K at 62% |

These weren't edge cases - a random 20-word sample across the app's own
level data came back correct only 50% of the time. This is a ceiling no
amount of scoring-logic tuning can fix, because the information (that the
sound really was, say, a B) was never in the recognizer's output to begin
with. allosaurus is a small *universal* phone recognizer, deliberately
built to cover ~2000 languages in one lightweight model; this app only
ever needs English, and trades breadth for accuracy the app doesn't need
by using `facebook/wav2vec2-lv-60-espeak-cv-ft` instead - a wav2vec2 model
fine-tuned to output IPA phones directly, trained on real speech across
60 languages rather than allosaurus's much smaller multilingual corpus.
Direct re-test on the exact same recordings: "bus" -> `b a s`, "jam" ->
`dʒ ɛ m`, "chip" -> `tʃ ɪ p` - all correct. The 20-word sample went from
10/20 wrong to 0/20 wrong; a second, independent 15-word sample (including
multisyllabic words) came back 13/15 correct, with the two exceptions
being a genuine acoustic ambiguity (see below) rather than a recognizer
miss.

**New dependencies**: `torch`, `transformers`, `phonemizer` (Python, in
`requirements.txt`), plus the system package `espeak-ng` (`brew install
espeak-ng` on macOS) - the phoneme tokenizer's `__init__` unconditionally
initializes a phonemizer backend even though this app only ever uses it in
the decode direction (audio -> phones), not the text -> phones direction
that actually needs espeak. The model weights (~1.2GB) download once from
Hugging Face on first use, the same lazy-load-and-cache pattern
`_get_recognizer()` used for allosaurus's weights.

**Confidence-window scoring was built for allosaurus's output shape, but
transfers directly** - `recognize(..., topk=5, timestamp=True)` gave
allosaurus's own decoder's emitting frames with alternates; the wav2vec2
integration in `scorer.py`'s `_recognize()` produces the same
`(start_time, [(phone, probability), ...])` shape by taking the model's
raw per-frame logits (~20ms/frame, softmax'd) directly, with `<pad>`
(this model's CTC blank token) mapped to the same `"<blk>"` sentinel
allosaurus used - `scorer_common.py`'s confidence-window functions don't
know or care which recognizer produced their input.

**IPA symbol coverage**: `ipa_arpabet.py`'s mapping table, originally built
against allosaurus's output, needed only two additions after switching
(`ᵻ`, `əl` - see the table) despite this model's vocabulary having ~388
phone symbols against allosaurus's much smaller set. The other ~270
unmapped symbols are real IPA, just not English ones (Mandarin tone-marked
vowels, French/German front-rounded vowels, retroflex consonants from
Hindi/Vietnamese, etc.) - expected from a 60-language model, and they
never appeared once across the entire English test matrix in this file's
history (confirmed directly, not assumed).

**A genuine remaining hard case, not a bug**: "hair" (canonical HH-EH-R)
scores low because the recognizer's best guess is `h eː` - no distinct R
phone at all. This isn't a recognition failure so much as a linguistic
one: "hair" is acoustically an r-colored vowel, not a vowel followed by a
separate consonant, and the model reasonably transcribes what it actually
hears (one merged rhotic vowel) rather than what cmudict's ARPABET
decomposition expects (a vowel, then a distinct R). No amount of window
tuning fixes a phone the recognizer never emits in the first place; this
would need either accepting rhotic-vowel IPA symbols as evidence of R, or
a different canonical source for r-colored words specifically. Left as a
known limitation rather than papered over.

## Forced alignment + GOP rebuild

Full replacement of the scoring engine, per explicit instruction: not a
patch on the confidence-window approach above, a different architecture.
`backend/align.py` (Needleman-Wunsch) is deleted; every scoring function
that guessed at time windows or free-recognized-then-diffed
(`scorer_common.py`'s old `apply_target_focus`, `expected_time_window`,
`build_response_from_confidence`, etc.) is deleted too - see git history if
any of that reasoning is needed again, but none of it runs anymore.
`DIAGNOSIS.md` (repo root) has the full pre-rebuild diagnosis this was
built from.

**Why**: the word a child is asked to say is always known in advance, so
the scorer should never be guessing what sequence of phones was produced
or where in the recording each one landed - it should force-align the
*known* sequence and measure how well the model's own posterior favored
each expected phone at its actual frame boundaries. See DIAGNOSIS.md for
exactly how window-guessing produced the "first phoneme reported wrong
when later ones are actually the problem" bug pattern.

**New files**: `backend/model_vocab.py` (ARPABET<->model vocab mapping,
verified at startup), `backend/gop_scorer.py` (emissions, forced alignment,
GOP + competitor computation), `backend/gop_config.py` (every tunable
constant, in one place), `backend/calibration.py` (Welford's-algorithm
speaker baseline + z-score classification), `backend/audio_preprocess.py`
(trim/pad/normalize/reject-silence), `backend/data/accent_variants.json`.
`backend/scorer.py` and `backend/scorer_stub.py` were rewritten in place
(same `score_word` signature main.py imports either of) rather than
renamed, so nothing else had to change to wire the new engine in.

### ARPABET -> espeak-ng ground truth table

Required to be verified, not guessed: every ARPABET phoneme cmudict can
produce was looked up by running `phonemizer`'s espeak-ng backend
(`en-us`, the same phonemizer configuration this model's training labels
were produced with) on a word chosen to isolate that phoneme, then that
exact IPA symbol was checked against
`Wav2Vec2Processor.from_pretrained(...).tokenizer.get_vocab()` directly.
All 39 phonemes matched on the first attempt - see `backend/model_vocab.py`
for the resulting `ARPABET_TO_MODEL_VOCAB` dict and
`verify_vocab_coverage()`, which re-checks this exact table against the
loaded model at every server startup and refuses to start the real scorer
if anything doesn't match (a version bump of the model, for instance,
could silently change its vocab).

| ARPABET | word used | espeak-ng output | symbol used |
|---|---|---|---|
| P | pig | pɪɡ | p |
| B | bed | bɛd | b |
| T | cat | kæt | t |
| D | bed | bɛd | d |
| K | cat | kæt | k |
| G | pig | pɪɡ | ɡ |
| F | fish | fɪʃ | f |
| V | vote | voʊt | v |
| TH | thumb | θʌm | θ |
| DH | this | ðɪs | ð |
| S | sun | sʌn | s |
| Z | zoo | zuː | z |
| SH | fish | fɪʃ | ʃ |
| ZH | measure | mɛʒɚ | ʒ |
| HH | hop | hɑːp | h |
| CH | chip | tʃɪp | tʃ |
| JH | judge | dʒʌdʒ | dʒ |
| M | mom | mɑːm | m |
| N | sun | sʌn | n |
| NG | sing | sɪŋ | ŋ |
| L | look | lʊk | l |
| R | red | ɹɛd | ɹ |
| W | wet | wɛt | w |
| Y | yes | jɛs | j |
| IY | leaf | liːf | iː |
| IH | fish | fɪʃ | ɪ |
| EY | day | deɪ | eɪ |
| EH | bed | bɛd | ɛ |
| AE | cat | kæt | æ |
| AA | mom | mɑːm | ɑː |
| AO | ball | bɔːl | ɔː |
| OW | vote | voʊt | oʊ |
| UH | look | lʊk | ʊ |
| UW | zoo | zuː | uː |
| AH | sun | sʌn | ʌ |
| ER | bird | bɜːd | ɜː |
| AW | cow | kaʊ | aʊ |
| AY | my | maɪ | aɪ |
| OY | boy | bɔɪ | ɔɪ |

Two judgment calls, both documented in `model_vocab.py` and neither
affecting a clinical target consonant (this app never targets a vowel):
**AH** covers both the stressed vowel in "sun" and the unstressed schwa in
"sofa"/"about" in cmudict (stress digits are stripped before this app ever
sees the phoneme) - the stressed form (ʌ) is used. **ER** covers both the
stressed rhotic vowel in "bird" and the unstressed one in "measure" -
the stressed form (ɜː) is used, since this app's Vocalic R practice track
targets are mostly stressed ("bird"-type) words.

### Accent variant tolerance

`backend/data/accent_variants.json`, seeded per explicit request with
common Indian English L1-transfer patterns. Every variant symbol was
checked against the model's vocab the same way the primary mapping was;
one seed entry (DH's dental-d variant, `d̪`) was dropped because that exact
symbol does not exist anywhere in this model's ~388-symbol vocabulary,
unlike its voiceless counterpart `t̪` (kept under TH) which does - see the
file's own `_comment` field. Toggle: `users.accent_tolerance_enabled` in
the database, defaulting on; wired through `/api/settings` and read in
`main.py`'s `/api/score` handler.

### Espeak-ng synthesis rate

Not a code decision but worth recording since it affects every test
result in this section: espeak-ng's default speech rate (~175wpm) produced
audio where this project's own model **confidently misheard a cleanly
synthesized final stop as a nasal** - a direct, frame-level-verified
finding, not a guess (see the smoke-test debugging trail: "pig" at default
rate put `ŋ` at -0.58 log-prob and the correct `ɡ` roughly -6.7 lower at
the aligned frame). Testing several rates (170 default, 130, 120, 110,
100) showed no single rate is clean for every phoneme simultaneously, but
130 was a reasonable, moderate middle ground and is what `-s 130` in
`eval/generate_synthetic.py` uses throughout. This is a real limitation of
using an older formant-synthesis TTS engine (espeak-ng) as a stand-in for
natural human speech when evaluating a model trained on real recordings
(CommonVoice) - see "Eval results" below for how much this likely still
costs in the derived global prior's variance.

### Eval results

Run via `python3 eval/generate_synthetic.py` (40 target/error word pairs,
espeak-ng `-s 130`) then `python3 eval/sweep.py` (derives `GLOBAL_PRIOR` and
sweeps `Z_WRONG_THRESHOLD`) then `python3 eval/run_eval.py` (scores the
whole corpus through the actual production `scorer.score_word`, not a
reimplementation). Current `backend/gop_config.py` values were copied
directly from this sweep's output.

**Bottom line, stated plainly per instruction not to spin this: accuracy on
the correct-vs-error decision is 58.8% (via the full production scorer,
including accent-variant tolerance; 73.8% via the raw z-score-only sweep
before accent tolerance and the stricter "any borderline phoneme also
fails the word" rule are applied) - false accept rate (a real error scored
as fully correct) is 32.5%, false reject rate (a correct production scored
as an error) is 50%. This is not a passing grade for a shipped product.**

What's actually working, verified independently of the accuracy numbers:
- Forced alignment itself: every one of 80 test recordings produced
  exactly the expected number of spans in the expected order (the
  defensive check in `align_canonical` that would raise on a mismatch
  never fired once).
- The vocab mapping: 100% verified against the live model, zero silent
  failures.
- The mechanism for catching some of the classic developmental
  substitutions genuinely works on clean examples - e.g. "wed" scored for
  target "red" (a control case from a prior session, not part of the
  40-pair corpus) correctly identified R as wrong with W as the top
  competitor.

What isn't working, and why (this is the honest part):
- **The dominant failure mode is false accepts on exactly the error
  patterns this app most needs to catch**: R->W gliding ("rabbit",
  "run"), K->T fronting ("cat", "king"), TH-fronting/stopping ("thumb",
  "think"), DH-stopping ("that") all scored the deliberately-wrong phoneme
  as "correct" in the eval run. In each case the phoneme's z-score landed
  just inside the "correct" band (roughly -0.2 to -1.0), not because the
  GOP was actually good, but because the **global prior's std for that
  phoneme is large enough to swallow the error** - e.g. G's prior is
  mean=-4.05, std=2.73 from only 5 samples ranging from -0.87 to -8.16
  across 5 different words. That range exists because GOP for a given
  phoneme varies substantially by phonetic context and by word (and,
  probably, by quirks of this specific TTS voice) - a single
  context-blind "mean/std for this phoneme, full stop" prior is too coarse
  to reliably separate a real error from ordinary word-to-word variation
  once that variation is this wide. The mandatory smoke test result below
  is the clearest single illustration of this: G's z-score for the "pin"
  error recording was -0.98, one hundredth of a standard deviation short
  of the -1.0 "wrong" cutoff.
- **Small sample sizes make several priors unstable.** Phonemes with only
  1-2 correct-trial occurrences (AO, AY, W, UH, EY...) got their std
  floored to `FLOOR_SIGMA` (0.15) since there wasn't enough data to
  estimate a real one, which makes z-scores for those phonemes swing
  wildly (a genuinely mild deviation reads as an enormous z). "cake"'s
  error trial produced z=+10.7 on its EY vowel for exactly this reason.
- **What would actually fix this**, in likely order of impact: (1) more
  calibration data per phoneme - ideally many recordings of the *same*
  word/context repeated, since that's what the real per-speaker
  calibration path (Step 4's actual intended use, not the cold-start
  global-prior path this eval measures) is designed around, and this eval
  never got to exercise that path at all (every trial used a fresh,
  never-before-seen `user_id` on purpose, to test the worst case); (2)
  real human speech instead of, or in addition to, espeak-ng synthesis for
  building the global prior, since a meaningful share of the observed
  variance is plausibly a TTS-quality artifact rather than genuine
  phonetic variation; (3) a context-aware prior (conditioning on
  neighboring phonemes or word position, not just the bare phoneme) if
  (1) and (2) aren't enough on their own.

### Mandatory smoke test result

`eval/audio/pig_correct.wav` and `eval/audio/pig_error.wav` (the literal
"pig"/"pin" pair from the 40-pair corpus, espeak-ng `-s 130`), scored via
`backend.scorer.score_word` directly, fresh `user_id` (no calibration
history, global prior only) for each:

- **"pig" (correct)**: percent_correct=100, all three phonemes (P, IH, G)
  status="correct". This half passes.
- **"pin" (error: final G said as N)**: percent_correct=83. P: correct.
  IH: borderline (z=-1.24, an incidental side effect of this specific
  recording, not the intended error). **G: status="correct", z=-0.98**
  (top competitor is correctly N at 37% - visible right in the data - but
  status is not "wrong" as required). **This half does not pass the
  literal requirement** ("must flag the final g as wrong with competitor
  n") - it's a near miss (0.02 z short of the threshold) rather than a
  clean failure, but a near miss is still a miss, and the same root cause
  (G's wide, thin-sampled global prior) explains it. Not reporting this as
  fixed.
