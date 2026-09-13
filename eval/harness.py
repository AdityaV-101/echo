"""Phase 0 measurement harness: the single entry point every scorer (old or
new) is evaluated through, from here on.

Ground truth label scheme (see the module docstring's derivation in
DIAGNOSIS/the rebuild brief): phones_accuracy is the mean of 5 annotators
on a 0/1/2 scale per rater. On this app's own child train split, 84.8% of
tokens are exactly 2.0 and only 1.54% are at or below 1.0 - treating
"< 2.0" as the error class (the old convention) makes ~90% of the positive
class a single annotator's one-point deduction, not a real error. Instead:

    accuracy == 2.0            -> label 0 (correct)
    accuracy <= 1.0             -> label 1 (error)
    1.0 < accuracy < 2.0        -> excluded from every metric below (the
                                    "ambiguous" band), reported separately
                                    as its own abstain-style coverage number.

Everything in this file operates on PHONEME OCCURRENCES (one canonical
phoneme, in one word, said once) as the unit of measurement - matching
phones_accuracy's own granularity and every existing eval script in this
repo (run_hypothesis_eval.py, sweep.py, run_eval.py all do the same).

A "predict_fn" is any callable: raw_cache_record -> list of per-phoneme
dicts, one per canonical position, each:
    {"status": "correct" | "wrong" | "unclear",
     "score": float,       # higher = more error-like; used for PR-AUC only,
                            # never for the correct/wrong/unclear call itself
     "heard": str | None}  # predicted substitution; None = predicted
                            # deletion or not applicable
"unclear" is this scorer's abstain: excluded from FRR/FAR/precision/recall/
substitution-naming, counted only in abstain_rate and coverage. A scorer
with no abstain concept (the current GOP z-score path) simply never emits it.
"""
import math
from pathlib import Path
from typing import Callable, Optional

try:
    from sklearn.metrics import average_precision_score
except ImportError:  # pragma: no cover - sklearn is a Phase 3 dependency too
    average_precision_score = None

EVAL_DIR = Path(__file__).parent

PredictFn = Callable[[dict], list[dict]]


def label_for_accuracy(acc: float) -> Optional[int]:
    """0 = correct, 1 = error, None = ambiguous (excluded)."""
    if acc >= 2.0:
        return 0
    if acc <= 1.0:
        return 1
    return None


def _word_position(index: int, length: int) -> str:
    if length == 1:
        return "single"
    if index == 0:
        return "initial"
    if index == length - 1:
        return "final"
    return "medial"


def _ground_truth_substitution(record: dict, index: int) -> Optional[tuple[str, Optional[str]]]:
    """Returns (category, pronounced_phone) for a mispronunciation at this
    canonical index, or None if there's no annotated mispronunciation there
    (shouldn't happen for a label==1 position under speechocean762's own
    convention, but not guaranteed 1:1 - handled defensively)."""
    for m in record["mispronunciations"]:
        if m["index"] == index:
            return m["category"], m["pronounced_phone"]
    return None


