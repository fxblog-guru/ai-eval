---
description: Evaluate a retrieval pipeline separately from the generation on top of it — Recall@k, MRR, nDCG, then citation validity and groundedness
argument-hint: <slug> [--stage retrieval|generation|both] [--k N]
---

> Read `.claude/EVAL-PROFILE.md` first — `§RAG`, `§Layers` (L1, L2), `§Quality gates`,
> `§Models`. The RAG theory this measures against lives in `agentic-fx/rag-reference-guide`;
> it is not restated here.

Evaluate the retrieval layer and the generation layer **separately**, because they fail separately
and the fix is different in each case.

## Why the split is the whole point

A wrong answer from a RAG system has causes that one aggregate score cannot tell apart:

| Symptom | Retrieval metrics | Groundedness | Fix belongs to |
|---|---|---|---|
| the right chunk was never retrieved | Recall@k low | nothing to ground in | chunking, embedding, k, query rewriting |
| retrieved at rank 8 and ignored | Recall@k fine, **MRR low** | low | ranking, reranker, context order |
| retrieved at rank 1 and contradicted | fine | low | the prompt, the model, or the corpus |
| retrieved and used correctly, still unhelpful | fine | fine | the corpus lacks it |

Teams that measure only end-to-end quality spend weeks tuning a prompt for a problem that was in
the retriever.

## Arguments

- **`<slug>`** — the system or feature slug
- `--stage` — `retrieval` (L1) · `generation` (L2) · `both` (default)
- `--k N` — override the retrieval depth. Default is `§RAG → k`; measure at the `k` production
  uses, not a convenient one.

## Preconditions (check before delegating)

- [ ] `§System under evaluation → Retrieval` is `yes` and `§RAG` is filled
- [ ] for `--stage retrieval`: a **labelled query set** exists — queries with the chunk ids that
      should be retrieved. Missing → STOP. Building one is the highest-value labelling work in a
      RAG system, and 50–100 queries is enough to start.
- [ ] **chunk ids are stable across index rebuilds** — if not, STOP: the labels expire on every
      rebuild and nothing here is measurable. That is an indexing-design finding, not a limitation
      to work around.
- [ ] corpus version and index build date are known and recordable

## Execution

Delegate to `rag-evaluator`.

**Retrieval (L1)** runs `evaluating-retrieval`: Recall@k and Precision@k for presence, MRR and
nDCG@k for rank. No LLM, no judge, deterministic given a fixed index — treat a retrieval regression
as an ordinary code regression. Includes `known-absent` queries, so the retriever is also judged on
what it does when the answer is not in the corpus.

**Generation (L2)** runs `evaluating-groundedness`: citation validity as a free code assertion
first, then claim-level groundedness, then answer relevance as a separate judge. Every judge is
subject to the trust gate (EVAL-CONTRACTS §5.4).

## Done criteria (exit gate)

- Retrieval and generation reported in **separate sections, never averaged**.
- Both presence and rank metrics reported; when they disagree, the disagreement is named as the
  finding — it points at ranking, not recall.
- Results broken down by query segment, not only overall. An overall Recall@k of 0.88 routinely
  hides 0.95 on queries phrased in the documentation's words and 0.52 on queries phrased the way
  users write.
- Groundedness decided at **claim level**; the metric is all-claims-supported, not an average.
- Correct abstention scored as PASS, not as failure to answer.
- **Every generation failure attributed** to retrieval, ranking, generation, or corpus.
- Corpus version, index build date, and the exact embedding model version recorded.
- Individual misses listed: the query, the expected chunk, the rank actually returned.

Report back: the retrieval table and the generation table separately, the failure attribution
breakdown, the worst query segment, and the single system to change first.
