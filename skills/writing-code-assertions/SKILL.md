---
name: writing-code-assertions
description: Write deterministic pass/fail checks for the failure modes an objective rule can decide — schema, fields, tool arguments, citations, forbidden content, numeric bounds — so they never need a judge, labels, or calibration. Use first inside /eval-judge, before considering an LLM judge.
version: 1.0.0
---

# Writing Code Assertions

> Read `.claude/EVAL-PROFILE.md` first — `§System under evaluation`, `§Quality gates`.
> `.claude/EVAL-CONTRACTS.md` §5.1 sets the preference order: assertion first, judge only if it fails.

## Action

Write a deterministic evaluator into `.evals/scripts/shared/assertions/` and register its id so
suites and dataset rows can reference it.

## Why this comes first, always

An assertion is free, instant, exact, and needs no calibration. A judge costs money per call,
takes seconds, is approximate, and needs 100–200 human labels before anyone may trust it
(EVAL-CONTRACTS §5.4).

Converting one FM from a judge to an assertion removes a variance source, a cost line, and a
labelling project. It is the highest-leverage move available in this phase, and it is skipped
constantly because reaching for a judge feels faster in the moment.

## The test: is this decidable by a rule?

Ask: **could a program with access to the output, the input, the tool calls, and the retrieved
context decide this with no judgement?**

| Failure mode | Assertion? | The check |
|---|---|---|
| Returns malformed JSON | yes | parse it |
| Output violates the declared schema | yes | validate against the schema |
| Invents an order number | yes | every order-shaped token in the output appears in a tool result |
| Cites a chunk that wasn't retrieved | yes | every cited id ∈ the retrieved set |
| Calls a forbidden tool | yes | tool-call log ∩ forbidden set = ∅ |
| Refunds more than the order total | yes | compare the argument to the fixture |
| Leaks the system prompt | yes | n-gram overlap with the prompt above a threshold |
| Returns another tenant's data | yes | every id in the output belongs to the caller's tenant |
| Exceeds the latency budget | yes | compare to the threshold |
| Answers in the wrong language | yes | language detection |
| **Is grounded in the retrieved context** | no | requires reading both and judging support |
| **Follows the refund policy** | partly | the amount is checkable; "explained the policy correctly" is not |
| **Tone is acceptable to a frustrated user** | no | judgement |

The middle row is the important one: **split it**. "Follows the refund policy" becomes an assertion
on the amount and a judge on the explanation. Two evaluators, each doing what it is good at, and
the expensive half shrinks.

## Step 1: Write it narrow

One assertion decides one thing, and its name says what:

```
assert:json-parses
assert:schema-valid
assert:order-id-exists
assert:citation-resolves
assert:no-forbidden-tool
assert:refund-within-total
assert:no-system-prompt-leak
assert:tenant-isolation
```

Not `assert:output-is-good`. A composite assertion that fails tells you nothing about which part
failed, and the per-FM reporting that finds regressions depends on that granularity.

## Step 2: Signature and contract

```python
def assert_order_id_exists(case, result) -> Verdict:
    """Every order-shaped token in the output appears in a tool result.

    case:   the dataset row  (input, fm, expect, dimensions, fixture)
    result: {output, steps, meta} from the provider adapter
    returns Verdict(passed: bool, reason: str, evidence: dict)
    """
```

`reason` is written for a human reading a failed scorecard six weeks later: name the token and
where it was expected to come from. `evidence` carries the extracted values so nobody has to
re-derive them from the trace.

## Step 3: Watch the two failure modes of assertions

**False negatives from over-strict matching.** An assertion on exact wording fails on a correct
answer phrased differently. Assert on the *fact*, not the sentence: extract the order id and
compare, rather than matching a template.

**False positives from under-specified matching.** `"the output contains the right number"` passes
when the number appears inside an unrelated sentence, or when the model hedged and gave two. Check
position and context, not just presence.

Test each assertion against known-good and known-bad outputs from the trace batch before trusting
it. An assertion is code; it has bugs; and its bugs are silent because nothing else checks it.

## Step 4: Register it

```yaml
# .evals/scripts/shared/assertions/registry.yaml
- id: order-id-exists
  fn: assertions.orders:assert_order_id_exists
  fm: [FM-001]
  description: every order-shaped token in the output appears in a tool result
  tested_against: [TB-2026-09-10-001/trace_8f2a1c, TB-2026-09-10-001/trace_2b91ff]
```

`tested_against` names the real traces used to check the assertion behaves correctly — the
assertion's own evidence, and the first thing to re-run when it starts behaving oddly.

## Step 5: Record the attempt in the FM file

When an assertion cannot decide an FM, write into the FM's `## Detector` **what was tried and what
went wrong**:

```
JDG-refund-timeline-v1 — assert:regex-business-days was tried and produced false positives on
correct answers that mention "business days" while quoting the right figure. The decision needs the
order's payment method and the policy table, so it is not decidable from the output alone.
```

Without this note, someone will try the same regex next quarter.

## Quality bar (self-check before reporting done)

- [ ] Every FM was assessed for an assertion before any judge was written.
- [ ] Each assertion decides exactly one thing, and its id says which.
- [ ] Each was tested against real known-good and known-bad outputs, recorded in `tested_against`.
- [ ] `reason` is written for a human, and names the specific value that failed.
- [ ] No assertion matches exact wording where the fact would do.
- [ ] FMs that could not be asserted carry the failed attempt in `## Detector`.
- [ ] The registry matches the code; a stale registry silently drops checks from suites.
