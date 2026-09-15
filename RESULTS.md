# Results (living document, updated as phases complete)

Every number below was produced by running the script named next to it -
none are estimates. Re-run the named script if the underlying cache
changes and re-paste.

## Part 1: Held-out test-split evaluation (final, single run)

`eval/run_test_eval.py`, run once. Speechocean762's own official TEST
partition (125 speakers) - distinct from the 125 subtrain+dev speakers the
frozen model was trained on (checked directly: zero speaker-id overlap
between `eval/speaker_split.json` and `eval/speechocean_test.jsonl`). No
prior phase touched this data in any way - no tuning happens in this
section either. This runs the exact shipped pipeline: `backend/
recording_gate.py`'s usable-recording gate, then the frozen Phase 3
classifier (`backend/data/phase3_model/`, loaded exactly as `backend/
decision.py` loads it) at the shipped thresholds (T_CORRECT=0.10,
T_ERROR=0.71 - the child-facing, precision>=0.5-constrained point).

**A real bug found and fixed while building this script, not before:**
`backend/decision.py`'s naming rule was setting `heard` (the substitution
named to the child) from `pos.llr_best_origin`, which is a CATEGORY string
("canonical", a phonological-process name like "stopping"/"fronting", or
"deletion" - see `llr_scorer.py`'s `_substitutions_for`), never an actual
ARPABET phoneme. It could never equal a ground-truth `pronounced_phone`,
so `substitution_naming_accuracy` was structurally ~0% by construction on
first run (confirmed: 0.0% across all three slices), not a real
measurement of anything. Root-caused and fixed to use `pos.top_competitor`
instead (`features.py`'s `_gop_and_lpr`: "the single most plausible
alternative reading of this span" - an actual ARPABET label), with
`llr_best_origin` still used to decide *whether* to name anything at all
(no naming when the local evidence's best explanation is "canonical" - no
alternative-candidate evidence - or "deletion" - no specific substitution
to name). Re-run after the fix: naming accuracy 0.0% -> 63.3%/76.7%/76.9%
across the three slices below. This is a `backend/` fix made during Part 1
(before the "don't touch backend/" freeze that starts with Part 2); no
number anywhere in this document before this section depended on it -
`substitution_naming_accuracy` was never previously reported in this file.

**Recording gate:** 97/15,967 words (0.6%) rejected as `unclear_recording`
before any phoneme verdict - excluded from every metric below (their own
band, same convention as the "ambiguous" label band).

| slice | n_speakers | n (phoneme occurrences) | precision | recall | FRR | abstain rate | naming accuracy | PR-AUC | expected false corrections / 10-word session |
|---|---|---|---|---|---|---|---|---|---|
| all speakers | 125 | 40,439 | 0.758 [0.620, 0.853] | 0.272 [0.187, 0.340] | 0.0022 [0.0013, 0.0034] | 14.8% | 0.633 [0.506, 0.735] (n=147) | 0.402 [0.294, 0.490] | 0.0218 |
| child | 64 | 18,515 | 0.667 [0.315, 0.824] | 0.216 [0.073, 0.340] | 0.0021 [0.0011, 0.0034] | 15.5% | 0.767 [0.333, 1.000] (n=30) | 0.289 [0.129, 0.416] | 0.0205 |
| age<=9 | - | 9,406 | 0.679 [0.267, 0.846] | 0.275 [0.074, 0.426] | 0.0026 [0.0015, 0.0057] | 16.6% | 0.769 [0.200, 1.000] (n=26) | 0.349 [0.126, 0.509] | 0.0331 |

95% CIs are speaker-clustered bootstrap (`bootstrap_ci_by_speaker`, n=2000),
same methodology as every other CI in this document. The naming-accuracy
CIs are as wide as they look: at n=30 and n=26 naming events, the interval
spans a third-to-all-of-the-range (child: [0.333, 1.000]; age<=9: [0.200,
1.000]) - the 76.7%/76.9% point estimates are real but should not be read
as more precise than that. Only the all-speakers slice (n=147) has a
usably tight interval (0.633 [0.506, 0.735]).

**Test is the primary figure here; the dev-split child-facing point
(recall=0.061 [0.019, 0.113], precision=0.500 [0.235, 0.732], T_ERROR=0.71,
reported in "Phase 5 operating points" above) is the development-time
estimate it superseded, not a rival number to reconcile against.** Test's
child slice carries 673 clear-error tokens and ~64 of them caught under a
matched comparison (below); dev's child-facing point had 293 positives and
18 caught. Test is the better-powered of the two, from a genuinely
held-out population (125 speakers with zero overlap with the 125
subtrain+dev speakers the frozen model trained on), and is the number that
should be trusted going forward. Dev's point stands as what the modeling
freeze was decided against, not as ongoing ground truth.

**The 0.061 -> 0.216 recall move as originally read here overstated a real
effect that is actually much smaller, because the two numbers were not
computed the same way.** Dev's child-facing point (`eval/phase5_two_points.py`'s
`evaluate_point`) has no abstain concept - every non-ambiguous attempt is
a binary flagged/not-flagged call. This section's headline table, built on
`harness.py`'s accumulator, excludes the `[T_CORRECT, T_ERROR)` abstain
band from the recall denominator entirely - a different metric wearing the
same name. Recomputed on the test child slice under dev's exact
convention (binary threshold, no abstain exclusion, same population
definition), with a speaker-clustered bootstrap CI:

| | recall | FRR | precision | clear-error prevalence |
|---|---|---|---|---|
| dev child-facing point (development-time estimate) | 0.061 [0.019, 0.113] | 0.0011 | 0.500 | 1.78% (293/16,422) |
| test child, matched convention (the correct comparison) | 0.095 [0.034, 0.149] | 0.0018 | 0.667 | 3.63% (673/18,515) |

Recall is a property of the positive class - P(flagged \| actual error) -
and has no dependence on how many negatives are in the population. Under
the matched convention it moves from 0.061 to 0.095 with heavily
overlapping CIs, and FRR moves from 0.0011 to 0.0018: both differences are
indistinguishable from sampling noise at these positive counts. Precision,
unlike recall, is exactly a function of prevalence given fixed recall/FRR
(Bayes' theorem: `precision = recall*prevalence / (recall*prevalence +
FRR*(1-prevalence))`), and it moves from 0.500 to 0.667 in lockstep with
the measured prevalence change from 1.78% to 3.63% - plugging dev's own
recall/FRR into that formula at test's prevalence predicts precision=0.675
against a measured 0.667. The base-rate formula accounts for the precision
shift exactly. There is no residual effect - in recall, FRR, or precision -
that requires an explanation beyond "matched detection characteristics,
applied to a population with a measurably different clear-error rate."
Both slices clear FRR<<0.05 comfortably either way.

**Within-phoneme table** (all-speakers slice, phonemes with >=10 positive
tokens, 29 of 39 canonical phonemes qualify) - this is a per-phoneme
breakdown of this one frozen scorer's test-split results (`harness.py`'s
own `by_phoneme` accumulation), not a repeat of the earlier "within-phoneme
evaluation" section's phoneme-identity-control methodology (that question -
does the classifier carry acoustic skill beyond phoneme-identity - was
already answered on dev data and stands as the project's real headline
finding; this table is a transparency artifact for the final frozen
scorer, not a new test of that question):

| phone | n | n_pos | precision | recall | FRR | PR-AUC | abstain |
|---|---|---|---|---|---|---|---|
| AH | 3651 | 128 | 0.667 | 0.062 | 0.001 | 0.215 | 22.2% |
| T | 3591 | 51 | 0.737 | 0.275 | 0.002 | 0.449 | 10.3% |
| N | 2769 | 41 | 0.609 | 0.341 | 0.004 | 0.454 | 9.2% |
| IH | 2687 | 43 | 0.643 | 0.209 | 0.002 | 0.364 | 14.6% |
| S | 2027 | 38 | 0.781 | 0.658 | 0.004 | 0.599 | 6.2% |
| D | 1610 | 26 | 0.769 | 0.385 | 0.002 | 0.435 | 13.8% |
| L | 1604 | 43 | 0.667 | 0.186 | 0.003 | 0.375 | 15.2% |
| IY | 1454 | 27 | 0.857 | 0.222 | 0.001 | 0.321 | 16.1% |
| K | 1334 | 14 | 0.833 | 0.357 | 0.001 | 0.621 | 4.3% |
| M | 1290 | 22 | 1.000 | 0.227 | 0.000 | 0.531 | 6.9% |
| AE | 1282 | 29 | 0.667 | 0.069 | 0.001 | 0.273 | 19.8% |
| DH | 1164 | 31 | 0.667 | 0.065 | 0.001 | 0.293 | 17.7% |
| AY | 1128 | 22 | 1.000 | 0.227 | 0.000 | 0.505 | 17.1% |
| HH | 1049 | 12 | 0.000 | 0.000 | 0.001 | 0.241 | 4.2% |
| EH | 1048 | 27 | 0.778 | 0.259 | 0.003 | 0.478 | 34.5% |
| R | 1022 | 31 | 0.818 | 0.290 | 0.003 | 0.391 | 23.2% |
| UW | 832 | 19 | 1.000 | 0.158 | 0.000 | 0.269 | 16.3% |
| F | 828 | 15 | 0.889 | 0.533 | 0.001 | 0.740 | 3.0% |
| EY | 683 | 39 | 1.000 | 0.744 | 0.000 | 0.740 | 37.0% |
| OW | 644 | 14 | nan | 0.000 | 0.000 | 0.181 | 31.2% |
| ER | 609 | 27 | 0.800 | 0.148 | 0.002 | 0.309 | 27.3% |
| AO | 579 | 17 | 0.750 | 0.176 | 0.003 | 0.388 | 30.2% |
| Z | 534 | 36 | 0.636 | 0.583 | 0.033 | 0.551 | 24.7% |
| V | 517 | 11 | 0.500 | 0.091 | 0.002 | 0.328 | 8.7% |
| NG | 512 | 15 | 1.000 | 0.467 | 0.000 | 0.524 | 11.5% |
| AA | 375 | 10 | 0.400 | 0.200 | 0.009 | 0.432 | 13.1% |
| SH | 304 | 12 | 0.750 | 0.250 | 0.004 | 0.621 | 19.1% |
| AW | 300 | 13 | 1.000 | 0.231 | 0.000 | 0.529 | 22.3% |
| TH | 203 | 11 | 0.636 | 0.636 | 0.045 | 0.400 | 50.7% |

`HH` (precision=recall=0.0, 12 positives, 0 caught) and `OW` (same
pattern, 14 positives) are the two weakest-covered phonemes with enough
data to say so plainly - not smoothed over. `TH`'s FRR (0.045) is the
highest of any phoneme with a nontrivial count, close to the global
FRR<=0.05 budget that was rejected as a selection rule in the Phase 5
section above, for the same reason: it's one phoneme's worth of noise
(n=203, only 89 negative tokens), not evidence of a systematic problem.
Full per-phoneme breakdown for all three slices (including phonemes below
the n>=10 filter, and both all-speakers/child/age<=9 versions) is in
`eval/test_eval_final.json`.

Data-access requests for PERCEPT-R, UltraSuite, and MyST (Phase 6's
external-corpus validation, not run this session) are drafted in
`eval/corpora.md`.

## Phase 5 operating points: two, not one - FRR budget replaced with a precision floor

**The FRR<=0.05 selection rule itself was wrong at this base rate.** It
produced a single point (k=1,n=1, T_ERROR=0.20: recall=0.427,
precision=0.138, FRR=0.0485) with 13.8% precision and 0% abstention -
naming a specific sound wrong 86% of the time it fires is not a usable
child-facing decision, and 0% abstention is a design failure, not
efficiency. Corrected (`eval/phase5_two_points.py`) to two operating
points for two different consumers, with a precision floor replacing the
FRR floor for the one that's allowed to speak to the child.

**k-of-n corroboration still doesn't help, confirmed a second way.**
Checked whether any k-of-n configuration can reach precision>=0.5 at any
threshold at all (fine grid, step 0.01): **none can** - 2-of-3, 3-of-4,
2-of-4, and 3-of-5 all top out below 0.5 precision regardless of T_ERROR,
too data-sparse to support the constraint. Only single-attempt
thresholding clears it. This is the same dispersion-diagnostic mechanism
as before (false alarms are speaker-systematic, not independent), showing
up under a different selection rule - not a fluke of the FRR-budget
framing specifically.

**Correction to a specific number from last turn:** the "2-of-4 at T=0.35"
point was described as "almost exactly" a precision>=0.5 answer - checked
directly, its precision is **0.200**, not >=0.5. At matched FRR (~0.006),
single-attempt thresholding (T=0.46) gives recall=0.167, precision=0.338 -
2-of-4 has higher recall (0.263) but lower precision (0.200) at that same
FRR. Neither dominates the other at FRR~0.006; neither clears the
precision floor either, so neither qualifies as child-facing regardless.

### Child-facing point (precision>=0.5 hard constraint, then max recall)

| metric | value |
|---|---|
| T_ERROR | 0.71 |
| recall | 0.061 [95% CI 0.019, 0.113] |
| precision | 0.500 [95% CI 0.235, 0.732] |
| FRR | 0.0011 [95% CI 0.0005, 0.0018] |
| abstain band | [T_CORRECT=0.10, T_ERROR=0.71) |
| **abstain rate** | **13.2%** (2169/16422 child attempts) |
| **expected false corrections per 10-word session** | **0.011** |

**This is far more conservative than the initial estimate of "recall
around 0.25."** That estimate came from misreading the 2-of-4/T=0.35
point's FRR (0.006) as if it implied similar precision; the actual
precision>=0.5 constraint, measured directly, caps single-attempt recall
at 6.1%, not 25%. 0.011 expected false corrections per 10-word session is
roughly **one false "you got that wrong" every 91 sessions** for a child
saying everything correctly - much rarer than the superseded point's
1-per-2-sessions, at the direct cost of catching far fewer real errors per
session. This is the headline product number: **at the threshold allowed
to name a specific sound, Echo is right about which sound is wrong half
the time it speaks, and it rarely speaks.**

### Therapist-queue point (no precision floor - ranked, not thresholded)

Every attempt's calibrated probability is retained
(`attempt_history`/`GET /api/therapist/top-k`); recall/precision at top-K
(pooled child attempts, ranked by probability, 293 true positives total):

| K | recall | precision | true positives caught |
|---|---|---|---|
| 10 | 0.024 | 0.700 | 7 |
| 25 | 0.048 | 0.560 | 14 |
| 50 | 0.065 | 0.380 | 19 |

Last turn's selected point (T=0.20, recall=0.427, precision=0.138)
belongs here, not at the child-facing threshold - its 0.48 expected false
corrections per 10-word session is the right number for a therapist
reviewing a ranked queue, not for a message shown directly to a child.

### Naming rule (implemented, `backend/decision.py` + `backend/scorer_phase3.py`)

A specific substitution is named only at `status=="wrong"` (p>=0.71). Below
that but at or above T_CORRECT=0.10, the response is `status=="unclear"` -
a non-naming nudge ("let's try that one more time"), no claim about which
sound was wrong. The old k-of-n/`confirmed_status` machinery is removed
from the live decision path (it never won any comparison run against it,
at either selection rule) - `backend/aggregation.py` is kept as correct,
tested infrastructure, unused by default.

**Verification, since the last version's k-of-n layer was found to be a
silent no-op:** `eval/phase5_joint_sweep.py` and `eval/phase5_two_points.py`
both compute their k/n counting directly from raw probabilities inline -
neither imports `backend.decision` or `backend.aggregation` (checked by
grep, not assumed). `eval/measure_k_of_n.py` does call
`aggregate_k_of_n`, but on `predict_gop_zscore`'s own status strings,
which are literally `"wrong"`/`"correct"` (checked in `eval/baselines.py`) -
not `decision.py`'s former `"candidate_wrong"`. **No number reported last
turn was measured through the broken path**; the bug only ever affected
`backend/decision.py`'s live runtime behavior, which is fixed, and the
now-removed k-of-n layer made the question moot regardless.

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

## Diagnostic: does the feature set discriminate within-phoneme at all, when data isn't the limit?

The child-only within-phoneme test above is confounded with a data problem
(only 3 phonemes measurable). To separate "the features don't work" from
"there isn't enough child data to see it work," `eval/phase3_within_phoneme_l2.py`
re-runs the identical within-phoneme test on the **all-speakers slice**
(children + speechocean762's adult L2 English speakers), where positive
counts per phoneme are large enough to measure reliably. **This is
explicitly not a clinical measurement** - speechocean762's adult speakers
are non-native L2 speakers, and their mispronunciation patterns (accent/
phonological-transfer driven) are a different error-generating process
than developmental child articulation errors. It answers one narrower,
purely methodological question: is this feature set structurally capable
of within-phoneme discrimination at all.

14 of Echo's curriculum phonemes clear 30 positives at the all-speakers
level (74.6% of curriculum weight) - two requested phonemes did not (SH:
24 positives, CH: 10) and are reported as not qualifying rather than forced
into the table:

| phone | n_pos | delta PR-AUC | 95% CI | echo weight |
|---|---|---|---|---|
| T | 200 | +0.254 | [+0.188, +0.303] | 5 |
| R | 107 | +0.262 | [+0.103, +0.414] | 57 |
| D | 119 | +0.154 | [+0.045, +0.247] | 5 |
| L | 102 | +0.153 | [+0.050, +0.274] | 45 |
| N | 162 | +0.129 | [+0.044, +0.235] | 4 |
| V | 33 | +0.196 | [-0.060, +0.391] | 4 |
| TH | 44 | +0.093 | [-0.039, +0.206] | 37 |
| S | 78 | +0.073 | [-0.046, +0.199] | 51 |
| Z | 83 | +0.063 | [-0.018, +0.148] | 35 |
| NG | 47 | +0.063 | [-0.097, +0.230] | 2 |
| DH | 67 | +0.056 | [-0.036, +0.155] | 3 |
| K | 44 | +0.026 | [-0.074, +0.173] | 36 |
| M | 62 | -0.005 | [-0.170, +0.168] | 5 |
| W | 60 | -0.005 | [-0.144, +0.156] | 2 |

**Echo-weighted aggregate: ΔPR-AUC = +0.123, 95% CI [+0.055, +0.199].
Clearly positive - does not cross zero.**

**Conclusion, stated as one of the two options with no hedge: (a) the
features work within-phoneme; child data is the binding constraint.**
Several individual phonemes clear a zero-excluding CI on their own (T, R,
D, L, N), and the weighted aggregate does too. The feature set is not
structurally incapable of within-phoneme discrimination - it discriminates
clearly once there's enough data to show it. The reason the child-only
within-phoneme test came back inconclusive (CI [-0.085, +0.148]) is that
only 3 phonemes had enough child positives to measure, not that the
underlying signal doesn't exist. **This changes the highest-value next
step: it is not "redesign the features," it is "get more child data for
the phonemes Echo actually teaches"** - PERCEPT-R (R misarticulation,
Prompt 1's Phase 6 corpus) is the most direct path, since R is both a
headline clinical target and one of the phonemes already showing the
clearest effect here.

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
