# Results (living document, updated as phases complete)

Every number below was produced by running the script named next to it -
none are estimates. Re-run the named script if the underlying cache
changes and re-paste.

## Phase 3 classifier: calibration is bad, do not threshold raw probabilities

`eval/train_phase3.py` computed a reliability diagram and Expected
Calibration Error (ECE) on the selected model's (logistic regression)
out-of-fold predictions, pooled child rows, 125 speakers - `class_weight=
"balanced"` was used to fight the ~2-3% base rate, and it has the known
side effect of pushing `predict_proba` output away from true class-
conditional probabilities:

| predicted P(error) bin | count | mean predicted | actual error rate |
|---|---|---|---|
| 0.0-0.1 | 6572 | 0.043 | 0.001 |
| 0.5-0.6 | 882 | 0.549 | 0.023 |
| 0.7-0.8 | 590 | 0.748 | 0.054 |
| 0.9-1.0 | 256 | 0.942 | 0.262 |

**ECE = 0.233.** In the model's most confident bin, it says "94% sure this
is an error" on average and is right 26% of the time. **This model's raw
probabilities cannot be used to set a threshold - Phase 5's FRR<=0.05
constraint is meaningless against an uncalibrated score.** Platt scaling or
isotonic regression (already planned in the original Phase 3 spec,
"recalibrate the probability on a held-out child slice") is now a hard
prerequisite for Phase 5, not an optional refinement - confirmed necessary
by this diagram, not assumed. See `eval/reliability_diagram.png`.

## Phase 3 classifier: coefficients, and two things that need a closer look

Full ranked list in `eval/phase3_results.json` (`lr_coefficients_standardized`,
final model fit on all pooled data, standardized features so magnitudes are
comparable). The core acoustic features behave as expected: `gop_i`
(-2.19, higher goodness-of-pronunciation -> lower P(error), matches its
Phase 2 univariate correlation of -0.337) and `llr_deletion` (+1.93, a
plausible deletion candidate -> higher P(error)) both have the sign they
should.

**Two things flagged, not smoothed over:**

1. **`llr_best`'s sign flipped.** Phase 2's univariate check found
   `llr_best` positively correlated with error (r=+0.256 overall, +0.182
   child) - more evidence for an alternative candidate should mean more
   likely an error, and it does on its own. In the full model, holding
   everything else constant, its standardized coefficient is **-1.65**,
   the opposite direction. This is a textbook multicollinearity/suppression
   pattern (`llr_best` is correlated with `gop_i`, `gop_lpr_i`, and the
   phoneme-identity dummies below), not a data error, but it means
   `llr_best`'s marginal contribution inside this model is not what its
   univariate signal alone would suggest - worth a VIF check or dropping
   correlated features one at a time before trusting this coefficient's
   sign in isolation.
2. **Target-phoneme identity dummies dominate the top of the ranking.**
   5 of the top 9 coefficients by magnitude are `expected_*` (which phone
   is the target): `expected_ER` (-2.87), `expected_N` (+2.41),
   `expected_M` (+2.36), `expected_DH` (-1.96), `expected_W` (+1.94),
   `expected_S` (+1.67) - all ranked above every acoustic feature except
   `gop_i`. M and N are typically among the earliest, easiest sounds
   developmentally, so a strong positive "this target phoneme itself
   predicts error" coefficient is not an obvious acoustic finding - it may
   be capturing this corpus's specific annotation patterns or word-list
   composition rather than something that generalizes to Echo's own level
   words. **Open question, not resolved here:** is the model substantially
   scoring "which phoneme is this" rather than "how good was this specific
   attempt"? Worth checking by re-running with the `expected_*` dummies
   dropped and seeing how much PR-AUC survives on acoustic features alone.

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
