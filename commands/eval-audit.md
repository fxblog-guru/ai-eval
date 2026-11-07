---
description: Audit an eval pipeline against EVAL-CONTRACTS — find the ways it is producing numbers nobody should act on
argument-hint: [path] [--severity blocking|high|medium]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Judge thresholds`, `§Sample sizes`, `§Quality gates`.
> EVAL-CONTRACTS §13 is the checklist this command runs.

Produce `.evals/reports/audits/YYYY-MM-DD-eval-audit.md`.

## When to run it

- Quarterly, on your own suites — eval pipelines rot quietly, and the rot looks like data.
- Before trusting an eval suite you inherited from another team.
- Immediately after any judge model changes, anywhere.
- When a suite has been green for a suspiciously long time.

## Arguments

- **`[path]`** — the eval root to audit (default: `.evals/` per the profile). Point it at another
  project's folder to audit an inherited suite.
- `--severity` — report only findings at or above this level

## Execution

Delegate to `eval-reporter` (`auditing-eval-pipelines`). It checks the EVAL-CONTRACTS §13 table
mechanically and reports each violation with the file that causes it.

### Blocking

| Check | Why it matters |
|---|---|
| A gated suite uses an `UNVALIDATED` judge | every number that gate produced is unattributable |
| A judge's test split has < 30 Pass or < 30 Fail | the TPR quoted from it does not mean what it appears to mean |
| A dataset case input appears in the system prompt or a judge's `train.jsonl` | the system is being tested on its own examples |
| A gated suite has `n < 30` | the gate cannot distinguish a regression from sampling noise |
| A gate compares a point estimate instead of a CI lower bound | the gate's outcome is partly decided by luck |
| An open FM has no dataset case | the suite reports that failure mode as fine, permanently |

### High

| Check | Why it matters |
|---|---|
| Judge is the same model family as the system, in a gated suite | family bias inflates the score |
| Suite pass rate > 0.95 across the last 3 runs | the suite has stopped discriminating; it is now a ritual |
| A judge validation is older than the current judge model version | the validation describes a model that is no longer running |

### Medium

| Check | Why it matters |
|---|---|
| A judge is used where a code assertion would decide it | paying for an approximate answer to an exact question |
| `origin: trace` share below 30% | the dataset tests an imagined product |
| Model id or temperature unpinned in a suite | runs cannot be compared to each other |

## Done criteria (exit gate)

- Every finding names the file and the line or key that causes it.
- Findings are ordered by severity, blocking first, and the blocking ones are stated plainly rather
  than softened.
- Every finding has a concrete remediation: the command to run or the file to change.
- The report states what was checked and found clean, not only what failed — an audit that lists
  only problems cannot be used to establish that anything is sound.
- A pipeline with zero blocking findings is reported as such. That is a meaningful result and
  should be recorded, with the date, as evidence for the next release.

Report back: counts by severity, every blocking finding with its remediation, and a one-line
answer to the question people actually run this for: **are these numbers safe to act on?**
