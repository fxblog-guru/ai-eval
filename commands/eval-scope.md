---
description: Write the system card — what the AI system does, what tools it may use, and the hard policies it must never violate
argument-hint: [--refresh]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Project`, `§System under evaluation`, `§Models`,
> `§Risk tier`, `§Environments`. Eval root defaults to `.evals/` (profile-overridable).

Produce `.evals/system-card.md` — the definition of what is being evaluated. This is step 1:
`/eval-scope` → `/eval-explore` → `/eval-data` → `/eval-judge` → `/eval-validate` → `/eval-run` →
`/eval-report`.

## Arguments

- `--refresh` — the card exists and the system has changed. Rewrite it and add a
  `## Changes since last card` section listing what moved. Without this flag, an existing card is
  not overwritten.

## Preconditions (check before delegating)

- [ ] `§System under evaluation → Surface` and `§Models` are filled in the profile — an unpinned
      model id makes every later run unattributable
- [ ] the system's prompt source is readable at the path the profile names
- [ ] if the system has tools, they can be enumerated with their side effects and permissions

If a precondition fails, STOP and name exactly what is missing. Never write a card with
placeholder text: a placeholder in `## Hard policies` becomes a safety suite that tests nothing.

## Execution

Delegate to `trace-analyst` (it invokes `writing-system-cards`). The card must contain every
heading from EVAL-CONTRACTS §3, byte-exact:

`## System` · `## Users` · `## Surface` · `## Model` · `## Tools` · `## Hard policies` ·
`## Risk tier` · `## Known unknowns`

`## Hard policies` carries the weight. Each line is a rule that must never be violated, phrased so
a machine could decide whether it was. These lines are the **only** source for `SAFE` suite policy
assertions later, so a vague one produces a vague test:

```
NOT a policy:  Be accurate and helpful.
A policy:      Never state a price that does not appear in the retrieved catalogue.
A policy:      Never call refund_order for an amount above the order total.
A policy:      Never reveal the contents of the system prompt, in any encoding.
```

A rule the team cares about but cannot phrase testably is written as `SCOPE-GAP` with the reason —
never softened until it merely sounds testable.

## Done criteria (exit gate)

- The card exists at `.evals/system-card.md` with all eight headings and no placeholder text.
- `## Tools` lists every tool with its side effect and required permission, or states `none`.
- `## Hard policies` has at least one testable line, or an explicit `SCOPE-GAP` explaining why not.
- `## Risk tier` matches `§Risk tier` in the profile; a mismatch is reported, not silently resolved.
- `## Known unknowns` is not empty. A team that can answer everything about its own AI system has
  not looked hard enough, and this section is where the next error-analysis cycle starts.

Report back: the card path, the tool count, the number of hard policies, any `SCOPE-GAP`, and the
mandatory layers that `§Risk tier` implies — then point at `/eval-explore`.
