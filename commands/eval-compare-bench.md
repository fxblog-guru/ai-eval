---
description: Compare two bundle-bench files (two bundle versions, or lessons vs no-lessons) and rule BETTER, WORSE, NO-SIGNIFICANT-DIFFERENCE or NOT-EVALUABLE
argument-hint: <a.json> <b.json> [--out report.md]
---

> EVAL-CONTRACTS §16 defines the file and the verdicts.

Answer one question with numbers: did the agent bundle get better at its job between `a` and `b`?

## Why this exists

A bundle that "learns" must show fewer repeated mistakes and more first-time passes on the same
tasks. Two percentages side by side cannot show that; a paired test over the same tasks can.

## Execution

1. Check both files exist and share `task_id`s. Fewer than 20 paired tasks → report
   `NOT-EVALUABLE` and how many more tasks are needed. Never fill a missing `first_pass`.
2. Run `python3 .evals/scripts/compare_bench.py <a> <b> --out .evals/reports/bench/<a>-vs-<b>.md`.
3. Report the verdict line, both first-pass intervals, and the token and duration deltas.

## Done criteria

- The verdict is the script's. `WORSE` exits 1 and is never reworded as "roughly the same".
- `NOT-EVALUABLE` names what is missing: paired tasks, or which metric was not reported.
