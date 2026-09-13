"""k-of-n evidence aggregation over repeated attempts at the same target
phoneme, added as a direct response to the precision ceiling: at this app's
real base rate, even a well-calibrated single-attempt operating point
cannot reach a clinically usable precision (see RESULTS.md's derivation) -
three out of four flagged errors would be false alarms at FRR=5%/recall=50%.
A practice level already gives 3-4 words sharing one target phoneme; asking
for k of n agreeing attempts before naming a specific error pattern trades
a little recall for a large precision gain, PROVIDED attempts are close
enough to independent for the trade to work as arithmetic predicts - see
eval/measure_k_of_n.py for the real (not assumed-independent) numbers this
was measured against before being trusted.
"""
from dataclasses import dataclass


@dataclass
class AggregatedVerdict:
    status: str  # "correct" | "wrong" | "unclear"
    n_wrong: int
    n_correct: int
    n_unclear: int
    n_total: int


def aggregate_k_of_n(statuses: list[str], k: int) -> AggregatedVerdict:
    """statuses: single-attempt verdicts ("correct" | "wrong" | "unclear")
    for one speaker's last n attempts at one target phoneme, oldest first.
    "wrong" iff at least k of them are "wrong". "unclear" attempts count
    toward neither total needed to reach a verdict (see the note below) -
    otherwise a run of ambiguous recordings would silently count as
    evidence of correctness, which is exactly the "abstain reads as pass"
    failure mode Phase 0's harness was built to catch in the first place.

    If there are not enough non-unclear attempts left for "wrong" to still
    be reachable even if every remaining attempt were wrong, and not enough
    for "correct" to be unreachable either, the aggregate itself is
    "unclear" - more attempts are needed before this phoneme can be
    scored at all, matching Phase 0's "abstain, don't guess" principle at
    the aggregate level too.
    """
    n_wrong = statuses.count("wrong")
    n_correct = statuses.count("correct")
    n_unclear = statuses.count("unclear")
    n = len(statuses)

    if n_wrong >= k:
        return AggregatedVerdict("wrong", n_wrong, n_correct, n_unclear, n)
    # Even if every still-open (unclear) slot flipped to "wrong", could k
    # still be reached? If not, this is settled "correct" already.
    if n_wrong + n_unclear < k:
        return AggregatedVerdict("correct", n_wrong, n_correct, n_unclear, n)
    return AggregatedVerdict("unclear", n_wrong, n_correct, n_unclear, n)


def binomial_at_least_k(n: int, k: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p) - the independence-assumed
    aggregate rate used only as a comparison point against the real,
    measured (correlated-attempts) rate in eval/measure_k_of_n.py. Never
    used as the reported number on its own."""
    from math import comb
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))
