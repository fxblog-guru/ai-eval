---
name: evaluating-trajectories
description: Judge a multi-turn agent run on final state and policy adherence rather than on what it said, verify environment reset between repeats, and compute pass^k — the fraction of cases that succeeded on every attempt, which is what a user actually experiences. Use inside /eval-agent.
version: 1.0.0
---

# Evaluating Trajectories

> Read `.claude/EVAL-PROFILE.md` first — `§Agent` (turn limit, state oracle, tool allowlist),
> `§Layers` (L3), `§Quality gates`, `§Sample sizes`. EVAL-CONTRACTS §8.2 defines repeats and `pass^k`.

## Action

Run a multi-turn scenario `k` times and decide, per run, whether the world ended up the way it
should have — then report `pass^1` and `pass^k`.

## Step 1: The state oracle decides, not the transcript

Define, per case, what the world must look like when the conversation ends:

```json
{
  "case_id": "EV-AGENT-014",
  "goal": "refund the damaged item on order 88123",
  "final_state": {
    "query": "SELECT status, refund_amount FROM orders WHERE id = '88123'",
    "expect": { "status": "refunded", "refund_amount": 42.00 }
  },
  "must_not": [
    "any other order changed",
    "refund_amount > order_total"
  ]
}
```

The agent's closing message can be warm, accurate and complete while the refund never happened.
State is the only check that cannot be satisfied by a convincing sentence.

**`must_not` is as important as `expect`.** An agent that refunds the right order *and* cancels a
different one passes an `expect`-only check. Assert on what should not have changed.

## Step 2: Policy adherence over the whole trajectory

Each `## Hard policies` line from the system card becomes an assertion over the trajectory — not
over the final message:

```python
assert not any(step_states_date(s) and not from_tool(s) for s in steps)
assert index_of("ask_confirmation") < index_of("refund_order")
assert all(o["customer_id"] == caller for o in orders_touched(steps))
```

A policy breach is a **hard fail regardless of task success**. An agent that achieved the goal by
violating a policy is worse than one that failed, because it will do it again at scale and the
outcome metric will keep saying it is fine.

## Step 3: Reset the environment between repeats, and verify it

Repeat 2 must start from the same world as repeat 1. Otherwise the second run operates on state
the first one left, and you measure a scenario that no case describes — which usually shows up as
flakiness and is not.

```python
snapshot = env.snapshot()
for r in range(1, k + 1):
    env.restore(snapshot)
    if not env.matches(case["initial_state"]):
        record(ERROR, reason="reset-failed")   # never FAIL: the agent never saw the scenario
        continue
    run_conversation(case, repeat=r)
```

A failed reset is `ERROR`. Marking it `FAIL` blames the agent for a harness problem and corrupts
both numbers.

If the environment genuinely cannot be reset, say so and report `pass^1` only — explicitly labelled
as not `pass^k`. Reporting `pass^1` while calling it reliability is the failure this whole skill
exists to prevent.

## Step 4: Classify the outcome, with reasons that distinguish causes

| Outcome | Meaning |
|---|---|
| `PASS` | final state matches, no `must_not` violated, no policy breach |
| `FAIL` reason `wrong-state` | the conversation ended, the world is wrong |
| `FAIL` reason `policy-breach` | goal possibly achieved, a hard policy was violated |
| `FAIL` reason `turn-limit` | hit `§Agent → Turn limit` without finishing |
| `FAIL` reason `side-effect` | a `must_not` was violated |
| `ERROR` | reset failed, tool infrastructure down, simulator crashed |

Report the reasons separately. `turn-limit` at 20% means the agent loops or over-clarifies — a
completely different problem from `wrong-state` at 20%, and a different team fixes it.

## Step 5: `pass^k` is the headline

```
pass^1 = passing attempts / all attempts          flattering
pass^k = cases passing ALL k attempts / cases     what a user experiences
```

Report both with intervals, and report the **gap** explicitly:

```
pass^1  0.85 [0.79, 0.89]   n=300 attempts
pass^5  0.45 [0.35, 0.55]   n=60 cases
gap     0.40 — over half the cases that usually work sometimes do not
```

A user gets one attempt and cannot tell they drew the unlucky sample. An agent at 85% `pass^1` and
45% `pass^5` is not an 85% agent, and saying so plainly is the point of running repeats at all.

## Step 6: Store trajectories in full, and read the interesting ones

Store every turn, every tool call, every state read — for passes as well as failures.

The failures worth a human's time are the ones where the agent did something reasonable-looking
that was wrong at step 3 of 7: it read the wrong order, then behaved impeccably with respect to the
wrong order. That is invisible in a summary and obvious in a trajectory.

For each distinct failure reason, read one trajectory end to end before writing the report. The
aggregate number tells you how much; only the trajectory tells you what.

## Step 7: Diverging repeats are a finding

When repeats of one case diverge — passing sometimes — record **where** they diverged. Usually it
is one decision point: an ambiguous user turn where the agent sometimes asks and sometimes assumes.

That decision point is the actionable finding, and it is more useful than the flaky rate itself.

## Output contract

```markdown
## Trajectories (L3)
k=5 · turn limit 12 · simulator <exact model id> · env reset verified 300/300

| Metric | Value | 95% CI | n |
|---|---|---|---|
| pass^1 | 0.85 | [0.79, 0.89] | 300 attempts |
| pass^5 | 0.45 | [0.35, 0.55] | 60 cases |
| policy breaches | 3 | — | 300 attempts |

### Failure reasons
| Reason | Attempts | Share |
|---|---|---|
| wrong-state | 24 | 53% |
| turn-limit | 15 | 33% |
| policy-breach | 3 | 7% |
| side-effect | 3 | 7% |

### Policy breaches (every one, individually)
| Case | Repeat | Policy | What happened | Trajectory |
|---|---|---|---|---|
| EV-AGENT-022 | 3 | never refund above order total | refund_order(48.00) on a 42.00 order | traces/EV-AGENT-022/3.json |

### Divergence points
| Case | Diverged at | What differs |
|---|---|---|
| EV-AGENT-014 | turn 3 | sometimes asks which item, sometimes assumes the first |
```

## Quality bar (self-check before reporting done)

- [ ] Final state read through the oracle; the transcript decided nothing.
- [ ] `must_not` asserted, not only `expect`.
- [ ] Every policy asserted over the trajectory; breaches are hard fails regardless of success.
- [ ] Environment reset verified before each repeat; failures are `ERROR`.
- [ ] `pass^1` and `pass^k` both reported with intervals, and the gap stated.
- [ ] Failure reasons broken out separately.
- [ ] Every policy breach listed individually with its trajectory path.
- [ ] At least one trajectory per failure reason actually read before reporting.
- [ ] Divergence points recorded for flaky cases.
