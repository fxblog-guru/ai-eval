---
description: Measure latency, token use, cost per request, and behaviour under rate limits or provider failure
argument-hint: <slug> --env <env> [--profile smoke|load|soak] [--force-fallback]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Layers` (L5), `§Quality gates` (p95 latency, cost per
> request), `§Environments` (load authorization), `§Budget`, `§Models`.

Measure what an LLM system costs to run, and what it does when the provider does not cooperate.

## Reuse, do not rebuild

`agentic-fx` already has `gatling-performance-testing` and `locust-performance-testing`. This
command drives one of them against the system's entry point rather than introducing a third load
tool. What is new is not the load generation; it is what gets measured and how it is sliced.

## What differs from ordinary performance testing

| Ordinary load test | An LLM system |
|---|---|
| latency roughly stable per endpoint | latency scales with **output** tokens — it depends on what the model decides to say |
| cost per request is a rounding error | cost per request is a line item, and a prompt change can double it silently |
| throughput bounded by your infrastructure | throughput bounded by **someone else's rate limit** |
| a dependency failure is rare and loud | a provider degradation is common, quiet, and looks like a quality problem |

## Arguments

- **`<slug>`** — the system or feature slug
- **`--env <env>`** — required; must authorize load testing
- `--profile` — `smoke` · `load` · `soak`
- `--force-fallback` — run with the primary provider disabled, to measure the degraded path

## Preconditions (check before delegating)

- [ ] L5 enabled in `§Layers`
- [ ] `§Environments` authorizes load testing for `--env` — a scheduled load test against a shared
      environment degrades it for everyone using it
- [ ] `§Quality gates` has p95 latency and cost-per-request values to encode as thresholds
- [ ] for `--force-fallback`: fault injection is permitted in this environment

## Execution

Delegate to `eval-reporter`: `measuring-latency-cost`, then `testing-failover` when faults are
being injected.

**Report latency conditioned on output length.** A p95 pooled over one-line answers and long
summaries describes neither, and is a number nobody can act on. Bucket it, and report
time-to-first-token separately wherever the surface streams — that is what a user perceives.

**Report tokens and cost as distributions, not means.** The mean hides the tail that dominates the
bill; a p99 at 20× the median usually has one findable cause.

## The question this command exists to ask

`--force-fallback` re-runs the **same eval dataset with the same judges** through the degraded path:

```
| Path | task success | cost/request | p95 |
|---|---|---|---|
| primary   | 0.87 [0.81, 0.91] | $0.021 | 4.1s |
| fallback  | 0.54 [0.46, 0.62] | $0.004 | 2.2s |
```

Fallback paths are almost never quality-evaluated, and the fallback is what serves users during an
incident — when load is highest and the most people are affected. If that gap is large, the
fallback is a different and much worse product served silently, which is a product decision someone
should make knowingly rather than discover.

## Done criteria (exit gate)

- Latency bucketed by output length; the pooled figure shown but not used as the headline.
- TTFT reported separately for streaming surfaces.
- Token and cost distributions with p99 and max; cost per 1,000 requests stated.
- Rate-limit behaviour **observed and classified**, not read from configuration — and the dangerous
  outcome named if present: returning something plausible and wrong when throttled.
- Retry behaviour on **state-changing** calls asserted; idempotency verified. A timeout plus a
  retry is two refunds.
- Cost regression gated on the interval's **upper** bound — the only gate here that does, because
  the risk is the value being too high.
- Whether degraded responses are **marked and countable** stated as a fact. If they are not,
  production quality metrics silently mix two systems, and a bad week of provider availability
  looks like a quality regression nobody can explain.
- Thresholds encoded in the load tool so the run self-fails.

Report back: the latency table by bucket, cost distribution and per-1000 figure, rate-limit
classification, the primary/fallback quality gap if measured, and any unmarked degradation.
