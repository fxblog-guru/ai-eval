"""Statistics for LLM evaluation.

Every rate this bundle reports carries a 95% Wilson interval, and every gate compares the
interval's LOWER BOUND against its threshold -- never the point estimate. See EVAL-CONTRACTS.md
section 8.3.

No dependencies beyond the standard library, so the linter and the runner can both use it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

Z95 = 1.959963984540054


# --------------------------------------------------------------------------- intervals

@dataclass(frozen=True)
class Rate:
    """A rate with its interval. Never report `p` without `lo`/`hi`."""

    k: int          # successes
    n: int          # trials
    p: float        # point estimate
    lo: float       # 95% Wilson lower bound -- this is what gates compare
    hi: float       # 95% Wilson upper bound

    def __str__(self) -> str:
        return f"{self.p:.3f} [{self.lo:.3f}, {self.hi:.3f}] (n={self.n})"

    def gate(self, threshold: float) -> str:
        """PASS / FAIL / NOT-EVALUABLE against a threshold.

        An interval that SPANS the threshold means the run lacked the power to answer the
        question. That is NOT-EVALUABLE -- a real verdict, not a coin flip.
        """
        if self.n == 0:
            return "NOT-EVALUABLE"
        if self.lo >= threshold:
            return "PASS"
        if self.hi < threshold:
            return "FAIL"
        return "NOT-EVALUABLE"


def wilson(k: int, n: int, z: float = Z95) -> Rate:
    """Wilson score interval.

    Used instead of the normal approximation (p +/- z*sqrt(p(1-p)/n)) because eval rates sit
    near 0 and 1, exactly where the normal approximation breaks: at p=0.97, n=100 it returns an
    upper bound above 1, and at p=1.0 it returns a zero-width interval claiming certainty from
    40 observations.
    """
    if n <= 0:
        return Rate(k=k, n=0, p=0.0, lo=0.0, hi=1.0)
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return Rate(k=k, n=n, p=p, lo=max(0.0, centre - half), hi=min(1.0, centre + half))


def n_for(p_expected: float, margin: float, z: float = Z95) -> int:
    """Roughly the sample size needed for a half-width of `margin` at `p_expected`.

    Report this whenever a gate comes out NOT-EVALUABLE: it turns a frustrating verdict into a
    concrete next action ("you need ~200 cases; this suite has 60").
    """
    if not 0.0 < p_expected < 1.0 or margin <= 0:
        raise ValueError("p_expected must be in (0,1) and margin > 0")
    return int((z * z * p_expected * (1 - p_expected)) / (margin * margin)) + 1


# --------------------------------------------------------------------------- repeats

def pass_at_1(outcomes: Iterable[Sequence[bool]]) -> Rate:
    """Per-ATTEMPT rate: what fraction of all attempts passed.

    Flattering, and not what a user experiences. Report it alongside pass_hat_k, never alone.
    """
    flat = [r for case in outcomes for r in case]
    return wilson(sum(flat), len(flat))


def pass_hat_k(outcomes: Iterable[Sequence[bool]]) -> Rate:
    """pass^k -- fraction of cases that passed on EVERY one of k repeats.

    This is the number that predicts production: a user gets one attempt and cannot tell they
    drew the unlucky sample. An agent at 85% pass^1 and 45% pass^5 is not an 85% agent.
    """
    cases = list(outcomes)
    return wilson(sum(1 for c in cases if c and all(c)), len(cases))


def classify(repeats: Sequence[bool]) -> str:
    """Roll k repeats of one case up to PASS / FAIL / FLAKY.

    FLAKY is a first-class outcome, not noise to retry away: a case passing 3 of 5 times says a
    user has a 40% chance of a bad answer, which is the most actionable number in the run.
    """
    if not repeats:
        return "ERROR"
    if all(repeats):
        return "PASS"
    if not any(repeats):
        return "FAIL"
    return "FLAKY"


def flaky_rate(outcomes: Iterable[Sequence[bool]]) -> Rate:
    cases = list(outcomes)
    return wilson(sum(1 for c in cases if classify(c) == "FLAKY"), len(cases))


# --------------------------------------------------------------------------- judge bias

def bias_correct(p_observed: float, tpr: float, fpr: float) -> float | None:
    """theta_hat = (p_obs - FPR) / (TPR - FPR)  -- EVAL-CONTRACTS section 5.5.

    The true pass rate after subtracting the judge's own measured error. Report it ALONGSIDE
    p_observed, never instead of it: a corrected figure with no raw figure beside it cannot be
    sanity-checked.

    Returns None when TPR - FPR < 0.5: below that the correction amplifies noise faster than it
    removes bias, and the judge is not good enough to use (the verdict is UNVALIDATED).
    """
    denom = tpr - fpr
    if denom < 0.5:
        return None
    return min(1.0, max(0.0, (p_observed - fpr) / denom))


# --------------------------------------------------------------------------- judge validation

@dataclass(frozen=True)
class Confusion:
    """Fail is the POSITIVE class: the judge's job is catching failures."""

    tp: int  # judge fail, human fail
    fp: int  # judge fail, human pass
    tn: int  # judge pass, human pass
    fn: int  # judge pass, human fail

    @property
    def tpr(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def tnr(self) -> float:
        return self.tn / (self.tn + self.fp) if (self.tn + self.fp) else 0.0

    @property
    def fpr(self) -> float:
        return 1.0 - self.tnr

    @property
    def fnr(self) -> float:
        return 1.0 - self.tpr

    @property
    def kappa(self) -> float:
        """Cohen's kappa -- agreement corrected for what chance would produce.

        Read it next to the confusion matrix, never alone: kappa 0.62 with 40 FN and 2 FP is a
        judge that misses failures; kappa 0.62 with 2 FN and 40 FP is a judge that cries wolf.
        Same number, opposite problems, opposite fixes.
        """
        n = self.tp + self.fp + self.tn + self.fn
        if n == 0:
            return 0.0
        po = (self.tp + self.tn) / n
        p_fail = ((self.tp + self.fn) / n) * ((self.tp + self.fp) / n)
        p_pass = ((self.tn + self.fp) / n) * ((self.tn + self.fn) / n)
        pe = p_fail + p_pass
        return (po - pe) / (1 - pe) if pe != 1 else 0.0

    # Deliberately no `accuracy` property. With 90% passes, a judge that always says pass scores
    # 90% accuracy and catches nothing -- which is the exact failure the metric hides.


def confusion_from_pairs(pairs: Iterable[tuple[str, str]]) -> Confusion:
    """Count (human, judge) label pairs into a Confusion. Labels are "pass" or "fail".

    The one place validation numbers are produced, so a validation.md can be recomputed from its
    inputs instead of trusted as typed (EVAL-CONTRACTS 5.3).
    """
    tp = fp = tn = fn = 0
    for human, judge in pairs:
        if judge == "fail":
            tp, fp = (tp + 1, fp) if human == "fail" else (tp, fp + 1)
        else:
            tn, fn = (tn + 1, fn) if human == "pass" else (tn, fn + 1)
    return Confusion(tp=tp, fp=fp, tn=tn, fn=fn)

def judge_verdict(c: Confusion, *, min_tpr: float, min_tnr: float,
                  min_kappa: float, min_separation: float = 0.5,
                  min_pass: int = 30, min_fail: int = 30) -> tuple[str, list[str]]:
    """VALIDATED / UNVALIDATED against EVAL-PROFILE section Judge thresholds.

    Returns the verdict and the list of reasons it failed. Miss any one threshold and the answer
    is UNVALIDATED -- however close the numbers are, and however inconvenient for the release.
    """
    reasons: list[str] = []
    n_fail = c.tp + c.fn
    n_pass = c.tn + c.fp
    if n_fail < min_fail:
        reasons.append(f"test split has {n_fail} Fail examples, need {min_fail}")
    if n_pass < min_pass:
        reasons.append(f"test split has {n_pass} Pass examples, need {min_pass}")
    if c.tpr < min_tpr:
        reasons.append(f"TPR {c.tpr:.3f} < {min_tpr}")
    if c.tnr < min_tnr:
        reasons.append(f"TNR {c.tnr:.3f} < {min_tnr}")
    if c.kappa < min_kappa:
        reasons.append(f"kappa {c.kappa:.3f} < {min_kappa}")
    if (c.tpr - c.fpr) < min_separation:
        reasons.append(
            f"TPR-FPR {c.tpr - c.fpr:.3f} < {min_separation}: bias correction would amplify noise"
        )
    return ("VALIDATED" if not reasons else "UNVALIDATED"), reasons


# --------------------------------------------------------------------------- paired comparison

@dataclass(frozen=True)
class Paired:
    """A paired comparison over the same dataset. `b` regressed, `c` improved."""

    b: int          # baseline PASS -> current FAIL
    c: int          # baseline FAIL -> current PASS
    unchanged: int
    delta: float    # current rate - baseline rate
    lo: float
    hi: float
    p_value: float

    @property
    def discordant(self) -> int:
        return self.b + self.c

    @property
    def has_power(self) -> bool:
        """Under ~10 discordant pairs, no test will find anything.

        The honest report is then "too few cases changed to detect a difference", not a p-value
        dressed up as a conclusion.
        """
        return self.discordant >= 10

    def __str__(self) -> str:
        return (f"{self.delta * 100:+.1f}pp [{self.lo * 100:+.1f}, {self.hi * 100:+.1f}] "
                f"({self.b} regressions, {self.c} improvements)")


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value over the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    m = max(b, c)
    tail = sum(math.comb(n, i) for i in range(m, n + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def paired(baseline: dict[str, bool], current: dict[str, bool], z: float = Z95) -> Paired:
    """Compare two runs case by case over the SAME dataset.

    The pairing is what gives the comparison power: cases that did not change carry no
    information about the difference, and removing them sharpens the estimate considerably.

    Reporting two separate percentages instead invites a conclusion the data may not support --
    "84% then 81%" reads as a 3-point drop when the honest reading is often "cannot tell apart".
    """
    shared = set(baseline) & set(current)
    b = sum(1 for k in shared if baseline[k] and not current[k])
    c = sum(1 for k in shared if not baseline[k] and current[k])
    unchanged = len(shared) - b - c
    n = len(shared)

    delta = (c - b) / n if n else 0.0
    # Interval on the paired difference of proportions.
    if n:
        var = (b + c - (c - b) ** 2 / n) / (n * n)
        half = z * math.sqrt(max(var, 0.0))
    else:
        half = 1.0
    return Paired(b=b, c=c, unchanged=unchanged, delta=delta,
                  lo=max(-1.0, delta - half), hi=min(1.0, delta + half),
                  p_value=mcnemar_exact(b, c))
