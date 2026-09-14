# Results (living document, updated as phases complete)

Every number below was produced by running the script named next to it -
none are estimates. Re-run the named script if the underlying cache
changes and re-paste.

## Within-phoneme evaluation: the real headline, and it does not clear baseline

The most important test run on this project so far
(`eval/phase3_within_phoneme.py`). Every number quoted for Phase 3 so far
(pooled ΔPR-AUC=+0.136, per-speaker "beats on 98/107") includes
**between-phoneme discrimination the app can never use** - Echo always
knows the target phoneme in advance, so telling an R-attempt apart from an
M-attempt contributes nothing to the actual product task, which is telling
a correct R from a wrong R. Within one target phoneme, phoneme identity is
constant and carries zero information - whatever's left has to be real
acoustic signal.

**Data coverage is the first finding, and it's bad news on its own:** of
Echo's 23 curriculum target phonemes (weighted by word count in
`levels.json` + `practice_tracks.json`), only **3 have enough positive
tokens (>=10) in the pooled dev+subtrain data to measure within-phoneme
performance at all: R, T, N.** These cover **16.9%** of Echo's curriculum
weight. The phonemes the app cares about most clinically - S (weight 51),
L (45), SH (40), TH (37), K (36), Z (35), CH (33) - all have between 2 and
9 positive tokens, nowhere near enough to say anything.

| phone | n | n_pos | prevalence | candidate PR-AUC | baseline PR-AUC | delta | echo weight |
|---|---|---|---|---|---|---|---|
| R | 470 | 14 | 3.0% | 0.160 | 0.113 | +0.047 | 57 |
| T | 1437 | 14 | 1.0% | 0.086 | 0.038 | +0.049 | 5 |
| N | 1180 | 16 | 1.4% | 0.153 | 0.197 | **-0.044** | 4 |

N is the one phoneme where the baseline actually wins once phoneme
identity stops varying - direct, if thin, evidence that part of N's
apparent contribution to the pooled result was "N is generally more
error-prone in this corpus," not genuine within-N acoustic discrimination.

**Echo-weighted within-phoneme delta (R, T, N only, renormalized over the
16.9% of curriculum weight with enough data): ΔPR-AUC = +0.042, 95% CI
[-0.085, +0.148] (bootstrap by speaker). The CI crosses zero. This does
NOT clear the baseline. This is now the reference number for whether
Phase 3's classifier is actually useful** - the pooled +0.136 is kept only
as a secondary line, explicitly labeled as including signal the product
cannot access.

