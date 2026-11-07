---
name: measuring-latency-cost
description: Measure what an LLM system costs to run — latency conditioned on output length, token and cost distributions rather than means, and time-to-first-token where the surface streams — driving the existing k6 or Locust repos rather than adding a third load tool. Use inside /eval-nfr.
version: 1.0.0
---

# Measuring Latency and Cost

> Read `.claude/EVAL-PROFILE.md` first — `§Layers` (L5), `§Quality gates` (p95 latency, cost
> per request), `§Environments` (load authorization), `§Budget`, `§Models`.

## Action

Report latency, token use and cost as **distributions conditioned on output length**, with the
gates encoded as thresholds in the load tool so a run fails on its own.

## Reuse, do not rebuild

`agentic-fx` already has `gatling-performance-testing` and `locust-performance-testing`. Drive one
of them against the system's entry point. What is new here is not load generation; it is what gets
measured and how it is sliced.

## What differs from ordinary performance testing

| Ordinary load test | An LLM system |
|---|---|
| latency roughly stable per endpoint | latency scales with **output** tokens — it depends on what the model decides to say |
| cost per request is a rounding error | cost per request is a line item, and a prompt change can double it silently |
| throughput bounded by your infrastructure | throughput bounded by **someone else's rate limit**, which can change without notice |
| a dependency failure is rare and loud | a provider degradation is common, quiet, and looks like a quality problem |

## Step 1: Condition latency on output length

A p95 pooled over one-line answers and long summaries describes neither. Bucket by output tokens:

```markdown
| Output tokens | n | p50 | p95 | p99 | TTFT p95 |
|---|---|---|---|---|---|
| 0–100 | 412 | 0.9s | 1.8s | 2.4s | 0.4s |
| 100–400 | 380 | 2.4s | 4.1s | 5.8s | 0.4s |
| 400+ | 108 | 6.1s | 11.2s | 18.9s | 0.5s |
| pooled | 900 | 2.1s | 7.4s | 16.1s | 0.4s |
```

The pooled p95 of 7.4s is a number nobody can act on. The buckets say: short answers are fine, long
ones are not, and the fix is either shorter outputs or streaming.

**Time to first token** is separate and matters more than total latency wherever the surface
streams — it is what a user perceives as responsiveness. A system with 11s total and 0.5s TTFT
feels fast; the same total with 9s TTFT feels broken.

## Step 2: Distributions, not means

```markdown
| Metric | p50 | p95 | p99 | max |
|---|---|---|---|---|
| input tokens | 1,840 | 3,200 | 6,100 | 31,400 |
| output tokens | 180 | 520 | 890 | 2,048 |
| cost per request | $0.009 | $0.021 | $0.043 | $0.19 |
```

The mean hides the tail that dominates the bill. A p99 at 20× the median usually has a cause worth
finding — one intent that retrieves far too much context, or one user pasting entire documents.

Report **cost per 1,000 requests** too. It is the number a budget conversation actually uses.

## Step 3: Recompute cost whenever the model changes

Cost per request is a function of the pinned model's rates. When `/eval-drift` evaluates a model
change, the cost delta is half the answer: a model that is 3 points better on task success and 2.4×
the cost is a decision, not an upgrade.

Report cost side by side with quality in every drift comparison.

## Step 4: Rate-limit behaviour

Push to the ceiling and record what happens. The four outcomes are very different:

| Behaviour | Verdict |
|---|---|
| queues, degrades gracefully | good |
| fails fast with a clear error | acceptable |
| retries silently and multiplies cost | expensive, and invisible until the bill |
| **returns something plausible and wrong** | **the dangerous one** |

The last is specific to LLM systems: a fallback path that returns a generic answer when the primary
is throttled, with nothing marking it as degraded. Users cannot tell, and neither can the quality
suite unless it is looking.

## Step 5: Cost regression is a quality gate

A prompt change that adds 600 tokens of instructions to every request raises cost by 30% and
changes no quality metric. Nothing turns red; the bill arrives a month later.

Gate on it: `cost_per_request_ci_upper` against the ceiling in `§Quality gates`. This is the one
gate that compares an **upper** bound, because the risk is the value being too high.

## Step 6: Encode the gates in the runner

Put the thresholds into the load tool so the run fails on its own, rather than producing a number
someone has to remember to check:

```javascript
// k6
export const options = {
  thresholds: {
    'http_req_duration{bucket:short}': ['p(95)<2000'],
    'http_req_duration{bucket:long}':  ['p(95)<12000'],
    'llm_cost_per_request':            ['p(95)<0.025'],
    'llm_ttft':                        ['p(95)<600'],
  },
};
```

## Step 7: Authorization

`§Environments` must authorize load testing for the target env. `prod` is not authorized by
default, and the CI templates keep L5 manual — a scheduled load test against a shared environment
degrades it for everyone using it.

## Quality bar (self-check before reporting done)

- [ ] Latency bucketed by output length; the pooled figure shown but not used as the headline.
- [ ] TTFT reported separately wherever the surface streams.
- [ ] Token and cost reported as distributions with p99 and max, not means.
- [ ] Cost per 1,000 requests stated.
- [ ] Rate-limit behaviour observed and classified, not read from configuration.
- [ ] Cost regression gated on the interval's **upper** bound.
- [ ] Thresholds encoded in the load tool so the run self-fails.
- [ ] Environment load authorization verified before the run.
