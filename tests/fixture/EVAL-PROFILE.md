# EVAL-PROFILE.md — broken fixture

Only the sections lint E024 reads. Every other section is left out on purpose, so each check that
reads the profile falls back to its documented default.

## Risk tier

- **Tier:** `medium`

| Tier | The system… | Mandatory layers |
|---|---|---|
| `low` | drafts text a human always reviews before it leaves | L0 L1 L2 |
| `medium` | answers users directly, or calls read-only tools | L0 L1 L2 L3 L4 |
| `high` | takes actions with side effects, handles money, PII, or safety-relevant decisions | L0 L1 L2 L3 L4 L5 L6 |

## Layers

E024: the tier is medium, which makes L4 mandatory, and L4 is off.

| Layer | Enabled | Runner | Output |
|---|---|---|---|
| `L0` contract | yes | `eval run --layer L0` (no model calls) | `evals/runs/contract/` |
| `L1` component | yes | retrieval + single-call metrics | `evals/runs/component/` |
| `L2` task | yes | golden dataset + evaluators | `evals/runs/task/` |
| `L3` agent | yes | simulated user + trajectory assertions | `evals/runs/agent/` |
| `L4` safety | no | red-team probes | `evals/runs/safety/` |
| `L5` nfr | no | k6 against the entry point | `evals/runs/nfr/` |
| `L6` production | no | sampled live traffic, judged offline | `evals/runs/production/` |