**What this means going forward:** the classifier isn't shown to be
better than GOP z-score at the one thing that matters (telling a correct
attempt from a wrong one, sound by sound), mostly because there isn't
enough labeled data yet for the sounds Echo actually teaches. R is the
closest phoneme to being measurable and is also the headline target of
PERCEPT-R (Prompt 1's Phase 6 pediatric validation corpus) - getting that
corpus is now higher priority than further pooled-model tuning, which
would be optimizing a number the product can't use.

## Ablations: phoneme dummies moved things moderately, not decisively

`eval/phase3_ablations.py`, direct follow-up to the within-phoneme result.

**Dropping the `expected_*` (target-phoneme-identity) dummies entirely**
and re-running the same CV: pooled CV child PR-AUC mean drops from 0.179 to
0.156 (**-13.1%**), pooled beat-baseline delta drops from +0.136 to +0.115
(still clearly positive, 95% CI [0.044, 0.204]). **Verdict: moved
moderately, not a collapse** - phoneme identity is a real contributor to
the pooled number but not the majority of it. This doesn't contradict the
within-phoneme finding above; they answer different questions (pooled
ranking-with-phoneme-identity-available vs. within-phoneme discrimination
specifically) and both are true at once.

**Feature-family ablation** (numeric only, no categoricals at all, so
this isolates which acoustic signal family carries weight independent of
any phoneme-identity question):

| family | n features | CV PR-AUC mean | pooled delta | 95% CI |
|---|---|---|---|---|
| llr_only | 7 | 0.062 | +0.013 | [-0.005, +0.032] (crosses zero) |
| gop_only | 4 | 0.084 | +0.030 | [+0.010, +0.054] |
| duration_entropy_only | 7 | 0.101 | +0.049 | [+0.001, +0.136] |
| all_numeric combined | 18 | 0.142 | +0.103 | [+0.034, +0.190] |

LLR features alone barely clear baseline (CI nearly crosses zero). GOP
features alone are the strongest single family. Duration/entropy alone is
surprisingly competitive (likely driven by entropy and free_decode_gap,
not `dur_z` specifically - see Phase 2's near-zero `dur_z` correlation).
Combining all three numeric families (0.142) clearly beats any single
family, meaning they carry complementary, non-redundant signal rather than
each re-deriving the same information.

## Phase 3 classifier: calibration - fixed, and it was a labeling problem, not a discrimination problem

**Correction to the framing of this section.** ECE=0.233 sounds like the
model is bad; it isn't. 26% observed precision in the top confidence bin at
~1.8% pooled prevalence is about **14.7x lift** (0.262/0.0178) - good
ranking wearing a badly wrong probability number. `eval/phase3_calibration.py`
tracked down the cause and it is exactly the one thing being tested for:
`class_weight="balanced"` reweights the training loss to fight the ~2-3%
base rate, which is known to distort `predict_proba` away from true
class-conditional probabilities even while preserving (or improving)
ranking.

**Dropping `class_weight="balanced"` entirely fixes almost all of it, and
improves ranking slightly:**

| | CV child PR-AUC mean | ECE, pooled | ECE, child slice |
|---|---|---|---|
| `class_weight="balanced"` (as committed) | 0.179 | 0.207 | 0.233 |
| `class_weight=None` | **0.186 (+3.9%)** | **0.004** | **0.031** |

Ranking did not "barely move" - it improved. There is no tradeoff here:
**`class_weight=None`, imbalance handled at the decision threshold in
Phase 5, is strictly better on both axes and is now the recommended
default**, superseding the committed model's balanced-weight setting.

**Nested calibration** (Platt and isotonic, each fit on out-of-fold scores
via a second grouped 5-fold split, applied only to speakers the calibrator
itself never saw - the same out-of-fold discipline as the base model)
applied on top of the *balanced* model's scores gets ECE down to a
comparable range (Platt: pooled 0.011, child 0.034; isotonic: pooled 0.007,
child 0.031) - confirming post-hoc calibration works as an alternative, but
given `class_weight=None` gets there directly with a ranking improvement
instead of a ranking cost, there's no reason to keep the balanced weighting
and calibrate around it. Child-slice PR-AUC after nested calibration
(0.156-0.162) is slightly lower than uncalibrated (0.178) - expected: each
calibrated score comes from a calibrator fit on a different 4/5 of
speakers, an extra held-out layer, not a sign calibration is hurting the
model.

**Phase 5 prerequisite, revised:** use `class_weight=None`. A light
isotonic touch-up on top is optional, not required - ECE is already ~0.03
on the child slice without it.

## Phase 3 classifier: coefficients - checked for collinearity before writing up any sign

**Correction to the earlier version of this section**, which described
`llr_best`'s sign flip as a "finding" before checking whether it was
interpretable at all. Checked now (`eval/phase3_multicollinearity.py`):

**Correlation matrix** (`llr_best`, `gop_i`, `gop_lpr_i`, `entropy`,
`ll_canonical_per_frame`): `gop_i` and `gop_lpr_i` are correlated 0.87;
`llr_best` correlates -0.70 with both. **VIF: gop_i=5.10 (high), gop_lpr_i=
4.63 (moderate), llr_best=2.23 (moderate), entropy=1.20, ll_canonical_per_frame=1.64.**

`gop_i`'s own VIF is technically the "high" one, not `llr_best`'s - the
block is collinear enough that no single coefficient's sign in {`gop_i`,
`gop_lpr_i`, `llr_best`} should be over-interpreted in isolation, by the
VIF check's own logic. That said, the bootstrap (500 resamples by speaker,
`class_weight=None`, the now-recommended setting) says more than VIF alone
can:

| feature | coef | 95% CI | distinguishable from 0? |
|---|---|---|---|
| gop_i | -1.851 | [-2.340, -1.360] | yes |
| llr_best | -1.551 | [-2.117, -0.967] | yes |
| gop_lpr_i | -0.949 | [-1.564, -0.315] | yes |
| entropy | +0.143 | [+0.044, +0.255] | yes |
| ll_canonical_per_frame | -0.202 | [-0.601, +0.559] | **no - crosses zero** |

