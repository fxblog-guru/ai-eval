---
name: computing-confidence-intervals
description: Turn raw run counts into rates that can be acted on — Wilson score intervals, pass^k for agents, judge-bias correction, and the sample size actually needed to detect a given change. Gates compare the interval's lower bound, never the point estimate. Use inside /eval-report.
version: 1.0.0
---

# Computing Confidence Intervals

> Read `.claude/EVAL-PROFILE.md` first — `§Quality gates`, `§Sample sizes`.
> `.claude/EVAL-CONTRACTS.md` §8.3 requires an interval on every reported rate.

## Action

Convert `results.jsonl` into the rates that go into `summary.md` and the scorecard, each with a
95% Wilson interval, and decide every gate on the interval's lower bound.

## Why a point estimate is not reportable here

With a true pass rate near 90% and 100 cases, the observed rate moves several points run to run
from sampling alone — before adding judge variance and model non-determinism. A threshold sitting
inside that band is decided by luck, and the pipeline will be green or red for reasons unrelated
to the system.

Two illustrative shapes:

| n | passes | rate | 95% Wilson interval | Gate at 0.80 |
|---|---|---|---|---|
| 30 | 25 | 0.833 | [0.663, 0.926] | **NOT-EVALUABLE** — the interval spans the threshold and most of the useful range |
| 100 | 60 | 0.600 | [0.503, 0.690] | FAIL — the whole interval sits below 0.80 |
| 100 | 84 | 0.840 | [0.756, 0.899] | **NOT-EVALUABLE** — the interval still spans the threshold |
| 400 | 336 | 0.840 | [0.801, 0.872] | PASS — lower bound 0.801 ≥ 0.80 |

Identical rate, three different answers. The difference is how much you know, and the interval is
what carries that.

## Step 1: Wilson, not normal approximation

```python
def wilson(k, n, z=1.96):
    """95% Wilson score interval. Correct near 0 and 1, where evals live."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z*z/n
    centre = (p + z*z/(2*n)) / d
    half = z * ((p*(1-p)/n + z*z/(4*n*n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))
```

The textbook `p ± 1.96·√(p(1-p)/n)` interval fails exactly where eval rates sit: at p = 0.97 with
n = 100 it produces an upper bound above 1, and at p = 1.0 it produces a zero-width interval
claiming certainty from 40 observations.

## Step 2: Choose the denominator deliberately

With `k` repeats per case there are two defensible rates, and they answer different questions:

- **Per-attempt rate** — `n = cases × k`. "What fraction of attempts succeed?"
- **Per-case rate** — `n = cases`, a case counted as passed only if all k repeats passed. "What
  fraction of tasks are reliably handled?"

**Report both.** The per-attempt rate is larger and more flattering; the per-case rate is what a
user experiences, because a user gets one attempt and cannot tell they drew the unlucky sample.

Repeats of the same case are not independent observations, so per-attempt intervals computed with
`n = cases × k` are optimistically narrow. Note this where it matters, and prefer the per-case
interval for gating.

## Step 3: `pass^k` for agent suites

```
pass^k = (cases where all k repeats passed) / (total cases)
```

Report `pass^1` (the per-attempt rate) and `pass^k` side by side, each with its interval. The gap
between them is the system's reliability, and it is usually far wider than teams expect: an agent
at 85% `pass^1` and 45% `pass^5` is not an 85% agent.

## Step 4: Apply the judge's bias correction

For any rate produced by a judge, apply EVAL-CONTRACTS §5.5:

```
theta_hat = (p_observed - FPR) / (TPR - FPR)
```

with TPR and FPR from that judge's `validation.md` test split. Report both numbers:

```
task success: 0.840 observed [0.756, 0.899] · 0.871 bias-corrected (JDG-grounded-v2: TPR 0.88, FPR 0.07)
```

The correction has its own uncertainty, since TPR and FPR are themselves estimates from ~100
labels. Do not present `theta_hat` as more precise than `p_observed` — it is a better centre with a
wider interval, not a sharper number.

## Step 5: Gate on the lower bound

```
gate passes  ⟺  ci_lower ≥ threshold
```

Not the point estimate, not the corrected estimate. The lower bound is the statement "we are 95%
confident the true rate is at least this", which is the only statement a release gate should be
built on.

When the interval **spans** the threshold, the honest verdict is `NOT-EVALUABLE`, not a coin flip:
the run does not have the power to answer the question that was asked of it. Report the sample
size that would.

## Step 6: Report the power you actually had

```python
def n_for(p_expected, margin, z=1.96):
    """Roughly the n needed for a half-width of `margin` at p_expected."""
    return int((z*z * p_expected * (1 - p_expected)) / (margin*margin)) + 1
```

`n_for(0.85, 0.05)` ≈ 196. `n_for(0.85, 0.02)` ≈ 1225.

Put this in the summary when a gate came out `NOT-EVALUABLE`: "to resolve a 5-point difference at
this pass rate you need ~200 cases; this suite has 60." That turns a frustrating verdict into a
concrete next action.

## Step 7: Per-failure-mode rates

Compute each FM's rate and interval separately. FM subsets are small, so their intervals are wide —
show them anyway. A wide interval that everyone can see is information; a point estimate that hides
the width is a claim nobody can evaluate.

An FM with under 10 cases is reported with its interval and the explicit note that it cannot
support a gate.

## Quality bar (self-check before reporting done)

- [ ] Every rate has a Wilson interval and an `n`. No bare percentages anywhere.
- [ ] Both per-attempt and per-case rates reported where `k > 1`.
- [ ] `pass^k` reported for agent suites, with `pass^1`.
- [ ] Judge-derived rates carry `theta_hat` with the TPR/FPR used.
- [ ] Gates compared against the lower bound, and the comparison is shown.
- [ ] Intervals spanning a threshold produce `NOT-EVALUABLE`, with the required `n` stated.
- [ ] Per-FM rates computed with their own intervals; thin FMs flagged as non-gating.
