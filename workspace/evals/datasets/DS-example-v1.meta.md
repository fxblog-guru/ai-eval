# DS-example-v1 — provenance

> Seed dataset. Three cases is far below the 100 a gated dataset needs; this exists so the
> scaffold runs, not so it gates anything.

## How it was built
Two cases pulled from the trace batch that produced FM-001, one synthetic happy-path control.

## Dimensions
| Dimension | Values | Derived from | Why it changes the answer |
|---|---|---|---|
| intent | status | the batch | the only intent this seed covers |
| data_state | found, not-found, no-id-given | the batch | FM-001 only fires when the tool returns nothing |
| length | short, long | the batch | long messages bury the id mid-text |

## FM -> dimension requirements
| FM | Requires |
|---|---|
| FM-001 | data_state in {not-found, no-id-given} |

## Counts per FM
| FM | Cases |
|---|---|
| FM-001 | 2 |
| (happy path) | 1 |

## Sampling weights
| Stratum | Share of traffic | Share of dataset | Weight |
|---|---|---|---|
| happy path | 96% | 33% | 2.88 |
| FM-001 | 4% | 67% | 0.06 |

Rates from this dataset must be read against these weights or they overstate the failure rate:
it was built failure-rich on purpose.

## Leakage check
3 case inputs checked against the system prompt, its few-shot examples, and all judge
train.jsonl files. 0 hits.

## Changes from v0
First version.