`llr_best`'s negative multivariate coefficient is bootstrap-stable (CI
entirely below zero) despite only moderate VIF (2.23, not the flagged
"high" feature) - this is **not simply noise from high VIF**, it looks
like a real suppression effect (its residual relationship with the outcome
reverses once `gop_i` is controlled for), which is a legitimate regression
phenomenon but not one diagnosed further here. `ll_canonical_per_frame`,
which previously appeared as a mid-ranked coefficient, is **not
distinguishable from zero at all** and should not be described as having a
meaningful sign in either direction. Overall, **55 of 109 coefficients**
have a bootstrap CI excluding zero - roughly half, mostly the acoustic
features and the higher-support categorical levels; the rest (mostly rare
one-hot categories) should not be read as meaningful individually.

The feature-family ablation above is the real answer to "which family
carries the signal" - `gop_only` (0.084) > `duration_entropy_only` (0.101,
though likely driven by entropy/free_decode_gap not `dur_z`) >
`llr_only` (0.062, barely clears baseline) individually, and all three
combined (0.142) beat any one family, meaning the families are
complementary rather than redundant.

## Per-speaker robustness: why 107 of 125, not 125

Restated plainly per review request: a speaker is excluded from the
per-speaker sign test / Wilcoxon test only when **all of their own labeled
attempts fall in a single class** (all correct or all error) - average
precision (and therefore a per-speaker PR-AUC delta) is undefined without
both classes present for that speaker. 125 pooled speakers - 18 single-class
speakers = 107 with a defined comparison overall; restricted to child
speakers specifically, 58 child speakers - 9 single-class = 49 with a
defined comparison. This is a property of the (small, imbalanced) data, not
a modeling choice - documented in `per_speaker_delta`'s docstring in
`eval/phase3_common.py`.

## Precision ceiling at the child slice's real base rate

`eval/check_extraction_bias.py` confirmed the child slice's base rate is
real, not an artifact of the extraction filter: 92 error tokens / 3108
total = 2.96%, with 0% differential drop rate between error and correct
tokens during extraction.

At any base rate this low, precision is capped by a simple identity
regardless of how good the underlying classifier is:

```
precision = r*P / (r*P + f*N)
```

where `r` = recall, `f` = FRR (false reject rate - a correct production
flagged wrong), `P` = fraction of attempts that are true errors, `N` =
fraction that are true corrects (`N = 1 - P`).

- **Real, measured operating point** (GOP z-score baseline, child slice,
  `eval/baselines.json`): r=47.8%, f=20.5%, P=2.96%. Ceiling: **6.6%** -
  which is exactly the precision that baseline actually measured (6.6%,
  confirming the formula against real data, not just algebra).
- **Illustrative FRR<=0.05 constraint** (Prompt 1's Phase 5 hard
  constraint, hypothetically hit exactly, recall=50%, same 2.96% base
  rate): ceiling is **23.4%** - roughly three of four flagged errors would
  still be false alarms.

**Conclusion: FRR<=0.05 alone is not a tight enough constraint at this base
rate.** A classifier can satisfy the FRR constraint perfectly and still
produce a child-facing experience where most "you got this sound wrong"
messages are wrong. This is why k-of-n evidence aggregation was evaluated
before, not after, Phase 3 - if it doesn't work, that changes what "success"
even means for the classifier.

## k-of-n evidence aggregation: underpowered and misdiagnosed, not negative

**Correction to an earlier version of this section**, which called the
result below "negative" - that overstated what n=4 can actually show, and
skipped the diagnostic that explains what's really going on.

The independence-assumed prediction (`backend.aggregation.binomial_at_least_k`,
verified against the reviewer's own worked numbers: 2-of-3 at per-attempt
FRR=5% -> 0.73% aggregate FRR, at per-attempt recall=50% -> 50% aggregate
recall - both match) says 2-of-3 aggregation should cut false alarms sharply
while leaving recall roughly unchanged. Measured on real dev data
(GOP z-score baseline's actual per-attempt calls, grouped by (speaker,
canonical phone), non-overlapping windows of 3), the child slice showed
recall collapsing to 0% on its 4 aggregated-positive windows, against an
independence-predicted ~46.7%.

