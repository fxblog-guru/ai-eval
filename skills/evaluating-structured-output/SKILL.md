---
name: evaluating-structured-output
description: Check JSON and other structured output with code assertions across four independent levels — parses, validates, semantically correct, referentially valid — so a schema pass is never mistaken for a correct answer. Use whenever the system emits structured data, in L0 and L2.
version: 1.0.0
---

# Evaluating Structured Output

> Read `.claude/EVAL-PROFILE.md` first — `§System under evaluation`, `§Layers` (L0, L2).
> EVAL-CONTRACTS §5.1: this is assertion territory. Almost nothing here needs a judge.

## Action

Write assertions for structured output, at four levels that fail independently.

## The four levels

Most teams check level 2 and report it as correctness. These are different questions:

| Level | Question | Kind |
|---|---|---|
| **1 Parses** | is it JSON at all? | assertion |
| **2 Validates** | does it match the schema? | assertion |
| **3 Semantically correct** | are the values right for this input? | assertion, usually |
| **4 Referentially valid** | do the ids, codes and enums exist in the real system? | assertion |

```json
{"order_id": "ORD-99999", "status": "in_transit", "eta_days": -3}
```

Parses. Validates against a schema with three string/enum/integer fields. Level 3 catches
`eta_days: -3`. Level 4 catches an order that does not exist. A suite that reports "schema
compliance: 100%" while shipping this is measuring the wrong thing confidently.

## Step 1: Levels 1 and 2 belong in L0

Schema conformance needs no model call at run time — it runs against recorded outputs and takes
milliseconds. Put it in the L0 contract suite, gate it at 100%, and run it on every merge request.

Assert on the schema the **consumer** uses, not a copy of it. A schema duplicated into the eval
suite drifts from production and starts passing things production rejects.

## Step 2: Level 3 — semantic assertions carry the value

Write these per field, from the failure taxonomy:

```python
assert eta_days >= 0                                # a negative ETA is not a schema problem
assert total == sum(line.amount for line in lines)  # arithmetic the model did
assert refund_amount <= order_total                 # policy, expressible as a bound
assert currency == order.currency                   # consistency with the input
assert not (status == "delivered" and eta_days > 0) # internally contradictory states
```

The last shape — **internally contradictory field combinations** — is where structured output
actually fails and where schemas never help. A model that fills every field plausibly and
inconsistently produces output that is perfectly valid and wrong, and downstream code will act on it.

## Step 3: Level 4 — referential validity

Every id, code and enum value in the output is checked against the real system:

- order ids exist and belong to the calling customer
- product codes exist in the catalogue
- enum values are in the **current** allowed set, not one the model remembers from training

Referential checks catch the invention failures that schema validation is structurally blind to: a
well-formed id for an order that never existed passes every string check there is.

## Step 4: Handle partial output honestly

Truncation at the token limit produces JSON that does not parse. This is common and it is **not**
the same failure as a model that formats badly:

- truncated at `max_tokens` → `ERROR`, with reason `truncated`. The model was cut off; that is a
  configuration problem, not a quality signal.
- complete but malformed → `FAIL` at level 1. That is the model.

Check `finish_reason` before classifying. Conflating the two produces a "JSON compliance" metric
that moves when someone changes `max_tokens`.

## Step 5: What still needs a judge

Almost nothing. The exceptions are free-text fields inside the structure — a `summary` or
`reason` field — where the *content* needs judgement.

Then judge that field alone, as its own binary decision, and keep the structural assertions
separate. One judge for "is this summary grounded" and seven assertions for the rest is both
cheaper and more diagnosable than one judge for "is this output good".

## Step 6: Report per level

```markdown
## Structured output
| Level | Check | Rate | 95% CI | Gate |
|---|---|---|---|---|
| 1 | parses | 0.98 | [0.95, 0.99] | 1.00 FAIL |
| 2 | schema valid | 0.97 | [0.93, 0.99] | 1.00 FAIL |
| 3 | semantically consistent | 0.84 | [0.78, 0.89] | 0.95 FAIL |
| 4 | references resolve | 0.91 | [0.86, 0.95] | 1.00 FAIL |

truncated (ERROR, not counted as FAIL): 4

### Level 3 failures
| Case | Field | Value | Rule violated |
|---|---|---|---|
| EV-TASK-044 | eta_days | -3 | eta_days >= 0 |
| EV-TASK-071 | total | 91.00 | != sum(lines) = 94.00 |
```

Reporting one combined number hides which level is failing, and each level is a different fix:
level 1–2 is prompt or output-mode configuration, level 3 is reasoning, level 4 is grounding.

## Quality bar (self-check before reporting done)

- [ ] All four levels checked separately and reported separately.
- [ ] Levels 1–2 live in the L0 suite and gate at 100%.
- [ ] The schema asserted against is the consumer's, not a copy.
- [ ] Semantic assertions include internally contradictory field combinations.
- [ ] Referential checks hit the real system, including tenant ownership.
- [ ] Truncation classified as `ERROR` with `finish_reason` checked, never as `FAIL`.
- [ ] Free-text fields judged separately from structural checks.
- [ ] Every failure names the field and the rule it broke.
