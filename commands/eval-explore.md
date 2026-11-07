---
description: Error analysis — read real traces, open-code what goes wrong, axial-code into a failure taxonomy
argument-hint: <trace-source> [--count N] [--batch TB-id]
---

> Read `.claude/EVAL-PROFILE.md` first — `§System under evaluation → Trace source`,
> `§Sample sizes`, `§Severity`, `§Domain knowledge`. Eval root defaults to `.evals/`.

Read real traces of the system and turn them into `.evals/taxonomy/` — the failure modes this
system actually has. Step 2 of the pipeline.

**This is the phase teams skip, and skipping it is why their evals measure nothing.** A taxonomy
derived from traces tells you what to build evaluators for. A metric list copied from a framework
tells you what that framework could measure.

## Arguments

- **`<trace-source>`** — a path to a JSONL export, a log query, or `--from-profile` to use
  `§System under evaluation → Trace source`
- `--count N` — how many traces to pull (default: `§Sample sizes → traces to code`, 100)
- `--batch TB-id` — continue coding an existing batch instead of pulling a new one

## Preconditions (check before delegating)

- [ ] `.evals/system-card.md` exists — without it there is no statement of what "correct" means
- [ ] the trace source resolves and returns traces conforming to EVAL-CONTRACTS §4
- [ ] **the traces are real.** Not synthetic examples, not the demo from the sprint review

If the system has no traces yet, STOP and say so plainly. The honest options are: ship it behind a
flag to a small group and collect traces, or accept that the taxonomy will be hypothetical and
record that in every artifact built on it. Do not quietly proceed with invented failures.

## Execution

Delegate to `trace-analyst`, which runs in order: `sampling-traces` → `open-coding-traces` →
`axial-coding-failures` → `building-failure-taxonomy`.

The human codes the **first 30 traces themselves** (`§Sample sizes`). This is not ceremony: the
categories that exist in this data are only visible to someone who read it. After 30, the agent
may propose codes for the rest, and the human accepts or rejects each one.

**Open coding before axial coding, always.** Write free-text notes about what is wrong with each
trace. Do not reach for a category while reading — categories chosen in advance are the categories
you will find, whether or not they are there.

## Done criteria (exit gate)

- `.evals/traces/<TB-id>/raw.jsonl` and `notes.md` exist, with one note block per coded trace.
- Every `FM-NNN` file has all six headings from EVAL-CONTRACTS §6.
- **Every FM has at least 3 trace refs under `## Evidence`.** Under 3 observations it is a
  hypothesis and stays in `notes.md` until it recurs — this is what keeps the taxonomy from filling
  with things somebody once worried about.
- `taxonomy/INDEX.md` lists every FM with severity, frequency, and status; ids were minted there,
  sequentially, and none was reused.
- Saturation is reported with its evidence: traces coded, new FMs in the last 20, and whether
  saturation was reached or the budget ran out. Those are different situations and the next phase
  needs to know which one happened.

Report back: batch id, traces coded, FM count by severity, the three most frequent failure modes
with their rates, saturation evidence, and the FMs that look fixable by editing one prompt line —
fix those before anyone builds an evaluator for them.
