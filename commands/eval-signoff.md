---
description: Assemble the evaluation evidence for a release decision and hand it to stlc's /qa-signoff
argument-hint: <release-id> [--slug <slug>]
---

> Read `.claude/EVAL-PROFILE.md` first — `§Quality gates`, `§Risk tier`,
> `§Test management & reporting`. EVAL-CONTRACTS §12 defines the handoff.

Assemble what a release decision needs from the evaluation side. **This command does not decide
anything.** The release decision belongs to `/qa-signoff` in `agentic-fx/stlc`; this produces the
evidence it consumes.

## Arguments

- **`<release-id>`** — the release being signed off
- `--slug` — the system slug (default: `§Project → System slug`)

## Preconditions

- [ ] a scorecard exists for the current build
- [ ] every layer that `§Risk tier` makes mandatory has been run, or the gap is stated explicitly
- [ ] `§Test management & reporting → QA lifecycle bundle` names `stlc`, or `none` — with `none`,
      this command prints the evidence bundle and stops there

## Output — the evidence bundle

```
## Verdict per suite     each enabled suite: PASS | FAIL | NOT-EVALUABLE, with the deciding gate
## Judge trust           every judge that contributed a number: version, TPR/TNR, validation state
## Coverage              FMs covered, FMs open with no case, layers required but not run
## Regression            per-FM deltas vs the release baseline, with intervals
## Unresolved            red-team findings at critical/high; blocking audit findings
## Evidence              run paths, scorecard paths, verdict URLs
## Caveats               what these numbers do NOT tell you
```

## `## Caveats` is mandatory and is not boilerplate

Write what this evaluation could not see, specifically. For example: the dataset was built from
staging traces and production traffic skews longer; L3 is disabled so multi-turn tool use is
unmeasured; one judge is `UNVALIDATED` so the tone gate is `NOT-EVALUABLE`; the retrieval corpus
was rebuilt after the baseline was frozen.

A sign-off package without caveats implies coverage that no evaluation has. The person accepting
the risk is entitled to know the shape of what was not measured.

## Refuse to summarize away a NOT-EVALUABLE

If any mandatory suite is `NOT-EVALUABLE`, the bundle says so at the top, in the first line. It is
not averaged into an overall percentage, not shown as amber, and not omitted because the other
suites passed. Someone is about to accept risk on behalf of users; they need to know which part of
the picture is missing rather than wrong.

## Handing off

With `stlc` configured: hand the bundle to `/qa-signoff <release-id>` as evidence, with every path
resolvable from the repo root. The decision, the record, and the accountability live there.

Report back: the bundle path, the per-suite verdicts, any `NOT-EVALUABLE`, the unresolved
critical/high findings, and the exact `/qa-signoff` invocation to run next.
