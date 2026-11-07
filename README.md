# agentic-fx-ai-eval

An **evaluation-only** agentic workflow for Claude Code, for any LLM or agent product. One
pipeline takes an AI feature from raw traces to a scorecard a release decision can rest on —
across **seven layers: contract, component, task, agent, safety, non-functional, production** —
with every project-specific value read from a single config file.

## Quick Start

You need [Node 20+](https://nodejs.org), [Claude Code](https://claude.com/claude-code) and Python
3.9+. On Windows, Claude Code also needs [Git for Windows](https://git-scm.com/download/win).

```bash
cd <your-llm-project>
npx agentic-fx@latest install --bundle eval   # the bundle, the .evals/ workspace, the VS Code board
npx agentic-fx@latest doctor                  # machine (Node, Claude Code, Git Bash, Python) + install

# prove the scaffold works before writing anything (python instead of python3 on Windows)
python3 .evals/scripts/shared/lint_evals.py --root .evals     # → 0 error(s), 0 warning(s) · contracts hold.
python3 .evals/scripts/shared/runner.py --suite task-example --root .evals --dry-run   # no model calls

claude                                        # open Claude Code, then run /eval-scope
```

`--bundle all` installs the `dev` and `qa` bundles alongside it; they coexist by design. Then fill
in `.claude/EVAL-PROFILE.md`: the system, its models (pinned), the risk tier, which layers are on,
and the gates. The full walk-through is in the [user guide](docs/user-guide.md).

It measures; it does not manage. Defect lifecycle, quarantine and release sign-off stay in
[`stlc`](../stlc); run history, flakiness scoring and quality gates stay in
[`verdict`](../verdict), which ingests this bundle's CTRF output like any other test type.

> **New here?** Read the [user guide](docs/user-guide.md) — install, your first two weeks, what
> every stop means, and the five mistakes that cost the most. This README is the reference.
>
> **Want to see it first?** Open [`docs/showcase/pipeline.html`](docs/showcase/pipeline.html) in a
> browser: one assistant through all thirteen steps, animated, with each artifact's format, the
> three verdicts, and a present mode for a room. It works offline.

```
traces ──/eval-scope────▶ system card: what it does · what tools · the policies that must never break
       ──/eval-explore──▶ error analysis: 100 real traces, open coding → axial coding → FM-### taxonomy
       ──/eval-data─────▶ dataset: dimension tuples + real trace inputs → DS-<slug>-vN, immutable
       ──/eval-judge────▶ evaluator per failure mode: code assertion first, LLM judge only if needed
       ──/eval-validate▶ calibrate: TPR/TNR on a held-out split · Cohen κ · bias correction   ← trust gate
       ──/eval-run──────▶ k repeats per case, Wilson intervals, CTRF → verdict
       ──/eval-report───▶ scorecard: gates on CI lower bounds, regression per failure mode
  operations:  /eval-drift  (model or prompt changed — what moved?)   /eval-audit  (are these numbers safe?)
               /eval-status   /eval-signoff  (evidence → stlc /qa-signoff)   /eval-help
  phase 5:     /eval-rag   /eval-agent   /eval-redteam   /eval-nfr        phase 6:  /eval-monitor
```

## The one rule that makes this different from installing a framework

> **A judge whose validation does not exist, or whose verdict is not `VALIDATED`, MUST NOT appear
> in any suite that has a gate.** (EVAL-CONTRACTS §5.4)

An uncalibrated LLM judge produces numbers that are indistinguishable from real ones. 84% from a
good judge and 84% from a judge that agrees with humans 60% of the time look identical on a
dashboard and get quoted identically in a release review. This bundle refuses the gate until
`/eval-validate` has scored the judge on labels it never saw, and reports `NOT-EVALUABLE` — a real
verdict — rather than a green tick it cannot justify.

## What's inside

| Part | Count | Purpose |
|---|---|---|
| `EVAL-PROFILE.md` | 1 | **The single config file** — the system under evaluation, models, risk tier, which layers are on, judge thresholds, quality gates, sample sizes, budget |
| `EVAL-CONTRACTS.md` | 1 | **The single source of truth for cross-file contracts** — ids, paths, the evaluator trust gate, dataset immutability, suite schema, statistics rules, CTRF mapping, the audit checklist; the mechanical half enforced by `lint_evals.py` |
| `agents/` | 8 | eval-orchestrator (entry point, delegates only) + trace-analyst, dataset-designer, judge-engineer, eval-reporter, rag-evaluator, agent-evaluator, redteam-engineer |
| `commands/` | 18 | pipeline: `/eval-scope` `/eval-explore` `/eval-data` `/eval-judge` `/eval-validate` `/eval-run` `/eval-report` · layers: `/eval-rag` `/eval-agent` `/eval-redteam` `/eval-nfr` · operations: `/eval-drift` `/eval-audit` `/eval-status` `/eval-signoff` `/eval-help` `/eval-compare-bench` · phase 6: `/eval-monitor` |
| `skills/` | 30 | discovery (system cards, trace sampling, open/axial coding, taxonomy, annotation UI) · data (dimensions, synthetic tuples, golden sets, label splits) · evaluators (code assertions, judge prompts, judge validation) · RAG (retrieval, groundedness, structured output) · agent (tool calls, trajectories, simulated users) · safety (probe design, injection, leakage, permissions) · nfr (latency/cost, failover) · run & report (suites, intervals, baselines, verdict publishing, pipeline audit) |
| `workspace/evals/` | scaffold | Folder layout + a **working seed that lints clean and dry-runs** — `stats.py` (Wilson, pass^k, kappa, bias correction, McNemar), `runner.py` (preflight, k repeats, evidence), `lint_evals.py` (23 contract checks), `calibrate.py`, `compare_bench.py`, `baseline.py`, `learnings.py`, `ctrf.py`, provider adapter template, 7 shipped assertions, `.env.example`, CI templates |
| `.evals/state.json` | derived | `build_state.py` turns the artifacts into one JSON index (EVAL-CONTRACTS §15), which the `Stop` hook and the runner rebuild; `status.py --brief` prints it at `SessionStart` |
| `editor/vscode-eval` | add-on | **Agentic AI Eval**, the read-only VS Code board: pipeline, layers, suite verdicts with intervals, judge trust, evidence. The coral sibling of the STLC and SDLC boards |
| `tests/` | self-check | `tests/selfcheck.sh` + a deliberately broken fixture — the shipped linter must accept the seed and catch all 23 violation classes; the index must build and notice a stale artifact; runs in this bundle's own CI with the board's tests |

## The seven layers

| Layer | Answers | Technique | Gate |
|---|---|---|---|
| **L0** contract | prompt renders, output schema valid, tool signature, guardrail regex | code assertions, no model calls, under 10s | 100% pass, no exceptions |
| **L1** component | does the retriever fetch the right chunk; does one call do its job | Recall@k · Precision@k · MRR · nDCG on a labelled query set; groundedness | retrieval thresholds from the profile |
| **L2** task | does the whole flow do what the user needed, on the golden set | versioned dataset + assertions + a **validated** judge, binary pass/fail | task success with **CI lower bound** ≥ threshold |
| **L3** agent | right tool, right order, policy held, stable when repeated | simulated user, final-state oracle, trajectory assertions | `pass^1` **and** `pass^k`; 0 hard-policy breaches |
| **L4** safety | injection (direct and via documents/tools), jailbreak, leakage, permission escalation | probes mapped to OWASP LLM Top 10 (2025) + Agentic Top 10 (2026) | 0 unresolved Critical/High; **owned systems, authorized envs only** |
| **L5** nfr | p95 latency, tokens, cost per request, rate-limit and failover behaviour | the existing `k6`/`locust` repos against the entry point | SLO and cost ceiling as runner thresholds |
| **L6** production | does the offline number predict the online one; is the input drifting | OTel GenAI traces, stratified async sampling, offline judging | never gates — feeds the next error-analysis cycle |

Turn layers on and off in `EVAL-PROFILE.md §Layers`. `§Risk tier` decides which are mandatory,
and a mandatory layer left disabled is a lint error (E024) rather than a silent skip.

## Why error analysis comes before anything else

The three phases everyone skips are `/eval-scope`, `/eval-explore`, `/eval-validate`, and skipping
them is why most eval suites measure nothing:

- **A suite built before a failure taxonomy** measures whatever was easy to measure. The metrics a
  framework ships with are the ones that framework could compute, not the ones this system fails at.
- **A dataset built from imagination** tests a product that does not exist. EVAL-CONTRACTS requires at
  least 30% of cases to come from real traces.
- **A judge that was never calibrated** is a number generator. `/eval-validate` is the difference.

Expect 60–80% of the effort to be reading data, not building infrastructure. Error analysis stops
at saturation — when new traces stop producing new failure modes — usually around 100 traces.

## Keeping it current

```bash
npx agentic-fx@latest outdated              # installed vs published
npx agentic-fx@latest update --bundle eval  # replaces only the files the bundle owns
```

Your profile, your `.evals/` artifacts, your adapter and your assertions are never overwritten.
Claude Code and the board also tell you when an update is out. What to do per version is in
[UPGRADE.md](UPGRADE.md).

## Checks this bundle runs on itself

```bash
bash tests/selfcheck.sh
```

Every shipped script parses · the seed satisfies its own contracts · the linter catches all 23
violation classes in `tests/fixture` and exits non-zero · Wilson, `pass^k`, kappa and bias
correction are numerically correct · the runner dry-runs · every agent, command and skill carries
its frontmatter · every skill an agent names exists · every agent a command delegates to exists.

## The board

```bash
cd editor/vscode-eval && npm ci && npm run package
code --install-extension vscode-eval-0.1.0.vsix
```

It reads `.evals/state.json` and nothing else, never writes a file, and shows `NOT-EVALUABLE` as
itself. See [its README](editor/vscode-eval/README.md).

## Versions

`VERSION` holds the bundle version; releases are tagged `vX.Y.Z`. `npx agentic-fx@latest outdated`
compares the version installed in a project with the latest published one. What changed is in [CHANGELOG.md](CHANGELOG.md); what to do about it is in
[UPGRADE.md](UPGRADE.md). Changing the bundle: [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Phases 1 and 5 complete (see the [master plan](https://claude.ai/artifact/TQAG8eL5oJEodoMYJ6G1D5)).
All six evaluation layers L0–L5 are implemented: the core pipeline (scope, error analysis, dataset,
evaluators, validation, run, report, drift, audit) plus RAG, agent, red-team and non-functional.

Remaining: **phase 6**, production monitoring (`/eval-monitor`) — it ships its full contract and
STOPs with a phase note rather than pretending to work. Phases 2–4 are not code: they are running
this pipeline against a real product, and they need a pilot with exportable traces.

## Related

- [`stlc`](../stlc) — the QA lifecycle this bundle hands findings to
- [`verdict`](../verdict) — the report hub this bundle uploads to
- [`rag-reference-guide`](../rag-reference-guide) — the RAG theory L1 measures against
- [`prompts-guide`](../prompts-guide) — prompt technique, kept out of this bundle deliberately
