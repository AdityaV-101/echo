"""Before treating any single coefficient's sign as a finding: check
whether the features it's entangled with are collinear enough to make
signs uninterpretable in the first place. VIF (variance inflation factor)
on {llr_best, gop_i, gop_lpr_i, entropy, ll_canonical_per_frame} plus the
full correlation matrix, then bootstrap CIs on every standardized
coefficient in the full model so it's visible which ones are
distinguishable from zero at all - a coefficient whose 95% CI crosses zero
should not be described as having a meaningful sign, flipped or otherwise.
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))

from phase3_common import build_xy, load_pooled_rows  # noqa: E402

EVAL_DIR = Path(__file__).parent
BLOCK = ["llr_best", "gop_i", "gop_lpr_i", "entropy", "ll_canonical_per_frame"]


def compute_vif(X: np.ndarray, names: list[str]) -> dict[str, float]:
    """VIF_j = 1 / (1 - R^2) from regressing feature j on all the others in
    the block. Standard variance-inflation-factor definition."""
    vif = {}
    for j, name in enumerate(names):
        y_j = X[:, j]
        X_others = np.delete(X, j, axis=1)
        reg = LinearRegression().fit(X_others, y_j)
        r2 = reg.score(X_others, y_j)
        vif[name] = float("inf") if r2 >= 1.0 else 1.0 / (1.0 - r2)
    return vif


def main():
    rows = load_pooled_rows()
    numeric, cat_encoded, y, groups, encoder, kept, feature_names = build_xy(rows)

    block_idx = [feature_names.index(f) for f in BLOCK]
    X_block = numeric[:, block_idx]

    print(f"=== Correlation matrix: {BLOCK} ===")
    corr = np.corrcoef(X_block, rowvar=False)
    header = "".join(f"{n:>14}" for n in BLOCK)
    print(f"{'':16}{header}")
    for i, name in enumerate(BLOCK):
        row_str = "".join(f"{corr[i, j]:14.3f}" for j in range(len(BLOCK)))
        print(f"{name:16}{row_str}")

    print(f"\n=== VIF ===")
    vif = compute_vif(X_block, BLOCK)
    for name, v in vif.items():
        flag = " <-- HIGH (>5)" if v > 5 else (" <-- MODERATE (>2.5)" if v > 2.5 else "")
        print(f"  {name:24} VIF={v:7.2f}{flag}")

    high_vif = [n for n, v in vif.items() if v > 5]
    print(f"\nVerdict: {'HIGH VIF present - coefficient signs within this block are NOT reliably interpretable individually: ' + str(high_vif) if high_vif else 'no VIF above 5 - signs are individually interpretable, collinearity is not the dominant explanation'}\n")

    # --- bootstrap CIs on every standardized coefficient (full model, all pooled data, resampled by speaker) ---
    print("=== Bootstrap 95% CIs on standardized coefficients (full model, resample by speaker, n_boot=500) ===")
    speakers = list(set(groups))
    n_sp = len(speakers)
    by_speaker_idx: dict[str, list[int]] = {}
    for i, sp in enumerate(groups):
        by_speaker_idx.setdefault(sp, []).append(i)

    import random
    rng = random.Random(0)
    n_boot = 500
    coef_samples = np.zeros((n_boot, len(feature_names)))
    for b in range(n_boot):
        drawn = [speakers[rng.randrange(n_sp)] for _ in range(n_sp)]
        idx = np.concatenate([by_speaker_idx[sp] for sp in drawn])
        scaler = StandardScaler()
        num_scaled = scaler.fit_transform(numeric[idx])
        X_boot = np.hstack([num_scaled, cat_encoded[idx]])
        model = LogisticRegression(class_weight=None, max_iter=2000, random_state=b)
        model.fit(X_boot, y[idx])
        coef_samples[b] = model.coef_[0]

    # point estimate: full model on all data (no class_weight, per the calibration finding)
    final_scaler = StandardScaler()
    num_scaled_full = final_scaler.fit_transform(numeric)
    X_full = np.hstack([num_scaled_full, cat_encoded])
    final_model = LogisticRegression(class_weight=None, max_iter=2000, random_state=0)
    final_model.fit(X_full, y)
    point_coefs = final_model.coef_[0]

    results = []
    for j, name in enumerate(feature_names):
        vals = np.sort(coef_samples[:, j])
        lo = vals[int(0.025 * n_boot)]
        hi = vals[min(n_boot - 1, int(0.975 * n_boot))]
        distinguishable = (lo > 0) or (hi < 0)
        results.append({"feature": name, "coef": float(point_coefs[j]), "ci_lo": float(lo), "ci_hi": float(hi),
                         "distinguishable_from_zero": bool(distinguishable)})
    results.sort(key=lambda r: -abs(r["coef"]))

    n_distinguishable = sum(1 for r in results if r["distinguishable_from_zero"])
    print(f"{n_distinguishable}/{len(results)} coefficients have a 95% CI that excludes zero.\n")
    print(f"{'feature':34} {'coef':>8} {'95% CI':>20} {'distinguishable?'}")
    for r in results[:25]:
        print(f"{r['feature']:34} {r['coef']:+8.4f} [{r['ci_lo']:+7.3f},{r['ci_hi']:+7.3f}]   {r['distinguishable_from_zero']}")

    for name in BLOCK:
        r = next(r for r in results if r["feature"] == name)
        print(f"\n{name}: coef={r['coef']:+.4f}  95% CI=[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}]  "
              f"distinguishable from zero: {r['distinguishable_from_zero']}")

    out = {
        "correlation_matrix": {BLOCK[i]: {BLOCK[j]: float(corr[i, j]) for j in range(len(BLOCK))} for i in range(len(BLOCK))},
        "vif": vif, "high_vif_features": high_vif,
        "coefficients_with_ci": results,
        "n_distinguishable_from_zero": n_distinguishable, "n_total_coefficients": len(results),
    }
    with open(EVAL_DIR / "phase3_multicollinearity.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'phase3_multicollinearity.json'}")


if __name__ == "__main__":
    main()
