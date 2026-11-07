# EVAL-CONTRACTS.md — the single source of truth for every cross-file contract

Skills, agents, and commands REFERENCE this file; they do not copy it. **When any other file in
this bundle disagrees with EVAL-CONTRACTS.md, EVAL-CONTRACTS.md wins** — fix the other file. The mechanical
half of these rules is enforced by `eval lint` (`.evals/scripts/shared/lint_evals.py`).

This bundle measures LLM systems. It does not own defect lifecycle, quarantine, release sign-off,
or portfolio metrics — those live in `agentic-fx/stlc` and are called back into (§12). It does not
own test reporting history — that is `agentic-fx/verdict` (§11).

---

## 1. Identifiers

| Id | Format | Rules |
|---|---|---|
| Failure mode | `FM-NNN` (zero-padded, ≥3 digits: `FM-001`) | permanent; never renumbered; the join key between taxonomy, evaluator, dataset row, and scorecard. A failure mode is *retired*, never deleted or reused. |
| Eval case | `EV-<SUITE>-<NNN>` — SUITE ∈ `TASK AGENT RAG SAFE NFR CONTRACT`, NNN 3 digits sequential **per suite** | identity = normalized input + the FM set it probes, never the NNN; rows are never renumbered |
| Dataset | `DS-<slug>-v<N>` | **immutable once published**. Any change to any row = bump `N`. Every run records the exact `DS` id it ran against. |
| Judge | `JDG-<slug>-v<N>` | one judge = one binary decision about one FM (or one tight FM group). Changing the prompt, the judge model, the model version, or the few-shot examples = bump `N`. Every `JDG-<slug>-v<N>` has its own `validation.md` (§5). |
| Red-team probe | `RT-<CODE>-<NNN>` — CODE = an OWASP id (`LLM01`…`LLM10`, `ASI01`…`ASI10`) | one probe = one attack technique against one surface |
| Baseline | `BASE-<id>` where `<id>` = `YYYY-MM-DD-<slug>` | freezes the tuple (system version, model id, prompt version, dataset id, judge ids) plus results with confidence intervals |
| Run | `<run-id>` = `YYYY-MM-DD-HHmm` | every run has `.evals/runs/<suite>/<slug>/<run-id>/` — no run without evidence |
| Annotator | `ANN-<initials>` | a human labeller. `ANN-AI` is reserved for machine-suggested labels, which never count as ground truth. |
| Trace batch | `TB-<YYYY-MM-DD>-<NNN>` | one pull of production/staging traces |
| Requirement (optional) | `REQ-NNN` | only when this bundle runs alongside `stlc` — same id space, never re-minted here |

`<slug>`: **lowercase-kebab** everywhere (`[a-z0-9]+(-[a-z0-9]+)*`). It is a directory segment;
spaces, uppercase, and `/` are rejected by lint.

---

## 2. Artifact paths (all relative to the eval root, default `.evals/`)

```
system-card.md                                   the system under evaluation (§3)
traces/<TB-id>/raw.jsonl                         pulled traces, one JSON object per line (§4)
traces/<TB-id>/notes.md                          open-coding notes, one block per trace
taxonomy/FM-NNN-<short-slug>.md                  one file per failure mode (§6)
taxonomy/INDEX.md                                the failure-mode register — the only place FM ids are minted
datasets/DS-<slug>-vN.jsonl                      the eval dataset, one case per line (§7)
datasets/DS-<slug>-vN.meta.md                    provenance: how built, dimensions, counts per FM, what changed from v(N-1)
datasets/DS-<slug>-retrieval-vN.jsonl            labelled query set for L1 retrieval (§7.3)
suites/personas/<name>.md                        simulated-user personas for L3 (§8.4)
judges/JDG-<slug>-vN.md                          the judge prompt + its decision contract (§5)
judges/<slug>/labels/{train,dev,test}.jsonl      human labels, split once and never re-shuffled (§5)
judges/<slug>/predictions/test.jsonl            the judge's own verdict on each test case: {case_id, judge: "pass"|"fail"} (§5.3)
judges/<slug>/validation.md                      TPR/TNR/kappa on the held-out test set — the trust gate (§5)
suites/<suite>.yaml                              what runs together: dataset + evaluators + repeats + gates (§8)
redteam/RT-<CODE>-NNN-<short-slug>.md            one attack probe (§9)
runs/<suite>/<slug>/<run-id>/results.jsonl       per-case, per-repeat raw outcome
runs/<suite>/<slug>/<run-id>/summary.md          aggregates with confidence intervals
runs/<suite>/<slug>/<run-id>/ctrf.json           the CTRF report uploaded to verdict (§11)
runs/<suite>/<slug>/<run-id>/traces/             full request/response evidence per case
baselines/BASE-<id>.json                         frozen comparison point (§10)
reports/<slug>/YYYY-MM-DD-scorecard.md           the human-facing verdict (§10)
reports/audits/YYYY-MM-DD-eval-audit.md          the audit of this eval pipeline itself (§13)
learnings/LRN-<TOPIC>.md                         a lesson from past runs: judge or system failure modes to check next time (§10.1)
logs/activity.jsonl                              run, score and regression events, git-ignored (docs/activity-format.md)
scripts/shared/                                  runner · stats · providers · judges · ctrf · lint
.env.example                                     every variable the runner reads
ci/                                              CI templates (gitlab · github)
```

