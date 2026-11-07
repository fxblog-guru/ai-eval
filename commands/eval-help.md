---
description: Explain the evaluation pipeline, what each command produces, and which one to run next
argument-hint: [command-name | concept]
---

> Read `.claude/EVAL-PROFILE.md` and `.claude/EVAL-CONTRACTS.md` before answering.

Explain the bundle. Writes nothing.

## Arguments

- **`[command-name]`** — explain one command: what it consumes, what it produces, what blocks it
- **`[concept]`** — explain one idea: `judge` · `taxonomy` · `baseline` · `pass^k` · `flaky` ·
  `wilson` · `tpr` · `bias-correction` · `leakage` · `not-evaluable` · `saturation`
- **no argument** — the pipeline overview plus the user's current state

## The pipeline

```
/eval-scope    → .evals/system-card.md          what is measured, and what must never happen
/eval-explore  → .evals/taxonomy/FM-NNN-*.md    how it actually fails, from real traces
/eval-data     → .evals/datasets/DS-<slug>-vN   cases that probe those failures
/eval-judge    → .evals/judges/JDG-<slug>-vN.md an evaluator per failure mode
/eval-validate → judges/<slug>/validation.md   proof the evaluators are trustworthy
/eval-run      → .evals/runs/<suite>/…          measurement, k repeats per case
/eval-report   → .evals/reports/<slug>/…        verdict against gates and baseline

operations:  /eval-drift  (model or prompt changed — what moved?)
             /eval-audit  (are these numbers safe to act on?)
             /eval-status (where am I, what is blocking)
             /eval-signoff (evidence bundle → stlc /qa-signoff)

phase 5:     /eval-rag  /eval-agent  /eval-redteam  /eval-nfr
phase 6:     /eval-monitor
```

## The three things people get wrong

1. **Starting at `/eval-run`.** A suite built before a failure taxonomy measures whatever was easy
   to measure. Start at `/eval-scope`, even when it feels like overhead — especially then.
2. **Gating on an unvalidated judge.** An uncalibrated judge produces numbers that look exactly
   like real data. `/eval-validate` is what tells them apart, and EVAL-CONTRACTS §5.4 refuses the gate
   until it has run.
3. **Concluding from one run.** A single run of 30 cases cannot distinguish a real regression from
   sampling noise. Repeats, intervals, and gating on the CI lower bound are not statistical
   decoration; they are the difference between a measurement and an impression.

## Concept answers to keep short and concrete

| Concept | The one-line version |
|---|---|
| `pass^k` | the fraction of cases that passed on **every** one of k repeats — the number that predicts production, because users get one attempt |
| `flaky` | a case that passed some repeats and failed others; a fact about the system, not noise to filter |
| `wilson` | the confidence interval used for every rate here; gates compare its **lower bound**, never the point estimate |
| `tpr` / `tnr` | how often the judge catches a real failure / correctly clears a real pass, measured on labels it never saw |
| `bias-correction` | `theta_hat = (p_obs - FPR) / (TPR - FPR)` — the true rate, after subtracting the judge's measured error |
| `leakage` | a test case that also appears in the system's prompt or the judge's few-shot examples; the system is being tested on its own answers |
| `not-evaluable` | the measurement could not be trusted. A real verdict, never converted to PASS or FAIL |
| `saturation` | the point where new traces stop producing new failure modes; where error analysis can stop |
| `recall@k` | did the right chunk come back at all — the ceiling on everything downstream |
| `mrr` / `ndcg` | did it come back **near the top**; Recall@k 0.95 with MRR 0.31 is a retriever that looks excellent and behaves badly |
| `groundedness` | every claim in the answer is supported by the retrieved context; decided per claim, not per answer |
| `indirect injection` | an instruction hidden in a retrieved document or tool result — the surface that never passes a human |

Answer the question asked, in a few lines, and name the one command that acts on it.
