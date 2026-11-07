---
description: Run an eval suite with k repeats per case, record evidence, and write results plus a CTRF report for verdict
argument-hint: <suite> [--env dev|staging|prod] [--repeats k] [--dry-run]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Layers`, `§Quality gates`, `§Sample sizes`,
> `§Budget`, `§Environments`, `§Test management & reporting`. EVAL-CONTRACTS §8 defines suites and
> repeats; §11 defines the CTRF mapping.

Execute `.evals/suites/<suite>.yaml` and write `.evals/runs/<suite>/<slug>/<run-id>/`. Step 6.

## Arguments

- **`<suite>`** — the suite name, matching a file in `.evals/suites/`
- `--env` — which environment (default `staging` per `§Environments`)
- `--repeats k` — override the suite's repeat count. **Use with care**: a repeat count chosen
  after seeing results is not a measurement. Prefer editing the suite.
- `--dry-run` — validate the suite, resolve the dataset and evaluators, estimate cost and token
  spend, and stop without calling a model

## Preflight (check before the first model call)

- [ ] every judge the suite names has `## Verdict` `VALIDATED` — else the run proceeds, every
      number is marked `UNVALIDATED`, and the gate verdict will be `NOT-EVALUABLE`
- [ ] model id and temperature are pinned in the suite — an unpinned run cannot be compared to any
      baseline, so it is a lint error, not a warning
- [ ] dataset `n` ≥ 30 for a gated suite; below 100 warn and name the suite (`§Sample sizes`)
- [ ] `§Environments` authorizes this layer in this env — L4 and L5 refuse an unauthorized env,
      and `prod` is never authorized for adversarial or load runs by default
- [ ] the estimated spend fits `§Budget` — a run that will exceed it stops **before** starting

A run that hits the budget mid-flight stops with `ERROR` (exit 4) and a partial `summary.md`. When
the adapter reports no usage the budget cannot be enforced, and `summary.md` says so. It never
reports a gate verdict from a truncated run.

## Execution

Delegate to `eval-reporter` (`running-eval-suites`). Each case runs `k` times per the suite.

Outcomes are `PASS`, `FAIL`, `FLAKY`, `ERROR`, `SKIPPED`. **`FLAKY` is a first-class result**: a
case that passes on 3 of 5 repeats is telling you something true about the system, not producing
noise for the harness to filter. Never retry a failing case to obtain a pass.

Outputs:

```
runs/<suite>/<slug>/<run-id>/results.jsonl   one row per case per repeat
runs/<suite>/<slug>/<run-id>/summary.md      rates with 95% Wilson intervals, per FM
runs/<suite>/<slug>/<run-id>/traces/         full request/response evidence per case
runs/<suite>/<slug>/<run-id>/ctrf.json       uploaded to verdict (EVAL-CONTRACTS §11)
```

## Done criteria (exit gate)

- `results.jsonl` has exactly `n × k` rows, or the shortfall is explained by `ERROR` rows.
- Every rate in `summary.md` carries an interval and an `n`. A bare percentage is not reportable.
- `ctrf.json` exists and was uploaded to `verdict`, or the upload failure is reported with its
  reason — never silently skipped.
- Every `FAIL` has a trace ref a human can open.
- The run records the exact dataset id, judge ids, model id, temperature, and prompt version.

Report back: run id, `n` and `k`, pass/fail/flaky counts, per-FM rates with intervals, judge trust
state, spend against budget, and the verdict URL — then point at `/eval-report`.
