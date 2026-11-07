---
name: sampling-traces
description: Pull a batch of real production or staging traces for error analysis, sampled for diversity rather than convenience, normalized to the EVAL-CONTRACTS trace format, and redacted at pull time. Use before open coding, or when /eval-explore runs.
version: 1.0.0
---

# Sampling Traces

> Read `.claude/EVAL-PROFILE.md` first — `§System under evaluation → Trace source`,
> `§Sample sizes`, `§Environments`. `.claude/EVAL-CONTRACTS.md` §4 defines the trace format.

## Action

Produce `.evals/traces/<TB-id>/raw.jsonl` — a batch of real traces, sampled so that reading them
tells you what this system does wrong, rather than what it does most often.

## Inputs — resolve before pulling (STOP conditions)

1. **A real trace source.** Production or staging logs, an OTel collector, a database table.
   No source → STOP. Say plainly: without traces, the failure taxonomy will be a list of failures
   somebody imagined, and every artifact built on it inherits that. The honest options are to ship
   behind a flag and collect traces, or to proceed and record "hypothetical" in every downstream
   artifact.
2. **Authorization** to read that data, per `§Environments`, plus whatever the organization
   requires for handling it.
3. **A target count** — `§Sample sizes → traces to code`, default 100.

## Step 1: Understand the population before sampling from it

Before pulling, find out: how many traces exist over what period, what the traffic looks like by
day and hour, and what dimensions vary (tenant, locale, intent, channel, input length).

A sample drawn without this is a sample from whatever happened to be at the top of the file — and
the top of a log file is one hour of one day, usually the hour someone was load-testing.

## Step 2: Stratify

Uniform random sampling of production traffic returns mostly happy path. That is a true picture of
the traffic and a useless one for error analysis: you spend most of your reading budget confirming
that the common case works.

Stratify across the dimensions that vary, and deliberately over-sample:

| Stratum | Why |
|---|---|
| long inputs and long outputs | where context limits, truncation, and drift live |
| sessions with retries or edits | the user telling you it went wrong |
| sessions with negative feedback, where collected | ground truth, free |
| unusual locales, tenants, data states | where assumptions baked into the prompt break |
| traces with tool errors or empty retrievals | the paths nobody designed |
| traces at the tail of the latency distribution | slow often means the system did something strange |
| plain happy path | a control group, so you can tell "always broken" from "broken here" |

Record the strata and their weights in `notes.md`. Rates computed later must be read against these
weights or they will overstate the failure rate — the sample was built to be failure-rich on
purpose.

## Step 3: Normalize

Map each trace into EVAL-CONTRACTS §4: `trace_id`, `ts`, `input`, `output`, `steps`, `meta`.

When the system emits OpenTelemetry GenAI spans, derive `steps` from the span tree and keep the
`gen_ai.*` attributes verbatim in `meta`. Do not lose the intermediate spans: the tool call that
returned nothing and the retrieval that returned the wrong chunk are usually the whole story, and
a trace flattened to input/output hides them.

## Step 4: Redact at pull time

Redaction happens here, once, before anything reads the batch. Replace, do not delete: a redacted
field that is present but masked keeps the trace structurally intact and readable.

Record in `notes.md` what was redacted and by what rule. A reviewer who hits a masked field needs
to know whether it was a name or an entire message.

## Step 5: Freeze

Write `.evals/traces/<TB-id>/raw.jsonl`, one JSON object per line, and `notes.md` with:

```
## Source        where from, what query, what period
## Strata        each stratum, its share of the population, its share of this sample, the weight
## Redaction     what was masked, by what rule
## Count         traces pulled, after de-duplication
## Excluded      what was dropped and why (malformed, test traffic, internal callers)
```

**Traces are evidence and are never edited after this point.** A trace that turns out to be
malformed is excluded in a new batch, with the exclusion recorded — not quietly fixed in place.

## Quality bar (self-check before reporting done)

- [ ] The batch spans more than one day and more than one hour of the day.
- [ ] Every stratum in the plan is actually represented; the ones that came back empty are named.
- [ ] `steps` survived normalization — spot-check three traces against the raw source.
- [ ] Internal test traffic and the team's own sessions are excluded, or explicitly kept and
      labelled. A demo conversation replayed 40 times will otherwise dominate the taxonomy.
- [ ] De-duplicated: identical inputs from a retry loop count once.
- [ ] The weights are written down. Without them, every rate computed downstream is wrong in a
      direction nobody will notice.
