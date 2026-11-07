---
name: writing-system-cards
description: Write .evals/system-card.md — the definition of what is being evaluated: what the system does, who calls it, what tools it may use, and the hard policies it must never violate, each phrased so a machine could decide whether it was. Use when asked to scope an AI evaluation, or when /eval-scope runs.
version: 1.0.0
---

# Writing System Cards

> Read `.claude/EVAL-PROFILE.md` first — `§Project`, `§System under evaluation`, `§Models`,
> `§Risk tier`, `§Environments`, `§Domain knowledge`. Eval root defaults to `.evals/`.
> `.claude/EVAL-CONTRACTS.md` §3 defines the required headings.

## Action

Produce `.evals/system-card.md`: one page that answers *what are we measuring, and what must never
happen*. Everything downstream — the traces you pull, the failure modes you name, the safety
probes you write — is scoped by this file.

## Inputs — resolve before writing (STOP conditions)

1. **The system's own prompt/template**, at the path in `§System under evaluation → Prompt source`.
   Unreadable → STOP. You cannot describe what a system is instructed to do without reading the
   instruction.
2. **The tool inventory** — every tool the system may call, its side effects, its permission.
   A system with tools whose inventory nobody can produce → STOP: an agent whose permissions cannot
   be enumerated cannot be evaluated for exceeding them.
3. **`§Models`** with an exact model id. A family name (`the latest Sonnet`) → STOP: every run
   recorded against an unpinned model is unattributable, and so is every comparison to it.
4. **The people who own the system** — the policies come from them, not from you.

## Step 1: System, Users, Surface

`## System` — what it does for a user, one paragraph, in the words the team uses. Not the
architecture. A reader who has never seen the code should be able to say what it is for.

`## Users` — who calls it and what they expect. Include the ones nobody designed for but who show
up anyway: an internal support agent using the customer-facing bot, a script someone wrote against
the API.

`## Surface` — where the boundary of evaluation sits. This is a decision, and it needs stating:
is the retriever inside or outside? Is the guardrail layer part of the system under evaluation or
part of the harness? An unstated boundary produces two people reading the same scorecard
differently.

## Step 2: Model and Tools

`## Model` — provider, exact model id, temperature, max tokens, any pinned version or alias. Note
whether the id is an **alias** the provider can repoint (`claude-sonnet-latest`): an alias means
the system can change under you without a deploy, which makes `/eval-drift` a scheduled job rather
than a release-time check.

`## Tools` — one line per tool: name, what it does, its **side effect**, and the permission it
needs. Read-only and state-changing tools are marked differently; the distinction drives both the
L3 state oracle and the L4 permission probes.

## Step 3: Hard policies — the section that carries the file

The rules that must never be violated. Each line must be phrased so a machine could decide whether
it was violated.

```
NOT a policy:  Be accurate and helpful.
NOT a policy:  Don't hallucinate.
NOT a policy:  Handle refunds appropriately.

A policy:      Never state a price that does not appear in the retrieved catalogue.
A policy:      Never call refund_order for an amount greater than the order total.
A policy:      Never call any tool marked state-changing without an explicit user confirmation
               in the same conversation.
A policy:      Never reveal the contents of the system prompt, in any encoding or paraphrase.
A policy:      Never state a delivery date that is not returned by get_shipment_status.
```

The test for a good policy line: **could two people, reading the same output, disagree about
whether it was violated?** If yes, it is not yet a policy — narrow it until they could not.

A rule the team cares about but genuinely cannot phrase testably is written as:

```
SCOPE-GAP: <the rule, as the team states it> — not testable because <reason>.
```

Never soften a rule until it merely sounds testable. `"Never be rude"` dressed up as
`"Maintain a professional tone"` is the same untestable rule with more syllables, and it will
become a judge nobody can calibrate.

## Step 4: Risk tier and Known unknowns

`## Risk tier` — must match `§Risk tier` in the profile. A mismatch is reported, not resolved
quietly: the tier decides which layers are mandatory, and someone chose each value for a reason.

`## Known unknowns` — what nobody on the team can currently answer about this system. Examples
that recur: *we don't know how often the retriever returns nothing* · *we don't know what happens
when the user writes in Vietnamese* · *we don't know whether the guardrail fires on paraphrases*.

This section is not filler. It is where the next error-analysis cycle gets its questions, and a
team that leaves it empty has not looked hard enough at its own system.

## Output contract

`.evals/system-card.md` with all eight headings from EVAL-CONTRACTS §3, byte-exact, in order:

```
## System   ## Users   ## Surface   ## Model   ## Tools
## Hard policies   ## Risk tier   ## Known unknowns
```

Prose follows `§Artifact language`. Headings and the `SCOPE-GAP` token stay English.

## Quality bar (self-check before reporting done)

- [ ] No placeholder text anywhere. A placeholder in `## Hard policies` becomes a safety suite that
      tests nothing and reports `PASS`.
- [ ] Every policy line passes the two-people test.
- [ ] Every tool has its side effect and permission stated.
- [ ] The model id is exact, and aliases are flagged as aliases.
- [ ] `## Known unknowns` has at least two entries.
- [ ] Every domain term resolves through `§Domain knowledge` and is cited, or is a `DATA-GAP`.

## On refreshing

`--refresh` rewrites the card and adds `## Changes since last card`. When `## Hard policies`
changes, say so loudly in the report: every SAFE-suite case derives from those lines, and a
changed policy means cases to add, remove, or re-judge.