class _Accumulator:
    """One instance per reported slice (overall, per-phoneme, per-position)."""

    def __init__(self):
        self.tp = self.fp = self.fn = self.tn = 0
        self.n_ambiguous = 0
        self.n_unclear = 0
        self.n_total = 0  # non-ambiguous phoneme occurrences seen
        self.scores: list[float] = []
        self.labels: list[int] = []
        self.naming_correct = 0
        self.naming_total = 0

    def add(self, label: Optional[int], status: str, score: float, heard: Optional[str], gt_sub):
        if label is None:
            self.n_ambiguous += 1
            return
        self.n_total += 1
        self.scores.append(score)
        self.labels.append(label)
        if status == "unclear":
            self.n_unclear += 1
            return
        predicted_error = status == "wrong"
        actual_error = label == 1
        if predicted_error and actual_error:
            self.tp += 1
        elif predicted_error and not actual_error:
            self.fp += 1
        elif not predicted_error and actual_error:
            self.fn += 1
        else:
            self.tn += 1

        if predicted_error and actual_error and gt_sub is not None:
            category, pronounced = gt_sub
            if category == "phone":
                self.naming_total += 1
                if heard == pronounced:
                    self.naming_correct += 1
            elif category == "deleted":
                self.naming_total += 1
                if heard is None:
                    self.naming_correct += 1
            # "unknown" / "ambiguous" ground truth: skip, can't judge naming
            # against an annotator's own uncertainty.

    def metrics(self) -> dict:
        considered = self.tp + self.fp + self.fn + self.tn
        precision = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else float("nan")
        recall = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else float("nan")
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision == precision and recall == recall and (precision + recall) > 0)
            else float("nan")
        )
        far = self.fn / (self.fn + self.tp) if (self.fn + self.tp) else float("nan")  # missed real errors
        frr = self.fp / (self.fp + self.tn) if (self.fp + self.tn) else float("nan")  # correct flagged wrong
        coverage = considered / self.n_total if self.n_total else float("nan")
        abstain_rate = self.n_unclear / self.n_total if self.n_total else float("nan")

        pr_auc = float("nan")
        if average_precision_score is not None and self.labels and len(set(self.labels)) > 1:
            pr_auc = float(average_precision_score(self.labels, self.scores))

        naming_accuracy = self.naming_correct / self.naming_total if self.naming_total else float("nan")

        return {
            "n_total": self.n_total,
            "n_ambiguous_excluded": self.n_ambiguous,
            "n_unclear": self.n_unclear,
            "coverage": coverage,
            "abstain_rate": abstain_rate,
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "precision": precision, "recall": recall, "f1": f1,
            "far": far, "frr": frr,
            "pr_auc": pr_auc,
            "substitution_naming_accuracy": naming_accuracy,
            "substitution_naming_n": self.naming_total,
        }


def evaluate(
    records: list[dict],
    predict_fn: PredictFn,
    slice_filter: Optional[Callable[[dict], bool]] = None,
) -> dict:
    """Runs predict_fn over every record (optionally restricted by
    slice_filter, e.g. lambda r: r["is_child"]), and returns overall metrics
    plus a breakdown per target (canonical) phoneme and per structural word
    position (initial/medial/final/single)."""
    overall = _Accumulator()
    by_phoneme: dict[str, _Accumulator] = {}
    by_position: dict[str, _Accumulator] = {}

    for record in records:
        if slice_filter is not None and not slice_filter(record):
            continue
        canonical = record["canonical"]
        predictions = predict_fn(record)
        assert len(predictions) == len(canonical), (
            f"predict_fn returned {len(predictions)} predictions for "
            f"{len(canonical)} canonical phonemes ({record.get('utt_id')}/{record.get('word_index')})"
        )
        length = len(canonical)
        for i, (phone, acc, pred) in enumerate(zip(canonical, record["phones_accuracy"], predictions)):
            label = label_for_accuracy(acc)
            gt_sub = _ground_truth_substitution(record, i)
            status, score, heard = pred["status"], pred["score"], pred["heard"]

            overall.add(label, status, score, heard, gt_sub)
            by_phoneme.setdefault(phone, _Accumulator()).add(label, status, score, heard, gt_sub)
            position = _word_position(i, length)
            by_position.setdefault(position, _Accumulator()).add(label, status, score, heard, gt_sub)

    return {
        "overall": overall.metrics(),
        "by_phoneme": {p: acc.metrics() for p, acc in sorted(by_phoneme.items())},
        "by_position": {pos: acc.metrics() for pos, acc in sorted(by_position.items())},
    }


def format_overall(name: str, m: dict) -> str:
    return (
        f"{name:28} n={m['n_total']:5} coverage={m['coverage']:.1%} abstain={m['abstain_rate']:.1%}  "
        f"FRR={m['frr']:.1%} FAR={m['far']:.1%} precision={m['precision']:.1%} recall={m['recall']:.1%} "
        f"f1={m['f1']:.3f} pr_auc={m['pr_auc']:.3f} naming_acc={m['substitution_naming_accuracy']:.1%} "
        f"(n={m['substitution_naming_n']})"
    )
