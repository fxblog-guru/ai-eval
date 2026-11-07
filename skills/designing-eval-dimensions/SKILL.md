---
name: designing-eval-dimensions
description: Derive the dimensions along which real inputs vary — intent, data state, locale, length, user expertise, edge conditions — from traces, so synthetic cases can be generated as tuples across them instead of as fifty rephrasings of one case. Use at the start of /eval-data.
version: 1.0.0
---

# Designing Eval Dimensions

> Read `.claude/EVAL-PROFILE.md` first — `§System under evaluation`, `§Sample sizes`, `§RAG`.
> Requires `.evals/taxonomy/` and the trace batch that produced it.

## Action

Produce the dimension list that `generating-synthetic-cases` will take tuples across. Written into
`DS-<slug>-vN.meta.md` under `## Dimensions`.

## The problem this solves

Ask a model for "50 varied test cases" and you get 50 rephrasings of one case. They will look
different — different names, different products, different phrasings — and they will exercise one
path through the system. The dataset appears large and covers almost nothing, which is worse than
a small dataset because it produces confidence.

Dimensions fix this by making variation explicit and combinatorial. You choose the axes; the
generator fills the grid; coverage becomes something you can count rather than hope for.

## Inputs — resolve before starting (STOP conditions)

1. `.evals/taxonomy/INDEX.md` — the failure modes tell you which axes matter. An FM that only fires
   for one locale makes locale a required dimension.
2. The **trace batch**. Dimensions are read off real inputs, not invented. A dimension list written
   without traces reflects the team's mental model of its users, which is exactly the thing error
   analysis exists to correct.
3. `.evals/system-card.md` — `## Users` and `## Tools` bound what can legitimately vary.

## Step 1: Read the traces for what actually varies

Go through the batch and list every way one input differs from another. Do not filter yet.

Dimensions that recur across systems, as a prompt for your reading — not as a checklist to adopt:

| Dimension | Example values | Why it matters |
|---|---|---|
| **intent** | check status · request refund · change address · complain · several at once | the primary axis; most systems have 5–15 real intents |
| **data state** | order exists · doesn't exist · exists but belongs to someone else · cancelled · partially shipped | where lookup tools return things the prompt didn't anticipate |
| **input completeness** | all details given · order id missing · ambiguous reference ("my last order") | drives the clarification path, which is usually untested |
| **locale / language** | en · vi · mixed · non-Latin names | prompts written in English quietly assume English |
| **length** | one line · a paragraph · a forwarded email thread | long inputs hit context limits and instruction drift |
| **user expertise** | uses product terms · describes things vaguely · uses the wrong term confidently | the last one is the interesting case, and the rarest in synthetic data |
| **tone** | neutral · frustrated · formal · abusive | frustration changes what a good answer is, not just how it reads |
| **edge conditions** | boundary amounts · dates at period ends · zero / null / very large values | the classic test-design boundaries, which apply here unchanged |

**Add the dimensions that are specific to this system.** A dimension list that could be pasted into
another product has not been derived from these traces. For a field-service product that might be
`job state`, `engineer availability`, `SLA window`; for a finance product, `currency`,
`rounding boundary`, `fiscal period edge`.

## Step 2: Cut to what changes the answer

A dimension earns its place if varying it could change whether the system answers correctly.
Customer first name varies in every trace and changes nothing — it is not a dimension, it is
filler.

Test each candidate: **is there a plausible reason the system behaves differently across these
values?** If not, drop it. Every retained dimension multiplies the grid, and a grid of 4,000 cases
is one nobody runs.

Aim for 4–6 dimensions with 3–5 values each. That is 100–600 tuples before sampling, which is the
right order of magnitude for a dataset of 100–200 cases.

## Step 3: Map dimensions to failure modes

For each FM, record which dimension values are needed to trigger it:

```
| FM | Requires |
|---|---|
| FM-001 | data_state = not-found |
| FM-007 | intent = refund × payment_method ∈ {card, paypal, bank} |
| FM-012 | length = long × intent = multiple |
```

This is what guarantees coverage later: a tuple set that never produces `data_state = not-found`
cannot trigger FM-001, and the suite will report FM-001 as fine forever.

## Step 4: Mark the invalid combinations

Some tuples are impossible or meaningless — `data_state = cancelled` × `intent = change-address`
may have no sensible instance. List them as excluded, with the reason. Unmarked, the generator
produces nonsense cases, and a human later quietly deletes them along with some legitimate ones.

## Output contract

Into `DS-<slug>-vN.meta.md`:

```markdown
## Dimensions
| Dimension | Values | Derived from | Why it changes the answer |
|---|---|---|---|
| intent | status, refund, address-change, complaint, multiple | 87 of 100 traces | different tool paths and policies |
| data_state | found, not-found, other-tenant, cancelled | 100 traces | FM-001 only fires on not-found |

## FM → dimension requirements
<the table from Step 3>

## Excluded combinations
| Combination | Why |
|---|---|
| cancelled × address-change | no such flow exists in the product |
```

## Quality bar (self-check before reporting done)

- [ ] Every dimension is traceable to variation actually observed in the batch.
- [ ] At least two dimensions are specific to this product, not generic.
- [ ] Every dimension passes the "could change the answer" test.
- [ ] Every open FM appears in the FM → dimension table. An FM with no dimension requirement means
      nobody knows what triggers it, which means the dataset will not.
- [ ] The grid size is stated, and it is a number someone would actually run.
- [ ] Invalid combinations are listed with reasons.
