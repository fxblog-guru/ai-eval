---
description: Evaluate a multi-turn tool-using agent on trajectory and final state with a simulated user, reporting pass^k alongside pass^1
argument-hint: <slug> [--k 5] [--persona <name>]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Agent` (turn limit, tool allowlist, state oracle,
> persona file), `§Layers` (L3), `§Quality gates`, `§Models` (the user-simulator model).
> `.evals/system-card.md` `## Tools` and `## Hard policies` bound what may happen.
> EVAL-CONTRACTS §8.2 defines repeats and `pass^k`.

Evaluate the agent the way a user meets it: several turns, real tools, and one attempt.

## Judge state and tool calls, never wording

The agent's reply text is the least reliable thing to assert on — it varies every run and says
nothing about whether the work got done. In order:

1. **Final state** via `§Agent → State oracle` — was the order actually refunded, for the right
   amount? The only check a convincing sentence cannot satisfy.
2. **Tool calls** — right tool, right arguments, forbidden tools untouched. A correct outcome
   reached by calling a tool the agent may not call is a failure, and it is invisible to anyone
   checking only the outcome.
3. **Policy adherence** — each `## Hard policies` line asserted over the whole trajectory. A breach
   is a hard fail regardless of task success.
4. **Reply text** — last resort, only where the explanation is itself the deliverable.

## Arguments

- **`<slug>`** — the system or feature slug
- `--k 5` — repeats per case (default `§Sample sizes`). Declared before the run, never adjusted
  after seeing results.
- `--persona <name>` — run one persona from `.evals/suites/personas/`

## Preconditions (check before delegating)

- [ ] L3 enabled in `§Layers` and `§Agent` filled
- [ ] a **state oracle** exists — without it you can only judge wording, which is the thing this
      command exists not to do. STOP and report it as a blocking gap.
- [ ] the environment can be **reset between repeats**. Without it `pass^k` is not measurable;
      STOP rather than reporting `pass^1` as if it were reliability.
- [ ] a persona file exists per scenario family
- [ ] the simulator model differs from the agent model (`§Models`)

## Execution

Delegate to `agent-evaluator`: `simulating-users` → `evaluating-tool-calls` →
`evaluating-trajectories`.

The simulated user holds a goal and — the part that matters — **withholds what a real person would
not think to say**. A simulator that answers every clarifying question immediately tests a
conversation nobody has, and makes almost any agent look competent.

Run the **cooperative** persona first. Everything should pass there; if it does not, stop and fix
that before interpreting any other persona's numbers.

## `pass^k` is the headline

```
pass^1 = passing attempts / all attempts       flattering
pass^k = cases passing ALL k attempts / cases  what a user experiences
```

Report both with intervals **and the gap**. A user gets one attempt and cannot tell they drew the
unlucky sample: an agent at 85% `pass^1` and 45% `pass^5` is not an 85% agent.

## Done criteria (exit gate)

- Final state, tool-call sequence, and policy verdicts reported separately per case.
- `must_not` asserted, not only `expect` — an agent that refunds the right order and cancels a
  different one passes an expect-only check.
- `pass^1` and `pass^k` reported with intervals, and the gap stated in words.
- Every environment reset verified; failed resets are `ERROR`, never `FAIL`.
- Failure reasons broken out: `wrong-state`, `policy-breach`, `turn-limit`, `side-effect`.
- Every policy breach listed individually with its trajectory path.
- Divergence points recorded for flaky cases — the turn where repeats stopped agreeing.
- At least one full trajectory read per failure reason before reporting.

Report back: `pass^1` and `pass^k` with the gap, failure reasons by share, every policy breach,
tool-call violations, turn-limit rate, and reset failures.
