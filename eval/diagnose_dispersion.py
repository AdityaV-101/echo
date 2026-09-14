"""Correction 2's actual diagnostic: are GOP z-score's false alarms on the
child slice speaker-systematic (some children get falsely flagged far more
than others, consistently) or just binomial noise around one shared rate?

For each speaker with n_i true-correct (label=0) child-slice tokens, FP_i of
them get a false "wrong" call. Under the null "everyone shares one false-
alarm rate p, independent per token," Var(FP_i/n_i) = p(1-p)/n_i. Pearson's
chi-squared statistic for k proportions sharing one rate,

    X^2 = sum_i (FP_i - n_i*p_hat)^2 / (n_i * p_hat * (1-p_hat))

is chi-square(df=k-1) under that null; X^2/(k-1) is the standard
"overdispersion" / heterogeneity ratio - well above 1 means speakers differ
systematically, which is exactly what would explain both the k-of-n
precision drop (false positives cluster on a few speakers rather than
scattering evenly, so k-of-n windows for THOSE speakers get flagged
regardless of the true label, while other speakers' true positives never
accumulate enough flags) and would make per-speaker calibration (Phase 5,
not yet built) the highest-value remaining lever rather than a better
population-level classifier.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from baselines import predict_gop_zscore  # noqa: E402
from harness import flatten_rows  # noqa: E402

EVAL_DIR = Path(__file__).parent


def main():
    with open(EVAL_DIR / "phase0_raw_cache_dev.json") as f:
        records = json.load(f)

    rows = flatten_rows(records, predict_gop_zscore, slice_filter=lambda r: r["is_child"])
    negative_rows = [r for r in rows if r["label"] == 0]  # true-correct tokens only - false-alarm-eligible

    by_speaker: dict[str, list[dict]] = {}
    for r in negative_rows:
        by_speaker.setdefault(r["speaker"], []).append(r)

    per_speaker = []
    total_n = total_fp = 0
    for speaker, rs in by_speaker.items():
        n_i = len(rs)
        fp_i = sum(1 for r in rs if r["status"] == "wrong")
        per_speaker.append({"speaker": speaker, "n": n_i, "fp": fp_i, "rate": fp_i / n_i})
        total_n += n_i
        total_fp += fp_i

    p_hat = total_fp / total_n
    print(f"Pooled child-slice false-alarm rate (GOP z-score, matches FRR): {p_hat:.4f} ({p_hat:.1%})")
    print(f"Speakers with >=1 true-correct token: {len(per_speaker)}\n")

    print(f"{'speaker':10} {'n':>5} {'fp':>4} {'rate':>7} {'expected_var':>13}")
    for s in sorted(per_speaker, key=lambda s: -s["rate"]):
        expected_var = p_hat * (1 - p_hat) / s["n"]
        print(f"{s['speaker']:10} {s['n']:5} {s['fp']:4} {s['rate']:6.1%} {expected_var:13.6f}")

    # Pearson chi-squared dispersion statistic
    chi_sq = sum(
        (s["fp"] - s["n"] * p_hat) ** 2 / (s["n"] * p_hat * (1 - p_hat))
        for s in per_speaker if s["n"] > 0
    )
    df = len(per_speaker) - 1
    ratio = chi_sq / df
    print(f"\nPearson chi-squared X^2 = {chi_sq:.2f}, df = {df}, overdispersion ratio X^2/df = {ratio:.2f}")

    try:
        from scipy.stats import chi2
        p_value = chi2.sf(chi_sq, df)
        print(f"p-value (chi-square, df={df}): {p_value:.2e}")
    except ImportError:
        p_value = None
        print("(scipy not available for exact p-value)")

    verdict = (
        "well above 1 - false alarms are speaker-systematic, not independent noise"
        if ratio > 2 else
        "close to 1 - consistent with independent per-token noise, no strong speaker effect"
    )
    print(f"\nVerdict: overdispersion ratio {ratio:.2f} is {verdict}")

    result = {
        "p_hat": p_hat, "n_speakers": len(per_speaker),
        "per_speaker": per_speaker,
        "chi_sq": chi_sq, "df": df, "overdispersion_ratio": ratio,
        "p_value": p_value,
    }
    with open(EVAL_DIR / "dispersion_check.json", "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote {EVAL_DIR / 'dispersion_check.json'}")


if __name__ == "__main__":
    main()
