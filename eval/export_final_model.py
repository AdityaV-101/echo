"""Exports the frozen Phase 3 model (logistic regression, class_weight=None
per the calibration finding, the feature set and preprocessing frozen in
eval/phase3_common.py) as a production-loadable artifact - trained on ALL
125 pooled subtrain+dev speakers, since a deployed model should use every
labeled example available, not just a CV fold's training split.

This is a finalize-and-persist step, not further tuning: no new features,
no new hyperparameter search, no new threshold selection happens here -
see eval/phase3_protocol.md's modeling freeze (2026-09-13).
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import ALL_NUMERIC_FEATURES, CATEGORICAL_FEATURES, EXTRA_NUMERIC_NAMES, build_xy, load_pooled_rows  # noqa: E402

EVAL_DIR = Path(__file__).parent
MODEL_DIR = Path(__file__).parent.parent / "backend" / "data" / "phase3_model"
FROZEN_DATE = "2026-09-13"


def main():
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)

    scaler = StandardScaler()
    num_scaled = scaler.fit_transform(numeric)
    X = np.hstack([num_scaled, cat_encoded])

    model = LogisticRegression(class_weight=None, max_iter=2000, random_state=0)
    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / "model.joblib")
    joblib.dump(scaler, MODEL_DIR / "scaler.joblib")
    joblib.dump(encoder, MODEL_DIR / "encoder.joblib")

    metadata = {
        "frozen_date": FROZEN_DATE,
        "numeric_features": ALL_NUMERIC_FEATURES + EXTRA_NUMERIC_NAMES,
        "categorical_features": CATEGORICAL_FEATURES,
        "n_training_rows": len(kept),
        "n_training_speakers": len(set(groups)),
        "class_weight": None,
        "notes": "Frozen per eval/phase3_protocol.md's modeling freeze - trained on all pooled "
                 "subtrain+dev (125 speakers). Not selected via a fresh sweep against this artifact; "
                 "the model class and features were fixed by the CV/ablation work preceding the freeze.",
    }
    with open(MODEL_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=1)

    print(f"Exported frozen model to {MODEL_DIR}/")
    print(f"  n_features: {len(feature_names)} ({len(ALL_NUMERIC_FEATURES + EXTRA_NUMERIC_NAMES)} numeric + {len(feature_names) - len(ALL_NUMERIC_FEATURES + EXTRA_NUMERIC_NAMES)} one-hot)")
    print(f"  trained on {len(kept)} rows, {len(set(groups))} speakers")


if __name__ == "__main__":
    main()
