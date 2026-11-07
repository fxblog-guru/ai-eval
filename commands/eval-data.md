---
description: Build a versioned, immutable eval dataset from the failure taxonomy — real trace inputs plus dimension-based synthetic cases
argument-hint: <slug> [--bump] [--suite TASK|AGENT|RAG|SAFE|NFR]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Sample sizes`, `§Models` (the generation model),
> `§RAG` when retrieval is enabled. EVAL-CONTRACTS §7 defines the format and the rules.

Produce `.evals/datasets/DS-<slug>-vN.jsonl` and its `.meta.md`. Step 3 of the pipeline.

## Arguments

- **`<slug>`** — kebab-case; names the dataset and appears in every run that uses it
- `--bump` — produce `v(N+1)` from the existing highest version; requires a stated reason, which
  goes into `.meta.md`
- `--suite` — which suite this dataset feeds (default `TASK`)

## Preconditions (check before delegating)

- [ ] `.evals/taxonomy/INDEX.md` exists with at least one `open` FM — no taxonomy, STOP and route
      to `/eval-explore`
- [ ] `.evals/system-card.md` exists — `## Hard policies` supply the `SAFE` cases
- [ ] `<slug>` is kebab-case
- [ ] for `--bump`: the previous version exists and a reason was given

## Execution

Delegate to `dataset-designer`: `designing-eval-dimensions` → `curating-golden-sets` →
`generating-synthetic-cases`.

**Dimensions come from the traces**, not from a template. Read what actually varies across real
inputs — intent, data state, locale, length, user expertise, edge conditions — then generate one
case per tuple across those dimensions.

Never ask a model for "50 varied examples". That reliably produces 50 rephrasings of one case: a
dataset that looks large and covers one thing.

## Done criteria (exit gate)

- Every **open** FM has at least one case. An FM with no case is a failure mode the suite will
  report as fine, forever.
- `origin: trace` share ≥ 30%, or the user has stated in writing that no traces exist and accepts
  a hypothetical dataset — recorded in `.meta.md`.
- Case count ≥ 100 for a gated dataset (`§Sample sizes`). Below 30 the dataset cannot gate at all.
- **Leakage check run and reported**: no case input appears verbatim in the system prompt, its
  few-shot examples, or any judge's `train.jsonl`.
- Every case has `case_id`, `input`, `fm`, `expect`, `origin`; synthetic cases also have
  `dimensions`.
- `.meta.md` records the dimension list, counts per FM, the sampling weights, and the delta from
  `v(N-1)`.

## Immutability

`DS-<slug>-vN` is frozen the moment a run references it. Fixing one typo is `v(N+1)`, not an edit.
A dataset that quietly changed between two runs makes those runs incomparable, and nothing in
either output will say so.

Report back: dataset id and path, case count, per-FM counts, the `origin` breakdown, the leakage
check result, and any FM still uncovered — then point at `/eval-judge`.
