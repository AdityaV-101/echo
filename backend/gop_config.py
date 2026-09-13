"""All tunable constants for the forced-alignment + GOP scoring pipeline,
in one place on purpose (per explicit instruction: "make these constants
in one config file so they are tunable, do not scatter them"). eval/sweep.py
is what should ever change Z_CORRECT_THRESHOLD / Z_WRONG_THRESHOLD - see
its output and the sweep results recorded in SETUP_NOTES.md before editing
those two by hand.
"""

# --- Audio preprocessing (see scorer.py's preprocess_audio) ---
TARGET_SAMPLE_RATE = 16000
SILENCE_TRIM_ENERGY_THRESHOLD = 0.02  # RMS, on peak-normalized audio (0-1 scale)
MIN_AUDIO_SECONDS = 0.4
SILENT_RECORDING_RMS_THRESHOLD = 0.005  # below this, reject rather than score

# How far beyond the detected speech boundary to keep on each side before
# cutting. Low-energy segments - nasal murmurs, fricatives, unreleased final
# stops - can dip under SILENCE_TRIM_ENERGY_THRESHOLD before the sound is
# actually over; trimming flush against the threshold silently ate exactly
# these (a word-final /m/ scored z=-11.95 on otherwise-clean audio because
# its low-energy tail got cut). This margin is kept deliberately generous
# rather than trimming flush, and only ever affects how much silence
# surrounds the speech, never the speech itself - see _trim_silence.
SILENCE_TRIM_MARGIN_SECONDS = 0.2

# --- GOP computation (see gop_scorer.py's compute_gop) ---
# A span can collapse to zero non-blank frames on a very short/fast phone;
# rather than produce no signal at all, fall back to the single
# highest-scoring frame in [start, end) (or the frame nearest the span if
# forced_align gave a zero-width span).
GOP_MIN_FRAMES_FOR_MEAN = 1

# --- Speaker calibration z-score decision bands (see calibration.py) ---
# GOP is always <= 0 (see gop_scorer.py); these thresholds apply to the
# z-score of a GOP against the speaker's own per-phoneme baseline, not to
# raw GOP. Set from eval/sweep.py's output against the 40-pair synthetic
# corpus (best operating point found: accuracy=0.738, FAR=0.500,
# FRR=0.025 - see "Eval results" in SETUP_NOTES.md; this FAR is not good,
# see that section for why and what it would take to improve it), not
# guessed.
Z_CORRECT_THRESHOLD = -1.0    # z > this -> correct
Z_WRONG_THRESHOLD = -2.0      # z <= this -> wrong; between the two -> borderline
BORDERLINE_WEIGHT = 0.5       # this phoneme's contribution to percent_correct

# Minimum samples of a speaker's own history for a phoneme before trusting
# their personal mean/std over the global prior (Step 4: "a global
# per-phoneme prior as the fallback when a speaker has fewer than 3 samples").
MIN_SPEAKER_SAMPLES = 3

# Speaker std floor: a speaker's very first few samples can have near-zero
# variance just from having almost no data, which would make the z-score
# formula (dividing by sigma) wildly oversensitive to the next sample. This
# is the minimum sigma ever used as the z-score denominator, regardless of
# what a speaker's own (possibly still-thin) history says.
FLOOR_SIGMA = 0.15

# --- Global per-phoneme prior (fallback for a speaker with < MIN_SPEAKER_SAMPLES) ---
# Populated below from the synthetic correct-vs-error corpus (see
# eval/generate_synthetic.py and eval/sweep.py) - see SETUP_NOTES.md for
# exactly how these were derived and when this was last regenerated.
# Format: {phoneme: (mean_gop, std_gop)}. A phoneme missing here (not yet
# covered by the synthetic corpus) falls back to GLOBAL_PRIOR_DEFAULT.
GLOBAL_PRIOR_DEFAULT = (-0.6, 0.5)
# Derived by eval/sweep.py from the 40-pair synthetic corpus's 40 "correct"
# recordings (espeak-ng en-us, -s 130). Sample sizes per phoneme are small
# (2-9 occurrences for most; see SETUP_NOTES.md for the full per-phoneme
# table with n) - this is a real, if thin, calibration, not a guess, and
# the eval numbers above already account for exactly this data's limits.
GLOBAL_PRIOR: dict[str, tuple[float, float]] = {
    "AA": (-3.1187, 1.2428),
    "AE": (-4.2223, 2.2860),
    "AH": (-5.7551, 1.5491),
    "AO": (-7.0925, 0.1500),
    "AY": (-2.9636, 0.1500),
    "B": (-4.2241, 3.0581),
    "CH": (-4.4735, 0.6424),
    "D": (-4.7790, 0.7211),
    "DH": (-4.7885, 2.8314),
    "EH": (-2.5636, 1.6998),
    "EY": (-4.3254, 0.1893),
    "F": (-4.5904, 4.5904),
    "G": (-4.0467, 2.7336),
    "IH": (-3.3151, 2.1013),
    "IY": (-0.4407, 0.6233),
    "JH": (-1.3914, 1.3914),
    "K": (-3.5081, 3.1836),
    "L": (-1.1706, 1.5126),
    "M": (-0.0190, 0.1500),
    "N": (-1.1696, 1.2360),
    "NG": (-0.1010, 0.1500),
    "OW": (-4.6827, 3.2071),
    "P": (-2.8573, 3.3207),
    "R": (-3.6121, 3.8767),
    "S": (-0.0496, 0.1500),
    "SH": (-2.1202, 1.4690),
    "T": (-0.0972, 0.1500),
    "TH": (-7.2923, 1.0500),
    "UH": (-10.0849, 0.1500),
    "UW": (-5.2457, 2.5632),
    "V": (-1.6145, 2.2832),
    "W": (-4.5210, 0.1500),
    "Z": (-4.2077, 0.7677),
}
