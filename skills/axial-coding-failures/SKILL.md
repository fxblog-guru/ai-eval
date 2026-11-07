---
name: axial-coding-failures
description: Group open-coding notes into failure modes at a level of granularity a team can act on — the step that turns a pile of observations into a taxonomy. Use after open-coding-traces, before building-failure-taxonomy.
version: 1.0.0
---

# Axial Coding Failures

> Read `.claude/EVAL-PROFILE.md` first — `§Severity`, `§Domain knowledge`.
> Requires `.evals/traces/<TB-id>/notes.md` from `open-coding-traces`.

## Action

Group the free-text notes into candidate failure modes. This is the step that carries the whole
error-analysis phase: the notes are raw observation, and the grouping is what makes them
actionable.

## The granularity problem

Everything here turns on one judgement, made repeatedly:

| Too fine | Right | Too coarse |
|---|---|---|
| "quoted 3-5 days for a card refund" · "quoted 2 days for a bank refund" · "quoted next-day for a PayPal refund" (3 FMs) | **"States a refund timeline that contradicts the policy for that payment method"** (1 FM, 3 instances) | "Gives wrong information" (1 FM, 40 instances, no evaluator can be written for it) |

Two tests, applied to every candidate group:

1. **Could one evaluator decide it?** If catching the group would need five different checks, the
   group is too coarse. If one check catches three of your groups, they are one group.
2. **Would one fix address it?** If the team would fix the whole group with one change — a prompt
   line, a retrieval parameter, a guardrail — it is one failure mode. If half the group needs a
   different fix, split it.

When the two tests disagree, follow the fix test. A taxonomy exists so someone can act on it.

## Step 1: Sort by what went wrong, not by where

Lay out every `verdict: problem` note and group by the **nature** of the error.

Resist grouping by pipeline stage ("retrieval problems", "generation problems"). Stage is an
attribute of a failure mode, not its identity, and stage-based groups always end up too coarse:
"retrieval problems" contains both "the corpus doesn't have this document" and "the query rewriter
dropped the product name", which have nothing in common and no shared fix.

## Step 2: Name each group as a statement, from the user's side

The name is a sentence describing what goes wrong, as a user would experience it:

```
Weak:    Hallucination
Weak:    Retrieval issues
Weak:    Prompt not followed

Strong:  Invents an order number when the lookup tool returns nothing
Strong:  Answers from general knowledge when the retrieved context does not cover the question,
         without saying so
Strong:  Applies the refund policy of the default region to a customer in another region
Strong:  Drops the second question when the user asks two things in one message
```

A strong name already implies its evaluator. That is the signal that the grouping is at the right
level.

## Step 3: Count, and be honest about the tail

For each group: how many of the coded traces show it. Apply the stratum weights from
`sampling-traces` — the sample was built failure-rich on purpose, so raw counts overstate
production rates. Report both: `12/100 in this sample ≈ 3% of production traffic, weighted`.

Groups with **fewer than 3 instances stay in the notes** as hypotheses. They are not promoted to
failure modes. A taxonomy that admits singletons fills with things one person saw once and becomes
a list nobody trusts.

Keep them visible under `## Hypotheses` with their trace refs — the next batch either confirms them
or it does not.

## Step 4: Separate what is already fixable

Some groups will be obviously fixable by editing one prompt line or one retrieval parameter. Mark
them:

```
### <group name>
**Likely fix:** the system prompt does not mention <X>  →  try that before building an evaluator.
```

**Say this out loud in the report.** Building an evaluator, labelling 200 examples, and calibrating
a judge for a failure that disappears when someone adds one sentence to a prompt is the most
expensive mistake available in this phase. Fix the obvious things, re-pull traces, and see what
survives. What survives is what deserves an evaluator.

## Step 5: Check the groups against the hard policies

Cross-reference `.evals/system-card.md` `## Hard policies`. Two findings come out of this:

- A policy with no corresponding failure group — either the system genuinely honors it, or the
  sample never exercised it. These are different, and the difference goes in the report. An
  untested policy that looks honored is how safety gaps ship.
- A failure group that violates a policy nobody wrote down — that is a missing policy line, and
  the system card needs updating.

## Output contract

Append to `.evals/traces/<TB-id>/notes.md`:

```
## Candidate failure modes
### <statement>
- **Instances:** <n>/<coded>  (weighted ≈ <p>% of traffic)
- **Traces:** <trace_id>, <trace_id>, <trace_id>, …
- **Severity:** blocking | major | minor
- **Where it goes wrong:** <the step, where the traces agree>
- **Likely fix:** <if there is an obvious one>
- **Policy:** <the ## Hard policies line it violates, if any>

## Hypotheses
<groups with fewer than 3 instances, with their trace refs>

## Policy coverage
<each hard policy: violated in n traces | never exercised by this sample | honored throughout>
```

## Quality bar (self-check before reporting done)

- [ ] Every group passes both granularity tests.
- [ ] Every group name is a statement from the user's side, not a category label.
- [ ] Every group has ≥ 3 instances; the rest are under `## Hypotheses`.
- [ ] Counts are weighted, and both raw and weighted numbers are shown.
- [ ] Groups with obvious fixes are flagged, and the report says so before anything else.
- [ ] Every hard policy appears in `## Policy coverage` with one of the three states.
- [ ] No note was left ungrouped. A leftover pile means the grouping is incomplete, not that those
      traces were uninteresting.
