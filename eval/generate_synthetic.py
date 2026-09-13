"""Step 8 (eval harness), part 1: synthesize a labeled correct-vs-error test
corpus with espeak-ng.

For each of 40 target words, generates:
- a "correct" recording: espeak-ng speaking the target word itself.
- an "error" recording: espeak-ng speaking a deliberately misspelled
  variant chosen to induce one specific, real developmental/articulation
  substitution pattern (e.g. target "rabbit", error spelling "wabbit" for
  the classic R->W gliding error) - covering this app's actual clinical
  target phonemes (R, S, L, TH, DH, Z, SH, CH, K) plus common context
  consonants, across a mix of initial and final positions.

Both recordings are always scored against the *target* word's canonical
phoneme sequence (never against a lookup of the misspelled text) - that
mirrors exactly how the real app works: the child is asked to say a known
word, and every recording is judged against that word's canonical
sequence, whatever was actually said.

Speech rate: -s 130 (moderate, clearly articulated). Chosen empirically,
not by default: espeak-ng's default rate (~175wpm) produced audio where
this project's own recognizer confidently misheard a clean, correctly-
pronounced final stop as a nasal (documented directly - see "Espeak-ng
synthesis rate" in SETUP_NOTES.md for the frame-level evidence). 130 was
the slowest rate tested where every phoneme in a control word was
recognized as at least a plausible top-3 candidate.
"""
import json
import subprocess
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from scorer_common import canonical_phonemes_for_word  # noqa: E402

AUDIO_DIR = Path(__file__).parent / "audio"
LABELS_PATH = Path(__file__).parent / "labels.json"
ESPEAK_RATE = "130"
ESPEAK_VOICE = "en-us"

# (target_word, error_spelling, phoneme_pattern_being_tested)
PAIRS = [
    ("pig", "pin", "G->N final (given smoke-test pair)"),
    ("rabbit", "wabbit", "R->W initial gliding"),
    ("red", "wed", "R->W initial gliding"),
    ("run", "wun", "R->W initial gliding"),
    ("rope", "wope", "R->W initial gliding"),
    ("car", "caw", "R->W final"),
    ("cat", "tat", "K->T initial fronting"),
    ("king", "ting", "K->T initial fronting"),
    ("cake", "take", "K->T initial fronting"),
    ("sun", "thun", "S->TH initial"),
    ("sock", "thock", "S->TH initial"),
    ("sing", "thing", "S->TH initial"),
    ("bus", "bud", "S->D final"),
    ("light", "wight", "L->W initial gliding"),
    ("look", "wook", "L->W initial gliding"),
    ("leaf", "weef", "L->W initial gliding"),
    ("leg", "weg", "L->W initial gliding"),
    ("thumb", "fumb", "TH->F initial fronting"),
    ("think", "tink", "TH->T initial stopping"),
    ("bath", "bat", "TH->T final stopping"),
    ("this", "dis", "DH->D initial stopping"),
    ("that", "dat", "DH->D initial stopping"),
    ("zoo", "doo", "Z->D initial stopping"),
    ("zip", "dip", "Z->D initial stopping"),
    ("shoe", "soo", "SH->S initial"),
    ("wish", "wiss", "SH->S final"),
    ("sheep", "seep", "SH->S initial"),
    ("chip", "tip", "CH->T initial deaffrication"),
    ("much", "mut", "CH->T final deaffrication"),
    ("chair", "tair", "CH->T initial deaffrication"),
    ("jump", "dump", "JH->D initial deaffrication"),
    ("juice", "doose", "JH->D initial deaffrication"),
    ("go", "doe", "G->D initial fronting"),
    ("dog", "dod", "G->D final fronting"),
    ("gate", "date", "G->D initial fronting"),
    ("fish", "pish", "F->P initial stopping"),
    ("van", "ban", "V->B initial stopping"),
    ("very", "berry", "V->B initial stopping"),
    ("love", "lub", "V->B final stopping"),
    ("moon", "noon", "M->N initial nasal confusion"),
]


def synth(text: str, out_path: Path):
    subprocess.run(
        ["espeak-ng", "-v", ESPEAK_VOICE, "-s", ESPEAK_RATE, "-w", str(out_path), text],
        check=True,
        capture_output=True,
    )


def main():
    AUDIO_DIR.mkdir(exist_ok=True)
    entries = []
    skipped = []
    for target_word, error_spelling, pattern in PAIRS:
        canonical = canonical_phonemes_for_word(target_word)
        if canonical is None:
            skipped.append(target_word)
            continue

        correct_path = AUDIO_DIR / f"{target_word}_correct.wav"
        error_path = AUDIO_DIR / f"{target_word}_error.wav"
        synth(target_word, correct_path)
        synth(error_spelling, error_path)

        entries.append({
            "target_word": target_word,
            "canonical": canonical,
            "audio_path": str(correct_path.relative_to(Path(__file__).parent)),
            "label": "correct",
            "synth_text": target_word,
            "pattern": pattern,
        })
        entries.append({
            "target_word": target_word,
            "canonical": canonical,
            "audio_path": str(error_path.relative_to(Path(__file__).parent)),
            "label": "error",
            "synth_text": error_spelling,
            "pattern": pattern,
        })
        print(f"synthesized: {target_word} ({canonical}) correct + error ({error_spelling!r}, {pattern})")

    with open(LABELS_PATH, "w") as f:
        json.dump(entries, f, indent=1)

    print(f"\n{len(entries)} recordings ({len(entries)//2} pairs) written to {LABELS_PATH}")
    if skipped:
        print(f"SKIPPED (not in cmudict): {skipped}")


if __name__ == "__main__":
    main()
