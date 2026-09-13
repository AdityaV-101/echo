"""Speaker-disjoint dev/sub-train split of eval/speechocean_train.jsonl.

Phase 0 requirement: dev must share zero speakers with sub-train (the slice
later phases fit thresholds/models on) or with the held-out test split.
speechocean762's own train/test split is already speaker-disjoint (verified
directly: 0 speaker overlap between speechocean_train.jsonl and
speechocean_test.jsonl, 125 speakers each) - this module only splits the
125 train speakers into two further disjoint groups.

Split is stratified by (is_child, age<=9) so dev isn't accidentally starved
of the app's real population (age<=9 has only 36 speakers total in train -
see DEV_FRACTION's effect on that stratum specifically, logged below).
Deterministic: a fixed seed, not re-randomized per run, so "dev" means the
same 25 speakers every time this is imported.
"""
import json
import random
from pathlib import Path

EVAL_DIR = Path(__file__).parent
TRAIN_MANIFEST = EVAL_DIR / "speechocean_train.jsonl"
SPLIT_SEED = 20240908  # fixed - do not change without re-running everything downstream
DEV_FRACTION = 0.2


def _speaker_strata(manifest_path: Path = TRAIN_MANIFEST) -> dict[str, dict]:
    speakers: dict[str, dict] = {}
    with open(manifest_path) as f:
        for line in f:
            d = json.loads(line)
            sp = d["speaker"]
            if sp not in speakers:
                speakers[sp] = {
                    "is_child": d["is_child"],
                    "age": d["age"],
                    "n_words": 0,
                }
            speakers[sp]["n_words"] += 1
    return speakers


def _stratum(info: dict) -> str:
    if not info["is_child"]:
        return "adult"
    return "child_age_le9" if info["age"] <= 9 else "child_age_gt9"


def compute_speaker_split(manifest_path: Path = TRAIN_MANIFEST) -> dict[str, str]:
    """Returns {speaker_id: "dev" | "subtrain"}."""
    speakers = _speaker_strata(manifest_path)
    by_stratum: dict[str, list[str]] = {}
    for sp, info in speakers.items():
        by_stratum.setdefault(_stratum(info), []).append(sp)

    rng = random.Random(SPLIT_SEED)
    assignment: dict[str, str] = {}
    for stratum, sp_list in by_stratum.items():
        sp_list = sorted(sp_list)  # deterministic order before shuffling
        rng.shuffle(sp_list)
        n_dev = max(1, round(len(sp_list) * DEV_FRACTION))
        dev_set = set(sp_list[:n_dev])
        for sp in sp_list:
            assignment[sp] = "dev" if sp in dev_set else "subtrain"
    return assignment


def summarize(assignment: dict[str, str], manifest_path: Path = TRAIN_MANIFEST) -> None:
    speakers = _speaker_strata(manifest_path)
    strata_counts: dict[str, dict[str, int]] = {}
    word_counts: dict[str, dict[str, int]] = {}
    for sp, info in speakers.items():
        stratum = _stratum(info)
        group = assignment[sp]
        strata_counts.setdefault(stratum, {"dev": 0, "subtrain": 0})[group] += 1
        word_counts.setdefault(stratum, {"dev": 0, "subtrain": 0})[group] += info["n_words"]
    print("Speaker split (speaker-disjoint, stratified, seed=%d):" % SPLIT_SEED)
    for stratum in sorted(strata_counts):
        sc = strata_counts[stratum]
        wc = word_counts[stratum]
        print(f"  {stratum:16} speakers: dev={sc['dev']:3} subtrain={sc['subtrain']:3}  "
              f"words: dev={wc['dev']:5} subtrain={wc['subtrain']:5}")
    total_dev_words = sum(wc["dev"] for wc in word_counts.values())
    total_subtrain_words = sum(wc["subtrain"] for wc in word_counts.values())
    print(f"  TOTAL words: dev={total_dev_words} subtrain={total_subtrain_words}")


if __name__ == "__main__":
    assignment = compute_speaker_split()
    summarize(assignment)
    out_path = EVAL_DIR / "speaker_split.json"
    with open(out_path, "w") as f:
        json.dump(assignment, f, indent=1, sort_keys=True)
    print(f"\nWrote {out_path}")