`<short-slug>`: **lowercase-kebab**, ≤ 5 words.

---

## 3. The system card (`.evals/system-card.md`)

Written once per evaluated system by `/eval-scope`, refreshed when the system changes. Required
headings, byte-exact:

```
## System            what the feature does, in one paragraph, in the user's words
## Users             who calls it, with what expectations
## Surface           API? chat? agent with tools? batch job? — and where the boundary of evaluation sits
## Model             provider · model id · temperature · max tokens · any pinned version
## Tools             every tool the system may call, with the side effects and the permission each needs
## Hard policies     the rules that must NEVER be violated, one per line, each testable
## Risk tier         low | medium | high — drives which layers are mandatory (§8)
## Known unknowns    what nobody on the team can currently answer about this system
```

`## Hard policies` lines are the only source for `SAFE` suite policy assertions. A policy that
cannot be phrased as a testable statement is a `SCOPE-GAP`, written as such, never softened.

---

## 4. Traces

One JSON object per line. Required keys (extra keys are preserved verbatim):

| Key | Type | Meaning |
|---|---|---|
| `trace_id` | string | stable, unique |
| `ts` | ISO-8601 | when it happened |
| `input` | object | what the user/caller sent |
| `output` | object | what the system returned |
| `steps` | array | ordered spans — each `{type: llm\|tool\|retrieval, name, input, output, ms}` |
| `meta` | object | model id, prompt version, env, tenant — whatever the system emits |

When the system is instrumented with OpenTelemetry GenAI semantic conventions, `steps` is derived
from the span tree and `meta` carries the `gen_ai.*` attributes verbatim. **Traces are evidence:
they are never edited.** Redaction happens at pull time and is recorded in `notes.md`.

The runner's own evidence (`runs/.../traces/`) is masked before it is written: API keys, bearer
tokens, JWTs, emails, and any string value under a key named like `api_key`, `authorization`,
`password`, `secret` or `token` become `[REDACTED:<kind>]`. `summary.md` records how many of each
kind were masked (`.evals/scripts/shared/redact.py`).

---

## 5. Evaluators — and the trust gate

An evaluator answers **one binary question about one output**: pass or fail. No Likert scales, no
0–10 scores, no weighted composites. A question that cannot be made binary is two questions.

### 5.1 Two kinds, in this order of preference

| Kind | Use when | Lives in |
|---|---|---|
| **Code assertion** | an objective rule decides it: schema valid, required field present, tool called with the right argument, forbidden string absent, number within range, latency under budget | `.evals/scripts/shared/assertions/` + referenced by id in the suite |
| **LLM judge** | the decision needs judgment: is this grounded in the retrieved context, does it follow the refund policy, is the tone acceptable | `.evals/judges/JDG-<slug>-vN.md` |

**Every failure mode must be attempted as a code assertion first.** Choosing a judge where a code
assertion is possible is a lint warning with the FM id named.

### 5.2 The label split (set once, never re-shuffled)

Human labels for a judge are split into three files under `judges/<slug>/labels/`:

| Split | Share | Used for |
|---|---|---|
| `train.jsonl` | 10–20% | examples that may be pasted into the judge prompt as few-shot |
| `dev.jsonl` | 40–45% | iterate on the judge prompt against this |
| `test.jsonl` | 40–45% | **held out.** Scored once per judge version. Never read while editing the prompt. |

Both `dev` and `test` must contain **30–50 Pass and 30–50 Fail** examples. Fewer → the judge is
`UNVALIDATED` (§5.4) regardless of the numbers it scores.

Every label row: `{case_id, output_ref, label: "pass"|"fail", annotator: "ANN-xx", ts, note}`.
Rows labelled by `ANN-AI` are suggestions; they must be confirmed by a human annotator before they
count, and the confirming annotator replaces the id.

### 5.3 What `validation.md` must contain

Written by `/eval-validate` per judge version. Required headings:

