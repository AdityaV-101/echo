"""Correction 1: comparing two independently-computed marginal CIs is not a
test of whether one scorer beats another on the same data - their sampling
noise is correlated (same speakers, same recordings, same label noise), and
a marginal-CI comparison throws that shared structure away. This uses
harness.paired_bootstrap_delta instead: resample speakers once per
iteration, apply that SAME resample to both scorers, difference their
PR-AUC. Re-tests the Phase 1 "beats GOP z-score on the child slice" claim
under the correct test rather than leaving an unsupported retraction in
place - see eval/phase3_protocol.md for where the outcome gets recorded.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from baselines import predict_gop_zscore  # noqa: E402
from harness import flatten_rows, paired_bootstrap_delta  # noqa: E402
from phase1_check import predict_phase1_naive  # noqa: E402

EVAL_DIR = Path(__file__).parent

SLICES = {
    "all_speakers": None,
    "child": lambda r: r["is_child"],
    "age_le9": lambda r: r["is_child"] and r["age"] <= 9,
}


def main():
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        gop_records = json.load(f)
    with open(EVAL_DIR / "phase1_raw_cache_dev.json") as f:
        phase1_records = json.load(f)

    gop_speakers = {r["speaker"] for r in gop_records}
    phase1_speakers = {r["speaker"] for r in phase1_records}
    assert gop_speakers == phase1_speakers, (
        f"phase0 and phase1 dev caches must share the same speaker set for a paired test - "
        f"symmetric difference: {gop_speakers ^ phase1_speakers}"
    )

    report = {}
    for slice_name, slice_filter in SLICES.items():
        gop_rows = [r for r in flatten_rows(gop_records, predict_gop_zscore, slice_filter) if r["label"] is not None]
        phase1_rows = [r for r in flatten_rows(phase1_records, predict_phase1_naive, slice_filter) if r["label"] is not None]

        result = paired_bootstrap_delta(phase1_rows, gop_rows, metric_name="pr_auc", n_boot=2000, seed=0)
        report[slice_name] = result
        lo, hi = result["ci"]
        verdict = "BEATS baseline (CI lower bound > 0)" if lo > 0 else "does NOT beat baseline (CI includes 0 or below)"
        print(f"{slice_name:14} phase1_naive - gop_zscore PR-AUC delta = {result['point_delta']:+.4f}  "
              f"95% CI [{lo:+.4f}, {hi:+.4f}]  P(delta>0)={result['frac_positive']:.1%}  n_boot={result['n_boot_valid']}")
        print(f"               -> {verdict}")

    with open(EVAL_DIR / "paired_significance_tests.json", "w") as f:
        json.dump({k: {"point_delta": v["point_delta"], "ci": list(v["ci"]),
                        "frac_positive": v["frac_positive"], "n_boot_valid": v["n_boot_valid"]}
                   for k, v in report.items()}, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'paired_significance_tests.json'}")


if __name__ == "__main__":
    main()
