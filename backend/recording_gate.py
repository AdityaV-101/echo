"""Phase 4: usable-recording gate. A real share of what would otherwise
read as "the child got it wrong" is actually "the recording wasn't
scorable" - conflating the two means the app can tell a child they made a
sound wrong when the real problem was a quiet mic or a different word
entirely. This runs BEFORE any correct/wrong/unclear verdict and can only
ever produce a distinct "unclear_recording" status, never "wrong".

Duration/RMS bounds are audio_preprocess.py's existing job (silence
rejection, minimum-length padding) - this module adds the one check that
needs the model's own output to compute: free_decode_gap, already a Phase 2
feature (backend/features.py). A large gap between what the model's free
CTC decode actually heard and what the canonical word would predict is
evidence the child said something else entirely, not that they mispronounced
the target sound.

Threshold derivation (not swept against a downstream metric, since that
would be exactly the kind of dev-set tuning eval/phase3_protocol.md's
modeling freeze rules out): free_decode_gap among speechocean762's
correctly-produced (phones_accuracy==2.0) tokens has mean=0.435, std=0.324
(computed directly, see eval/phase3_common.py's cached features). The
reject threshold is set at approximately mean + 3.3*std (~99.9th
percentile of the correct-production distribution, computed directly) -
conservative on purpose: it should only catch genuine outliers, not
routinely reject normal correct speech. Revisit once real production
recordings (not speechocean762 word-clips) are available to check this
transfers.
"""
from dataclasses import dataclass

FREE_DECODE_GAP_REJECT_THRESHOLD = 1.5  # see module docstring for derivation


@dataclass
class GateResult:
    usable: bool
    reason: str | None = None  # None if usable=True


def check_recording_usable(free_decode_gap: float) -> GateResult:
    """Called after audio_preprocess.preprocess_audio (duration/RMS/silence
    checks already happened there and raise SilentRecordingError directly)
    and after computing word-level features. Returns usable=False only for
    a free_decode_gap outlier - everything else is left to the phoneme-level
    correct/wrong/unclear decision in backend/decision.py."""
    if free_decode_gap > FREE_DECODE_GAP_REJECT_THRESHOLD:
        return GateResult(
            usable=False,
            reason=(
                f"free_decode_gap={free_decode_gap:.3f} exceeds "
                f"{FREE_DECODE_GAP_REJECT_THRESHOLD} - the model's free decode of this "
                "recording explains the audio much better than the canonical word does, "
                "suggesting a different word was said rather than a mispronunciation of this one."
            ),
        )
    return GateResult(usable=True)
