# Phase 3 protocol (locked in before any classifier is trained)

## MODELING FREEZE - 2026-09-13

**No further feature engineering, hyperparameter search, or threshold
tuning against `eval/speaker_split.json`'s dev/subtrain pool from this date
forward.** With only 3 child phonemes measurable within-phoneme (R, T, N)
and a weighted delta whose 95% CI crosses zero ([-0.085, +0.148] - see
RESULTS.md), any further tuning against this dev set is fitting noise, not
signal: the confidence intervals are wide enough that a change which
happens to move the point estimate positive after this point would not be
distinguishable from chance. The all-speakers/L2 diagnostic (RESULTS.md)
confirms the feature set itself is not the problem - it discriminates
clearly once there's enough data (weighted delta +0.123, CI
[+0.055, +0.199], several individual phonemes clearing a zero-excluding
CI on their own) - so the correct response to an inconclusive child result
is "get more child data" (PERCEPT-R), not "keep adjusting the model against
the data already in hand."

The frozen artifacts, as committed at this date: `backend/llr_scorer.py`,
`backend/features.py`, the feature set and preprocessing in
`eval/phase3_common.py` (numeric features, categorical features,
`MISSING_SENTINEL`), and the selected model class (logistic regression,
`class_weight=None` per the calibration finding, per-fold `StandardScaler`).
Phases 4 and 5 proceed using these frozen artifacts and the measurements
already made - they do not re-open model selection.


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

**Superseding update, after the within-phoneme test (see RESULTS.md):**
the pooled child-slice delta above includes between-phoneme discrimination
the product cannot use - Echo always knows the target phoneme in advance,
so telling an R-attempt from an M-attempt is not a task the deployed
system ever performs. **The criterion now applies to the Echo-curriculum-
weighted WITHIN-phoneme delta**, computed by `eval/phase3_within_phoneme.py`,
not the pooled number. Measured result: ΔPR-AUC = +0.042, 95% CI
[-0.085, +0.148] - **does not currently meet the criterion** (CI crosses
zero). The pooled delta (+0.136, [+0.069, +0.224]) is retained only as a
secondary, explicitly-labeled line - it is real, but it is not evidence the
product's actual task improved. See RESULTS.md's within-phoneme section for
the full breakdown and the data-coverage problem behind it (only 3 of 23
curriculum phonemes have enough data to measure within-phoneme at all).

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

### Actual CV results (`eval/train_phase3.py`, per-fold StandardScaler - see preprocessing audit below)

Grouped 5-fold CV, pooled subtrain+dev (47,076 rows, 125 speakers),
`class_weight="balanced"` for both models, scaler refit inside each fold:

| model | fold PR-AUCs (child) | mean | std | fold prevalences | fold lifts |
|---|---|---|---|---|---|
| logistic regression | 0.150, 0.127, 0.135, 0.323, 0.162 | 0.179 | 0.073 | 2.11%, 1.80%, 1.13%, 2.30%, 1.86% | 7.11x, 7.03x, 11.92x, 14.02x, 8.70x |
| hist gradient boosting | 0.113, 0.133, 0.125, 0.372, 0.177 | 0.184 | 0.096 | (same) | 5.35x, 7.39x, 11.06x, 16.15x, 9.53x |

Per-fold scaling barely moved the numbers (0.179 vs the pooled-scaler run's
0.178) - re-run confirms **logistic regression is still selected** (HGB's
mean doesn't clear LR's mean+1std), not carried forward from the earlier
run. Fold 3 is still the top fold by both raw PR-AUC and lift (14.02x,
still highest even after controlling for its base rate), so it isn't a
pure base-rate artifact - genuinely easier fold, not investigated further
this pass. Fold 2 has the lowest prevalence (1.13%) but a respectable lift
(11.92x), confirming lift and raw PR-AUC can diverge and lift is the
better cross-fold comparison.

**Beat-baseline test - corrected to use ALL 125 pooled speakers, not just
the 24 dev speakers** (see the per-speaker diagnostic below for why the
dev-only number was misleading): logistic regression's out-of-fold
predictions (every speaker predicted by a fold that never trained on them)
vs GOP z-score, both restricted to the full pooled child population
(16,422 rows both, prevalence 1.78%):

