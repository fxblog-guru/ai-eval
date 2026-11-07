---
name: open-coding-traces
description: Read traces one at a time and write free-text notes about what went wrong, before any category exists — the first half of error analysis. Enforces that a human codes the first 30 traces themselves and that machine-suggested codes are confirmed, never assumed. Use when /eval-explore runs, before axial coding.
version: 1.0.0
---

# Open Coding Traces

> Read `.claude/EVAL-PROFILE.md` first — `§Sample sizes`, `§Severity`, `§Domain knowledge`.
> Requires `.evals/system-card.md` (what "correct" means) and a trace batch from `sampling-traces`.

## Action

Read each trace in `.evals/traces/<TB-id>/raw.jsonl` and append a free-text note to `notes.md`
describing what is wrong with it — **without using any category**, because no categories exist yet.

## Why no categories yet

The categories you bring to the data are the categories you will find in it. Open with
"faithfulness, relevance, coherence" and every trace will be sorted into one of those three,
including the twenty that were actually about the system confidently inventing an order number.

Open coding is the deliberate refusal to categorize while reading. The categories come out of the
notes in `axial-coding-failures`, after the reading is done.

## Inputs — resolve before starting (STOP conditions)

1. `.evals/traces/<TB-id>/raw.jsonl` with the target count (`§Sample sizes`, default 100).
2. `.evals/system-card.md` — particularly `## Hard policies`. Without a statement of what must
   never happen, you are reacting to outputs rather than evaluating them.
3. **A human available to code the first 30.** Not negotiable — see below.

## Step 1: The human codes the first 30

`§Sample sizes → traces coded by a human before AI assistance` is 30, and it is a floor, not a
target.

This is not ceremony. The failure modes present in *this* data are visible only to someone who
read it, and the person who reads 30 traces acquires a model of the system that no summary
transfers. Afterwards they can judge a proposed code in seconds; before, they cannot judge one at
all.

Practically: present one trace at a time — input, the step sequence, output — and capture what the
reader says. Do not offer suggestions during these 30. A suggestion becomes the reader's frame,
and the point of this phase is that the frame comes from the data.

## Step 2: One note per trace

```
### <trace_id>
- **What the user wanted:** <one line, in the user's terms>
- **What happened:** <one line — the outcome, not the mechanism>
- **What's wrong:** <free text. Be specific and concrete. Quote the output.>
- **Where it went wrong:** <which step, when the trace shows it — retrieval? tool call? the final
  generation? Often the visible symptom is three steps downstream of the cause.>
- **Severity guess:** blocking | major | minor   <against §Severity>
- **Verdict:** ok | problem
```

Write in the specific, not the general. `"Said the refund would take 3-5 days, but the policy page
says 10 business days for this payment method"` is a note you can build an evaluator from.
`"Inaccurate information"` is not.

A trace with nothing wrong gets `verdict: ok` and a one-line note. Those matter: without them you
cannot compute a rate, and a notes file containing only problems reads as a system that fails
always.

## Step 3: Machine assistance, after 30 — with confirmation

From trace 31 the agent may propose notes. Every proposal is **presented to the human, who accepts,
edits, or rejects it**. Batch them — twenty at a time, each with its trace ref — so review is fast.

- An accepted note carries the confirming human's annotator id.
- A proposal nobody looked at is not a finding. It is not written to `notes.md`.
- `ANN-AI` appears only on unconfirmed proposals, and unconfirmed proposals never count toward any
  rate, taxonomy, or label minimum (EVAL-CONTRACTS §5.2).

Reject-rate is worth watching: when the agent's proposals are being rejected more than a third of
the time, it has the wrong model of the system and the human should code another twenty directly.

## Step 4: Track saturation while you read

After each block of 20 traces, record: how many notes described something not seen before.

```
## Saturation
| Traces | New distinct problems in this block |
|---|---|
| 1–20 | 11 |
| 21–40 | 6 |
| 41–60 | 3 |
| 61–80 | 1 |
| 81–100 | 1 |
```

Saturation is when that column flattens near zero — new traces stop teaching you anything. That is
where reading can stop. Typically around 100 traces; sometimes 60, sometimes 200.

**Report honestly whether saturation was reached or the budget ran out.** They look identical in
the artifact and mean opposite things: one says the taxonomy is complete, the other says it is a
partial view that will need another pass.

## Output contract

`.evals/traces/<TB-id>/notes.md`, appended to the file `sampling-traces` created:

```
## Coding
<one ### block per trace, in the order read>

## Saturation
<the table above>

## Annotators
<annotator ids, how many traces each coded, and how many were AI-proposed then confirmed>
```

## Quality bar (self-check before reporting done)

- [ ] At least 30 traces coded by a human with no prior suggestion.
- [ ] Every note quotes or points at something concrete in the trace.
- [ ] `ok` traces are coded too, not skipped.
- [ ] No note uses a category name — if a note says "hallucination", it has skipped ahead; rewrite
      it as what actually happened.
- [ ] The saturation table exists and the report says which of the two stopping conditions applied.
- [ ] Every AI-proposed note has a confirming human annotator id, or it is not in the file.
