---
description: Answer "did the model upgrade, provider change, or prompt edit break anything" with a paired comparison against a frozen baseline
argument-hint: <slug> --against BASE-id [--change model|prompt|provider|retrieval]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Models`, `§Quality gates`, `§Budget`.
> EVAL-CONTRACTS §8.3 (paired comparison) and §10 (baselines).

Re-run a frozen dataset against a changed system and report the **difference with its interval**.

## Why this is the command that pays for the bundle

"We're moving from Sonnet to Opus — what breaks?" · "The provider bumped the model under the same
alias — are we still fine?" · "I tightened the system prompt — did any old case regress?"

These questions arrive weekly and are currently answered by trying three prompts by hand and
forming an impression. With a versioned dataset and a frozen baseline they are answered with
evidence in the time one suite takes to run.

## Arguments

- **`<slug>`** — the system or feature slug
- **`--against BASE-id`** — the baseline to compare to. Required; a drift check with no baseline
  is just a run.
- `--change` — what changed, recorded in the report: `model` · `prompt` · `provider` · `retrieval`

## Preconditions

- [ ] the baseline exists and records its full tuple: system version, model id, prompt version,
      dataset id, judge ids
- [ ] **the dataset version is identical** to the baseline's. A different dataset makes the
      comparison meaningless — that is a new baseline, not a drift check.
- [ ] **the judge versions are identical and still `VALIDATED`.** If the judge model itself
      changed, the judge validation is void (EVAL-CONTRACTS §5.4): re-validate first, or the comparison
      measures the judge's drift and calls it the system's.

Any mismatch → STOP and name it. A drift report built on a shifted baseline is worse than no
drift report, because it will be believed.

## Execution

Delegate to `eval-reporter`: run the suite, then `comparing-baselines` in paired mode.

**Report the difference with its interval, not two percentages side by side.** 84% and 81% printed
next to each other invite a conclusion the data may not support; `-3.0pp [-7.1, +1.1]` says what
is actually known — which here is "no detectable change".

Per failure mode, report the delta and its interval separately. The aggregate is the number most
likely to mislead: a model upgrade that improves fluency while losing one policy behaviour shows
up as a flat total and a collapsed FM.

## Done criteria (exit gate)

- The report states the configuration of **both** sides, in full.
- Every delta carries an interval; no bare point differences anywhere.
- Per-FM deltas are listed, and any FM breaching `§Quality gates → per-FM regression margin` is
  named at the top.
- Cases that changed outcome are listed individually with trace refs for both sides — the pairs
  where old passed and new failed are the whole point of the exercise.
- The verdict is `PASS`, `FAIL`, or `NOT-EVALUABLE` on the regression gate specifically.

Report back: the aggregate delta with its interval, the FMs that moved beyond the margin, the
count of cases that flipped in each direction, and a plain-language answer to the question that
was actually asked — including "no detectable difference at this sample size" when that is the
honest one.
