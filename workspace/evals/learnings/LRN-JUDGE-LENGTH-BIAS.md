---
id: LRN-JUDGE-LENGTH-BIAS
title: Judges pass long, fluent answers that hide one wrong fact
status: active
confidence: provisional
applies_to: [L2, L3, judge]
evidence: [runs/task-example/2026-09-16-0900]
probe: Does the judge's test split include long answers with a single wrong figure?
created: 2026-10-26
updated: 2026-10-26
---

- **Do:** put at least five long, confident, wrong answers in the judge's dev and test splits.
- **Why:** the false negatives in past validations clustered on answers over 200 words.
- **Not:** adding "be strict" to the prompt; it raises false positives without catching these.
