---
name: evaluating-groundedness
description: Check that every claim in a generated answer is supported by the retrieved context — citation validity as a free code assertion first, then claim-level groundedness and answer relevance with a validated judge. Reference-free: needs no ground-truth answers. Use inside /eval-rag --stage generation.
version: 1.0.0
---

# Evaluating Groundedness

> Read `.claude/EVAL-PROFILE.md` first — `§RAG`, `§Layers` (L2), `§Quality gates`,
> `§Models` (the judge, which must not share a family with the system in a gated suite).
> EVAL-CONTRACTS §5 governs every judge used here, including these.

## Action

Decide, per answer, whether it says anything the retrieved context does not support — and separate
that from whether it answered the question at all.

## The three checks, cheapest first

| Check | Kind | Cost | Catches |
|---|---|---|---|
| **Citation validity** | code assertion | free | fabricated chunk ids, citations to nothing |
| **Groundedness** | judge, claim-level | per claim | claims the context does not support |
| **Answer relevance** | judge | per answer | grounded answers that miss the question |

Run them in this order. A large share of "hallucination" in a citing RAG system is caught by the
first one, for nothing, before any judge is involved.

## Step 1: Citation validity — an assertion, never a judge

```python
cited     = {ids the answer cites}
retrieved = {ids in the retrieved set for this query}
passed    = cited <= retrieved          # every citation resolves
```

Exact, instant, no calibration, no labels. Anyone who builds a judge for this is paying for an
approximate answer to a question that has an exact one.

Two failure shapes, and they are different problems:

- **Dangling citation** — cites an id that was not retrieved. Usually invention.
- **Citation drift** — the id was retrieved, but that chunk does not support the sentence it is
  attached to. Not catchable in code; this is what the groundedness judge is for.

## Step 2: Groundedness at the claim level, not the answer level

Decompose the answer into atomic claims, then decide each one against the retrieved context.

```
Answer: "Card refunds take 10 business days, and you'll get an email when it's processed."

Claim 1: card refunds take 10 business days       → supported by pol-refund-014   PASS
Claim 2: the user receives an email on processing → not in any retrieved chunk    FAIL
```

Answer-level judging misses exactly this case: four correct sentences and one invented one reads as
"mostly grounded" and gets passed. Claim level makes it binary and makes the failure locatable.

The metric is then unambiguous:

```
groundedness = (answers where EVERY claim is supported) / (answers)
```

Not "average share of supported claims". An answer with one invented sentence is an answer a user
cannot rely on, and averaging hides precisely the cases that matter.

## Step 3: What counts as supported

State this in the judge prompt, explicitly — it is the decision that drives most disagreements
during validation:

```
SUPPORTED:
- the chunk states it directly
- the chunk states it in different words with the same meaning
- it follows from the chunk by arithmetic the chunk's own numbers permit

NOT SUPPORTED:
- generally true, but not in any retrieved chunk   ← the common one
- true of a different case in the chunk (wrong payment method, wrong region, wrong product)
- a plausible elaboration the chunk does not make
- a hedge attached to an unsupported claim ("typically", "usually", "generally")
```

The fourth is worth its own attention. Hedged invention passes casual review because it sounds
careful, and users read "refunds usually take 3-5 days" as a fact.

## Step 4: Answer relevance is a separate judge

An answer can be perfectly grounded and useless: it quotes the retrieved policy accurately and
never addresses what was asked.

Keep the two judges separate. Combining them into "answer quality" produces a score that cannot
distinguish "invented something" from "answered a different question" — and those need different
fixes, in different systems.

## Step 5: Abstention is correct behaviour, and must be scored as such

When the retrieved context does not contain the answer, the correct response is to say so. A judge
that has not been told this marks every abstention as a failure, and the system gets optimized
toward answering everything — which is the behaviour the groundedness metric exists to prevent.

Put abstention cases in the dataset deliberately (the `known-absent` queries from
`evaluating-retrieval`) and state in the judge prompt:

```
An answer that declines because the context does not cover the question is PASS for groundedness,
provided it does not also assert unsupported facts while declining.
```

## Step 6: Attribute every failure to a stage

Cross-reference the L1 retrieval result for the same query, and label each generation failure:

| Pattern | Attribution | Who fixes it |
|---|---|---|
| chunk not retrieved, answer invented | **retrieval** | chunking, embedding, k, query rewriting |
| chunk retrieved at rank 8, answer invented | **ranking** | reranker, context ordering |
| chunk retrieved at rank 1, answer contradicts it | **generation** | prompt, model |
| chunk retrieved, answer grounded, still unhelpful | **corpus** | the documentation itself |

**This table is the deliverable.** A groundedness rate with no attribution tells a team something
is wrong; the attribution tells them which of four different systems to open.

## Step 7: These judges are judges

Everything in EVAL-CONTRACTS §5 applies: one binary decision, verdict before reasoning, few-shot from
the `train` split only, validated on held-out labels before it may gate, and not from the same
model family as the system under evaluation.

Groundedness judges have one characteristic bias worth targeting during validation: they pass long,
fluent, confidently-worded answers that contain an unsupported claim in the middle. Put several in
the dev split on purpose and confirm the judge catches them.

## Output contract

```markdown
## Generation (L2)
| Metric | Value | 95% CI | Judge | Gate |
|---|---|---|---|---|
| citation validity | 0.94 | [0.89, 0.97] | assert:citation-resolves | 1.00 FAIL |
| groundedness | 0.82 | [0.75, 0.87] | JDG-grounded-v2 (VALIDATED, TPR 0.88 TNR 0.91) | 0.95 FAIL |
| answer relevance | 0.91 | [0.85, 0.95] | JDG-relevance-v1 (VALIDATED) | 0.85 PASS |
| abstention correctness | 0.61 | [0.44, 0.76] | JDG-grounded-v2 | — |

bias-corrected groundedness: 0.85 (TPR 0.88, FPR 0.09)

### Failure attribution
| Cause | Cases | Share |
|---|---|---|
| retrieval — chunk never returned | 14 | 52% |
| ranking — returned below rank 5 | 7 | 26% |
| generation — contradicted a top-ranked chunk | 6 | 22% |

### Unsupported claims
| Case | Claim | Nearest retrieved chunk | Why it failed |
|---|---|---|---|
| EV-RAG-031 | "you'll get an email when processed" | pol-refund-014 | no chunk mentions email notification |
```

## Quality bar (self-check before reporting done)

- [ ] Citation validity run as a code assertion before any judge.
- [ ] Groundedness decided at claim level; the metric is all-claims-supported, not an average.
- [ ] Answer relevance is a separate judge, not folded in.
- [ ] Abstention cases present, and correct abstention scored as PASS.
- [ ] Every judge `VALIDATED`, with its TPR/TNR shown next to the number it produced.
- [ ] Bias correction applied and reported next to the observed rate.
- [ ] Every failure attributed to retrieval, ranking, generation, or corpus.
- [ ] Unsupported claims listed individually with the nearest retrieved chunk.
