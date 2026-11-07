---
name: splitting-label-sets
description: Split human labels into train/dev/test once, with the class balance judge validation requires, and keep the test split closed — the discipline that makes a TPR number evidence rather than decoration. Use when /eval-judge --labels runs, before any judge is validated.
version: 1.0.0
---

# Splitting Label Sets

> Read `.claude/EVAL-PROFILE.md` first — `§Judge thresholds`, `§Sample sizes`.
> `.claude/EVAL-CONTRACTS.md` §5.2 defines the split and the minimums.

## Action

Split human labels into `.evals/judges/<slug>/labels/{train,dev,test}.jsonl` — once, with a
recorded seed, never re-shuffled.

## Why three splits and not two

| Split | Share | What it is for | Who may look at it |
|---|---|---|---|
| `train` | 10–20% | few-shot examples pasted into the judge prompt | the prompt author, freely |
| `dev` | 40–45% | iterate the judge prompt against this, as often as you like | the prompt author, freely |
| `test` | 40–45% | score the finished judge, once | **nobody, while the prompt is being edited** |

Two splits is the common shortcut and it destroys the number people care about. If you tune the
prompt against the same set you report on, you have measured how well the prompt was tuned to
those examples, and that number does not transfer.

The test split is only evidence because it was closed. Opening it mid-iteration converts it into a
second dev set, silently — nothing errors, the number just stops meaning what it says.

## Inputs — resolve before splitting (STOP conditions)

1. Human labels: `{case_id, output_ref, label: "pass"|"fail", annotator, ts, note}`.
2. **Enough of each class.** `§Judge thresholds` requires 30–50 Pass and 30–50 Fail in **each** of
   dev and test. With train, that is roughly 100–200 labels per failure mode.
   Not enough → STOP and say how many more are needed, of which class. A TPR computed from eight
   Fail examples is a number that will be quoted as if it were evidence.
3. **Real annotator ids.** Rows with `ANN-AI` that no human confirmed are suggestions. They do not
   count toward the minimums and they do not go in `test` at all.

## Step 1: Audit the labels before splitting

- **Class balance.** If 95% are Pass, the judge can score 95% "accuracy" by always saying pass —
  which is why accuracy is not a metric here and TPR/TNR are. Label more failures; they are the
  scarce resource, and they are the ones the judge exists to catch.
- **Annotator agreement.** Where two people labelled the same item, compute agreement. Below ~80%,
  stop: the humans do not agree on the criterion, so no judge can be calibrated to it. Fix the
  rubric first — that disagreement is a finding about the failure-mode definition, and a valuable
  one.
- **Duplicates.** The same output labelled twice by the same person, or near-identical outputs, are
  collapsed. Duplicates across splits are leakage of the worst kind.

## Step 2: Stratify the split

Do not split randomly over the whole pool. Stratify so each split is representative on the axes
that matter:

- **label** (pass/fail) — the hard requirement
- **failure mode**, where labels span several
- **dimension values**, where the underlying cases carry them
- **output length** — long outputs are where judges are most often wrong, so every split needs them

Random splitting of 120 labels routinely produces a test split with 18 Fail examples and all of
the long outputs in dev.

## Step 3: Write the split, with the seed

```json
{"case_id": "EV-TASK-014", "output_ref": "runs/task/refunds/2026-09-10-1420/results.jsonl#L42",
 "label": "fail", "annotator": "ANN-LN", "ts": "2026-09-11T09:12:00Z",
 "note": "quoted 3-5 days, policy for card is 10", "fm": "FM-007", "split_seed": 20260911}
```

Record in `.evals/judges/<slug>/labels/README.md`:

```markdown
## Split
seed: 20260911 · stratified on: label, fm, output_length_bucket
| Split | Rows | Pass | Fail |
|---|---|---|---|
| train | 24 | 12 | 12 |
| dev   | 58 | 30 | 28 |
| test  | 58 | 29 | 29 |

## Annotators
ANN-LN 94 · ANN-TH 46 · overlap 20 · agreement 0.90 (kappa 0.80)

## Rules
- test is opened only by /eval-validate, once per judge version
- few-shot examples come from train only
- adding labels appends to the same split by the same stratification; it never re-shuffles
```

## Step 4: Adding labels later

More labels arrive. **Do not re-shuffle.** Re-splitting moves items that were in test into train,
which quietly invalidates every previous validation and makes past and present numbers
incomparable.

Append new labels to the splits using the same stratification and seed. Record the date and the
new counts. If the class balance in test drifts outside 30–50, append preferentially to restore it.

## Step 5: Keep test closed, mechanically

- `test.jsonl` is read only by `validating-judges`.
- A judge prompt containing any example whose `case_id` is in `dev` or `test` is a blocking lint
  finding.
- When someone has looked at test while iterating — it happens — the honest repair is to label a
  fresh test set. Not to pretend. A compromised test split produces a validated-looking judge with
  no validation behind it, which is strictly worse than an `UNVALIDATED` one.

## Quality bar (self-check before reporting done)

- [ ] dev and test each have 30–50 Pass and 30–50 Fail.
- [ ] The split is stratified on label, FM, and output length, and the strata are recorded.
- [ ] The seed is recorded and the split is reproducible.
- [ ] Inter-annotator agreement computed on the overlap and reported.
- [ ] No `ANN-AI`-only row in `test`.
- [ ] No duplicate or near-duplicate output across splits.
- [ ] `README.md` states the rules, so the next person does not re-shuffle it.
