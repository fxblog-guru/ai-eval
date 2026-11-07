---
name: testing-failover
description: Break the provider on purpose and observe what the system does — whether the fallback engages, whether its output quality was ever evaluated, and whether a degraded answer is distinguishable from a normal one. Use inside /eval-nfr.
version: 1.0.0
---

# Testing Failover

> Read `.claude/EVAL-PROFILE.md` first — `§Layers` (L5), `§Models`, `§Environments`,
> `§Quality gates`. Requires an environment where faults may be injected.

## Action

Inject provider faults during a run and record what the system does, including whether anyone can
tell afterwards.

## The question nobody asks

Most LLM systems have a fallback: a second provider, a smaller model, a cached response, a canned
message. Almost none have **evaluated the fallback's output quality**.

That matters because the fallback path is taken exactly when the primary provider is having a bad
day — which is when load is highest and the most users are affected. The path that serves your
worst hour is usually the only one that was never measured.

## Step 1: Inject the faults that actually happen

| Fault | How | What to watch |
|---|---|---|
| timeout | delay the provider past the client timeout | does it retry? how many times? does it retry a **state-changing** call? |
| 429 rate limit | force the limit | back-off, or a retry storm that makes it worse |
| 500 error | return an error | fallback engages, or the error reaches the user raw |
| slow but successful | 10× latency, valid response | does the client time out and double-charge for a response that arrived? |
| **partial stream** | cut the stream mid-response | does the user get a truncated answer presented as complete? |
| malformed response | valid HTTP, unparseable body | handled, or a stack trace |
| provider down entirely | block the host | the full fallback path |

The **partial stream** case is the most under-tested and among the most damaging: a truncated
answer that reads as complete, saying "your refund will take" and stopping.

## Step 2: Record what the user gets, not just whether it recovered

Three very different outcomes look identical in an uptime graph:

| Outcome | Verdict |
|---|---|
| clear degraded-service message | good |
| correct answer from the fallback model | good, **if the fallback was evaluated** |
| **a plausible answer from a weaker model, unmarked** | the dangerous one |
| silent truncation presented as complete | the dangerous one |

## Step 3: Run the eval suite through the fallback path

This is the step that gives the skill its value, and it is one command:

```
/eval-run task --env staging --force-fallback
```

Run the **same dataset** with the primary provider disabled. You now have a task-success number for
the degraded path, comparable to the normal one because the dataset and judges are identical.

```markdown
| Path | task success | 95% CI | cost/request | p95 latency |
|---|---|---|---|---|
| primary (claude-sonnet-5) | 0.87 | [0.81, 0.91] | $0.021 | 4.1s |
| fallback (smaller model) | 0.54 | [0.46, 0.62] | $0.004 | 2.2s |
```

If that gap is large — and it usually is — the fallback is not a fallback, it is a different and
much worse product served silently to users during incidents. That is a product decision someone
should make knowingly rather than discover.

## Step 4: Check that degraded answers are marked

Can anyone tell, afterwards, that a response came from the fallback?

- Does the response carry a marker the client can render?
- Does the trace record which provider served it?
- Can you count fallback-served requests for a given day?

If the answer is no, then production quality metrics silently mix two systems, and a bad week of
provider availability looks like a quality regression that nobody can explain — the investigation
goes to the prompt, and the prompt was fine.

## Step 5: Watch for retried side effects

A timeout followed by a retry on a **state-changing** call is a duplicate action: two refunds, two
tickets, two emails.

```python
assert called.count("refund_order") <= 1
assert idempotency_key_present("refund_order")
```

This is where a latency problem turns into a money problem, and it only appears under fault
injection.

## Step 6: Never in production

Fault injection runs only where `§Environments` authorizes it. Deliberately breaking a provider
connection in `prod` is an outage you caused.

## Quality bar (self-check before reporting done)

- [ ] All seven fault types injected, including partial stream and slow-but-successful.
- [ ] The eval suite re-run through the fallback path on the same dataset with the same judges.
- [ ] The primary/fallback quality gap reported with intervals, alongside cost and latency.
- [ ] Whether degraded responses are marked and countable is stated as a fact.
- [ ] Retry behaviour on state-changing calls asserted; idempotency verified.
- [ ] Environment authorization checked; never run against production.
- [ ] Every finding names what a user would experience, not only what the system did.
