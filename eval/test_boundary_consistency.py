"""Regression test for the silence-trim bug (Step 3): a word whose target
phoneme appears in both initial and final position must score both
occurrences as correct on clean audio. The original bug ("mom" scoring its
word-final M as wrong, z=-11.95, on a clean recording, while the identical
initial M scored perfectly) was traced to audio_preprocess.py's silence
trimmer cutting flush against its energy threshold and eating the low-energy
tail of the word-final sound before it was actually over. Fixed by keeping
SILENCE_TRIM_MARGIN_SECONDS of margin beyond the detected boundary instead
of cutting flush - see audio_preprocess._trim_silence.

This must pass. Run directly: python3 test_boundary_consistency.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from audio_preprocess import preprocess_audio  # noqa: E402
from hypothesis_scorer import score_word_hypothesis  # noqa: E402
from scorer_common import canonical_phonemes_for_word  # noqa: E402

WORDS = ["mom", "dad", "pop", "kick", "sis"]
AUDIO_DIR = Path(__file__).parent / "boundary_test_audio"


def synth(word: str) -> Path:
    AUDIO_DIR.mkdir(exist_ok=True)
    path = AUDIO_DIR / f"{word}.wav"
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "130", "-w", str(path), word], check=True, capture_output=True)
    return path


def main() -> int:
    all_passed = True
    for word in WORDS:
        canonical = canonical_phonemes_for_word(word)
        if canonical is None:
            print(f"SKIP {word}: not in cmudict")
            continue
        repeated = canonical[0]
        assert canonical[-1] == repeated, f"{word}: canonical {canonical} doesn't repeat the first phoneme at the end"

        audio_path = synth(word)
        audio = preprocess_audio(str(audio_path))
        result = score_word_hypothesis(canonical, audio)

        first, last = result.phonemes[0], result.phonemes[-1]
        word_ok = result.word_status == "correct"
        both_ok = first.status == "correct" and last.status == "correct"
        passed = word_ok and both_ok

        ratio = min(first.confidence, last.confidence) / max(first.confidence, last.confidence, 1e-9)
        print(
            f"{'PASS' if passed else 'FAIL'} {word:6s} {canonical}  "
            f"word_status={result.word_status:8s} "
            f"initial({repeated})={first.status}/{first.confidence:.3f}  "
            f"final({repeated})={last.status}/{last.confidence:.3f}  "
            f"conf_ratio={ratio:.2f}"
        )
        all_passed = all_passed and passed

    print()
    print("ALL PASS" if all_passed else "FAILED")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