```
## Judge            JDG-<slug>-vN · judge model id · which FM it decides
## Labels           counts per split, annotators, labelling date
## Confusion        TP / FP / TN / FN on the TEST split, as a 2x2 table
## Rates            TPR · TNR · FPR · FNR · Cohen's kappa — each to 3 decimals
## Disagreements    every FP and FN, one line each, with the trace ref and why
## Correction       the bias-corrected estimator and its inputs (§5.5)
## Verdict          VALIDATED | UNVALIDATED, against §Judge thresholds in EVAL-PROFILE
```

The numbers are **computed, never typed**: `scripts/shared/calibrate.py JDG-<slug>-vN` reads
`labels/test.jsonl` and `predictions/test.jsonl` and prints `## Confusion`, `## Rates`,
`## Disagreements` and `## Verdict` against §Judge thresholds. Lint recomputes them (E023): a
stated TPR, TNR or kappa more than 0.0015 from the computed value, or a verdict that differs, is an
error; so is a judge a gated suite uses whose calibration cannot be recomputed (missing
predictions, or a labelled test case with no judge verdict).

`## Disagreements` is not optional and is not summarized. Reading the actual disagreements is how
a judge gets fixed; a rate with no disagreement list is a number nobody can act on.

### 5.4 The trust gate — the rule that makes this bundle different

> A judge whose `validation.md` does not exist, or whose `## Verdict` is not `VALIDATED`, **MUST
> NOT** appear in any suite that has a gate.

An `UNVALIDATED` judge may still run, in exploratory mode. Then:
- every number it produces is written with the literal marker `UNVALIDATED` beside it,
- it never enters `reports/<slug>/YYYY-MM-DD-scorecard.md`,
- it never contributes to a `BASE-<id>`,
- the suite's gate result is `NOT-EVALUABLE`, never `PASS`.

Changing the judge model — including a provider-side version bump — invalidates the validation.
Bump the judge version and re-validate against the same held-out test split.

### 5.5 Bias correction

An observed pass rate from an imperfect judge is corrected before it is reported:

```
theta_hat = (p_observed - FPR) / (TPR - FPR)
```

where `TPR` and `FPR` come from the judge's own `validation.md` test split. Report `theta_hat`
alongside `p_observed`, never instead of it. When `TPR - FPR < 0.5` the correction amplifies noise
beyond usefulness — the judge is not good enough and the verdict is `UNVALIDATED`.

Fail is the positive class, so the formula runs on the observed fail rate and the corrected pass
rate is one minus its result. The runner writes it under `## Results` for `pass^1` when exactly one
evaluator — a `VALIDATED` judge whose `## Rates` gives TPR and TNR — decides the suite. It is not
applied to `pass^k` (a product of k decisions, which the linear correction does not describe) nor
when several evaluators combine into one outcome; `summary.md` states which reason applied.
Gates read the raw interval, not `theta_hat`.

### 5.6 Judge hygiene (checked by `/eval-audit`)

- The judge model MUST NOT be from the same model family as the system under evaluation in any
  gated suite. Same-family judging inflates scores.
- The judge prompt MUST NOT receive the reference answer unless the judge's job is explicitly
  reference-based comparison; state which mode it is under `## Judge`.
- Judge prompts state the criterion and the failure conditions, then ask for a verdict, then a
  one-sentence reason. Reason **after** verdict is forbidden — reason first, verdict second, so the
  reasoning is not written to justify an already-chosen answer.

---

## 6. Failure modes (`.evals/taxonomy/`)

One file per FM. Required headings:

```
## Statement       one sentence: what goes wrong, from the user's point of view
## Evidence        >= 3 trace refs (TB-id + trace_id) where this was observed — never zero
## Frequency       how many of the N coded traces showed it, as a fraction
## Severity        blocking | major | minor — against §Severity in EVAL-PROFILE
## Detector        the evaluator that catches it: an assertion id, or JDG-<slug>-vN
## Status          open | mitigated | retired
```

FM ids are minted **only** in `taxonomy/INDEX.md`, sequentially, never reused. A failure mode with
fewer than 3 observed instances is a hypothesis, not a failure mode: it lives in the trace notes
until it recurs.

---

## 7. Datasets (`.evals/datasets/DS-<slug>-vN.jsonl`)

One case per line. Required keys:

| Key | Type | Meaning |
|---|---|---|
| `case_id` | string | `EV-<SUITE>-<NNN>` |
| `input` | object | exactly what is sent to the system |
| `fm` | array | the FM ids this case probes; `[]` is allowed only for happy-path coverage cases |
| `expect` | object | the assertions/judges that decide it, by id |
| `origin` | string | `trace` (from a real trace, with its ref) \| `synthetic` \| `handwritten` |
| `dimensions` | object | the tuple that generated it, when `origin = synthetic` (§7.2) |

### 7.1 Immutability

`DS-<slug>-vN` never changes after it is referenced by a run. Fixing a typo in one row is a new
version. `DS-<slug>-vN.meta.md` records what changed from `v(N-1)` and why.

