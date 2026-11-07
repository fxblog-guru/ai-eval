---
description: Calibrate a judge against held-out human labels — TPR, TNR, Cohen's kappa, bias correction — and decide VALIDATED or UNVALIDATED
argument-hint: <slug> [--version vN]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Judge thresholds`, `§Sample sizes`.
> EVAL-CONTRACTS §5.2, §5.3, §5.4, §5.5 define the split, the file, the gate, and the correction.

Produce `.evals/judges/<slug>/validation.md` — the proof that a judge's verdicts mean something.
Step 5 of the pipeline, and **the gate that separates this bundle from installing a framework and
running it**.

## Why this exists

If the judge is wrong, every number downstream is wrong — and it will look exactly like real data.
A pass rate of 84% from an uncalibrated judge and a pass rate of 84% from a calibrated one are
indistinguishable on a dashboard. This command is what tells them apart.

## Arguments

- **`<slug>`** — the judge slug
- `--version vN` — validate a specific judge version (default: the highest)

## Preconditions (check before delegating)

- [ ] `.evals/judges/JDG-<slug>-vN.md` exists
- [ ] `.evals/judges/<slug>/labels/dev.jsonl` and `test.jsonl` exist
- [ ] **each of dev and test has 30–50 Pass and 30–50 Fail** (`§Judge thresholds`). Fewer → STOP.
      A TPR computed from 8 examples is a number, not evidence, and it will be quoted as if it
      were evidence.
- [ ] labels carry real annotator ids. Rows labelled `ANN-AI` that no human confirmed are
      suggestions, not ground truth, and do not count toward the minimums.

## Execution

Delegate to `judge-engineer` (`validating-judges`):

1. Score on **dev**. Iterate the judge prompt against dev as much as you like.
2. When iteration stops, score **once** on the held-out **test** split. Opening test while still
   editing the prompt converts it into a second dev set and the validation becomes decoration.
3. Save the judge's test verdicts to `judges/<slug>/predictions/test.jsonl`, then run
   `python3 .evals/scripts/shared/calibrate.py JDG-<slug>-vN` and paste its confusion matrix, rates,
   disagreements and verdict. Never type a rate: lint E023 recomputes them.
4. **List every false positive and every false negative individually**, with its trace ref and one
   line on why the judge got it wrong.
5. Compute `theta_hat = (p_obs - FPR) / (TPR - FPR)` and record its inputs.
6. Keep the `## Verdict` the script computed: `VALIDATED` or `UNVALIDATED` against `§Judge thresholds`.

## Done criteria (exit gate)

- All seven headings from EVAL-CONTRACTS §5.3 are present.
- `## Disagreements` lists every FP and FN separately. This section is never summarized — the
  rates tell you whether the judge is good, the disagreements are the only thing that tells you
  how to make it better.
- `## Verdict` is the honest one. A judge that misses the threshold stays `UNVALIDATED` however
  inconvenient that is for the release.
- If `TPR - FPR < 0.50`, the verdict is `UNVALIDATED` regardless of the other numbers: below that,
  the bias correction amplifies noise faster than it removes bias.

## What UNVALIDATED means in practice

The judge may still run, in exploratory mode. Then:

- every number it produces carries the literal marker `UNVALIDATED`,
- it never enters a scorecard or a `BASE-<id>`,
- any suite that gates on it returns `NOT-EVALUABLE`, not `PASS` and not `FAIL`.

`NOT-EVALUABLE` is a real answer: it says the measurement could not be trusted. Converting it to
`PASS` to make a pipeline green is the failure this whole bundle exists to prevent.

## Re-validation triggers

Re-run this command when: the judge prompt changes · the judge model changes · the provider bumps
the model version under a stable alias · the few-shot examples change · the failure mode's
definition changes. Each of those is a `--bump` on the judge version first.

Report back: TPR, TNR, kappa, `theta_hat`, the verdict, the disagreement count with the two most
instructive ones quoted, and every suite currently gating on this judge.
