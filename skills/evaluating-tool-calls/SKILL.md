---
name: evaluating-tool-calls
description: Check tool selection, arguments, sequencing and the handling of tool failures with code assertions — including the calls that should NOT have happened, which outcome-only checking cannot see. Use inside /eval-agent, and for single-turn tool use in L2.
version: 1.0.0
---

# Evaluating Tool Calls

> Read `.claude/EVAL-PROFILE.md` first — `§Agent` (tool allowlist), `§Layers` (L2, L3).
> `.evals/system-card.md` `## Tools` is the inventory; `## Hard policies` bound what may be called.
> EVAL-CONTRACTS §5.1: this is assertion territory almost entirely.

## Action

Assert on what the system called, with what, in what order, and what it did when a call failed.

## Five independent checks

| Check | Question | Missed by |
|---|---|---|
| **Selection** | right tool for this intent? | outcome-only checking, when a wrong tool happens to work |
| **Arguments** | right values, right types, right units? | schema validation, when types are right and values are wrong |
| **Sequencing** | in an order that makes sense? | per-call checking |
| **Restraint** | did it avoid calling what it shouldn't? | **everything except an explicit forbidden-set check** |
| **Failure handling** | what did it do when a call returned an error or nothing? | happy-path datasets |

### Restraint is the one that gets skipped

A correct outcome reached by calling a tool the agent was not permitted to call is a **failure**.
So is calling a state-changing tool twice because the first call's response was slow. Neither is
visible to anyone checking only the final answer.

```python
called = [s["name"] for s in steps if s["type"] == "tool"]
assert set(called) & forbidden == set()                        # never touched
assert called.count("refund_order") <= 1                       # not duplicated
assert not (confirm_required and "refund_order" in called      # no unconfirmed side effect
            and "ask_confirmation" not in called)
```

## Step 1: Selection — assert the set, not the wording

```python
assert "get_order" in called            # the tool that answers this intent
assert "search_policy" not in called    # not the one that looks similar
```

Where several tools could legitimately answer, assert on the **outcome constraint** instead of
pinning one path: the case is about getting the right answer, not about a route you happened to
prefer. Over-specifying the path turns every legitimate refactor into a red suite.

## Step 2: Arguments — compare to the fixture, not to a fixed string

```python
call = first_call(steps, "get_order")
assert call["input"]["order_id"] == case["fixture"]["order_id"]    # the right order
assert call["input"]["customer_id"] == case["input"]["user_id"]    # not another customer's
assert "limit" not in call["input"] or call["input"]["limit"] <= 100
```

Watch for the argument failures that pass type checks: right type, wrong unit (days vs hours);
right shape, wrong entity (the customer's id where the order's belongs); silently defaulted
optional arguments that change the result.

## Step 3: Sequencing — assert dependencies, not a full script

```python
assert index_of("get_order") < index_of("refund_order")       # look before acting
```

Assert the **dependencies that matter**: read before write, confirm before side effect,
authenticate before access. A full expected sequence is brittle and will fail on a refactor that
changed nothing a user could notice.

## Step 4: Failure handling — the half nobody tests

Every tool fails sometimes: an error, a timeout, an empty result. What the system does then is
where the most damaging failure modes live — most commonly, **answering as if the call had
succeeded**, which is how invented ids and fabricated statuses reach users.

Put these in the dataset explicitly, with fixtures that force the condition:

| Fixture | Assert |
|---|---|
| tool returns empty | the answer says it could not find it, and invents no id |
| tool returns an error | the answer does not present a result as fact |
| tool times out | the system does not silently retry a state-changing call |
| tool returns another tenant's data | the system refuses rather than relaying it |

These cases are cheap to construct and routinely reveal more than the entire happy-path suite.

## Step 5: Report by check, not as one rate

```markdown
## Tool calls
| Check | Rate | 95% CI | n |
|---|---|---|---|
| selection | 0.96 | [0.91, 0.98] | 120 |
| arguments | 0.89 | [0.82, 0.93] | 120 |
| sequencing | 0.99 | [0.95, 1.00] | 120 |
| restraint (no forbidden call) | 1.00 | [0.97, 1.00] | 120 |
| failure handling | 0.58 | [0.45, 0.70] | 40 |

### Violations
| Case | Check | What happened |
|---|---|---|
| EV-AGENT-012 | arguments | get_order called with the customer's id in the order_id field |
| EV-AGENT-031 | failure handling | get_order returned empty; answer stated "order 881234 is in transit" |
```

One combined "tool use accuracy" would read as 0.88 and hide that failure handling is at 0.58 —
which is the finding.

## Quality bar (self-check before reporting done)

- [ ] All five checks asserted separately and reported separately.
- [ ] The forbidden-tool set is asserted explicitly, not assumed.
- [ ] Duplicate state-changing calls checked.
- [ ] Arguments compared against fixtures, not fixed strings.
- [ ] Sequencing asserts dependencies, not a full script.
- [ ] Failure-handling cases present, with fixtures that force empty, error and timeout.
- [ ] Every violation names the case, the check, and the specific argument or call.
- [ ] No judge used where any of this was decidable in code.
