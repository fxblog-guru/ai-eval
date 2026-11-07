---
name: writing-judge-prompts
description: Design an LLM-as-judge for one binary decision — verdict before reasoning, explicit failure conditions, few-shot examples from the train split only, and deliberate defenses against length and family bias. Use inside /eval-judge, only after a code assertion has been tried and failed.
version: 1.0.0
---

# Writing Judge Prompts

> Read `.claude/EVAL-PROFILE.md` first — `§Models` (the judge model), `§Judge thresholds`,
> `§Domain knowledge`. `.claude/EVAL-CONTRACTS.md` §5.6 sets judge hygiene; §5.4 is the trust gate.

## Action

Write `.evals/judges/JDG-<slug>-vN.md` — a judge that makes **one binary decision about one output**.

A judge written here is not usable for gating until `validating-judges` scores it on held-out
labels and writes `## Verdict VALIDATED`. That is not a formality; it is the only thing separating
this judge from a plausible-sounding number generator.

## Preconditions

- A code assertion was attempted and the reason it failed is recorded in the FM's `## Detector`
  (`writing-code-assertions`). Skipping that step means paying for an approximate answer to a
  question that had an exact one.
- `§Models → judge` is an exact model id, and for any gated FM it is **not the same family** as the
  system under evaluation. A judge from the same family systematically over-rewards outputs shaped
  like its own.

## The four rules

### 1. One binary decision

Not a 1–5 score. Not "rate helpfulness, accuracy, and tone". A scale invites the judge to park on
3 for everything ambiguous, and a composite hides which part failed.

If the FM genuinely needs two decisions, that is two judges — each validatable, each reportable.

### 2. Verdict first, reasoning second

```
Output exactly:
VERDICT: PASS | FAIL
REASON: <one sentence>
```

Reasoning generated before the verdict becomes justification for an answer the model has already
committed to, and it reliably talks itself into PASS. Verdict first keeps the reason a description
rather than an argument.

(This is the opposite of the usual chain-of-thought advice, and it is deliberate: here you want the
judge's first instinct, recorded, not its best defense of it.)

### 3. State the failure conditions explicitly

A judge told only what "good" looks like invents its own failure conditions, and invents different
ones on different calls — which shows up later as a judge that cannot be calibrated.

List what FAIL looks like, concretely, from the FM's `## Evidence`.

### 4. Few-shot from `train` only

Examples come from `train.jsonl`. Pulling them from dev or test destroys the split and the
validation built on it (EVAL-CONTRACTS §5.2). Cite the row ids in the judge file.

## The template

```markdown
# JDG-refund-timeline-v1

## Judge
Decides FM-007 — whether the answer states a refund timeline consistent with the policy for the
order's payment method.
Judge model: <exact id> · temperature 0 · mode: reference-free
Not the same family as the system under evaluation: confirmed.

## Criterion
The answer PASSES if every refund timeline it states matches the policy table for that order's
payment method, or if it states no timeline at all.

## Failure conditions
FAIL if the answer:
- states a number of days that differs from the policy for that payment method
- states a timeline without a payment method being determinable from the input or tool results
- says "instant", "immediately", or "right away" for any method whose policy is over 1 day
- hedges across a range that does not contain the policy figure (e.g. "3 to 5" when policy is 10)

PASS if the answer:
- states the correct figure, in any phrasing or unit that resolves to it
- declines to give a timeline and directs the user to the policy or to support
- gives the correct figure and adds a caveat about bank processing

## Inputs given to the judge
- the user message
- the system's answer
- the retrieved policy rows for this payment method
NOT given: the reference answer (this judge is reference-free)

## Prompt
<the literal prompt, with the {placeholders} the runner fills>

## Few-shot
From train.jsonl rows: L03 (PASS), L11 (FAIL), L18 (FAIL, long fluent wrong), L22 (PASS, edge)

## Output contract
VERDICT: PASS | FAIL
REASON: one sentence
Anything else is an ERROR for that case, not a FAIL.
```

## Defending against the biases that actually bite

**Length bias.** Long, fluent, confidently wrong answers are the case judges most reliably pass —
and the case that most reliably harms users. Put at least one in `train` as a FAIL example and
several in `dev`, and check the judge catches them. If it does not, say so in the prompt:
`length and fluency are not evidence of correctness; judge only against the criterion above`.

**Position bias.** Where the judge compares two outputs, run both orders and check the verdict is
stable. An unstable verdict means the judge is scoring position, not quality.

**Self-preference.** Covered by the family rule. Where the same family is unavoidable — a small
team with one provider — record it in the judge file and treat the judge as `UNVALIDATED` for
gating, however good its numbers look.

**Verbosity of the reason.** Cap the reason at one sentence. A judge given room to write a
paragraph starts reasoning toward a verdict again.

## Determinism

Temperature 0. Judges are not the place for sampling diversity. Where the provider still varies,
`§Budget → Judge calls per case` allows repeats, but measure the judge's own variance before
raising it — and report judge variance separately from system variance, or the two get conflated
into "the evals are flaky".

## Quality bar (self-check before reporting done)

- [ ] One binary decision, about one FM.
- [ ] Verdict before reason in the output contract.
- [ ] Failure conditions listed concretely, derived from the FM's real evidence.
- [ ] Few-shot examples cited to `train.jsonl` rows only.
- [ ] A long-fluent-wrong example is present and the judge is checked against it.
- [ ] Judge model is exact, temperature 0, family checked and recorded.
- [ ] `## Inputs given to the judge` states what is deliberately withheld.
- [ ] The judge is not referenced by any gated suite yet — `/eval-validate` comes first.
