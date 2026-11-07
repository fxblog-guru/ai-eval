---
name: curating-golden-sets
description: Pull real trace inputs into the eval dataset so at least 30% of cases come from traffic that actually happened, covering every open failure mode, with deliberate over-sampling of failures and recorded weights. Use inside /eval-data, before generating synthetic cases.
version: 1.0.0
---

# Curating Golden Sets

> Read `.claude/EVAL-PROFILE.md` first — `§Sample sizes`, `§Severity`.
> `.claude/EVAL-CONTRACTS.md` §7 defines the dataset format and the 30% trace-origin rule.

## Action

Select real trace inputs, turn each into a dataset case, and write them to
`.evals/datasets/DS-<slug>-vN.jsonl` with `origin: trace`.

## Why real inputs are not optional

Synthetic inputs are clean. They have correct spelling, one question per message, the order id in
a recognizable format, and no ambiguity the author did not intend. Real inputs have a forwarded
email thread, a phone number where an order id should be, three questions in one sentence, and a
typo in the product name.

A system that scores 92% on synthetic inputs and 64% on real ones is the normal case, and only the
second number describes the product. EVAL-CONTRACTS §7.2 sets the floor at 30% `origin: trace` for
exactly this reason.

## Inputs — resolve before starting (STOP conditions)

1. `.evals/taxonomy/INDEX.md` with the open FMs.
2. The trace batch with its `notes.md` — the coded traces and their verdicts.
3. `§Sample sizes → cases in a gated dataset` — 100 minimum, 200 target.

If no traces exist, STOP and escalate. Proceeding means the dataset is entirely hypothetical, which
is sometimes the right call for a pre-launch system — but it is the user's call to make, in
writing, and it gets recorded in `.meta.md` so nobody reads the resulting numbers as production
truth.

## Step 1: Cover every open FM first

For each open FM, pull its `## Evidence` trace refs into the dataset. Those traces are known to
trigger it, which makes them the highest-value cases available: they are the ones where you
already know what should happen.

Target 3–10 cases per FM depending on severity. A `blocking` FM with one case is gated on a single
example, and a single example can pass by luck.

## Step 2: Add the happy path, deliberately

Cases where the system behaves correctly are not filler. Without them:

- you cannot compute a meaningful rate — everything fails, and the number is uninterpretable,
- you cannot detect a fix that breaks something that worked (the most common regression),
- the judge sees only failures during validation and learns to say fail.

Target 30–40% happy-path cases. Take them from `verdict: ok` traces, across the same dimension
spread as the failure cases.

## Step 3: Write each case

```json
{
  "case_id": "EV-TASK-014",
  "input": { "message": "hi i ordered 2 weeks ago order 88123 where is it", "user_id": "u_4412" },
  "fm": ["FM-001"],
  "expect": { "assert": ["order-id-exists", "no-invented-dates"], "judge": ["JDG-grounded-v1"] },
  "origin": "trace",
  "source": "TB-2026-09-10-001/trace_8f2a1c",
  "dimensions": { "intent": "status", "data_state": "not-found", "length": "short" }
}
```

**Keep the input as it was.** Do not fix the spelling, do not add the punctuation, do not tidy the
formatting. Every correction removes a real condition the system has to handle, and the cleaned-up
version is exactly the synthetic case you were trying not to write.

Redact, do not normalize. A masked name is still a name-shaped token in the same position.

`source` is required for `origin: trace` and is not optional: it is how anyone later checks whether
a case is still representative.

## Step 4: Over-sample failures, and write down the weights

A dataset mirroring production traffic spends 90% of its budget re-confirming the happy path.
Deliberately over-sample the failure modes — and record the sampling weights in `.meta.md`:

```markdown
## Sampling weights
| Stratum | Share of traffic | Share of dataset | Weight |
|---|---|---|---|
| happy path | 87% | 35% | 2.49 |
| FM-001 (not-found) | 4% | 25% | 0.16 |
| FM-007 (refund timeline) | 2.4% | 20% | 0.12 |
```

Without these weights, every rate computed from this dataset understates real-world quality, and
nothing in the output says so. With them, a production estimate can be recovered.

## Step 5: Check leakage before writing

Grep each case input against:

- the system prompt and its few-shot examples,
- every judge's `train.jsonl`,
- any example file the system loads at runtime.

A hit means the system is being tested on an answer it was shown. Replace the case and note the
check in `.meta.md`. This is a blocking audit finding (EVAL-CONTRACTS §13), so catching it here is much
cheaper than catching it later.

## Quality bar (self-check before reporting done)

- [ ] Every open FM has at least 3 cases, more for `blocking`.
- [ ] 30–40% happy-path cases, spread across the same dimensions.
- [ ] Every case has `source` pointing at a real trace, and the trace resolves.
- [ ] No input was cleaned up, reworded, or tidied.
- [ ] Sampling weights are recorded.
- [ ] Leakage check run against all three surfaces, with the result written down.
- [ ] Every case carries the FM ids it probes — an untagged case can never be reported per-FM, and
      per-FM is how regressions are actually found.
