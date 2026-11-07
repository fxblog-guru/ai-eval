---
name: auditing-eval-pipelines
description: Check an eval pipeline against EVAL-CONTRACTS and report every way it is producing numbers nobody should act on — unvalidated judges gating releases, leaked datasets, undersized samples, gates on point estimates, suites that have stopped discriminating. Use when /eval-audit runs, quarterly, or before trusting an inherited suite.
version: 1.0.0
---

# Auditing Eval Pipelines

> Read `.claude/EVAL-PROFILE.md` first — `§Judge thresholds`, `§Sample sizes`, `§Quality gates`,
> `§Risk tier`. `.claude/EVAL-CONTRACTS.md` §13 is the checklist.

## Action

Produce `.evals/reports/audits/YYYY-MM-DD-eval-audit.md` answering one question: **are these numbers
safe to act on?**

## Why eval pipelines need auditing

They rot quietly, and the rot looks like data. A judge model gets repointed by the provider under a
stable alias. A dataset gets a "quick fix" without a version bump. A suite that once discriminated
drifts to 98% pass and becomes a ritual. None of these turn anything red. Every one of them means
the dashboard is now decorative.

## Step 1: Blocking checks

Run every one, mechanically. These are the findings that mean a number currently being acted on
should not be.

| Check | How to check it | Finding |
|---|---|---|
| Gated suite uses an `UNVALIDATED` judge | for each `suites/*.yaml` with `gates`, resolve each `judge:` to its `validation.md` and read `## Verdict` | that gate's history is unattributable |
| Judge test split under-sized | count Pass and Fail in each `labels/test.jsonl` | the TPR being quoted does not mean what it appears to |
| **Dataset leakage** | grep each `input` from each `DS-*.jsonl` against the system prompt, its few-shot examples, and every judge `train.jsonl` | the system is tested on answers it was shown |
| Gated suite `n < 30` | count rows in the referenced dataset | the gate cannot distinguish a regression from noise |
| Gate on a point estimate | read each suite's gate keys — they must name a CI lower bound | the gate's outcome is partly luck |
| Open FM with no dataset case | every `open` FM in `INDEX.md` ∩ the `fm` arrays across datasets | that failure mode is reported as fine, permanently |
| **Frozen dataset was edited** | compare each dataset's current hash to the hash recorded in every run's `config.json` | every run referencing it is now incomparable, silently |

The leakage check is the one most often skipped and most often positive. Do it literally: extract
every case input, normalize whitespace, and search. Report every hit with both locations.

## Step 2: High checks

| Check | How | Why it matters |
|---|---|---|
| Judge same family as the system, in a gated suite | compare `§Models` rows | family bias inflates the score by an amount nobody has measured here |
| Suite pass rate > 0.95 across the last 3 runs | read run summaries | it has stopped discriminating; it now confirms rather than tests |
| Validation older than the current judge model | compare `validation.md` date and model id against `§Models` | the validation describes a model that is no longer running |
| Judge validated, but never re-validated after an FM definition changed | compare FM file mtime to validation date | the judge is calibrated to a different question |

The alias case deserves its own look: when `§Models → judge` is an alias rather than a pinned
version, flag it regardless of dates. The model can change with no repo change and no signal.

## Step 3: Medium checks

| Check | Why it matters |
|---|---|
| A judge decides something a code assertion could | paying for an approximate answer to an exact question, and carrying a labelling burden for it |
| `origin: trace` share below 30% | the dataset tests an imagined product |
| Model id or temperature unpinned in a suite | runs are not comparable to each other |
| No baseline for a gated suite | regressions can only be found against something |
| Mandatory layer for `§Risk tier` disabled | a risk the tier says must be measured is not being |

## Step 4: Look for the things a checklist misses

Mechanical checks find contract violations. Read for the rest:

- **Does the taxonomy still match reality?** If the newest FM is eight months old and the product
  shipped four features since, the taxonomy describes a system that no longer exists.
- **Do the gates still bind?** A gate at 0.70 on a suite that has run at 0.94 for a year is not a
  gate; it is a formality. Say so.
- **Is anyone reading the scorecards?** A pipeline nobody reads has the same effect as no pipeline
  and a higher cost. This is a legitimate audit finding.
- **Are failures being fixed or accepted?** The same FM failing for six months with `status: open`
  is a decision that was never made explicitly.

## Step 5: Report what is clean, too

An audit that lists only problems cannot be used to establish that anything is sound — and
establishing that is half of why people run it, especially before a release.

```markdown
## Checked and clean
- All 4 gated suites use VALIDATED judges (JDG-grounded-v2, JDG-tone-v1)
- Leakage check: 214 case inputs against 3 surfaces — 0 hits
- All datasets hash-match their referencing runs
- Every open FM has ≥ 3 cases
```

## Step 6: Every finding gets a remediation

```markdown
### BLOCKING — task-refunds gates on an UNVALIDATED judge
`suites/task-refunds.yaml` gates `task_success_ci_lower` using `judge:JDG-tone-v1`, whose
`judges/tone/validation.md` reads `## Verdict UNVALIDATED` (TNR 0.71, threshold 0.80).
Every release gated on this suite since 2026-07-02 was decided by an uncalibrated judge.

**Fix:** label 40 more Fail examples for tone, re-run `/eval-validate tone`. Until it passes,
remove the gate from the suite — the honest state is NOT-EVALUABLE, not a green gate.
```

A finding without a specific next action gets deferred. Name the command and the file.

## Quality bar (self-check before reporting done)

- [ ] Every EVAL-CONTRACTS §13 check ran and its result is recorded — including the ones that passed.
- [ ] The leakage check ran literally, across all three surfaces.
- [ ] Every finding names the file and the specific line or key.
- [ ] Findings are ordered by severity, blocking first, stated plainly rather than softened.
- [ ] Every finding has a concrete remediation with the command to run.
- [ ] `## Checked and clean` is present.
- [ ] The report opens with the one-line answer: **are these numbers safe to act on?**
