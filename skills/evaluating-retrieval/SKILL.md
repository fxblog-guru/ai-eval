---
name: evaluating-retrieval
description: Measure the retriever on its own, with no LLM in the loop — Recall@k and Precision@k for presence, MRR and nDCG@k for rank — against a labelled query set, so a wrong answer can be attributed to retrieval rather than blamed on the prompt. Use inside /eval-rag --stage retrieval.
version: 1.0.0
---

# Evaluating Retrieval

> Read `.claude/EVAL-PROFILE.md` first — `§RAG` (retriever, corpus, k, labelled query set,
> retrieval gates), `§Layers` (L1). The RAG theory lives in `agentic-fx/rag-reference-guide`;
> this skill measures against it rather than restating it.

## Action

Run the retriever alone over a labelled query set and report presence **and** rank metrics with
intervals, into the L1 section of the run summary.

## Why the LLM must not be in the loop here

The moment a generator is involved, you can no longer tell a retrieval failure from a generation
failure — which is the entire reason to measure this stage separately. Call the retriever directly,
collect the ranked chunk ids, and compare to the labels. No model, no judge, no calibration.

This also makes the measurement **deterministic** given a fixed index. A retrieval regression is an
ordinary code regression: reproducible, bisectable, and fixable without anyone discussing prompts.

## Inputs — resolve before starting (STOP conditions)

1. **A labelled query set**: `.evals/datasets/DS-<slug>-retrieval-vN.jsonl`, each row a query plus
   the chunk ids that *should* be retrieved.
   No labelled set → STOP. Building one is the highest-value labelling work in a RAG system, and
   50–100 queries is enough to start. Guessing instead produces a recall number with nothing
   behind it.
2. **Stable chunk ids.** If ids change on every index rebuild, the labels expire immediately and
   nothing here is measurable. Report it as a **blocking** finding — this is an indexing-design
   problem, not an evaluation limitation to work around.
3. **Corpus version and index build date.** Recorded in the run. A comparison across two different
   index builds is not a comparison, and no metric will say so.
4. `k` from `§RAG`. Measure at the `k` the system actually uses in production, not a convenient one.

## Step 1: Build the labelled set from real queries

Take queries from the trace batch, not from imagination. For each, a human marks which chunks
genuinely answer it.

Three label kinds, and the distinction matters:

| Label | Meaning | Used by |
|---|---|---|
| **relevant** | contains the answer | Recall, Precision, MRR, nDCG |
| **partially relevant** | contributes but is insufficient alone | nDCG (graded), not binary Recall |
| **known-absent** | the corpus genuinely does not answer this | the abstention check below |

**`known-absent` queries are not optional.** A retriever is also judged on what it does when the
answer is not there, and a system that always returns its top-k regardless is guaranteeing that
some answers are grounded in irrelevant text. Include 10–20% of these.

## Step 2: Presence metrics

```
Recall@k    = |retrieved@k ∩ relevant| / |relevant|      did we get them at all
Precision@k = |retrieved@k ∩ relevant| / k               how much of the context is noise
```

Recall@k is the one that bounds everything downstream: a chunk that was never retrieved cannot be
used, no matter how good the prompt is. It is the ceiling on the whole system.

Precision@k matters for a different reason than it looks: low precision means the generator is
reading mostly irrelevant text, which raises cost, raises latency, and measurably increases the
chance it grounds an answer in the wrong chunk.

## Step 3: Rank metrics — where presence-only measurement misleads

```
MRR     = mean(1 / rank of the first relevant chunk)
nDCG@k  = DCG@k / ideal DCG@k     (graded, so partial relevance counts)
```

A correct chunk at position 8 of 10 counts as a full hit for Recall@k and is frequently ignored by
the generator. **Recall@k = 0.95 with MRR = 0.31 is a retriever that looks excellent and behaves
badly**, and it is a common shape — especially with a large `k` chosen to "be safe".

Report both families, always. When they disagree, the disagreement *is* the finding: it points at
ranking and reranking, not at recall.

## Step 4: The abstention check

For `known-absent` queries, report what the retriever returns and what the similarity scores look
like. Two useful numbers:

- **abstention rate** — how often the system returns nothing or flags low confidence
- **score separation** — the gap between top scores on answerable vs known-absent queries

No separation means no threshold can ever distinguish them, which means the generator will receive
confident-looking irrelevant context and behave accordingly. That is a retriever-design finding,
and it is invisible to Recall@k.

## Step 5: Report by query segment, not only overall

Break results down by the dimensions from `designing-eval-dimensions` — query length, intent,
whether the query uses corpus vocabulary or the user's own words, locale.

An overall Recall@k of 0.88 routinely hides 0.95 on queries phrased in the documentation's own
terms and 0.52 on queries phrased the way users actually write. The second number is the product.

## Step 6: Pin the configuration

Record in the run: retriever type and version, embedding model **and its exact version**, `k`,
chunk size and overlap, reranker if any, index build date, corpus version, and any query-rewriting
step.

Changing an embedding model silently invalidates every historical retrieval number — the vectors
mean something different — and nothing about the metrics will look wrong.

## Output contract

Into the run summary, an L1 section:

```markdown
## Retrieval (L1)
corpus v7 · index built 2026-09-14 · embedding <exact model id> · k=10 · reranker: none

| Metric | Value | 95% CI | Gate | Verdict |
|---|---|---|---|---|
| Recall@10 | 0.88 | [0.82, 0.92] | 0.90 | FAIL |
| Precision@10 | 0.31 | [0.26, 0.37] | — | — |
| MRR | 0.64 | [0.57, 0.70] | 0.60 | PASS |
| nDCG@10 | 0.71 | [0.65, 0.76] | 0.70 | NOT-EVALUABLE |

### By segment
| Segment | Recall@10 | MRR | n |
|---|---|---|---|
| query uses doc vocabulary | 0.95 [0.89, 0.98] | 0.78 | 60 |
| query in user's own words | 0.52 [0.41, 0.63] | 0.35 | 40 |

### Abstention (known-absent queries, n=18)
returned chunks anyway: 18/18 · score separation: none (0.71 vs 0.69 mean top score)

### Misses
| Query | Expected chunk | Rank returned | Note |
|---|---|---|---|
| "how long for a card refund" | pol-refund-014 | not in top 10 | doc says "payment card", query says "card" |
```

The `### Misses` table is what someone acts on. Aggregate metrics say whether to worry; the misses
say what to change.

## Quality bar (self-check before reporting done)

- [ ] No LLM was called anywhere in this stage.
- [ ] Both presence (Recall@k, Precision@k) and rank (MRR, nDCG@k) reported.
- [ ] Every metric carries an interval and an `n`.
- [ ] Results broken down by query segment, not only overall.
- [ ] `known-absent` queries included, with abstention rate and score separation.
- [ ] Full configuration pinned, including the exact embedding model version.
- [ ] Individual misses listed with the expected chunk and the rank actually returned.
- [ ] Chunk id stability verified against the previous index build.