**Why 0-of-4 is not evidence the true rate is 0%:** at the predicted
per-window recall of 0.467, `P(observe 0 hits in 4 independent trials) =
(1-0.467)^4 ≈ 8.1%` - an 8% event is unlikely, not essentially impossible.
Four trials cannot distinguish a true recall of 47% from a true recall of
0%. The child-slice k-of-n result is **underpowered**, not a demonstrated
failure - stated plainly because the earlier framing didn't make this
distinction and shouldn't have called it settled.

**The diagnostic that actually matters** (`eval/diagnose_dispersion.py`):
are GOP z-score's false alarms on true-correct child productions scattered
independently across speakers, or systematically worse for some children
than others? Per-speaker false-alarm rate (FP / true-correct-tokens) for
the 11 child-slice speakers with at least one true-correct token, compared
against the binomial-expected variance `p(1-p)/n_i` at the pooled rate
p_hat=20.5%:

| speaker | n | false alarms | rate |
|---|---|---|---|
| 0048 | 172 | 48 | 27.9% |
| 0056 | 219 | 56 | 25.6% |
| 8585 | 323 | 82 | 25.4% |
| 0104 | 266 | 61 | 22.9% |
| 9556 | 361 | 81 | 22.4% |
| 5414 | 267 | 57 | 21.3% |
| 3088 | 229 | 45 | 19.7% |
| 3020 | 286 | 55 | 19.2% |
| 5408 | 361 | 68 | 18.8% |
| 1435 | 261 | 41 | 15.7% |
| 0006 | 271 | 24 | **8.9%** |

Pearson's chi-squared statistic for k proportions sharing one rate:
**X² = 43.13, df = 10, overdispersion ratio X²/df = 4.31, p ≈ 4.7×10⁻⁶.**
A ratio this far above 1 (four times the variance binomial sampling alone
would produce) means false alarms are **speaker-systematic**: speaker 0048
gets falsely flagged more than 3x as often as speaker 0006, consistently,
not as a run of bad luck. This is the direct explanation for why 2-of-3
aggregation didn't behave as the independence assumption predicted -
windows aren't independent draws when some speakers carry a persistently
higher false-alarm rate than others, and it means **per-speaker calibration
(Phase 5, not yet built) is the highest-value remaining lever**, likely
ahead of a better population-level classifier on its own.

**Action, not a verdict:** the k-of-n mechanism (`backend/aggregation.py`)
is implemented and correct (verified against the reviewer's own worked
arithmetic). It is not being shipped or ruled out from this measurement -
it gets re-measured once Phase 5's per-speaker calibration exists (which
this diagnostic says should reduce exactly the systematic component that
broke the independence assumption here), and on more data (subtrain+dev
pooled) if the child-slice window count is still too small at that point.

## Phase 0 baselines (child / age<=9), with raw counts and 95% CIs

**Correction:** the hypothesis-scorer baseline abstains on ~23% of tokens;
its precision/recall/PR-AUC were originally reported on a 70/2321
(child) denominator while the other two baselines used 92/3016 - not
comparable, and the earlier single table invited exactly the wrong read.
`eval/baselines.json` now reports every baseline **twice**, per slice:
`common_coverage_subset` (all three scorers restricted to positions where
the abstaining scorer gives a definitive call - the fair like-for-like
comparison) and `full_set_abstentions_as_miss` (the full labeled
population, with an abstention on a true error coerced to a miss and an
abstention on a true correct coerced to a harmless non-flag - the
comparable-denominator table to use going forward). PR-AUC barely moves
between the two framings (it uses continuous scores regardless of the
coerced status); precision/recall/FRR/FAR do move, most visibly
hypothesis_lambda0's child-slice recall (50.0% restricted-to-coverage vs
38.0% full-set-as-miss) - the coverage-restricted number alone would have
overstated it.

See `eval/phase3_protocol.md` for the full success-criterion table this
feeds into. Full breakdown (all slices, all metrics, per-phoneme/per-position)
is in `eval/baselines.json`.
