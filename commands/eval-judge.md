---
description: Build an evaluator for each failure mode — a code assertion where possible, an LLM judge only where judgment is genuinely required
argument-hint: <slug> [--fm FM-NNN] [--labels] [--bump]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Models` (the judge model, which must not share a
> family with the system under evaluation in a gated suite), `§Judge thresholds`, `§Sample sizes`.
> EVAL-CONTRACTS §5 is the contract; §5.4 is the trust gate.

Produce an evaluator for every `open` failure mode. Step 4 of the pipeline.

## Arguments

- **`<slug>`** — the judge slug, kebab-case
- `--fm FM-NNN` — build the evaluator for one failure mode only
- `--labels` — split existing human labels into `train`/`dev`/`test` (delegates to
  `dataset-designer` / `splitting-label-sets`) instead of writing an evaluator
- `--bump` — produce `JDG-<slug>-v(N+1)`; required whenever the prompt, the judge model, the model
  version, or the few-shot examples change

## Preconditions (check before delegating)

- [ ] `.evals/taxonomy/` has the FM(s) being covered
- [ ] `§Models → judge` names an exact model id, not a family
- [ ] the judge model is not from the same family as the system under evaluation, for any FM whose
      evaluator will gate — else warn loudly and record it in the judge file

## Execution

Delegate to `judge-engineer`. For every FM, decide the evaluator kind **in this order**:

1. **Code assertion** (`writing-code-assertions`) — an objective rule decides it. Schema valid,
   required field present, tool called with the right argument, forbidden string absent, number in
   range, citation resolves to a real chunk id. Free, instant, exact, needs no calibration.
2. **LLM judge** (`writing-judge-prompts`) — the decision genuinely needs judgment.

Reaching for a judge where an assertion would do is the expensive mistake of this phase: it turns
a free exact check into a paid approximate one that then needs 100–200 human labels before anyone
may trust it. Try the assertion first; if it does not work, say why in the FM file.

**One judge decides one binary question.** Not a 1–5 score, not a composite of three qualities. A
question that cannot be binary is two judges.

## Judge-prompt rules (enforced at review)

- **Verdict first, reasoning second.** Reasoning written before the verdict becomes justification
  for an answer already chosen.
- Few-shot examples come from the `train` split **only**. Pulling them from dev or test destroys
  the split and the validation that depends on it.
- State the criterion, then the explicit failure conditions, then ask for the verdict. A judge told
  only what "good" looks like invents its own failure conditions, differently each time.
- Put a long, fluent, confidently wrong answer in the dev split on purpose. That is the case judges
  most reliably pass, and the one your users will most reliably be harmed by.

## Done criteria (exit gate)

- Every `open` FM has a `## Detector` naming an assertion id or `JDG-<slug>-vN`.
- Every judge file has `## Judge`, `## Criterion`, `## Failure conditions`, `## Output contract`,
  and its few-shot examples cited to `train.jsonl` rows.
- No judge is referenced by a gated suite yet — that requires `/eval-validate` first.

Report back: per FM, the evaluator kind and the reason; the judge ids created; and the explicit
next step — `/eval-validate <slug>`, which is what makes any of these usable for a gate.
