---
name: validating-judges
description: Score a judge against held-out human labels — confusion matrix, TPR/TNR, Cohen's kappa, every disagreement listed individually, and the bias-corrected estimator — then rule VALIDATED or UNVALIDATED. This is the gate that decides whether any number downstream may be acted on. Use when /eval-validate runs.
version: 1.0.0
---

# Validating Judges

> Read `.claude/EVAL-PROFILE.md` first — `§Judge thresholds`, `§Sample sizes`.
> `.claude/EVAL-CONTRACTS.md` §5.3 defines the file, §5.4 the gate, §5.5 the correction.

## Action

Produce `.evals/judges/<slug>/validation.md` and set `## Verdict` to `VALIDATED` or `UNVALIDATED`.

## Why this is the most important skill in the bundle

An uncalibrated judge produces numbers that are indistinguishable from real ones. 84% from a good
judge and 84% from a judge that agrees with humans 60% of the time look identical on a dashboard,
get quoted identically in a release review, and only one of them means anything.

This skill is the only thing that tells them apart.

## Inputs — resolve before starting (STOP conditions)

1. `.evals/judges/JDG-<slug>-vN.md`.
2. `labels/dev.jsonl` and `labels/test.jsonl` with **30–50 Pass and 30–50 Fail in each**
   (`§Judge thresholds`). Fewer → STOP, and say how many more of which class are needed.
3. Confirmation that the test split has not been read during prompt iteration. If it has, the
   honest repair is a fresh test set — not proceeding and hoping.

## Step 1: Iterate on dev, freely

Run the judge over `dev.jsonl`. Compare its verdicts to the human labels. Read the disagreements,
edit the prompt, run again. As many rounds as you like — that is what dev is for.

Stop iterating when dev numbers plateau, or when you notice yourself adding prompt clauses that
only address one specific dev example. That second signal means you have started fitting the dev
set, and further iteration will make test performance worse, not better.

## Step 2: Score test, once

Run the judge over `test.jsonl` and keep its verdicts, one line per case, in
`judges/<slug>/predictions/test.jsonl` as `{"case_id": "...", "judge": "pass"|"fail"}`. Every
labelled test case needs one. **This happens once per judge version.** If the numbers
disappoint, the response is to improve the judge and bump the version — not to re-score test until
it cooperates.

## Step 3: The confusion matrix

Compute it, do not type it:

```bash
python3 .evals/scripts/shared/calibrate.py JDG-<slug>-vN --root .evals
```

Paste its `## Confusion`, `## Rates`, `## Disagreements` and `## Verdict` into `validation.md`,
then fill each disagreement's *why*. Lint (E023) recomputes them from the same two files, so a
number edited by hand fails CI. The definitions below say what the script computes.

Fail is the **positive** class: the judge's job is catching failures.

|  | Human: fail | Human: pass |
|---|---|---|
| **Judge: fail** | TP | FP |
| **Judge: pass** | FN | TN |

```
TPR (recall)      = TP / (TP + FN)     how often a real failure is caught
TNR (specificity) = TN / (TN + FP)     how often a real pass is left alone
FPR               = FP / (FP + TN)     = 1 - TNR
FNR               = FN / (FN + TP)     = 1 - TPR
```

**Do not report accuracy.** With 90% passes, a judge that always says pass scores 90% accuracy and
catches nothing. That is the exact failure this metric hides, and it is common.

## Step 4: Cohen's kappa

```
kappa = (p_observed - p_expected) / (1 - p_expected)
```

where `p_expected` is the agreement expected from the two raters' marginal distributions. Kappa
corrects for agreement that happens by chance when one class dominates.

**Read kappa next to the confusion matrix, never alone.** A kappa of 0.62 with 40 FN and 2 FP is a
judge that misses failures; a kappa of 0.62 with 2 FN and 40 FP is a judge that cries wolf. Same
number, opposite problems, opposite fixes.

## Step 5: List every disagreement — the section that is actually useful

Every FP and every FN, individually:

```markdown
## Disagreements

### False negatives (judge said pass, human said fail) — 6
| Case | Output ref | Why the judge missed it |
|---|---|---|
| EV-TASK-031 | …#L88 | answer was long and confident; the wrong figure appeared in the third paragraph |
| EV-TASK-044 | …#L102 | figure was correct but for a different payment method; judge didn't check which |

### False positives (judge said fail, human said pass) — 3
| Case | Output ref | Why the judge over-flagged |
|---|---|---|
| EV-TASK-012 | …#L34 | answer gave "ten business days"; judge matched digits only |
```

The rates say whether the judge is good enough. **The disagreements are the only thing that says
how to make it better.** Never summarize this section: "mostly length-related" is not something
anyone can act on, and it discards the two examples that would have fixed the prompt.

Patterns worth naming explicitly when they appear: the judge missing long fluent wrong answers
(length bias), missing failures in a specific dimension value, or passing anything that includes a
hedge.

## Step 6: Bias correction

```
theta_hat = (p_observed - FPR) / (TPR - FPR)
```

The true pass rate, after subtracting the judge's measured error. Report `theta_hat` **alongside**
`p_observed`, never instead of it — a corrected figure with no raw figure beside it cannot be
sanity-checked.

When `TPR - FPR < 0.50`, the denominator is small enough that the correction amplifies noise faster
than it removes bias. The verdict is `UNVALIDATED` regardless of anything else.

## Step 7: The verdict

`VALIDATED` requires **all** of `§Judge thresholds`: TPR ≥ threshold, TNR ≥ threshold, kappa ≥
threshold, `TPR - FPR` ≥ 0.50, and both splits meeting their label minimums.

Miss any one → `UNVALIDATED`. This is the moment the whole bundle's discipline is tested, because
there is always a release waiting and the judge is always nearly good enough. An `UNVALIDATED`
judge that gets marked VALIDATED because the numbers were close produces a gate that reports PASS
for reasons unrelated to the system.

## Step 8: Record the re-validation triggers

At the end of the file:

```markdown
## Re-validate when
- the judge prompt changes (bump version first)
- the judge model changes, including a provider-side version bump under a stable alias
- the FM definition changes
- the system's output format changes materially
Last validated: 2026-09-16 against judge model <exact id>
```

The alias case is the one that catches teams out: nothing in the repo changes, and the judge is
quietly a different model.

## Quality bar (self-check before reporting done)

- [ ] All seven headings from EVAL-CONTRACTS §5.3.
- [ ] Test scored once, after iteration stopped.
- [ ] Confusion matrix as a 2×2 with raw counts, not percentages.
- [ ] TPR, TNR, FPR, FNR, kappa to 3 decimals, from `calibrate.py`. No accuracy anywhere.
- [ ] `predictions/test.jsonl` has a verdict for every labelled test case; lint shows no E023.
- [ ] Every FP and FN listed individually with a why.
- [ ] `theta_hat` reported with its inputs and next to `p_observed`.
- [ ] The verdict is the honest one.
- [ ] Re-validation triggers recorded with the judge model id and date.
- [ ] If `UNVALIDATED`: every suite currently gating on this judge is named in the report.
