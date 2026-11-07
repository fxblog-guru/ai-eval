---
name: publishing-to-verdict
description: Write CTRF JSON from an eval run and upload it to the verdict report hub so eval results get history, flakiness scoring, and quality gates alongside every other test type. Use at the end of /eval-run.
version: 1.0.0
---

# Publishing to Verdict

> Read `.claude/EVAL-PROFILE.md` first — `§Test management & reporting`.
> `.claude/EVAL-CONTRACTS.md` §11 defines the CTRF mapping.
> `verdict` is the `agentic-fx` report hub: it ingests CTRF JSON, JUnit XML, and Playwright JSON.

## Action

Write `runs/<suite>/<slug>/<run-id>/ctrf.json` and upload it with the evidence directory.

## Why eval results belong in the same hub as every other test

The team already has one place where test results accumulate. Putting eval runs there gives, for
free, three things this bundle would otherwise have to build:

1. **History** — the pass rate of this suite over the last 40 runs, per FM, without anyone
   maintaining a spreadsheet.
2. **Flakiness scoring** — verdict computes flakiness across runs, which for an LLM system **is**
   the non-determinism measurement. A case whose outcome varies run to run at fixed temperature is
   exactly what verdict's flaky score is designed to surface.
3. **Quality gates and a shared vocabulary** — the release conversation stays in one place, and
   eval results sit next to the e2e and API results for the same build.

## Step 1: Map the run to CTRF

One **test result per case per repeat**. Not one per case: the repeats are the point, and
collapsing them discards the flakiness signal verdict exists to compute.

```json
{
  "results": {
    "tool": { "name": "agentic-fx-ai-eval", "version": "1.0.0" },
    "summary": { "tests": 500, "passed": 412, "failed": 71, "skipped": 0, "pending": 0, "other": 17,
                 "start": 1758000000000, "stop": 1758003600000 },
    "tests": [
      {
        "name": "EV-TASK-014",
        "status": "failed",
        "duration": 2140,
        "message": "assert:order-id-exists — output contains order 88999, not present in any tool result",
        "trace": "runs/task/refunds/2026-09-16-1420/traces/EV-TASK-014/3.json",
        "suite": "task-refunds",
        "tags": ["fm:FM-001", "judge:JDG-grounded-v2", "dataset:DS-refunds-v3",
                 "model:<exact id>", "repeat:3", "layer:L2"],
        "extra": { "repeat": 3, "of": 5, "assertions": ["order-id-exists"],
                   "tokens_in": 1840, "tokens_out": 212, "cost": 0.0091 }
      }
    ],
    "environment": { "testEnvironment": "staging", "buildName": "<prompt version>",
                     "commit": "<sha>", "branch": "<branch>" }
  }
}
```

### The tags carry the analysis

| Tag | Enables |
|---|---|
| `fm:FM-001` | per-failure-mode history and regression tracking across runs, in the hub |
| `judge:JDG-grounded-v2` | spotting the moment a judge version changed and rates moved with it |
| `dataset:DS-refunds-v3` | never comparing runs across dataset versions by accident |
| `model:<id>` | the model-upgrade view, which is what `/eval-drift` answers ad hoc |
| `layer:L2` | filtering contract runs from task runs from safety runs |
| `unvalidated` | marking every result whose judge was not validated |

Tags are the whole reason this integration is worth doing. Without them the hub shows a pass rate;
with them it answers "which failure mode regressed when we changed model".

## Step 2: Status mapping

| Eval outcome | CTRF status |
|---|---|
| `PASS` | `passed` |
| `FAIL` | `failed` |
| `ERROR` | `other` — **never** `failed`. A provider timeout is not a quality signal. |
| `SKIPPED` | `skipped` |

`FLAKY` is not a per-repeat status: it is the roll-up across repeats. Emit each repeat with its own
true status and let verdict compute flakiness from them. That is what its flaky score is for, and
pre-computing it here would both duplicate and weaken it.

## Step 3: The UNVALIDATED marker

When any judge in the suite is not `VALIDATED`:

- add the tag `unvalidated` to every result it decided,
- set the suite-level gate to `NOT-EVALUABLE` rather than letting verdict's gate compute a pass,
- put it in the upload message.

The hub must not show a green run whose numbers came from an uncalibrated judge. That green is
precisely the outcome EVAL-CONTRACTS §5.4 exists to prevent, and it is more dangerous here than in the
local report because more people see it and none of them will check.

## Step 4: Upload with evidence

```bash
export VERDICT_URL=... VERDICT_API_KEY=...
verdict upload \
  --project "<system slug>" \
  --type eval \
  --env "<env>" \
  --tag "<suite>" --tag "layer:<L>" --tag "dataset:<DS id>" \
  runs/<suite>/<slug>/<run-id>/ctrf.json \
  --evidence runs/<suite>/<slug>/<run-id>
```

`--evidence` uploads the full traces. For an eval run this matters more than for an e2e run: the
artifact someone needs when a case fails is the model's actual output and the steps that produced
it, and a message field cannot carry it.

## Step 5: Handle the failure honestly

An upload failure is **reported**, never swallowed. The run is still valid and its local artifacts
are complete; say that, give the local path, and give the exact command to retry.

Write `.verdict-run.json` with the run id and URL, as the verdict CLI does elsewhere, so the
scorecard can link to it.

## Quality bar (self-check before reporting done)

- [ ] One CTRF result per case per repeat.
- [ ] Every result tagged with FM, judge, dataset, model, layer, repeat.
- [ ] `ERROR` mapped to `other`, never `failed`.
- [ ] Flakiness left to verdict, not pre-computed.
- [ ] `unvalidated` tag applied wherever it applies, and the gate set to `NOT-EVALUABLE`.
- [ ] Evidence directory uploaded.
- [ ] `message` on failures names the assertion or judge id and the specific value — it is what a
      person reads first, often the only thing they read.
- [ ] Upload failures reported with the retry command.
