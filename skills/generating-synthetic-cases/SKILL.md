---
name: generating-synthetic-cases
description: Fill dataset gaps by generating one case per tuple across the declared dimensions, so coverage is countable rather than hoped for — never by asking a model for "N varied examples". Use inside /eval-data, after curating real trace cases.
version: 1.0.0
---

# Generating Synthetic Cases

> Read `.claude/EVAL-PROFILE.md` first — `§Models` (the generation model, which is never the
> judge), `§Sample sizes`. Requires `## Dimensions` from `designing-eval-dimensions`.

## Action

Generate cases for the dimension tuples that real traces did not cover, and append them to
`DS-<slug>-vN.jsonl` with `origin: synthetic`.

## The rule that makes this work

**One case per tuple. Never "generate 50 varied examples".**

Free-form generation collapses toward the model's prior: fifty outputs that differ in names and
surface phrasing while exercising one path. The failure is invisible in review — each case looks
fine individually — and it produces a dataset that is large and shallow.

Tuple-driven generation makes coverage a property you can count. You know exactly which
combinations exist because you enumerated them.

## Inputs — resolve before starting (STOP conditions)

1. `## Dimensions` and `## Excluded combinations` from `designing-eval-dimensions`.
2. The already-written `origin: trace` cases — you are filling their gaps, not starting over.
3. `§Models → synthetic data generation`. **This must not be the judge model.** A model that
   generated a case and then grades the answer to it is grading its own idea of the question.

## Step 1: Enumerate the grid, subtract what exists

Take the Cartesian product of the dimensions, remove the excluded combinations, then remove every
tuple already covered by a trace case.

```
4 intents × 4 data states × 3 lengths × 2 tones = 96
- 6 excluded combinations                        = 90
- 34 already covered by trace cases              = 56 tuples to generate
```

If the remainder is far larger than the dataset budget, sample it — but sample so that **every FM
requirement from the dimension map is still covered**, and record which tuples were dropped.
Dropping tuples silently is how an FM ends up with no case in a dataset that looks complete.

## Step 2: Generate one input per tuple

Prompt the generation model per tuple, not per batch. One tuple, one case, one call:

```
Write a single realistic user message for this scenario.

intent: refund
data_state: order-belongs-to-another-customer
length: long
tone: frustrated

Requirements:
- Write it the way a real customer writes: imperfect punctuation, some redundancy, the relevant
  detail buried mid-message rather than stated first.
- Do not state the scenario labels. A reader should infer them from the message.
- Do not make the message self-evidently a test case.
- Include exactly one order reference, formatted as: <the product's real format>

Output only the message.
```

Per-tuple calls cost more and are worth it: batch generation makes the model optimize for variety
within the batch, which pulls every case toward being different from its neighbours rather than
being faithful to its tuple.

## Step 3: De-duplicate by meaning

Even per-tuple generation repeats itself. Check near-duplicates — by embedding similarity if
available, otherwise by reading. Two cases that differ only in the customer's name are one case.

Regenerate duplicates with an explicit instruction to differ on the dimension that matters, not on
surface detail.

## Step 4: Review a sample by hand — this step is not optional

Read at least 20% of generated cases, and **every case for a `blocking` FM**.

What to look for:

| Problem | What it looks like |
|---|---|
| **Tells on itself** | "I'd like to request a refund for order 88123 which I believe belongs to another customer" — no real user says this. The system will handle it correctly for the wrong reason. |
| **Wrong tuple** | tagged `data_state: not-found` but the message names an order that exists in the fixture |
| **Impossible** | references a product, flow, or state the system does not have |
| **Too clean** | perfect grammar, one question, ideal formatting — this is the synthetic-data failure mode |
| **Leaks the answer** | phrases the question in the words of the expected response |

Rejected cases are regenerated, not edited into shape. An edited case drifts away from its tuple
and the grid stops meaning what it says.

## Step 5: Write with full provenance

```json
{
  "case_id": "EV-TASK-071",
  "input": { "message": "…", "user_id": "u_synth_071" },
  "fm": ["FM-003"],
  "expect": { "assert": ["no-other-tenant-data"], "judge": ["JDG-tenant-isolation-v1"] },
  "origin": "synthetic",
  "dimensions": { "intent": "refund", "data_state": "other-tenant", "length": "long", "tone": "frustrated" },
  "generated_by": "<exact model id>",
  "reviewed_by": "ANN-LN"
}
```

`reviewed_by` on every hand-reviewed case. An unreviewed synthetic case for a `blocking` FM should
not be in a gated dataset.

## Step 6: Fixtures must match

A case with `data_state: not-found` requires the test environment to actually not have that order.
Where the system reads a database or calls tools, the fixture is part of the case — write it
alongside, and make sure the runner loads it.

A mismatch here is the quietest failure available: the case runs, the system answers correctly for
a state the case did not intend, and the suite reports a pass for a failure mode it never
exercised.

## Quality bar (self-check before reporting done)

- [ ] One case per tuple; no batch generation anywhere.
- [ ] Every FM's dimension requirement is covered after any sampling.
- [ ] Near-duplicates removed.
- [ ] ≥ 20% hand-reviewed, and 100% of `blocking`-FM cases.
- [ ] Generation model ≠ judge model, and the id is recorded per case.
- [ ] Every case carries its `dimensions`.
- [ ] Fixtures exist for every case whose `data_state` requires one.
- [ ] `origin: trace` share is still ≥ 30% after adding these.
