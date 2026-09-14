"""Shared plumbing for every Phase 3 follow-up analysis (within-phoneme
eval, ablations, calibration, multicollinearity) - factored out of
eval/train_phase3.py so each analysis script stays focused on its own
question instead of re-deriving the feature matrix and CV loop.
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from harness import flatten_rows, label_for_accuracy, paired_bootstrap_delta  # noqa: E402
from baselines import predict_gop_zscore  # noqa: E402

EVAL_DIR = Path(__file__).parent

ALL_NUMERIC_FEATURES = [
    "llr_best", "llr_margin", "gop_i", "gop_lpr_i", "dur_z", "entropy",
    "ll_canonical_per_frame", "free_decode_gap",
    "llr_best_speaker_rel", "gop_i_speaker_rel", "gop_lpr_i_speaker_rel", "dur_z_speaker_rel",
    "syllable_count", "frame_count_word",
]
EXTRA_NUMERIC_NAMES = ["llr_deletion", "llr_second_best", "has_deletion_candidate", "has_second_best_candidate"]
MISSING_SENTINEL = -5.0
CATEGORICAL_FEATURES = ["expected", "position", "llr_best_origin", "top_competitor"]

FEATURE_FAMILIES = {
    "llr_only": ["llr_best", "llr_margin", "llr_deletion", "llr_second_best", "llr_best_speaker_rel",
                 "has_deletion_candidate", "has_second_best_candidate"],
    "gop_only": ["gop_i", "gop_lpr_i", "gop_i_speaker_rel", "gop_lpr_i_speaker_rel"],
    "duration_entropy_only": ["dur_z", "entropy", "dur_z_speaker_rel", "syllable_count", "frame_count_word",
                               "ll_canonical_per_frame", "free_decode_gap"],
}
FEATURE_FAMILIES["all_numeric"] = ALL_NUMERIC_FEATURES + EXTRA_NUMERIC_NAMES


def load_pooled_rows() -> list[dict]:
    rows = []
    for split in ("subtrain", "dev"):
        with open(EVAL_DIR / f"phase2_features_{split}.json") as f:
            rows.extend(json.load(f))
    return rows


def load_all_gop_records() -> list[dict]:
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        dev = json.load(f)
    with open(EVAL_DIR / "phase0_raw_cache_subtrain.json") as f:
        subtrain = json.load(f)
    return dev + subtrain


def load_dev_gop_records() -> list[dict]:
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        return json.load(f)


def load_speaker_split() -> dict:
    with open(EVAL_DIR / "speaker_split.json") as f:
        return json.load(f)


def _numeric_value(row: dict, feat: str) -> float:
    if feat == "llr_deletion":
        return row["llr_deletion"] if row["llr_deletion"] is not None else MISSING_SENTINEL
    if feat == "llr_second_best":
        return row["llr_second_best"] if row["llr_second_best"] is not None else MISSING_SENTINEL
    if feat == "has_deletion_candidate":
        return 1.0 if row["llr_deletion"] is not None else 0.0
    if feat == "has_second_best_candidate":
        return 1.0 if row["llr_second_best"] is not None else 0.0
    return row[feat]


def build_xy(
    rows: list[dict],
    numeric_features: list[str] = None,
    categorical_features: list[str] = None,
    encoder: OneHotEncoder | None = None,
):
    """Returns (numeric, cat_encoded, y, groups, encoder, kept, feature_names).
    numeric_features/categorical_features default to everything - pass a
    subset for an ablation. categorical_features=[] (empty list, not None)
    disables one-hot encoding entirely (numeric-only ablations)."""
    if numeric_features is None:
        numeric_features = ALL_NUMERIC_FEATURES + EXTRA_NUMERIC_NAMES
    if categorical_features is None:
        categorical_features = CATEGORICAL_FEATURES

    kept = [i for i, r in enumerate(rows) if label_for_accuracy(r["phone_accuracy"]) is not None]
    y = np.array([label_for_accuracy(rows[i]["phone_accuracy"]) for i in kept])
    groups = np.array([rows[i]["speaker"] for i in kept])

    numeric = np.zeros((len(kept), len(numeric_features)), dtype=np.float64)
    for j, feat in enumerate(numeric_features):
        for row_i, i in enumerate(kept):
            numeric[row_i, j] = _numeric_value(rows[i], feat)

    if categorical_features:
        cat_raw = np.array([[str(rows[i][feat]) for feat in categorical_features] for i in kept])
        if encoder is None:
            encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
            cat_encoded = encoder.fit_transform(cat_raw)
        else:
            cat_encoded = encoder.transform(cat_raw)
        cat_names = list(encoder.get_feature_names_out(categorical_features))
    else:
        cat_encoded = np.zeros((len(kept), 0), dtype=np.float64)
        cat_names = []

    return numeric, cat_encoded, y, groups, encoder, kept, numeric_features + cat_names


def child_pr_auc(y_true, y_score, is_child_mask) -> float:
    if is_child_mask.sum() == 0 or len(set(y_true[is_child_mask])) < 2:
        return float("nan")
    return float(average_precision_score(y_true[is_child_mask], y_score[is_child_mask]))


def lift(pr_auc: float, prevalence: float) -> float:
    if pr_auc != pr_auc or not prevalence:
        return float("nan")
    return pr_auc / prevalence


def make_lr(seed, class_weight="balanced"):
    return LogisticRegression(class_weight=class_weight, max_iter=2000, random_state=seed)


def run_lr_cv(numeric, cat_encoded, y, groups, is_child, n_splits=5, seed=0, class_weight="balanced", scale=True):
    """Grouped k-fold CV, StandardScaler fit per fold (only if scale=True).
    Returns (fold_stats, oof_scores, speaker_to_fold)."""
    gkf = GroupKFold(n_splits=n_splits)
    oof_scores = np.full(len(y), np.nan)
    fold_stats = []
    speaker_to_fold = {}

    for fold_i, (train_idx, val_idx) in enumerate(gkf.split(numeric, y, groups)):
        for sp in set(groups[val_idx]):
            speaker_to_fold[sp] = fold_i

        if scale:
            scaler = StandardScaler()
            num_train = scaler.fit_transform(numeric[train_idx])
            num_val = scaler.transform(numeric[val_idx])
        else:
            num_train, num_val = numeric[train_idx], numeric[val_idx]

        model = make_lr(seed + fold_i, class_weight=class_weight)
        X_train = np.hstack([num_train, cat_encoded[train_idx]])
        X_val = np.hstack([num_val, cat_encoded[val_idx]])
        model.fit(X_train, y[train_idx])
        proba = model.predict_proba(X_val)[:, 1]
        oof_scores[val_idx] = proba

        val_child = is_child[val_idx]
        n_child = int(val_child.sum())
        n_child_pos = int(y[val_idx][val_child].sum())
        prevalence = n_child_pos / n_child if n_child else float("nan")
        pr_auc = child_pr_auc(y[val_idx], proba, val_child)
        fold_stats.append({
            "fold": fold_i, "n_val": len(val_idx), "n_child": n_child, "n_child_pos": n_child_pos,
            "prevalence": prevalence, "pr_auc": pr_auc, "lift": lift(pr_auc, prevalence),
        })

    return fold_stats, oof_scores, speaker_to_fold


def summarize_folds(fold_stats: list[dict]) -> dict:
    vals = np.array([f["pr_auc"] for f in fold_stats if f["pr_auc"] == f["pr_auc"]])
    lifts = np.array([f["lift"] for f in fold_stats if f["lift"] == f["lift"]])
    return {"mean": float(vals.mean()), "std": float(vals.std()), "min": float(vals.min()), "max": float(vals.max()),
            "lift_mean": float(lifts.mean()), "lift_min": float(lifts.min()), "lift_max": float(lifts.max())}


def _row_key(r: dict) -> tuple:
    return (r["utt_id"], r["word_index"], r["index"])


def per_speaker_delta(candidate_rows: list[dict], baseline_rows: list[dict]) -> dict:
    cand_by_key = {_row_key(r): r for r in candidate_rows}
    base_by_key = {_row_key(r): r for r in baseline_rows}
    shared_keys = set(cand_by_key) & set(base_by_key)
    assert len(shared_keys) == len(cand_by_key) == len(baseline_rows), (
        f"candidate/baseline row sets must match exactly - candidate={len(cand_by_key)} "
        f"baseline={len(base_by_key)} shared={len(shared_keys)}"
    )
    by_speaker: dict[str, list[tuple]] = {}
    for key in shared_keys:
        c, b = cand_by_key[key], base_by_key[key]
        assert c["label"] == b["label"], f"label mismatch at {key}"
        by_speaker.setdefault(c["speaker"], []).append((c["label"], c["score"], b["score"]))

    per_speaker = []
    excluded_single_class = 0
    for speaker, triples in by_speaker.items():
        labels = [t[0] for t in triples]
        if len(set(labels)) < 2:
            excluded_single_class += 1
            continue
        c_scores = [t[1] for t in triples]
        b_scores = [t[2] for t in triples]
        c_pr = float(average_precision_score(labels, c_scores))
        b_pr = float(average_precision_score(labels, b_scores))
        per_speaker.append({"speaker": speaker, "n": len(triples), "n_pos": sum(labels),
                             "candidate_pr_auc": c_pr, "baseline_pr_auc": b_pr, "delta": c_pr - b_pr})

    deltas = [p["delta"] for p in per_speaker]
    n_beats = sum(1 for d in deltas if d > 0)
    n_loses = sum(1 for d in deltas if d < 0)
    n_ties = sum(1 for d in deltas if d == 0)

    from scipy.stats import binomtest, wilcoxon
    sign_test = binomtest(n_beats, n_beats + n_loses, p=0.5) if (n_beats + n_loses) > 0 else None
    try:
        wilcoxon_result = wilcoxon(deltas) if len(deltas) >= 1 and any(d != 0 for d in deltas) else None
    except ValueError:
        wilcoxon_result = None

    return {
        "n_speakers_included": len(per_speaker), "n_speakers_excluded_single_class": excluded_single_class,
        "n_beats": n_beats, "n_loses": n_loses, "n_ties": n_ties,
        "sign_test_p_value": sign_test.pvalue if sign_test else float("nan"),
        "wilcoxon_p_value": wilcoxon_result.pvalue if wilcoxon_result else float("nan"),
        "mean_delta": float(np.mean(deltas)) if deltas else float("nan"),
        "median_delta": float(np.median(deltas)) if deltas else float("nan"),
        "per_speaker": per_speaker,
    }


def candidate_rows_from_oof(rows, kept, oof_scores, child_only_speakers=None):
    """child_only_speakers: optional set to restrict to; None = all kept rows."""
    out = []
    for row_i, i in enumerate(kept):
        r = rows[i]
        if child_only_speakers is not None and r["speaker"] not in child_only_speakers:
            continue
        out.append({
            "utt_id": r["utt_id"], "word_index": r["word_index"], "index": r["index"],
            "speaker": r["speaker"], "phone": r["expected"], "position": r["position"],
            "label": label_for_accuracy(r["phone_accuracy"]),
            "status": "wrong" if oof_scores[row_i] >= 0.5 else "correct",
            "score": float(oof_scores[row_i]), "heard": None, "gt_sub": None,
        })
    return out


def gop_rows_for(records, child_only=True):
    sf = (lambda rec: rec["is_child"]) if child_only else None
    return [r for r in flatten_rows(records, predict_gop_zscore, slice_filter=sf) if r["label"] is not None]


def echo_phoneme_weights() -> dict[str, int]:
    """Word counts per target phoneme from Echo's own curriculum
    (levels.json + practice_tracks.json), NOT speechocean762's phoneme
    distribution - this is the weighting the within-phoneme headline uses."""
    from collections import Counter
    weights = Counter()
    with open(Path(__file__).parent.parent / "backend" / "data" / "levels.json") as f:
        levels = json.load(f)
    for lvl in levels:
        for w in lvl["words"]:
            weights[w["target_phoneme"]] += 1
    with open(Path(__file__).parent.parent / "backend" / "data" / "practice_tracks.json") as f:
        tracks = json.load(f)
    for phoneme, track in tracks.items():
        weights[phoneme] += sum(len(tier["words"]) for tier in track["tiers"])
    return dict(weights)
