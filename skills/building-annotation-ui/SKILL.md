---
name: building-annotation-ui
description: Build a purpose-built trace review interface so labelling takes seconds per item instead of minutes — the single highest-leverage investment in an evaluation workflow, because every judge depends on labels a human actually produced. Use during /eval-explore and before any large labelling push.
version: 1.0.0
---

# Building an Annotation Interface

> Read `.claude/EVAL-PROFILE.md` first — `§Sample sizes`, `§Severity`, `§Domain knowledge`.
> Labels produced here feed `splitting-label-sets` and `validating-judges`.

## Action

Build a small, local, single-purpose interface for reading traces and labelling them.

## Why this is worth a day of work

Judge validation needs 100–200 labels per failure mode (`§Sample sizes`). At two minutes per item
in a spreadsheet — scrolling raw JSON, copying ids, losing your place — that is six hours of
unpleasant work, and it does not get done. The judge stays unvalidated, the gate stays
`NOT-EVALUABLE`, and the whole pipeline stalls on the one step that cannot be skipped.

At ten seconds per item it is half an hour, and it happens. The interface is not a nicety; it is
what makes the labelling actually occur.

## Step 1: Build for your data, not in general

Do not reach for a generic annotation platform. The value is entirely in showing **this** system's
traces the way they need to be read:

- a RAG trace shows the query, the retrieved chunks **with their scores and ranks**, and the answer
  — with cited chunks highlighted inline
- an agent trace shows turns and tool calls as a timeline, with arguments and return values
  expandable and the final state alongside
- a structured-output trace shows the JSON next to the schema, with violations marked

A generic tool shows you JSON. Reading raw JSON is the cost you are trying to remove.

## Step 2: One screen, one decision, keyboard only

```
┌─ trace 34 / 100 ──────────────────── FM-007 refund timeline ─┐
│ USER   hi how long till i get my money back for order 88123  │
│                                                              │
│ TOOLS  get_order(88123) → {payment_method: "card", ...}      │
│        search_policy("refund timeline") → 3 chunks           │
│          ▸ pol-refund-014  0.91  "card refunds: 10 business… │
│          ▸ pol-refund-008  0.72  "PayPal refunds: up to 5 …  │
│                                                              │
│ ANSWER Your refund should arrive in 3-5 business days.       │
│                                                              │
│ [j] pass   [f] fail   [s] skip   [n] note   [←] back         │
└──────────────────────────────────────────────────────────────┘
```

Rules that matter more than they look:

- **One decision per screen.** Pass or fail. A screen offering five fields per item halves the rate.
- **Keyboard only.** Reaching for a mouse is the difference between ten seconds and forty.
- **Show the evidence inline.** If deciding requires opening another window to check the policy,
  the annotator will guess instead. Put the retrieved chunk on the screen.
- **A back key.** Annotators change their mind one item later, constantly. Without back they either
  lose the correction or stop to fix it by hand.
- **Progress and autosave.** Labelling stops halfway; it must resume.

## Step 3: Make the criterion visible while labelling

Put the failure mode's `## Statement` at the top of the screen, always visible.

Without it, the criterion drifts over a session: the first twenty items get labelled against one
standard and the last twenty against another, and the resulting labels are internally inconsistent
in a way that caps every judge trained or validated against them. The judge cannot beat its labels.

## Step 4: Capture the note, not just the verdict

The `[n]` key adds one line of free text. Those lines are where the judge's failure conditions come
from (`writing-judge-prompts`), and where the disagreement analysis becomes actionable
(`validating-judges`).

A label with no note is a datum. A label with "said 3-5 but this is a card, so 10" is the rubric
writing itself.

## Step 5: Write labels in the contract format

Append directly, one line per label:

```json
{"case_id": "EV-TASK-014", "output_ref": "runs/task/2026-09-16-1420/results.jsonl#L42",
 "label": "fail", "annotator": "ANN-LN", "ts": "2026-09-16T09:12:00Z",
 "note": "said 3-5 days but payment_method is card, policy is 10", "fm": "FM-007"}
```

Never write straight into `train/dev/test`. Labels land in one pool and are split once by
`splitting-label-sets` — splitting as you go destroys the stratification and makes the test split
whatever happened to be labelled last.

## Step 6: Support the overlap

Have two people label the same 20 items, to compute agreement (`splitting-label-sets` Step 1).

Below ~80% agreement, the humans do not agree on the criterion, so **no judge can be calibrated to
it**. Fix the failure-mode definition first. That disagreement is one of the most valuable findings
in the whole pipeline, and it is only visible if the interface makes overlap cheap.

## Step 7: Keep it local and disposable

A local HTML file reading JSONL, or a small Streamlit/Flask app. No deployment, no auth, no
database. It will be rewritten when the trace shape changes, and that is fine — it should cost an
hour to rewrite.

If the traces contain PII, keep it local, and do not publish it anywhere.

## Quality bar (self-check before reporting done)

- [ ] One decision per screen, keyboard-driven, with a back key.
- [ ] All evidence needed for the decision is on screen — no second window.
- [ ] The failure-mode statement is visible while labelling.
- [ ] Notes capturable in one keystroke.
- [ ] Labels appended in the contract format, to one pool, never pre-split.
- [ ] Progress saved continuously; a session can resume.
- [ ] Overlap mode supported for agreement measurement.
- [ ] Local only; no PII leaves the machine.
- [ ] Timed on ten real items: if it is not around ten seconds each, fix the interface before
      labelling 200.
