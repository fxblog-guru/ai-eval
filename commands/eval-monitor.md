---
description: Sample live traffic, judge it offline with a validated judge, and compare production quality against the offline suite
argument-hint: <slug> [--window 7d] [--sample N]
---

> **Phase 6 — specified, not yet implemented.** Running it now STOPs with this message.

> Read `.claude/EVAL-PROFILE.md` first — `§Layers` (L6), `§Environments` (live sampling is
> opt-in), `§System under evaluation → Trace source`. EVAL-CONTRACTS §4 defines the trace format.

Close the loop: measure the system where it actually runs, and feed what you find back into the
next error-analysis cycle.

## This does not gate anything

L6 never blocks a deploy. It answers two questions that offline evaluation structurally cannot:

1. **Does the offline number predict the online one?** If the golden set says 88% and sampled
   production says 71%, the dataset does not represent the traffic — and that is a finding about
   the *evaluation*, not about the system.
2. **Is the input distribution drifting?** New intents, longer inputs, a locale nobody planned
   for. Drift in the inputs invalidates a dataset quietly, without any gate turning red.

## Sampling

Sample **asynchronously**, never in the request path — an evaluation that adds latency to a user's
request will be turned off the first time someone looks at a latency graph.

Stratify the sample rather than taking it uniformly: uniform sampling of production traffic
returns mostly happy path, which is the part already known to work. Over-sample the segments where
failure modes were found, and record the weights so rates are read correctly.

Sampling `prod` requires the `§Environments` opt-in and whatever data handling the organization
requires. Redaction happens at pull time and is recorded in the batch's `notes.md`.

## Judging

Only a `VALIDATED` judge may score production samples (EVAL-CONTRACTS §5.4). The bias correction
matters more here than anywhere else: online rates get quoted to people outside the team, in
contexts where nobody will ask what the judge's TPR was.

Where the product collects user feedback — thumbs, corrections, abandonment — correlate it against
the judge's verdicts. Low correlation is a finding about the judge, and it is the strongest
available signal that a judge which validated cleanly on curated labels does not transfer to real
traffic.

## The loop this closes

```
production traces  →  /eval-monitor  →  new failure modes  →  /eval-explore (next cycle)
                                     →  drift in inputs     →  /eval-data --bump
                                     →  judge disagreement  →  /eval-validate (re-label)
```

An evaluation system that never ingests production data measures a snapshot of the past, and gets
more confident about it over time.

## Done criteria (when implemented)

- The sample is stratified, the weights are recorded, and the redaction is documented.
- Online rates are reported with intervals and bias correction, alongside the offline rate from
  the same period.
- The offline/online gap is stated explicitly, with an interpretation.
- New failure modes are filed as trace notes for the next `/eval-explore`, not minted as FM ids
  here — FM ids are minted in one place only (EVAL-CONTRACTS §6).

Until Phase 6: pull production traces manually with `/eval-explore --batch` on a monthly cadence.
That gets most of the value; the automation is the part that makes it happen when nobody remembers.