### 7.2 Composition rules

- Every **open** FM has at least one case. An FM with no case is a lint error.
- At least 30% of cases have `origin: trace`. A dataset made only of synthetic cases tests an
  imagined product.
- Synthetic cases are generated from an explicit dimension list (e.g. `{intent, tone, locale,
  data_state, length}`) by taking tuples across dimensions, not by asking a model for "50 varied
  examples" — that produces 50 near-duplicates.
- **Leakage**: no case input may appear verbatim in the system's prompt, few-shot examples, or the
  judge's `train.jsonl`. `/eval-audit` greps for this and reports every hit as blocking.

### 7.3 Retrieval datasets (`DS-<slug>-retrieval-vN.jsonl`)

L1 retrieval is measured against a labelled query set, one query per line:

| Key | Type | Meaning |
|---|---|---|
| `case_id` | string | `EV-RAG-<NNN>` |
| `input` | object | `{query: "..."}` — exactly what goes to the retriever |
| `relevant` | array | chunk ids that contain the answer |
| `partial` | array | chunk ids that contribute but are insufficient alone — graded nDCG only |
| `known_absent` | bool | the corpus genuinely does not answer this |
| `origin` | string | `trace` \| `synthetic` \| `handwritten` |

`known_absent` rows are **required**, 10–20% of the set: a retriever is also judged on what it does
when the answer is not there, and one that always returns its top-k regardless guarantees some
answers are grounded in irrelevant text.

**Chunk ids must be stable across index rebuilds.** If they are not, every label expires on every
rebuild and L1 is not measurable — that is a blocking indexing-design finding, not a limitation to
work around. Every retrieval run records the corpus version, the index build date, and the exact
embedding model version: a comparison across two index builds is not a comparison, and no metric
will say so.

---

## 8. Suites (`.evals/suites/<suite>.yaml`)

A suite binds a dataset to evaluators, a repeat count, and gates. Required keys:

```yaml
suite: task-refunds            # kebab; matches the filename
layer: L2                      # L0 | L1 | L2 | L3 | L4 | L5 | L6  (§8.1)
dataset: DS-refunds-v3
repeats: 5                     # k — how many times each case runs (§8.2)
evaluators:
  - assert:schema-valid        # code assertion by id
  - judge:JDG-grounded-v2      # judge by id — must be VALIDATED to gate
gates:
  task_success_ci_lower: 0.80  # gate on the LOWER BOUND of the 95% CI, never the point estimate
  regression_margin: 0.05      # no FM may drop more than this vs the baseline
baseline: BASE-2026-09-01-refunds
prompt_path: prompts/refunds.md # optional; lint checks no dataset case leaks into it (§13)
```

### 8.1 The seven layers

| Layer | Scope | Determinism | Required for risk tier |
|---|---|---|---|
| `L0` contract | prompt renders, output schema, tool signature, guardrail regex — no model call | deterministic | all |
| `L1` component | retrieval quality, one LLM call in isolation | mixed | all |
| `L2` task | end-to-end task success on the golden set | judged | all |
| `L3` agent | multi-turn trajectory, tool order, policy adherence | judged | medium, high |
| `L4` safety | adversarial probes (§9) | adversarial | medium, high |
| `L5` nfr | latency, tokens, cost, failover | deterministic | high |
| `L6` production | sampled live traffic | online | high |

A layer that the risk tier requires and the profile disables is a lint error (E024), not a silent
skip. Lint reads both halves from EVAL-PROFILE: the tier from `§Risk tier`'s `Tier:` line, the
layers it requires from that section's `Mandatory layers` column, and what is on from `§Layers`.
A tier still at its `low | medium | high` placeholder makes nothing mandatory yet; a chosen tier
with no row in the table is itself an E024.

### 8.2 Repeats and non-determinism

- `L0` and `L5` run once per case (`repeats: 1`) — nothing about them is sampled.
- `L1` and `L2` default to `repeats: 3`, `L3` to `repeats: 5`.
- A case that passes on some repeats and fails on others is **`FLAKY`**, a first-class outcome, not
  a fail to retry away. Flaky rate is reported and tracked; `verdict` computes it across runs.
- Agent suites report **`pass^k`** — the fraction of cases that passed on *every one* of the k
  repeats — alongside `pass^1`. `pass^k` is the number that predicts production behaviour.
- Temperature, seed (where the provider supports it), and model id are pinned in the suite and
  recorded in every run. An unpinned model id is a lint error.

### 8.4 L3 agent suites

An agent suite additionally declares a **state oracle** and a **persona**. Trajectories are judged
on final state and tool calls, never on the agent's wording — the reply text varies every run and
says nothing about whether the work got done.

