---
description: Turn a run into a scorecard — gates against confidence-interval lower bounds, per-failure-mode regression against a baseline, and an honest verdict
argument-hint: <slug> [--run <run-id>] [--baseline BASE-id] [--freeze]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Quality gates`, `§Sample sizes`,
> `§Test management & reporting`. EVAL-CONTRACTS §10 defines the scorecard and the baseline.

Produce `.evals/reports/<slug>/YYYY-MM-DD-scorecard.md`. Step 7 — the last step of the core loop.

## Arguments

- **`<slug>`** — the system or feature slug
- `--run <run-id>` — which run to report on (default: the most recent for this slug)
- `--baseline BASE-id` — compare against this baseline (default: the one the suite names)
- `--freeze` — after reporting, write this run as a new `.evals/baselines/BASE-<id>.json`

## Preconditions

- [ ] the run exists with `results.jsonl` and `summary.md`
- [ ] the baseline exists, or `--baseline none` is given explicitly — a first run with no baseline
      reports absolute numbers only and says so, rather than inventing a comparison

## Execution

Delegate to `eval-reporter`: `computing-confidence-intervals` → `comparing-baselines`.

**Every rate gets a 95% Wilson interval. Every gate compares the lower bound.** Gating on a point
estimate is the most common way a green pipeline ships a regression: with a true pass rate near
90%, a sample of 100 moves several points from sampling noise alone, and a threshold sitting in
that band is decided by luck.

**Regression is judged per failure mode, not on the total.** A total that holds steady while
FM-003 collapses and FM-007 improves is the most common shape of a real regression, and the
totals row is exactly where it hides.

## Required headings (EVAL-CONTRACTS §10)

`## Verdict` · `## Configuration` · `## Results` · `## Per failure mode` · `## Flaky` ·
`## Judge trust` · `## Evidence` · `## What changed`

## The verdict

One of three values, and only these:

| Verdict | Means |
|---|---|
| `PASS` | every gate's CI lower bound cleared its threshold, and every judge that decided anything is `VALIDATED` |
| `FAIL` | a gate did not clear. Name the single gate that decided it. |
| `NOT-EVALUABLE` | the measurement itself could not be trusted: an `UNVALIDATED` judge gated something, `n` was below 30, the run was truncated by budget, or the model id was unpinned |

`NOT-EVALUABLE` is never converted to `PASS` to turn a pipeline green, and never to `FAIL` to be
safe — both are false statements about a different thing. It means: go fix the measurement, then
ask again.

## Done criteria (exit gate)

- `## Verdict` names the single gate or condition that decided it.
- Every number in `## Results` carries an interval and an `n`.
- `## Per failure mode` shows the delta against the baseline per FM, with each delta's interval.
- `## Flaky` lists every case that passed on some repeats and failed on others — these are not
  filtered out, they are the system's unpredictability made visible.
- `## Judge trust` lists every judge, its version, its TPR/TNR, and `VALIDATED` / `UNVALIDATED`.
- `## What changed` is prose a person who was not in the run can read.
- With `--freeze`: the new `BASE-<id>.json` records the full tuple (system version, model, prompt
  version, dataset id, judge ids) — a baseline missing any of those cannot be compared against
  later, which makes it worse than no baseline.

## Handing off

Findings with a lifecycle go to `agentic-fx/stlc` (EVAL-CONTRACTS §12): a product defect to
`/qa-defect` citing the FM id and the run path; a release decision to `/qa-signoff` with this
scorecard as evidence. This bundle never opens, triages, or closes anything itself.

Report back: the verdict and the gate that decided it, the per-FM deltas that moved most, the
flaky count, judge trust state, and the scorecard path.
