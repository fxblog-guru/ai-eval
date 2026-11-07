---
name: comparing-baselines
description: Compare a run against a frozen baseline as a paired test over the same dataset, report differences with intervals rather than two percentages, and judge regression per failure mode because the total hides it. Use inside /eval-report and /eval-drift.
version: 1.0.0
---

# Comparing Baselines

> Read `.claude/EVAL-PROFILE.md` first — `§Quality gates` (regression margin).
> `.claude/EVAL-CONTRACTS.md` §10 defines the baseline; §8.3 the paired comparison.

## Action

Compare the current run to `.evals/baselines/BASE-<id>.json` and report what moved, with enough
information for someone to decide whether it matters.

## Step 1: Verify the comparison is legitimate

| Must match | Why |
|---|---|
| dataset id **and file hash** | different cases, different rate — nothing to compare |
| judge ids **and versions** | a changed judge measures its own drift and attributes it to the system |
| judge validation state | both sides must be `VALIDATED`, or the comparison is `NOT-EVALUABLE` |
| the metric definition | per-case vs per-attempt rates are not comparable |

A mismatch → STOP and name it. A drift report built on a shifted baseline is worse than none,
because it gets believed and acted on.

What is *expected* to differ is exactly one thing: the system (model, prompt, retrieval, or code).
Record what that one thing is.

## Step 2: Paired, not two independent samples

The same cases ran on both sides, so compare per case, not rate against rate:

| Case | Baseline | Current | |
|---|---|---|---|
| EV-TASK-014 | PASS | PASS | unchanged |
| EV-TASK-022 | PASS | **FAIL** | regression |
| EV-TASK-031 | FAIL | **PASS** | improvement |
| EV-TASK-044 | FAIL | FAIL | still failing |

The pairing is what gives the comparison power: the cases that did not change carry no information
about the difference, and removing them from the calculation sharpens it considerably.

For a paired binary comparison, McNemar's test over the discordant pairs (the two bold rows) is
the right check. With `b` regressions and `c` improvements:

```
McNemar (exact, small samples): p = 2 · P(X ≥ max(b,c)) for X ~ Binomial(b+c, 0.5)
```

When `b + c` is small — say under 10 — no test will find anything, and the honest report is "too
few cases changed to detect a difference", not a p-value dressed up as a conclusion.

## Step 3: Report the difference with its interval

```
GOOD:  -3.0pp [-7.1, +1.1]  (n=200 paired, 9 regressions, 3 improvements) — no detectable change
BAD:   baseline 84%, current 81%
```

Two percentages side by side invite a conclusion the data may not support. The second form gets
read as "it got worse by 3 points" when the correct reading is "we cannot tell these apart".

Use the interval on the **paired difference**, not the two separate rates' intervals. Overlapping
individual intervals do not mean no difference, and non-overlapping ones are not required for a
difference to be real — reasoning from the two intervals gets this wrong in both directions.

## Step 4: Per failure mode — where the real finding is

This is the step that earns the skill:

```markdown
## Per failure mode
| FM | Baseline | Current | Δ | Interval | Verdict |
|---|---|---|---|---|---|
| FM-001 | 0.95 [0.88, 0.98] | 0.96 [0.89, 0.99] | +0.01 | [-0.06, +0.08] | unchanged |
| FM-003 | 0.88 [0.79, 0.94] | 0.61 [0.50, 0.71] | **-0.27** | [-0.40, -0.13] | **REGRESSION** |
| FM-007 | 0.62 [0.51, 0.72] | 0.89 [0.80, 0.94] | +0.27 | [+0.14, +0.39] | improvement |
| overall | 0.84 | 0.83 | -0.01 | [-0.06, +0.04] | unchanged |
```

The overall row says nothing happened. FM-003 collapsed and FM-007 improved, and they cancelled.

**This is the most common shape of a real regression**, and it is precisely what an aggregate
metric is built to hide. A prompt change that fixes one behaviour by breaking another produces
exactly this table, and teams that watch only the total ship it.

Any FM breaching `§Quality gates → per-FM regression margin` is named at the top of the report,
before anything else.

## Step 5: List the flipped cases individually

```markdown
## Cases that changed
### Regressions (9)
| Case | FM | Baseline trace | Current trace | What changed |
|---|---|---|---|---|
| EV-TASK-022 | FM-003 | …/2026-09-01/traces/EV-TASK-022/1.json | …/2026-09-16/… | now cites a chunk that wasn't retrieved |
```

The pairs where old passed and new failed are the entire point of a drift check. Give both trace
paths so someone can open them side by side — that diff is what makes the finding actionable.

## Step 6: Freezing a new baseline

With `--freeze`, write `BASE-<id>.json` carrying the **full tuple**: system version, model id,
prompt version, dataset id and hash, judge ids and versions, results, per-FM results, and `n`/`k`.

A baseline missing any of those cannot be compared against later, which makes it worse than no
baseline — it looks usable and quietly is not.

Freeze deliberately, not on every green run. A baseline is a claim that this is the state worth
comparing to.

## Quality bar (self-check before reporting done)

- [ ] Dataset hash, judge ids and versions verified identical; the single intended change named.
- [ ] Comparison is paired, and the discordant counts are shown.
- [ ] Differences reported as deltas with intervals, never as two percentages.
- [ ] Per-FM table present, with the overall row at the bottom, not the top.
- [ ] FMs breaching the regression margin named at the very top of the report.
- [ ] Flipped cases listed individually, both trace paths given.
- [ ] Where `b + c` is small, the report says the comparison lacked power instead of implying a
      finding.
- [ ] Any frozen baseline carries the full tuple.