- Each case declares `final_state` (what must be true at the end) **and** `must_not` (what must not
  have changed). An agent that refunds the right order and cancels a different one passes an
  `expect`-only check.
- The environment is **reset between repeats** and the reset is verified. A failed reset is `ERROR`,
  never `FAIL`: the agent was never given the scenario the case describes.
- The user-simulator model is pinned in `§Models` and **must differ from the agent model**; it is
  recorded in every run, and changing it invalidates baseline comparison exactly as a system change
  does.
- The simulator never grades, and never sees the expected final state.
- Hitting `§Agent → Turn limit` is an outcome (`FAIL`, reason `turn-limit`), counted separately
  from task failures.

### 8.3 Statistics

- Every reported rate carries a **95% Wilson score interval**. Point estimates alone are not
  reportable and lint strips them from scorecards.
- Gates compare the **CI lower bound** against the threshold: `PASS` when the lower bound clears
  it, `FAIL` when the whole interval sits below it, and **`NOT-EVALUABLE` when the interval spans
  it** — the run did not have the power to answer the question that was asked of it.
- **Every** declared gate is evaluated, each on the metric its key names (`task_success_ci_lower`
  and `pass_k_ci_lower` on `pass^k`, `pass_1_ci_lower` on `pass^1`, `flaky_rate_max` on the flaky
  rate's upper bound, `regression_margin` on the largest drop vs the baseline, total or per FM).
  The suite verdict is `FAIL` if any gate fails, `PASS` only if every gate passes, and
  `NOT-EVALUABLE` otherwise — including a gate key the runner cannot measure.
- A suite with **no gate declared** is `NOT-EVALUABLE`, decided by `no gate declared`. It reports
  numbers; nothing was asked of it, so nothing passed.
- A case whose every repeat was `ERROR` was never measured. It stays out of the rates, is counted
  and named as *not run* in `summary.md`, and keeps the verdict from being `PASS`.
- Runner exit codes: `0` PASS · `1` FAIL or preflight STOP · `2` no such suite · `3` NOT-EVALUABLE ·
  `4` aborted on the budget (EVAL-PROFILE §Budget) · `5` refused before the first call: the
  estimate is over the budget and no human passed `--confirm-cost` (§8.5).
- **Needs human.** A gated suite must name `system_version` (which build the gate is about) and,
  when a judge decides it, `labels_owner` (the `ANN-xx` who owns that judge's labels). Unset or a
  `<placeholder>` → the verdict is `NOT-EVALUABLE`, decided by `needs human: <what>`. The runner
  never fills either in.
- Comparing two runs (prompt change, model change) is a paired comparison over the same dataset
  version — report the difference with its interval, not two separate percentages.
- `n < 100` on a gated suite is a lint warning naming the suite; `n < 30` is a lint error. A gate
  on 30 cases cannot distinguish a real regression from sampling noise.

### 8.5 Token economy

A run spends only what its question needs, and says what it will spend before it starts.

| Lever | Suite key | What it saves |
|---|---|---|
| **Estimate first** | `tokens_per_call`, `tokens_per_judge_call` (else the last run's `cost.json`) | cases x repeats x (1 + judges) x tokens per call, printed before the first call. Over EVAL-PROFILE §Budget → exit `5` unless `--confirm-cost`. Unknown is printed as unknown. |
| **Sample to power** | `ci_half_width` (optional `expected_pass`, default 0.5) | runs the smallest subset whose Wilson half-width meets the target (never under 30 when gated), one case per failure mode first, in a stable hash order; says how many it skipped |
| **Cache** | — (`--no-cache` to bypass) | an attempt whose system version, prompt hash, model, temperature, evaluators, case input and repeat are all unchanged is reused from `cache/<suite>/`, not re-run or re-judged. Errors are never cached. |
| **Cheap checks first** | `judge_adapter` | an attempt a code assertion already failed is not sent to the judge |

`summary.md` has a `## Cost` table: the estimate against the actual, and the tokens each lever saved.

---

## 9. Red-team probes (`.evals/redteam/`)

One file per probe. Required headings:

```
## Code            OWASP id + name (e.g. LLM01 Prompt Injection)
## Surface         where it enters: user message | retrieved document | tool output | file upload
## Attack          the exact payload or the generator that produces it
## Success means   what the attacker achieving the goal looks like, as a testable condition
## Severity        critical | high | medium | low
## Authorization   the environments this may run in — from §Environments
```

Probes run **only** against systems the team owns, in environments whose `§Environments` row
authorizes adversarial testing. A probe whose `## Authorization` does not name the target env
refuses to run. Production is never authorized by default.

---

## 10. Baselines and scorecards

A `BASE-<id>.json` freezes:

```json
{
  "id": "BASE-2026-09-01-refunds",
  "system": { "version": "...", "prompt_version": "...", "model": "..." },
  "dataset": "DS-refunds-v3",
  "judges": ["JDG-grounded-v2"],
  "results": { "task_success": { "p": 0.84, "ci": [0.79, 0.88], "n": 240, "k": 5 } },
  "per_fm": { "FM-001": { "p": 0.91, "ci": [0.86, 0.95] } }
}
```

A suite moves to a new baseline only through `scripts/shared/baseline.py promote --to BASE-<id>`, and
back through `revert`, which restores the baseline the current one replaced. Both rewrite only the
suite's `baseline:` line and append `{ts, suite, action, from, to, why}` to
`baselines/HISTORY.jsonl`; a `BASE-*.json` file is never edited or deleted.

Regression is judged **per failure mode**, not on the total. A total that holds steady while one
FM collapses and another improves is the most common way a real regression ships.

The scorecard (`reports/<slug>/YYYY-MM-DD-scorecard.md`) required headings:

```
## Verdict         PASS | FAIL | NOT-EVALUABLE — and the one gate that decided it
## Configuration   system version · model · prompt version · dataset id · judge ids · run id
## Results         per gate: value with CI, threshold, pass/fail
## Per failure mode  FM id · rate with CI · delta vs baseline · verdict
## Flaky           cases that passed on some repeats and failed on others
## Judge trust     each judge: version, TPR/TNR, VALIDATED or UNVALIDATED
## Evidence        run path, trace refs for every failure
## What changed    vs the named baseline, in prose
```

`NOT-EVALUABLE` is a real verdict and is never converted to `FAIL` or `PASS` to make a pipeline
green. It means: the measurement itself was not trustworthy.

### 10.1 Lessons (`.evals/learnings/`)

A lesson is one file in the format the sdlc and stlc bundles share: front matter `id`
(`LRN-<TOPIC>`), `title`, `status` (`active` | `deprecated`), `confidence` (`provisional` |
`established`), `applies_to` (suite names, layers, `judge`, or `*`), `evidence`, `probe` (a
question ending in `?`), `created`, `updated`; then 3-10 lines of Do / Why / Not. The runner
prints the active lessons that apply to the suite or its layer before the first call
(`scripts/shared/learnings.py list` prints the same). A lesson whose text matches an injection,
secret-exfiltration, credential or invisible-character rule is withheld from both and fails
`learnings.py check`; there is no override.

---

## 11. Reporting to `verdict`

Every run writes `ctrf.json` (CTRF JSON) and uploads it:

```
verdict upload --project <system-slug> --type eval --env <env> --tag <suite> ctrf.json --evidence runs/<suite>/<slug>/<run-id>
```

Mapping into CTRF:

| Eval concept | CTRF field |
|---|---|
| eval case × repeat | one test result |
| `EV-<SUITE>-<NNN>` | `name` |
| pass / fail / flaky | `status` (`passed` / `failed` / `flaky`) |
| FM ids | `tags` as `fm:FM-001` |
| judge id | `tags` as `judge:JDG-grounded-v2` |
| dataset id | `tags` as `dataset:DS-refunds-v3` |
| model id | `tags` as `model:<id>` |
| `UNVALIDATED` judge | `tags` as `unvalidated` + suite-level `NOT-EVALUABLE` |

`verdict`'s flakiness score over these runs **is** the non-determinism measure — the bundle does
not reimplement it.

---

## 12. Handing off to `stlc`

This bundle measures; it does not manage. When a run produces a finding that needs a lifecycle:

| Finding | Goes to |
|---|---|
| A failure mode that is a product defect | `/qa-defect` in `stlc` — the defect cites the FM id and the run path |
| A red-team finding | `/qa-defect` with the `RT-` id and the OWASP code |
| A release decision | `/qa-signoff` in `stlc`, with the scorecard path as evidence |
| A recurring flaky case that is an infrastructure problem | `/qa-quarantine` in `stlc` |

The eval bundle never opens, triages, or closes defects itself.

---

## 13. The eval audit (`/eval-audit`)

Run quarterly, and before trusting any eval suite inherited from someone else. It checks this
file's rules mechanically and reports each violation with severity. The checks
that the files alone decide are also lint errors (code in the last column), so CI catches them
between audits:

| Check | Severity | Lint |
|---|---|---|
| A gated suite uses an `UNVALIDATED` judge | blocking | E009 E010 |
| A judge's test split has < 30 Pass or < 30 Fail | blocking | E014 |
| A dataset case input appears in the system prompt or judge `train.jsonl` | blocking | E019 |
| A gated suite has `n < 30` | blocking | E013 |
| A gate compares a point estimate instead of a CI lower bound | blocking | E012 |
| An open FM has no dataset case | blocking | E008 |
| Judge model is the same family as the system under evaluation, in a gated suite | high | E020 |
| Suite pass rate > 0.95 across the last 3 runs | high — the suite has stopped discriminating | E021 |
| A judge used where a code assertion would decide it | medium | — |
| `origin: trace` share below 30% | medium | W001 |
| Model id or temperature unpinned in a suite | medium | E011 W006 |
| A validation older than the current judge model version | high | E022 |
| `validation.md` rates or verdict differ from what its test labels and predictions compute | blocking | E023 |
| A layer the risk tier makes mandatory is disabled in EVAL-PROFILE §Layers | blocking | E024 |

How lint decides them: **E019** — a dataset input of 24+ characters found, whitespace- and
case-insensitively, in a judge's `labels/train.jsonl` or in the file a suite names as `prompt_path`.
**E020** — the `Judge model:` line under a judge's `## Judge` shares its family (the id's first
token: `claude`, `gpt`, `gemini`) with the suite's `model`. **E021** — the last 3 `summary.md` files
under `runs/<suite>/` each report `pass^k` above 0.95. **E022** — the judge model recorded in
`validation.md` (`## Judge`, or `Last validated: ... against judge model <id>`) differs from the one
the judge file names. A check whose input is missing (no model line, no `prompt_path`, fewer than 3
runs) does not fire; `/eval-audit` still reviews it by hand.

---

## 14. Vocabulary (byte-exact tokens)

Status and verdict tokens are matched literally by lint, gates, and the CTRF writer. Never
translate them, even when `§Artifact language` is not English.

| Domain | Tokens |
|---|---|
| Case outcome | `PASS` `FAIL` `FLAKY` `ERROR` `SKIPPED` |
| Gate verdict | `PASS` `FAIL` `NOT-EVALUABLE` |
| Judge verdict | `VALIDATED` `UNVALIDATED` |
| FM status | `open` `mitigated` `retired` |
| Severity | `blocking` `major` `minor` |
| Red-team severity | `critical` `high` `medium` `low` |
| Case origin | `trace` `synthetic` `handwritten` |
| Gap markers | `SCOPE-GAP` `COVERAGE-GAP` `DATA-GAP` |

Prose in artifacts follows `§Artifact language` in EVAL-PROFILE. Headings, ids, table column
names, and the tokens above stay English because parsers match them byte-exact.

---

## 15. `.evals/state.json` — a derived read model, not a source of truth

The eval artifacts (system card, taxonomy, datasets, judges and their validations, suites, runs,
scorecards, probes) are authoritative. `.evals/state.json` is **generated** from them by
`.evals/scripts/shared/build_state.py`, never hand-edited, and rebuilt by the `Stop` hook at the end
of every turn and by the runner after every run. It is git-ignored: it is a cache, not a record.
Its purpose is that nothing outside this bundle has to parse markdown. The VS Code board
(`editor/vscode-eval`), CI and the `SessionStart` brief (`status.py --brief`) read this one file
or the same derivation.

If `state.json` and the artifacts disagree, **the artifacts are right**. `build_state.py --check`
exits 1 when they do, so CI can fail on a stale or edited index.

```jsonc
{
  "schema": 1,                          // bumped only when a key below changes meaning or goes away
  "generator_version": "1.1.0",         // bumped when the derivation changes
  "generated_at": "2026-10-16T10:00:00+00:00",
  "source_hash": "<sha256 over every file read, as path:body-hash lines, sorted>",
  "root": "evals",
  "project": "<EVAL-PROFILE §Project Name, else the system card title, else the folder>",
  "system_slug": "<§System slug>" ,     // null while it is a <placeholder>
  "risk_tier": "medium",                // low | medium | high | null
  "layers_enabled": ["L0", "L1", "L2"], // §Layers rows with Enabled = yes; null = no profile found
  "phase": "Run",                       // the ladder below
  "next_command": "/eval-report",       // shown and copied by readers, never run by them
  "system_card": { "path": ".evals/system-card.md", "system": "…", "seed": false, "risk_tier": "medium" },
  "totals": { "failure_modes_open": 3, "failure_modes_blocking_open": 1, "datasets": 2,
              "judges": 2, "judges_validated": 1, "suites": 4, "suites_gated": 2, "runs": 9,
              "latest_pass": 2, "latest_fail": 1, "latest_not_evaluable": 1, "redteam_probes": 6 },
  "failure_modes": [{ "id": "FM-001", "title": "…", "severity": "blocking", "status": "open",
                      "detector": "assert:no-invented-ids", "frequency": "…", "path": "…" }],
  "datasets": [{ "id": "DS-refunds-v3", "path": "…", "meta": "…", "retrieval": false,
                 "cases": 240, "trace_share": 0.42, "sha256": "…" }],
  "judges": [{ "id": "JDG-grounded-v2", "path": "…", "validation": "…",
               "verdict": "VALIDATED", "tpr": 0.91, "tnr": 0.88, "kappa": 0.74 }],
  "suites": [{
    "suite": "task-refunds", "path": "…", "layer": "L2", "dataset": "DS-refunds-v3",
    "model": "…", "repeats": 5, "gated": true, "gates": { "task_success_ci_lower": 0.8 },
    "baseline": "BASE-…", "baseline_p": 0.84, // the baseline's task_success p; null = none or unreadable
    "regression_margin": 0.05,          // gates.regression_margin, else 0
    "evaluators": ["assert:schema-valid", "judge:JDG-grounded-v2"],
    "unvalidated_judges": [],           // §5.4: non-empty on a gated suite = NOT-EVALUABLE only
    "runs": 3,
    "latest_run": { "run_id": "2026-10-15-0900", "path": "…", "summary": "…", "ctrf": "…",
                    "verdict": "PASS",  // PASS | FAIL | NOT-EVALUABLE | null (no summary)
                    "decided_by": "task_success_ci_lower",
                    "pass_1": { "p": 0.9, "lo": 0.86, "hi": 0.93, "n": 1200 },
                    "pass_k": { "p": 0.84, "lo": 0.79, "hi": 0.88, "n": 240 },
                    "flaky": { "p": 0.03, "lo": 0.01, "hi": 0.06, "n": 240 },
                    "failed_attempts": 31, "errors": 0, "failing_cases": ["EV-TASK-014"] },
    "previous_run": { "run_id": "…", "verdict": "PASS", "pass_k": { … } }
  }],
  "redteam": [{ "id": "RT-LLM01-001", "code": "LLM01 Prompt Injection", "severity": "high",
                "authorized": true, "path": "…" }],
  "baselines": ["BASE-2026-09-01-refunds"],
  "scorecards": [{ "slug": "refunds", "date": "2026-10-15", "path": "…", "verdict": "PASS" }],
  "audit": { "date": "2026-10-01", "path": "…", "mentions_blocking": 0 }
}
```

Rules the builder follows, and readers may rely on:

- **The ladder** is `Scope → Explore → Data → Evaluate → Validate → Run → Report`, and `phase` is
  the furthest rung whose artifact exists: a failure mode, a dataset, a suite with evaluators,
  every judge a suite names `VALIDATED` (a suite of code assertions only needs no validation), a
  run folder, a scorecard. There is no sign-off rung: release decisions belong to `stlc` (§12).
- **Runs** are read from `runs/<suite>/<run-id>/` and `runs/<suite>/<slug>/<run-id>/`; the newest
  run id is the latest run.
- **A rate is always reported with its interval** (§8.3). The builder copies `p`, `lo`, `hi` and
  `n` from `summary.md` and never recomputes or rounds them.
- `NOT-EVALUABLE` is copied as itself. No reader may show it as pass or fail (§10).
- Anything unreadable is `null`, never a guess. `layers_enabled: null` means "no profile found",
  not "no layers".

---

## 16. Bundle bench — does a bundle learn across versions?

The eval bundle also measures the agent bundles (`sdlc`, `stlc`): the same tasks, run under two
bundle versions, or under one version with and without its lessons. One JSON file per side:

```json
{ "schema": 1, "bundle": "sdlc", "version": "1.9.0", "condition": "lessons",
  "tasks": [ { "task_id": "T-001", "first_pass": true, "repeat_errors": 0,
               "tokens": 41200, "duration_s": 312.5 } ] }
```

| Field | Type | Meaning |
|---|---|---|
| `task_id` | string | pairs the task across the two files; required |
| `bundle`, `version`, `condition` | string | per file, or overridden per task; `condition` is `lessons` or `no-lessons` |
| `first_pass` | bool \| null | the task's first review passed |
| `repeat_errors` | int | failures that match a lesson that already existed |
| `tokens` | int \| null | tokens spent on the task; `null` = not reported |
| `duration_s` | number \| null | wall-clock seconds; `null` = not reported |

`scripts/compare_bench.py <a> <b>` pairs tasks by `task_id` and decides on the paired first-pass
difference (exact McNemar, α 0.05): `BETTER`, `WORSE` (exit 1, so CI can gate on it),
`NO-SIGNIFICANT-DIFFERENCE`, or `NOT-EVALUABLE` (exit 3) when fewer than 20 tasks pair or a paired
task has no `first_pass`. Each side's first-pass rate carries its Wilson interval. Repeat-error rate
and median tokens and duration are reported with deltas; a median over a metric some tasks did not
report is shown as `—`, never computed from the subset.
