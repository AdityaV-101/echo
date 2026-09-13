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

At the positive-token counts this project actually has (tens, not
thousands, per slice - see Phase 0's child-slice base rate), a point
estimate on its own invites reading noise as signal. bootstrap_ci_by_speaker
resamples SPEAKERS with replacement (never individual tokens - a speaker's
attempts are correlated with each other, so resampling tokens directly
would understate the true uncertainty), which is why every row this module
produces carries its speaker.
"""
import random
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


def flatten_rows(
    records: list[dict],
    predict_fn: PredictFn,
    slice_filter: Optional[Callable[[dict], bool]] = None,
) -> list[dict]:
    """One row per phoneme occurrence (ambiguous-label rows included, with
    label=None - callers filter those out, but keeping them here lets a
    caller compute ambiguous-band coverage without a second pass). Every row
    carries its speaker, which is what makes bootstrap_ci_by_speaker (and
    any other speaker-grouped analysis - the k-of-n aggregation, the
    extraction-bias check) possible without re-deriving predictions."""
    rows = []
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
            rows.append({
                "utt_id": record.get("utt_id"), "word_index": record.get("word_index"), "index": i,
                "speaker": record.get("speaker"),
                "phone": phone, "position": _word_position(i, length),
                "label": label_for_accuracy(acc),
                "status": pred["status"], "score": pred["score"], "heard": pred["heard"],
                "gt_sub": _ground_truth_substitution(record, i),
            })
    return rows


class _Accumulator:
    """One instance per reported slice (overall, per-phoneme, per-position,
    or one bootstrap resample)."""

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

    def add_row(self, row: dict):
        self.add(row["label"], row["status"], row["score"], row["heard"], row["gt_sub"])

    def metrics(self) -> dict:
        considered = self.tp + self.fp + self.fn + self.tn
        n_positive = self.tp + self.fn  # actual errors among considered (non-unclear) rows
        n_negative = self.fp + self.tn  # actual corrects among considered rows
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
            "n_positive": n_positive, "n_negative": n_negative,
            "base_rate": n_positive / considered if considered else float("nan"),
            "coverage": coverage,
            "abstain_rate": abstain_rate,
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "precision": precision, "recall": recall, "f1": f1,
            "far": far, "frr": frr,
            "pr_auc": pr_auc,
            "substitution_naming_accuracy": naming_accuracy,
            "substitution_naming_n": self.naming_total,
        }


def _accumulate(rows: list[dict]) -> _Accumulator:
    acc = _Accumulator()
    for row in rows:
        acc.add_row(row)
    return acc


def evaluate_from_rows(rows: list[dict]) -> dict:
    """Same output shape as evaluate() (overall/by_phoneme/by_position),
    from an already-flattened row list - the shared implementation
    evaluate() and bootstrap_ci_by_speaker both build on."""
    by_phoneme: dict[str, list[dict]] = {}
    by_position: dict[str, list[dict]] = {}
    for row in rows:
        by_phoneme.setdefault(row["phone"], []).append(row)
        by_position.setdefault(row["position"], []).append(row)
    return {
        "overall": _accumulate(rows).metrics(),
        "by_phoneme": {p: _accumulate(rs).metrics() for p, rs in sorted(by_phoneme.items())},
        "by_position": {pos: _accumulate(rs).metrics() for pos, rs in sorted(by_position.items())},
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
    rows = flatten_rows(records, predict_fn, slice_filter)
    return evaluate_from_rows(rows)


def bootstrap_ci_by_speaker(
    rows: list[dict],
    metric_names: tuple[str, ...] = ("precision", "recall", "pr_auc", "frr", "far", "f1"),
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, tuple[float, float]]:
    """95% CI (2.5th/97.5th percentile) for each named metric, resampled by
    SPEAKER with replacement - a drawn speaker contributes every one of
    their rows as a block, so within-speaker correlation (the same child's
    attempts are not independent trials) is preserved in the resample
    rather than washed out by resampling individual tokens. NaN draws
    (e.g. a resample with zero positives, undefined precision) are dropped
    from that metric's percentile calculation rather than treated as 0."""
    by_speaker: dict[str, list[dict]] = {}
    for row in rows:
        by_speaker.setdefault(row["speaker"], []).append(row)
    speakers = list(by_speaker.keys())
    n_sp = len(speakers)
    if n_sp == 0:
        return {name: (float("nan"), float("nan")) for name in metric_names}

    rng = random.Random(seed)
    samples: dict[str, list[float]] = {name: [] for name in metric_names}
    for _ in range(n_boot):
        drawn = [speakers[rng.randrange(n_sp)] for _ in range(n_sp)]
        boot_rows = []
        for sp in drawn:
            boot_rows.extend(by_speaker[sp])
        m = _accumulate(boot_rows).metrics()
        for name in metric_names:
            v = m[name]
            if v == v:  # not NaN
                samples[name].append(v)

    ci = {}
    for name in metric_names:
        vals = sorted(samples[name])
        if not vals:
            ci[name] = (float("nan"), float("nan"))
            continue
        lo = vals[max(0, int(0.025 * len(vals)))]
        hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
        ci[name] = (lo, hi)
    return ci


def format_overall(name: str, m: dict) -> str:
    return (
        f"{name:28} n={m['n_total']:5} P={m['n_positive']:4} N={m['n_negative']:4} base_rate={m['base_rate']:.1%} "
        f"coverage={m['coverage']:.1%} abstain={m['abstain_rate']:.1%}  "
        f"TP={m['tp']:3} FP={m['fp']:3} FN={m['fn']:3}  "
        f"FRR={m['frr']:.1%} FAR={m['far']:.1%} precision={m['precision']:.1%} recall={m['recall']:.1%} "
        f"f1={m['f1']:.3f} pr_auc={m['pr_auc']:.3f} naming_acc={m['substitution_naming_accuracy']:.1%} "
        f"(n={m['substitution_naming_n']})"
    )
