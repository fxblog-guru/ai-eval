# DS-example-retrieval-v1 — provenance

> Seed labelled query set for L1. Three queries is far below the 50–100 a real retrieval
> evaluation needs; this exists so the scaffold runs.

## How it was built
Two queries pulled from the trace batch, one handwritten `known_absent` control.

## Corpus
corpus v7 · index built 2026-09-14 · embedding `text-embedding-example-v2` · k=10 · no reranker

Chunk id stability verified against the v6 build: ids are content-hash based and survive a rebuild.
Without that property the labels expire on every rebuild and L1 is not measurable at all.

## Labels
| Kind | Count | Used by |
|---|---|---|
| relevant | 3 | Recall@k, Precision@k, MRR, nDCG |
| partial | 1 | graded nDCG only |
| known_absent | 1 | abstention rate and score separation |

## Changes from v0
First version.
