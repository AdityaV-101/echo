# Phase 3 protocol (locked in before any classifier is trained)

Written in response to review feedback on Phase 0, before touching a
classifier. Every number cited here comes from `eval/baselines.json` /
`eval/phase1_check.json` after the `harness.py` refactor that added raw
counts and speaker-clustered bootstrap CIs - re-run these scripts if the
dev cache ever changes and re-paste the numbers here.

## Success criterion (corrected)

**Comparing two independently-computed marginal CIs is not a valid test of
"does A beat B" when both are scored on the same data - their sampling
noise is correlated (same speakers, same recordings, same label noise), and
a marginal-CI comparison throws that shared structure away.** The original
version of this criterion did exactly that and is wrong; replaced with a
**paired bootstrap on the difference** (`harness.paired_bootstrap_delta`,
`eval/paired_significance_tests.py`): resample speakers once per iteration,
apply that SAME resample to both scorers, take
`delta = candidate_PR_AUC - gop_zscore_PR_AUC` on each resample. Report the
95% CI of delta and the fraction of resamples with delta > 0.

**Criterion: Phase 3's classifier counts as beating the GOP z-score
baseline on the child slice only when the 95% CI of delta has a lower bound
> 0.**

### Re-testing the Phase 1 retraction under the correct test

The marginal-CI comparison (child: 0.120 [0.039, 0.212] vs 0.077
[0.039, 0.133], near-total overlap) led to retracting Phase 1's "55% better
than GOP z-score" claim as unsupported. Re-tested with the paired bootstrap
(`eval/paired_significance_tests.py`), which removes the noise the two
scorers share instead of double-counting it:

| slice | delta (phase1 - gop_zscore) | 95% CI | P(delta>0) | verdict |
|---|---|---|---|---|
| all speakers | +0.0062 | [-0.0232, +0.0400] | 68.2% | does not beat baseline |
| child | +0.0435 | [-0.0054, +0.0838] | 95.5% | does not beat baseline (barely - lower bound just below 0) |
| age<=9 | +0.0542 | [+0.0004, +0.1006] | 98.2% | **beats baseline** |

**Recorded outcome, both directions stated plainly:** the correct test is
more favorable to Phase 1 than the (wrong) marginal comparison suggested -
on the age<=9 slice specifically, Phase 1's naive rule does show a
statistically supported improvement over GOP z-score (lower CI bound just
above 0, +0.0004 - a real but thin margin). On the broader child slice
(ages 6-15) it falls just short (lower bound -0.0054, 95.5% of resamples
still favor Phase 1). On all speakers, no support either way. The blanket
retraction was too strong; the corrected, precise statement is: **not
supported on the broad child slice, supported (thinly) on age<=9
specifically.**

**Model/hyperparameter selection never uses F1.** F1 is a function of
precision and recall at whatever operating threshold is implicit in a
"wrong"/"correct" call - Phase 5 is what sets that threshold for real
(subject to the FRR<=0.05 hard constraint), and it hasn't run yet. Selecting
a model by F1 now bakes in an arbitrary, not-yet-justified threshold and
can rank two models backwards once Phase 5 recalibrates. PR-AUC is
threshold-free and is what gets reported and selected on throughout
Phase 3.

## Cross-validation protocol

A single 24-speaker dev split is too small to trust for model/hyperparameter
selection at an ~92-positive-token child base rate (see the CI widths
above - a 5-point PR-AUC move is well within noise). Phase 3 uses **grouped
k-fold cross-validation by speaker, pooling subtrain (101 speakers) and dev
(24 speakers)** - group = speaker, via `sklearn.model_selection.GroupKFold`
(or `StratifiedGroupKFold` if fold-to-fold base-rate variance turns out to
matter - to be decided from the actual fold statistics, not assumed).

- k=5 folds, grouped by speaker, over the pooled 125-speaker subtrain+dev
  population.
- Every model/hyperparameter choice is scored by **mean and spread (std,
  min/max) of child-slice PR-AUC across the 5 folds**, not a single number.
- The held-out test split (125 speakers, fully disjoint from
  subtrain+dev - verified in the Phase 0 recheck) is **not touched** during
  this cross-validation. It is scored exactly once, at Phase 5's final run,
  per the rebuild's ground rule 1.
- Feature extraction for subtrain (`eval/extract_features_cache.py
  subtrain`) was required before this could run (subtrain was never
  feature-extracted during Phases 0-2, which only needed the dev split for
  checkpointing) - done, 38,075 rows.

### Actual CV results (`eval/train_phase3.py`)

Grouped 5-fold CV, pooled subtrain+dev (47,076 rows, 125 speakers),
`class_weight="balanced"` for both models:

| model | fold PR-AUCs (child slice) | mean | std | min | max |
|---|---|---|---|---|---|
| logistic regression | 0.148, 0.127, 0.136, 0.321, 0.161 | 0.178 | 0.072 | 0.127 | 0.321 |
| hist gradient boosting | 0.113, 0.133, 0.125, 0.372, 0.177 | 0.184 | 0.096 | 0.113 | 0.372 |

HGB's mean (0.184) doesn't clear LR's mean+1std (0.178+0.072=0.250), so
**logistic regression is selected** (per the "keep the linear one if within
noise, because it's inspectable" rule). Fold 3 is a clear outlier for both
models (0.321 / 0.372 vs the other folds' 0.11-0.18) - whichever speakers
landed in that validation fold happen to be unusually well-predicted;
worth a closer look before trusting the mean too literally, but not
investigated further in this pass.

**Beat-baseline test**, dev-speaker subset of logistic regression's
out-of-fold predictions (never trained on these speakers) vs GOP z-score on
the identical dev child population (3108 rows both):

**delta PR-AUC = +0.2389, 95% CI [+0.0478, +0.3900], P(delta>0)=99.8%.
Lower bound > 0: Phase 3's classifier beats the GOP z-score baseline on the
child slice**, per the corrected criterion above.

Caveat disclosed, not hidden: the categorical one-hot encoder (phone
identity, position, llr_best_origin, top_competitor) was fit on the full
pooled dataset before the CV split, not per-fold. These are closed,
linguistically-fixed vocabularies (39 ARPABET phones, 4 positions, ~12
process names) rather than anything derived from labels or fold-specific
statistics, so this isn't leakage in the sense that matters for the
result - but it's a deviation from strict per-fold preprocessing worth
naming rather than leaving implicit.

## Precision ceiling (see RESULTS.md for the full derivation)

At the child slice's real base rate (3.0%, 92/3108) and GOP z-score's real
operating point (FRR=20.5%, recall=47.8%), the precision ceiling formula
`precision = r*P / (r*P + f*N)` gives roughly 6.6% precision - which is
exactly what was measured (6.6%, see `eval/baselines.json`). FRR<=0.05 alone
is not a sufficient constraint at this base rate: even a hypothetical
perfect FRR=0.05/recall=0.50 operating point only reaches ~24% precision
(three-in-four flagged errors would still be false alarms). This is why
k-of-n evidence aggregation (see `eval/measure_k_of_n.py`) is being added
as a design change now rather than left for later - the single-attempt
operating point Phase 5 would otherwise choose cannot hit a clinically
usable precision on its own at this base rate, independent of how good the
classifier is.
