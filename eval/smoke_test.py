"""Pipeline smoke test: does hypothesis_scorer run end-to-end without
crashing and produce a verdict, on a couple of espeak-synthesized clips.

This is NOT a correctness test. Default-rate espeak audio is a documented
synthesis artifact - the "pig" clip synthesized at espeak's default ~175wpm
is acoustically ambiguous enough that this exact model favors NG over a
correctly-produced G (confirmed by comparing against the same word
synthesized slower: pig_slow and pig_s100 both score correctly, pig at
default rate does not - see the conversation record, not reproduced here).
Treating that clip's verdict as a correctness signal was a mistake in an
earlier iteration of this project; real correctness numbers come from
eval/run_hypothesis_eval.py against speechocean762 (real human speech),
never from espeak. This script only checks that the pipeline executes.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from audio_preprocess import preprocess_audio  # noqa: E402
from hypothesis_scorer import score_word_hypothesis  # noqa: E402

AUDIO_DIR = Path(__file__).parent / "smoke_test_audio"


def synth(word: str) -> Path:
    AUDIO_DIR.mkdir(exist_ok=True)
    path = AUDIO_DIR / f"{word}.wav"
    subprocess.run(["espeak-ng", "-v", "en-us", "-w", str(path), word], check=True, capture_output=True)
    return path


def main() -> int:
    cases = [("pig", ["P", "IH", "G"]), ("cat", ["K", "AE", "T"])]
    for word, canonical in cases:
        audio = preprocess_audio(str(synth(word)))
        result = score_word_hypothesis(canonical, audio)
        print(f"{word}: word_status={result.word_status} winner={result.winner} "
              f"n_candidates={result.n_candidates} (pipeline executed - verdict not checked, see module docstring)")
    print("SMOKE TEST OK (pipeline runs end-to-end)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
