# Diagnosis: why the current scorer is architecturally wrong

Written before any rebuild code, per instructions. Answers below are cited
to exact functions/lines in the code as it stands right now.

## 1. How does it currently decide the time window for each expected phoneme?

It doesn't align anything. `expected_time_window()` in
`backend/scorer_common.py:456-499` computes a **non-overlapping equal-time
partition** of the recording, purely from arithmetic on the phoneme's index:

```python
span = speech_end - speech_start
t0 = speech_start + span * occurrence_index / canonical_len
t1 = speech_start + span * (occurrence_index + 1) / canonical_len
```

For a 3-phone word, phoneme index 0 is simply assumed to occupy the first
third of the recording's duration, index 1 the second third, index 2 the
last third - regardless of what the audio actually contains. `speech_start`
and `speech_end` aren't detected from the audio either: they're
`_PADDING_SECONDS` (a fixed 0.3s constant) subtracted from each end of the
file's total duration (`scorer.py:193-194`), i.e. "however much silence we
padded on, assume that's exactly where speech starts and ends." A small
fixed tolerance (0.11s, also a constant, tuned by sweeping test cases - see
`scorer_common.py:480-491`) is added on each side to reduce (not eliminate)
boundary misses.

This is a guess, not an alignment. It assumes every phone in a word takes
equal time, which is false (vowels run longer than stops; unstressed
syllables compress; consonant clusters vary widely), and it has no
mechanism to detect when the guess is wrong for a specific recording. This
is exactly the "estimates windows without real alignment" bug.

## 2. Where does it get its confidence numbers from?

Raw per-frame softmax output of the recognizer model, filtered to whatever
time window step 1 guessed. `scorer.py`'s `_recognize()` runs the wav2vec2
model, takes `torch.softmax(logits, dim=-1)`, and keeps the top-5 highest-
probability vocabulary entries per frame (`scorer.py:158-176`). Then
`best_confidence_in_window()` (`scorer_common.py:502-535`) scans every frame
whose timestamp falls inside the *guessed* window and returns the highest
probability seen for the target phoneme symbol across all of them.

So "confidence" is just "the highest softmax probability the model ever
assigned to this phone symbol, at any frame the window-guessing arithmetic
happened to include" - not a probability of anything conditioned on real
frame boundaries, and not comparable across phonemes with different-width
guessed windows.

## 3. Where could an off-by-one or reversed index produce "first phoneme
reported wrong, later phonemes reported right" when the opposite is true?

Three independent mechanisms, all stemming from the same root cause (no
real alignment), can each produce this symptom on their own:

- **Fixed `speech_start` doesn't track true speech onset.** If the actual
  recording has any leading noise, mic warm-up, or a slow onset beyond the
  fixed 0.3s padding assumption, every window is shifted late relative to
  the real audio - phoneme 0's *guessed* window can start after phoneme 0
  has already finished being spoken and phoneme 1 has begun, so phoneme
  0's window captures phoneme 1's frames (and gets judged on those) while
  phoneme 0's real frames fall into no window at all or get attributed to
  nothing. This isn't a strict index reversal, but it produces the exact
  reported symptom: the sound that's actually first reads as wrong (its
  real evidence was never examined) while a later sound reads as
  suspiciously fine (it "stole" credit meant for an earlier one).
- **Equal-duration assumption breaks hardest for word-initial position.**
  Initial consonants (especially unstressed ones, or ones in a blend) are
  frequently the shortest phones in a word, while index-0's guessed slot
  is sized as `1/N` of the whole span like every other phone's slot. A
  short true phoneme 0 plus a long true phoneme 1 means phoneme 0's guessed
  window (sized for an "average" phone) overruns into phoneme 1's actual
  content, and the reverse for whichever phoneme follows - again reading as
  "first one wrong, next one suspiciously confirmed," without any index
  arithmetic bug at all being necessary. Confirmed directly during earlier
  testing: an 8-phone word ("computer") had its target phoneme's true,
  94.7%-confidence frame land 16ms outside its guessed window before the
  tolerance constant was loosened - i.e. the guess was simply wrong, not
  off by a clean single frame.
- **No verification that a window's assigned evidence was ever actually
  produced by that phoneme.** Because there's no forced alignment ground
  truth to check the guess against, nothing in the pipeline can detect
  "this window is empty/wrong" versus "this window is right" - it just
  reports whatever confidence number the guess happened to turn up. A
  systematically-early or -late guess for one recording produces
  confident-looking but meaningless numbers with no signal that anything
  is wrong.

All three are symptoms of the same design flaw named in the instructions:
guessing at the sequence-to-time mapping instead of computing it. The fix
in this rebuild (`torchaudio.functional.forced_align`) replaces every one
of these guesses with the actual CTC-optimal frame boundaries for the known
target sequence, which is why forced alignment is a categorically different
fix rather than a fourth patch on the guessing logic.
