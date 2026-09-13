# Results (living document, updated as phases complete)

Every number below was produced by running the script named next to it -
none are estimates. Re-run the named script if the underlying cache
changes and re-paste.

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

## k-of-n evidence aggregation: real vs assumed (`eval/measure_k_of_n.py`)

The independence-assumed prediction (`backend.aggregation.binomial_at_least_k`,
verified against the reviewer's own worked numbers: 2-of-3 at per-attempt
FRR=5% -> 0.73% aggregate FRR, at per-attempt recall=50% -> 50% aggregate
recall - both match) says 2-of-3 aggregation should cut false alarms sharply
while leaving recall roughly unchanged. **Measured on real dev data
(GOP z-score baseline's actual per-attempt calls, grouped by (speaker,
canonical phone), non-overlapping windows of 3), that is not what happens:**

| slice | | single-attempt | 2-of-3 (real) | 2-of-3 (independence theory) |
|---|---|---|---|---|
| all speakers | precision | 23.8% [12.8, 34.8] | 15.5% [6.0, 26.9] | - |
| | recall | 46.5% [38.9, 56.0] | 35.0% [24.3, 49.1] | 44.8% |
| | FRR | 18.5% [16.3, 20.5] | 16.8% [14.3, 19.2] | 9.0% |
| child | precision | 6.2% [2.3, 11.0] | **0.0% [0.0, 0.0]** (n_pos=4) | - |
| | recall | 46.7% [40.0, 51.0] | **0.0% [0.0, 0.0]** (n_pos=4) | 45.0% |
| | FRR | 19.9% [16.9, 22.6] | 18.4% [15.6, 21.4] | 10.3% |

(95% CIs bootstrapped by speaker in brackets.)

**This is the opposite of the hoped-for result.** On the child slice, every
one of the 4 windows where the child truly had a persistent problem (>=2 of
3 true errors) was missed entirely by 2-of-3 aggregation - recall collapsed
to 0%, not the ~45% independence would predict. FRR did improve, but far
less than theory predicts (18.4% real vs 10.3% theoretical), and on the
all-speakers slice precision went DOWN under aggregation (23.8% -> 15.5%),
not up.

**Reading this honestly:** the GOP z-score baseline's per-attempt "wrong"
calls are not landing on the true-positive windows with any consistency -
its false positives are scattered across many different (speaker, phone)
pairs rather than concentrated, so requiring 2-of-3 agreement mostly
filters out isolated true positives along with the false ones. Attempts are
evidently NOT close to independent in the direction the design change
hoped for, at least not for this scorer. Two things are also true that cut
against over-interpreting this as final: (1) the aggregated-ground-truth
population is tiny (n_pos=4 for the child slice) - this measurement itself
has a wide, mostly-unknown uncertainty band despite the CI reading as a
tight [0%, 0%] (that tightness is an artifact of tp=0 in every bootstrap
resample, not evidence of a precisely-known 0% rate); (2) this was measured
against the GOP z-score baseline specifically, chosen because it is the
best already-computed scorer - a properly trained Phase 3 classifier, whose
errors may correlate differently with the underlying acoustic evidence,
could behave differently. **The mechanism (`backend/aggregation.py`) is
implemented and ready, but this measurement does not currently support
shipping k-of-n aggregation as a precision fix.** Re-measure against the
Phase 3 classifier once it exists, on more data (subtrain+dev pooled) if
the child-slice window count is still too small, before deciding whether to
rely on it.

## Phase 0 baselines (child / age<=9), with raw counts and 95% CIs

See `eval/phase3_protocol.md` for the full success-criterion table this
feeds into. Full breakdown (all slices, all metrics, per-phoneme/per-position)
is in `eval/baselines.json`.
