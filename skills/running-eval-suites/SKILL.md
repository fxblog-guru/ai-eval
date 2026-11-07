---
name: running-eval-suites
description: Execute a suite with k repeats per case, enforce the preflight checks that stop an untrustworthy run before it spends money, treat FLAKY as a real outcome, and write results with full evidence. Use when /eval-run runs.
version: 1.0.0
---

# Running Eval Suites

> Read `.claude/EVAL-PROFILE.md` first — `§Layers`, `§Sample sizes`, `§Budget`,
> `§Environments`, `§Quality gates`. `.claude/EVAL-CONTRACTS.md` §8 defines suites and repeats.

## Action

Execute `.evals/suites/<suite>.yaml` and write `.evals/runs/<suite>/<slug>/<run-id>/`.

## Step 1: Preflight — before the first model call

Every one of these is cheaper to check now than to discover in a scorecard:

| Check | On failure |
|---|---|
| every judge named has `## Verdict VALIDATED` | run proceeds, all numbers marked `UNVALIDATED`, gate verdict will be `NOT-EVALUABLE` |
| model id and temperature pinned in the suite | **STOP** — an unpinned run cannot be compared to anything, including itself |
| dataset file hash matches what the suite declares | **STOP** — a frozen dataset was edited; every prior run is now incomparable |
| dataset `n` ≥ 30 for a gated suite | **STOP** — below this no gate can distinguish signal from noise |
| dataset `n` ≥ 100 | warn, name the suite |
| `§Environments` authorizes this layer in this env | **STOP** for L4/L5 in an unauthorized env |
| estimated spend fits `§Budget` | **STOP before starting** — not halfway |
| fixtures exist for every case that declares one | **STOP** — otherwise cases silently test a state they didn't intend |

Estimate spend from `n × k × (avg tokens) × rate` plus judge calls. Show it to the user on
`--dry-run` and before any run above the nightly budget.

## Step 2: Execute

For each case, `k` times:

1. Load the case's fixture, if any. **Reset any mutable state between repeats** — for suites with
   side effects, repeat 2 starting from repeat 1's leftovers is measuring something else.
2. Call the provider adapter (`§System under evaluation → Adapter`) with the case input.
3. Capture `{output, steps, meta}` plus latency and token counts.
4. Run every assertion in `expect.assert`.
5. Run every judge in `expect.judge`.
6. Write one `results.jsonl` row.

Run cases concurrently where the system allows it, but keep repeats of the same case sequential
when fixtures mutate. Respect provider rate limits: a run that half-fails on 429s produces a
results file full of `ERROR` rows that look like system failures.

## Step 3: Outcomes

| Outcome | When |
|---|---|
| `PASS` | every assertion and judge passed, on this repeat |
| `FAIL` | at least one failed — record **which**, by id |
| `ERROR` | the harness failed: provider error, timeout, malformed judge output, missing fixture |
| `SKIPPED` | the case declares a dimension the env cannot provide |

Roll up across repeats per case:

| Case outcome | When |
|---|---|
| `PASS` | all k repeats passed |
| `FAIL` | all k repeats failed |
| `FLAKY` | some passed, some failed |

**`FLAKY` is a first-class result, not noise to eliminate.** A case that passes 3 of 5 times is
telling you that a user has a 40% chance of a bad answer. That is the most actionable number in
the run.

**Never retry a case to obtain a pass.** Repeats are declared in the suite, before results exist.
A repeat count adjusted after seeing the outcome is not a measurement.

`ERROR` never becomes `FAIL`. A provider timeout is not a quality signal, and burying it in the
fail count corrupts both numbers. Report the error rate separately; above ~5% the run is not
reportable and should be re-run when the infrastructure is healthy.

## Step 4: Evidence

```
runs/<suite>/<slug>/<run-id>/
├─ results.jsonl      one row per case per repeat
├─ summary.md         rates with Wilson intervals, per FM and overall
├─ ctrf.json          for verdict (publishing-to-verdict)
├─ config.json        dataset id + hash, judge ids + versions, model id, temperature,
│                     prompt version, suite hash, env, start/end, spend
└─ traces/<case_id>/<repeat>.json    full request, steps, response, assertion and judge details
```

`config.json` is what makes the run reproducible and comparable. A run missing any of its fields
cannot be used as a baseline and should say so rather than being quietly frozen as one.

Store full traces for every case, not only failures. The passing case you need to inspect is the
one that starts failing next month.

## Step 5: Budget enforcement

Track spend as you go. On breach: stop, write a partial `summary.md` marked `TRUNCATED`, and
report `ERROR`.

A truncated run **never produces a gate verdict**. Partial results on an unrepresentative subset
are worse than no results: the cases that ran are usually the first ones in the file, which are
usually one stratum.

## Quality bar (self-check before reporting done)

- [ ] Every preflight check ran, and its result is in `config.json`.
- [ ] `results.jsonl` has `n × k` rows, or the shortfall is explained by `ERROR` rows.
- [ ] Fixture state was reset between repeats where the suite mutates anything.
- [ ] `FLAKY` cases are identified and listed, not filtered.
- [ ] `ERROR` is reported separately from `FAIL`, with the error rate.
- [ ] Every `FAIL` names the assertion or judge id that decided it.
- [ ] Full traces stored for every case and repeat.
- [ ] Spend recorded against budget.
- [ ] No case was retried to get a better result.
