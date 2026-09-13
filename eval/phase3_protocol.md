# Phase 3 protocol (locked in before any classifier is trained)

Written in response to review feedback on Phase 0, before touching a
classifier. Every number cited here comes from `eval/baselines.json` /
`eval/phase1_check.json` after the `harness.py` refactor that added raw
counts and speaker-clustered bootstrap CIs - re-run these scripts if the
dev cache ever changes and re-paste the numbers here.

## Success criterion

**Metric: PR-AUC (average precision) on the child slice, with a 95%
bootstrap CI resampled by speaker (`harness.bootstrap_ci_by_speaker`).**

| model | PR-AUC | 95% CI |
|---|---|---|
| always-correct (floor) | 0.030 | [0.011, 0.055] |
| GOP z-score (current best baseline) | 0.077 | [0.039, 0.133] |
| hypothesis scorer (λ=0) | 0.047 | [0.019, 0.091] |
| Phase 1 naive (llr>0, no calibration) | 0.120 | [0.039, 0.212] |

Phase 3's classifier is judged against **0.077** (GOP z-score). It counts
as beating the baseline only when its child-slice PR-AUC's 95% CI does not
overlap the GOP z-score CI's upper bound (0.133) - i.e. its lower CI bound
must exceed 0.133. A higher point estimate whose CI overlaps 0.077's
interval is reported as "not distinguishable from the current baseline at
this sample size," not as a win. Note already-visible from this table:
Phase 1's own naive-rule point estimate (0.120) looked like a large
improvement over GOP z-score before computing a CI; its actual CI
([0.039, 0.212]) overlaps GOP z-score's almost entirely. That comparison is
retracted as unsupported - stated here so the same mistake isn't repeated
for Phase 3's model.

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
  subtrain`) is required before this can run - subtrain was never
  feature-extracted during Phases 0-2, which only needed the dev split for
  checkpointing. That extraction is running now; this document will be
  updated with the actual fold results once it completes and the CV loop
  runs.

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
