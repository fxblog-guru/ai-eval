---
name: building-failure-taxonomy
description: Turn confirmed failure groups into permanent FM-NNN files and the INDEX register — the join key that connects traces, dataset cases, evaluators, and scorecards for the life of the system. Use after axial-coding-failures, as the last step of /eval-explore.
version: 1.0.0
---

# Building a Failure Taxonomy

> Read `.claude/EVAL-PROFILE.md` first — `§Severity`, `§Risk tier`.
> `.claude/EVAL-CONTRACTS.md` §6 defines the FM file; §1 defines id minting.

## Action

Write one `.evals/taxonomy/FM-NNN-<short-slug>.md` per confirmed failure group, and maintain
`.evals/taxonomy/INDEX.md` — the register where FM ids are minted, and the only place they are.

## Why the ids are permanent

`FM-003` appears in dataset rows, in evaluator definitions, in CTRF tags, in baselines, and in
every scorecard comparison for as long as the system exists. Renumbering breaks every historical
comparison silently — the numbers still line up, they just refer to different things now.

So: ids are minted sequentially in `INDEX.md`, never reused, never renumbered. A failure mode that
stops being relevant is `retired`, and its file stays.

## Inputs — resolve before writing (STOP conditions)

1. `.evals/traces/<TB-id>/notes.md` with `## Candidate failure modes` from `axial-coding-failures`.
2. Every candidate has **at least 3 trace refs**. Fewer → it stays a hypothesis. No exceptions:
   this rule is what keeps the taxonomy trustworthy.
3. `.evals/taxonomy/INDEX.md` — read it first, whether or not it exists, to find the next id.

## Step 1: Mint ids in INDEX.md, one at a time

Open `INDEX.md`, take the highest existing `FM-NNN`, and assign the next ones. Never assign an id
anywhere else; never fill a gap left by a retired FM.

Before minting, check for duplicates: a new candidate that restates an existing FM in different
words gets its trace refs appended to the existing file instead. The duplicate check is a real
step — after a few cycles, "invents a tracking number" and "fabricates a shipment reference" will
be proposed as separate FMs by different people.

## Step 2: Write the FM file

```markdown
# FM-007 — States a refund timeline that contradicts the policy for that payment method

## Statement
When the user asks how long a refund takes, the system gives a timeline from general knowledge
instead of the policy for the payment method on the order, understating it by 5–7 days.

## Evidence
- TB-2026-09-10-001 / trace_8f2a1c — card refund, said "3-5 business days", policy says 10
- TB-2026-09-10-001 / trace_b31e09 — PayPal refund, said "instant", policy says up to 5 days
- TB-2026-09-10-001 / trace_44c7d2 — bank transfer, said "2 days", policy says 10

## Frequency
9 of 100 coded traces. Weighted ≈ 2.4% of traffic (over-sampled stratum: refund intents).

## Severity
major — the user plans around the wrong date and contacts support when it slips. Not `blocking`:
no money moves incorrectly, and the refund itself is processed correctly.

## Detector
JDG-refund-timeline-v1 — needs the order's payment method and the policy table, so a code
assertion cannot decide it. A regex over "business days" was tried and produced false positives on
correct answers.

## Status
open
```

### On each heading

**`## Statement`** — one sentence from the user's side, specific enough that someone could write a
test case from it alone. The mechanism goes here only if it is part of the definition.

**`## Evidence`** — at least 3 real trace refs, each with one line of what happened in that trace.
Bare trace ids are not evidence anyone can act on six months later; the one-liners are what make
the file readable after the batch has scrolled out of memory.

**`## Frequency`** — raw count over coded traces, **and** the weighted estimate, with the stratum
named. Both numbers, always: the raw one tells you how confident the estimate is, the weighted one
tells you how much it matters.

**`## Severity`** — against `§Severity`, **with the reasoning**. The reasoning is what makes the
severity reviewable; a bare `major` is an assertion nobody can argue with or learn from.

**`## Detector`** — the evaluator that catches it, filled in by `/eval-judge`. Left as `TBD` here.
When the answer is a judge, record **why a code assertion did not work** — including the assertion
that was tried and what it got wrong. That note prevents the same dead end being rediscovered.

**`## Status`** — `open` · `mitigated` (a fix shipped; keep measuring, do not delete) · `retired`
(no longer applicable; the file stays as history).

## Step 3: Maintain INDEX.md

```markdown
# Failure mode register

Ids are minted here, sequentially, and never reused or renumbered.

| Id | Statement | Severity | Frequency | Detector | Status | First seen |
|---|---|---|---|---|---|---|
| FM-001 | Invents an order number when the lookup tool returns nothing | blocking | 4% | assert:order-id-exists | open | TB-2026-09-10-001 |
| FM-007 | States a refund timeline contradicting the payment method policy | major | 2.4% | JDG-refund-timeline-v1 | open | TB-2026-09-10-001 |

## Retired
| Id | Statement | Retired | Why |
|---|---|---|---|
```

## Step 4: Report the coverage gaps

Two gaps matter to the next phase and belong in the report, not buried in a file:

- **Policies with no FM** — either honored, or never exercised by this sample. Say which.
- **FMs whose likely fix is a prompt edit** — list them, and recommend fixing before anyone builds
  an evaluator. An evaluator built for a failure that a one-line prompt change removes is pure
  waste, and it will still be running, and passing, a year later.

## Quality bar (self-check before reporting done)

- [ ] Every FM has all six headings, filled.
- [ ] Every FM has ≥ 3 trace refs, each with a one-line description.
- [ ] Every frequency shows both raw and weighted, with the stratum named.
- [ ] Every severity carries its reasoning.
- [ ] No id was reused, renumbered, or minted outside `INDEX.md`.
- [ ] Duplicate check against existing FMs was run, and the result is stated.
- [ ] `INDEX.md` matches the files exactly — a register that drifts from its contents is worse than
      no register, because it is consulted instead of the files.
