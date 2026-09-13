"""Tunables for hypothesis_scorer.py's decision procedure. Kept separate
from gop_config.py: gop_config.py's z-score thresholds calibrated GOP
against a per-phoneme baseline distribution, which is a different kind of
knob than these - there is no per-speaker or per-phoneme fitting here, just
a temperature for turning candidate scores into a posterior and a margin
below which the system refuses to answer.
"""

MAX_CANDIDATES = 40

# Candidate scores are length-normalized CTC log-likelihoods (see
# score_candidates); dividing by this before softmax controls how sharply
# the posterior concentrates on the best-scoring candidate. Not fit against
# data yet - starting point, to be tuned once eval/speechocean.py numbers
# exist for both splits.
SOFTMAX_TEMPERATURE = 1.0

# margin = score(best) - score(second_best), in the same length-normalized
# log-likelihood units as the candidate scores. Below this, the system
# returns "unclear" instead of forcing a correct/wrong verdict - refusing
# to answer on ambiguous audio rather than guessing. Placeholder until
# eval/run_hypothesis_eval.py's coverage-precision sweep on the dev split
# sets it from real numbers instead of by hand.
UNCERTAIN_MARGIN = 0.15

# Per-phoneme display confidence (Step 2d): max-pooled probability over the
# phoneme's aligned frame span, optionally smoothed by averaging the top-K
# frames instead of taking a single max. K=1 is a pure max.
CONFIDENCE_TOP_K_FRAMES = 3

# --- Bayesian prior over hypothesis origin (data/hypothesis_priors.json) ---
# final_score = norm_ctc_loglik + LAMBDA * log_prior. LAMBDA=0 recovers the
# pure-acoustic scoring this module started with, and is what's used here:
# eval/run_hypothesis_eval.py's sweep on 3000 real speechocean762 dev words
# (9142 phoneme observations) showed F1 dropping monotonically as LAMBDA
# increases (0.329 at 0.0, down to 0.161 at 2.0) - canonical's fixed
# log_prior of 0.0 against every other candidate's negative prior means
# turning LAMBDA up just biases the system toward "no error" regardless of
# acoustic evidence, trading recall for a small precision gain at a bad
# rate. Measured, not assumed - see that sweep's output before changing
# this back up.
LAMBDA = 0.0

# --- Per-user phonological-process adaptation ---
# A user's confirmed process count feeds a saturating (not linear) boost to
# that process's prior for that user's future attempts, on top of the base
# prior in hypothesis_priors.json: boost = min(MAX_PROCESS_BOOST,
# PROCESS_BOOST_RATE * log1p(count)). Saturating because a handful of
# confirmations should already shift the prior meaningfully, and an
# unbounded linear boost would eventually let a user's history override
# the acoustic evidence entirely, which is never what's wanted - the
# acoustic score still has to be in the running.
PROCESS_BOOST_RATE = 0.3
MAX_PROCESS_BOOST = 1.0

# A process only counts as "confirmed" for adaptation when the system's own
# verdict on it was definitive (word_status == "wrong", not "unclear") -
# see hypothesis_scorer.record_confirmed_process. There's no therapist
# manual-confirmation step in this app yet; this is the only signal
# available, and it's deliberately gated on non-ambiguous verdicts only.
