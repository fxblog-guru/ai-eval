# EVAL-PROFILE.md — agentic-fx-ai-eval configuration

Every agent, command, and skill in this bundle reads this file first. Fill it in for your system;
keep the section headings exactly as written (skills reference them by name, e.g.
"EVAL-PROFILE §Judge thresholds"). Values marked `(default)` are assumed when left untouched.

## Project

- **Name:** `<the AI system being evaluated>`
- **One-liner:** `<what it does for a user, in their words>`
- **System slug:** `<lowercase-kebab>` — used as the verdict project name and in artifact paths
- **Eval root:** `.evals/` (default) — all evaluation artifacts live under this folder
- **Artifact language:** `en` (default) — the language skills write artifact PROSE in (system card,
  failure-mode statements, scorecard narrative). Set to your team's language (e.g. `vi`).
  Structural tokens stay English regardless — headings, ids (FM/EV/DS/JDG), table columns,
  and the status vocabulary in EVAL-CONTRACTS.md §14 — because parsers match them byte-exact.

## System under evaluation

- **Surface:** `chat | api | agent | batch` — what the caller talks to
- **Entry point:** `<the function, endpoint, or CLI the runner invokes>`
- **Adapter:** `.evals/scripts/shared/providers/<name>.py` — the thin function the runner calls.
  It takes a case `input` and returns `{output, steps, meta}` per EVAL-CONTRACTS §4.
- **Prompt source:** `<path to the system prompt / template, version-controlled>`
- **Prompt version key:** `<how a prompt version is identified — a git sha, a file header, a const>`
- **Tools the system may call:** `<one line each: name · side effect · permission required>`
- **Retrieval:** `yes | no` — when yes, fill §RAG below
- **Trace source:** `<where production traces come from: a log store, an OTel collector, a DB table>`
- **Source repo (read-only grounding):** `<path — used to verify prompts, tools, and guardrails; never modified>`

## Models

| Role | Provider | Model id | Temperature | Notes |
|---|---|---|---|---|
| system under evaluation | `<provider>` | `<exact model id>` | `<temp>` | pinned in every suite |
| judge (default) | `<provider>` | `<exact model id>` | `0` | MUST NOT be the same family as the system in gated suites |
| synthetic data generation | `<provider>` | `<exact model id>` | `<temp>` | generation only, never judging |
| user simulator (L3) | `<provider>` | `<exact model id>` | `<temp>` | plays the human in multi-turn agent suites |

An unpinned model id is a lint error: a run whose model cannot be identified cannot be compared to
a baseline, and every number it produced is unattributable.

## Risk tier

- **Tier:** `low | medium | high`

| Tier | The system… | Mandatory layers |
|---|---|---|
| `low` | drafts text a human always reviews before it leaves | L0 L1 L2 |
| `medium` | answers users directly, or calls read-only tools | L0 L1 L2 L3 L4 |
| `high` | takes actions with side effects, handles money, PII, or safety-relevant decisions | L0 L1 L2 L3 L4 L5 L6 |

A mandatory layer disabled in §Layers is a lint error (E024), not a silent skip. Lint reads the
`Mandatory layers` column above, so keep this table if you change it.

## Layers

| Layer | Enabled | Runner | Output |
|---|---|---|---|
| `L0` contract | yes | `eval run --layer L0` (no model calls) | `.evals/runs/contract/` |
| `L1` component | yes | retrieval + single-call metrics | `.evals/runs/component/` |
| `L2` task | yes | golden dataset + evaluators | `.evals/runs/task/` |
| `L3` agent | no | simulated user + trajectory assertions | `.evals/runs/agent/` |
| `L4` safety | no | red-team probes (§Environments must authorize) | `.evals/runs/safety/` |
| `L5` nfr | no | k6 (alt: Locust) against the entry point | `.evals/runs/nfr/` |
| `L6` production | no | sampled live traffic, judged offline | `.evals/runs/production/` |

**This is the portability mechanism** — the bundle fits any AI system by shaping this table. A
text-summarizer disables L3; a system with no retrieval disables the RAG parts of L1; an internal
tool may disable L5. Commands skip a disabled layer silently and report the skip.

## Judge thresholds

The trust gate of EVAL-CONTRACTS §5.4 compares against these.

| Metric | Threshold | Notes |
|---|---|---|
| TPR (recall on Fail cases) | `0.80` (default) | on the held-out test split |
| TNR (specificity) | `0.80` (default) | on the held-out test split |
| Cohen's kappa | `0.60` (default) | read together with the confusion matrix, never alone |
| `TPR - FPR` | `0.50` (default) | below this the bias correction amplifies noise — judge rejected |
| Labels per split | `30` Pass and `30` Fail minimum | dev and test each |

Raise these for a `high` risk tier. Lowering them below the defaults requires a written note in
the judge's `validation.md` explaining what the looser judge is still good enough to decide.

## Quality gates

