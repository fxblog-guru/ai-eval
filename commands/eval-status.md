---
description: Show where this system is in the evaluation pipeline, what is blocking the next step, and which judges can currently be trusted
argument-hint: [slug]
---

> Read `.claude/EVAL-PROFILE.md` first. Eval root defaults to `.evals/`.

Report the current state of the evaluation, read-only. Writes nothing.

## Execution

Delegate to `eval-orchestrator`. It starts from the derived index
(`python3 .evals/scripts/shared/status.py` prints it, EVAL-CONTRACTS §15) and reads the files below
only for what the index does not carry. If the index and a file disagree, the file is right; say so.

```
.evals/system-card.md              → scope done?
.evals/taxonomy/INDEX.md           → how many FMs, by severity and status
.evals/datasets/DS-*.jsonl         → which datasets, which version is current, case counts
.evals/judges/*/validation.md      → each judge: version, TPR/TNR, VALIDATED | UNVALIDATED
.evals/suites/*.yaml               → each suite: layer, dataset, repeats, gates, baseline
.evals/runs/*/*/                   → latest run per suite, its verdict, its date
.evals/baselines/BASE-*.json       → what is comparable, and to when
```

## Required output sections

```
## Pipeline state     which phase is complete, which is next, and the one command that advances it
## Judge trust        every judge with its validation state — UNVALIDATED ones listed first
## Coverage           open FMs with no dataset case; enabled layers with no suite
## Staleness          judges validated before the current judge model; baselines older than the
                      current dataset version; suites not run in over 30 days
## Blocking           what stops the next phase, one line each, each with its fix
```

## What to surface without being asked

- Any **gated suite naming an `UNVALIDATED` judge** — this is the state that silently produces
  numbers people act on, and it is invisible until someone looks.
- Any **open FM with no case**, because that failure mode is being reported as fine.
- Any **suite above 0.95 pass rate on its last three runs** — it has stopped discriminating.
- Any **mandatory layer** for `§Risk tier` that is disabled in `§Layers`.
- Any **dataset referenced by a run that no longer matches its file hash** — that means something
  edited a frozen dataset, and every run referencing it is now incomparable.

Report back: the phase, the single next command, and the blocking list. Keep it short — this
command is run to orient, not to read.