**delta PR-AUC = +0.1363, 95% CI [+0.0687, +0.2239], P(delta>0)=100.0%.**
In lift units: candidate 10.00x, baseline 2.36x, **delta_lift = +7.64x**.
Lower bound > 0 by a wide margin - **this is the headline result.**

**Per-speaker robustness** (`eval/train_phase3.py`'s per_speaker_delta,
joined by exact phoneme-attempt key so both scorers are compared on
identical populations per speaker): logistic regression beats GOP z-score
on **98 of 107 speakers** with a defined per-speaker PR-AUC (18 excluded -
single class among their own tokens), sign test p=4.9e-20, Wilcoxon
p=1.6e-15. Restricted to the 49 child speakers with a defined PR-AUC:
**44 of 49**, sign test p=7.6e-09, Wilcoxon p=7.2e-08. This is the number
that survives composition effects - a pooled point estimate is hostage to
a few error-dense speakers (exactly what happened to the dev-only number
below); "beats on 44 of 49 child speakers" does not depend on which
speakers happen to carry the most positive tokens.

**Secondary, dev-only (24 speakers, kept for comparison, NOT the
headline):** delta PR-AUC = +0.2401, 95% CI [+0.0458, +0.3913] (delta_lift
+8.11x). Diagnosed and explained, not just noted: dev speakers are spread
across all 5 folds (0:4, 1:1, 2:6, 3:4, 4:9 - not concentrated in fold 3),
but fold 3's dev-speaker subset specifically (n=529, 39 positives) scores
PR-AUC=0.617 against fold 3's subtrain subset's 0.153 - a handful of dev
speakers happen to be unusually easy, and that composition effect (not
simple fold-selection) is what inflated the dev-only delta relative to the
125-speaker headline. The dev-only number is real but should never be
quoted as the headline on its own.

**Numeric preprocessing audit (explicit, per review request):**

- **Scaler**: `StandardScaler` is fit fresh on each fold's TRAINING rows
  only (`eval/train_phase3.py`'s `run_cv`) and applied to that fold's
  validation rows with the fold's own fitted scaler - never fit on the
  pooled set. Applies to logistic regression only; HGB uses raw numeric
  values (tree splits are invariant to monotonic per-feature scaling, so
  scaling would be a no-op). The FINAL model used only for coefficient
  inspection (not for any performance claim) is fit with a scaler on the
  full pooled set - legitimate for that purpose since it's never scored
  out-of-sample.
- **Imputer**: none in the statistical sense. `llr_deletion` /
  `llr_second_best` are undefined for some positions by construction (a
  single-phoneme word has no deletion candidate; a phone with only one
  documented substitution rule has no second-best). Missing values are
  filled with a fixed constant (`MISSING_SENTINEL = -5.0`, chosen because
  it's far below the observed LLR range and does not depend on any data
  statistic, pooled or per-fold), plus an explicit `has_deletion_candidate`
  / `has_second_best_candidate` binary flag so the model can distinguish
  "no such candidate" from "candidate present with an unusually low LLR."
  Nothing here could leak across the train/validation boundary because
  nothing here is fit on data at all.
- **Feature selection**: none.
- **Speaker-relative features** (`*_speaker_rel`): computed upstream in
  `eval/build_phase2_features.py`, which processes each speaker's own
  attempts in (utt_id, word_index) order and centers each attempt on that
  speaker's running mean computed from ONLY their own prior attempts
  (Welford accumulator) - never another speaker's data, never a future
  attempt of the same speaker's. Verified by construction (the accumulator
  is keyed and updated per speaker, sequentially) rather than by a
  separate check in this pass.
- **Categorical one-hot encoding** (phone identity, position,
  llr_best_origin, top_competitor): fit on the full pooled set, not per
  fold. Not revisited further - these are closed, linguistically-fixed
  vocabularies (39 ARPABET phones, 4 positions, ~12 process names), not
  label-derived or fold-specific statistics, so this doesn't affect the
  result in the way a pooled scaler or imputer would.

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