| Gate | Threshold | Applies to |
|---|---|---|
| contract pass rate | `1.00` | L0 — no exceptions, no quarantine |
| task success (CI lower bound) | `0.80` | L2 |
| agent `pass^k` (CI lower bound) | `0.65` | L3, with `k` from the suite |
| per-FM regression margin | `0.05` | every gated suite, against its baseline |
| hallucination / groundedness | `0.95` | L1/L2 when §RAG is filled |
| unresolved Critical+High red-team findings | `0` | L4 |
| p95 latency | `<ms>` | L5 |
| cost per request | `<currency amount>` | L5 |
| flaky rate | `0.05` | every suite — above this the system is unpredictable, not merely imperfect |

Gates compare the **lower bound of the 95% Wilson interval** against the threshold, never the
point estimate (EVAL-CONTRACTS §8.3).

## Sample sizes

| Purpose | Minimum | Target |
|---|---|---|
| traces to code in error analysis | `100` | until saturation — new traces stop producing new failure modes |
| traces coded by a human before AI assistance | `30` | — |
| labels per judge, per failure mode | `100` | `200` |
| cases in a gated dataset | `100` | `200`+ |
| repeats per case (L2) | `3` | `5` |
| repeats per case (L3) | `5` | `10` |

`n < 30` on a gated suite is a lint error. A gate on 30 cases cannot tell a real regression from
sampling noise.

## Environments

| Env | Purpose | Adversarial testing authorized | Load testing authorized | Live traffic sampling |
|---|---|---|---|---|
| `dev` | fast feedback, cheap models | yes | no (shared) | no |
| `staging` (default) | full runs against real infrastructure | yes | yes | no |
| `prod` | — | **no** | **no** | read-only sampling, opt-in |

Credentials and endpoints per env live in `.evals/.env.<env>` (copy from `.evals/.env.example`).
Red-team and load runs MUST refuse an environment whose column says no. CI never authorizes an
env: the `.evals/ci/` templates keep L4 and L5 jobs manual.

## Budget

- **Per-run token budget:** `<tokens>` — the runner aborts and reports when exceeded, rather than
  silently spending
- **Per-run cost ceiling:** `<amount>` — same behaviour
- **Nightly suite budget:** `<amount>`
- **Judge calls per case:** `1` (default) — raise only when judge variance is measured and material

The runner reads the two per-run lines above (a `<placeholder>` means no ceiling);
`EVAL_TOKEN_BUDGET` / `EVAL_COST_CEILING` in `.evals/.env.<env>` override them for one environment.
It adds up the `tokens_in`, `tokens_out` and `cost` the adapter returns in `meta` after every call.
An adapter that returns none of them cannot be held to a ceiling: `summary.md` then says the
budget was **NOT ENFORCED** for that run rather than counting zero spend.

A run that hits the budget stops with `ERROR` (exit code 4) and a partial `summary.md`. It never reports a gate
verdict from a truncated run.

## Severity

How a failure mode's `## Severity` is decided:

| Severity | Means |
|---|---|
| `blocking` | a user is harmed, misled about something consequential, or the system takes a wrong action with side effects |
| `major` | the user's task fails or needs rework, but nothing incorrect leaves the system |
| `minor` | the output is usable but below the bar — tone, formatting, verbosity |

## RAG (when §System under evaluation sets Retrieval to yes)

- **Retriever:** `<vector store / hybrid / BM25 — and the library>`
- **Corpus:** `<what is indexed, how it is chunked, when it was last rebuilt>`
- **k:** `<how many chunks are retrieved>`
- **Labelled query set:** `.evals/datasets/DS-<slug>-retrieval-vN.jsonl` — queries with the chunk
  ids that should be retrieved
- **Retrieval gates:** Recall@k `<value>` · MRR `<value>` · nDCG@k `<value>`
- **Reference:** the `agentic-fx/rag-reference-guide` repo holds the RAG theory this bundle
  measures against — do not restate it here.

## Agent (when L3 is enabled)

- **Turn limit:** `<max turns before the run is cut>`
- **Tool allowlist per suite:** `<how tools are restricted during evaluation>`
- **State oracle:** `<how final state is checked — a DB query, an API read, a mock's call log>`
  Trajectory is judged on **state and tool calls**, not on the wording of the agent's replies.
- **User simulator persona file:** `.evals/suites/personas/<name>.md`

## Test management & reporting

- **Report hub:** `verdict` (default) — `VERDICT_URL` and `VERDICT_API_KEY` in `.evals/.env.<env>`
- **Verdict project:** `<the system slug>` · **type:** `eval`
- **QA lifecycle bundle:** `agentic-fx/stlc` — defects, quarantine, and release sign-off are raised
  there (EVAL-CONTRACTS §12). Set to `none` if this bundle runs standalone; findings are then listed in
  the scorecard only.
- **Tracker:** `ADO | Jira | none` — used only by `stlc`, never written to from here.

## Domain knowledge

- **Wiki:** `<path to the compiled domain wiki, if the project has one — e.g. qa/wiki/compiled/index.md>`
  When present, every domain term and business rule in a failure-mode statement or a judge prompt
  resolves through it and is cited. Wiki silence is a reported `DATA-GAP`, never a guess.
