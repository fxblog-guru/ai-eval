# ai-eval user guide

For the engineer who has been handed this bundle and has to produce a trustworthy number about an
LLM feature. The [README](../README.md) says what the bundle is; this says what you actually do,
in what order, and what to do when it stops.

If you only read one thing: **the pipeline refuses to let you gate a release on a judge nobody
calibrated.** Most of what feels like friction here is that rule doing its job.

To see the whole pipeline before reading about it, open
[`docs/showcase/pipeline.html`](showcase/pipeline.html) in a browser. One sample assistant goes
through all thirteen steps, including a judge that fails validation at v1 and an agent suite that
comes back `NOT-EVALUABLE`.

---

## 1. What you will be able to say at the end

Not "the AI seems good". These:

- *"Task success is 84%, and we're 95% confident it's at least 79%, on 200 cases from real traffic."*
- *"Moving to the new model changed nothing we can detect: −1.2pp, interval −5.8 to +3.4."*
- *"FM-003 regressed from 0.88 to 0.61. Here are nine traces."*
- *"That number is NOT-EVALUABLE — the judge deciding it agrees with our reviewers 61% of the time."*

The last one is the point. A pipeline that can only say "green" is not measuring anything.

---

## 2. Day 1 — install and prove the scaffold works

You need Node 20+, Claude Code and Python 3.9+ (and Git for Windows on Windows).

```bash
cd <your-llm-project>
npx agentic-fx@latest install --bundle eval   # --bundle all installs the dev and qa bundles too
npx agentic-fx@latest doctor                  # checks Node, Claude Code, Git Bash, Python, the editor, the install
```

The installer puts the bundle in `.claude/`, the workspace in `.evals/`, and the **VS Code board**
("Agentic AI Eval") into VS Code, Cursor or Windsurf, whichever it finds (`--no-addons` skips it).
The board shows the pipeline, each suite's latest verdict with its interval, and which judges can
be trusted, live from `.evals/state.json`. `doctor` checks the machine and the install, not the
scaffold: the lint and the dry run below do that.

Or by hand:

```bash
cd <your-llm-project>
git clone https://gitlab.com/agentic-fx/ai-eval.git /tmp/ai-eval
mkdir -p .claude
cp -r /tmp/ai-eval/{agents,commands,skills} .claude/
cp /tmp/ai-eval/{EVAL-PROFILE.md,EVAL-CONTRACTS.md} .claude/
cp -r /tmp/ai-eval/workspace/evals ./.evals
cp .evals/.env.example .evals/.env.staging
```

Prove it runs before you write anything (`python` instead of `python3` on Windows):

```bash
python3 .evals/scripts/shared/lint_evals.py --root .evals
# → 0 error(s), 0 warning(s) / contracts hold.

python3 .evals/scripts/shared/runner.py --suite task-example --root .evals --dry-run
# → 3 cases x 3 repeats = 9 calls / dry run: no model calls made.
```

Both green means the shipped seed is intact. The seed is a small working example — a system card,
one failure mode, a three-case dataset, an L1 retrieval suite. **Read it before replacing it**; it
shows the shape of everything you are about to write.

### Fill in `EVAL-PROFILE.md`

Six fields decide everything downstream. The rest can stay on defaults:

| Field | Why it matters |
|---|---|
| `§System under evaluation → Adapter` | the one function that reaches your system |
| `§Models → system` | **exact model id.** Not `-latest` — an alias the provider can repoint means your system changes with no commit, and every historical comparison is quietly wrong |
| `§Models → judge` | must be a **different model family** from the system, in any gated suite |
| `§Risk tier` | decides which layers are mandatory |
| `§Layers` | turn on every layer your tier makes mandatory (L0–L2 for `low`, up to L4 for `medium`, all seven for `high`); one left off is lint E024. Leave the others off until you need them |
| `§Environments` | which env may be attacked or load-tested. `prod`: neither |

### Write the adapter

`.evals/scripts/shared/providers/<your-system>.py`, copied from `example.py`. One function:

```python
def call(case_input: dict) -> dict:
    return {"output": {...}, "steps": [...], "meta": {...}}
```

**`steps` is the part people skip and regret.** It is the ordered spans — each LLM call, tool call
and retrieval, with its input and output. Without it, a failure shows up three steps downstream of
its cause and you cannot tell a retrieval problem from a prompt problem. If your system is
instrumented with OpenTelemetry GenAI conventions, derive `steps` from the span tree.

---

## 3. Day 1–2 — L0, the layer that pays immediately

L0 needs no traces, no judge, no tokens, and runs in under ten seconds. Do it before anything else;
it usually finds something real on the first run.

```
/eval-scope
```

Produces `.evals/system-card.md`. The section that carries the file is `## Hard policies`. Test each
line: **could two people, reading the same output, disagree about whether it was violated?** If
yes, it is not a policy yet.

```
✗  Be accurate and helpful.
✗  Don't hallucinate.
✓  Never state an order id that did not come from a tool result.
✓  Never quote a refund timeline that differs from the policy for that payment method.
✓  Never return data for an order that does not belong to the calling customer.
```

A rule you genuinely cannot make testable is written as `SCOPE-GAP: <rule> — not testable because
<reason>`. Never soften it into something that merely sounds testable — that produces a judge
nobody can calibrate and a gate that means nothing.

Then build the L0 suite: output schema, required fields, tool signatures, guardrail patterns,
citation resolution. Gate it at 100% and run it on every merge request.

---

## 4. Week 1 — error analysis, the part that cannot be delegated

```
/eval-explore --from-profile --count 100
```

**You read the first 30 traces yourself.** This is not ceremony and it is not skippable. The
failure modes present in *your* data are visible only to someone who read it; after 30 you can
judge a proposed code in seconds, before 30 you cannot judge one at all.

The order matters:

1. **Open coding** — free-text notes on what is wrong with each trace. Do not reach for a category
   while reading. Categories chosen in advance are the ones you will find, whether or not they are
   there.
2. **Axial coding** — group the notes into failure modes. This step carries the whole phase.
3. **Taxonomy** — `FM-001`, `FM-002`, … permanent ids, each with **at least three real trace refs**.

Under three observations it is a hypothesis, not a failure mode. It stays in the notes until it
recurs. This one rule is what keeps the taxonomy from filling with things somebody worried about
once.

### Getting the granularity right

The single judgement you make repeatedly:

| Too fine | Right | Too coarse |
|---|---|---|
| "quoted 3-5 days for a card refund" · "quoted 2 days for a bank refund" (2 FMs) | **"States a refund timeline that contradicts the policy for that payment method"** (1 FM, 2 instances) | "Gives wrong information" (1 FM, 40 instances, no evaluator can be written) |

Two tests: **could one evaluator decide it?** and **would one fix address it?** When they disagree,
follow the fix test — a taxonomy exists so someone can act on it.

### Before you build anything, fix the obvious

`/eval-explore` flags failure modes whose likely fix is one prompt line. **Fix those, re-pull
traces, and see what survives.** Building a judge and labelling 200 examples for a failure that
disappears when someone adds a sentence to the prompt is the most expensive mistake available here
— and that judge will still be running, still passing, a year later.

### Build the annotation interface

Before any labelling push over ~50 items, run `building-annotation-ui`. At two minutes per item in
a spreadsheet, judge validation is six hours of unpleasant work and does not get done; at ten
seconds it happens. This is the difference between a validated judge and a permanently
`NOT-EVALUABLE` gate.

---

## 5. Week 2–3 — dataset, evaluators, calibration

```
/eval-data <slug>        # ≥30% cases from real traces, one case per dimension tuple
/eval-judge <slug>       # code assertion first; judge only where judgement is required
/eval-validate <slug>    # ← the gate
```

### Try a code assertion first, every time

| Failure mode | Assertion? |
|---|---|
| invents an order number | **yes** — every id-shaped token appears in a tool result |
| cites a chunk that wasn't retrieved | **yes** — cited ids ⊆ retrieved ids |
| refunds more than the order total | **yes** — compare to the fixture |
| leaks the system prompt | **yes** — n-gram overlap |
| is grounded in the retrieved context | no — needs judgement |
| tone acceptable to a frustrated user | no — needs judgement |

Converting one failure mode from a judge to an assertion removes a cost line, a variance source and
a 200-label project. It is the highest-leverage move in this phase and it is skipped constantly,
because reaching for a judge feels faster in the moment.

### What validation actually requires

- Human labels split **once**: train 10–20%, dev 40–45%, test 40–45%
- **30–50 Pass and 30–50 Fail in each of dev and test** — fewer and the TPR does not mean what it
  appears to
- Iterate the judge prompt against **dev** freely; score **test** once, at the end
- Every false positive and false negative listed individually, with why

The rates tell you whether the judge is good. **The disagreements are the only thing that tells you
how to improve it** — so that section is never summarized.

`## Verdict` is `VALIDATED` or `UNVALIDATED`, and it is the honest one. There will always be a
release waiting and the judge will always be nearly good enough. That is exactly the moment the
rule is worth having.

---

## 6. Week 3–4 — measure, freeze, and gain the drift check

```
/eval-run task --env staging
/eval-report <slug> --freeze     # writes BASE-<id>
```

From the moment a baseline exists you can answer, with evidence, the question that arrives weekly:

```
/eval-drift <slug> --against BASE-2026-09-16-refunds --change model
```

It reports a **paired difference with its interval**, not two percentages:

```
-3.0pp [-7.1, +1.1]  (n=200 paired, 9 regressions, 3 improvements)  → no detectable change
```

"84% then 81%" reads as a three-point drop. The interval says what is actually known.

**Regression is judged per failure mode, never on the total.** A total that holds steady while
FM-003 collapses and FM-007 improves is the most common shape of a real regression — and the totals
row is exactly where it hides.

---

## 7. If your system is RAG — do this before touching the prompt

```
/eval-rag <slug> --stage retrieval
```

A wrong answer has causes that need different fixes, and one blended score cannot tell them apart:

| What happened | Recall@k | MRR | Groundedness | Fix belongs to |
|---|---|---|---|---|
| chunk never retrieved | low | — | nothing to ground in | chunking, embedding, k, query rewriting |
| retrieved at rank 8, ignored | **fine** | low | low | reranker, context order |
| retrieved first, contradicted | fine | fine | low | prompt, model, or the corpus |

Recall@k is the **ceiling** on everything downstream. Teams that measure only end-to-end quality
spend weeks tuning a prompt for a problem that was in the retriever.

Two things gate this layer, and both are worth knowing on day one:

- **A labelled query set** — 50–100 queries with the chunk ids that should come back, of which
  10–20% are `known_absent` (the corpus genuinely does not answer them). This is the highest-value
  labelling work in a RAG system.
- **Stable chunk ids across index rebuilds.** If ids change on rebuild, every label expires on
  every rebuild and L1 is not measurable at all. That is a blocking indexing finding, not a
  limitation to work around — and finding it early saves the whole layer.

---

## 8. When a command stops

Every stop is a contract doing its job. The common ones:

| Message | What it means | What to do |
|---|---|---|
| no traces at the source | the taxonomy would be failures you imagined | ship behind a flag and collect traces, or accept a hypothetical dataset **in writing** and record it |
| `FM-00x` has fewer than 3 trace refs | it is a hypothesis | leave it in the notes; the next batch confirms it or does not |
| gated suite names an `UNVALIDATED` judge | the gate would be decided by an uncalibrated judge | label more examples and re-validate, or remove the gate. Those are the only two options |
| dev/test split has under 30 Pass or Fail | the TPR would not mean what it says | label more of the scarce class — usually Fail |
| model id is unpinned | the run would be unattributable | put an exact id in the suite; never an alias ending `latest` |
| dataset `n < 30` on a gated suite | cannot tell a regression from noise | more cases, or drop the gate until you have them |
| dataset hash mismatch | someone edited a frozen dataset | bump to `vN+1`; every run referencing the old one is now incomparable |
| open FM with no dataset case | the suite reports that failure as fine, forever | add cases, or retire the FM deliberately |
| probe authorization missing | the target env does not permit adversarial testing | use an authorized env. There is no override, and `prod` is never authorized by default |

### The three verdicts

| Verdict | Means |
|---|---|
| `PASS` | every gate's **CI lower bound** cleared its threshold, and every judge involved is `VALIDATED` |
| `FAIL` | a gate did not clear. The report names the single gate that decided it |
| `NOT-EVALUABLE` | the measurement could not be trusted — unvalidated judge, `n` too small, truncated run, or the interval spans the threshold |

`NOT-EVALUABLE` is a real answer. It is never converted to `PASS` to turn a pipeline green, and
never to `FAIL` to be safe. It means: go fix the measurement, then ask again.

---

## 9. Your rhythm once it is running

| When | Run | You get |
|---|---|---|
| every merge request | L0 contract suite | schema, tool signatures, guardrails — seconds, no tokens |
| nightly | `/eval-run task` on the pinned dataset | task success with intervals, pushed to `verdict` |
| model, provider or prompt changed | `/eval-drift --against BASE-…` | a paired difference with its interval |
| before a release | `/eval-redteam` · `/eval-report` · `/eval-signoff` | findings, scorecard, and the evidence bundle for `stlc` |
| monthly | `/eval-explore --batch` on fresh traces | new failure modes; the taxonomy stays current |
| quarterly, or on any inherited suite | `/eval-audit` | one answer: are these numbers safe to act on? |

**Why the split:** a full eval on every merge request is either expensive, slow, or too small to be
significant — you can pick at most two. Cheap deterministic checks on every MR and the full judged
sweep nightly is the arrangement that survives.

---

## 10. The five mistakes that cost the most

1. **Starting at `/eval-run`.** A suite built before a failure taxonomy measures whatever was easy
   to measure. The metrics a framework ships with are the ones that framework could compute.
2. **Gating on an uncalibrated judge.** 84% from a good judge and 84% from a judge that agrees with
   humans 61% of the time are indistinguishable on a dashboard, and get quoted identically.
3. **Building an evaluator for a failure a prompt edit removes.** Fix the obvious first, re-pull
   traces, then build for what survives.
4. **A dataset everything passes.** Above 95% the suite has stopped discriminating. Around 70% is
   where the signal is — if your first run passes almost everything, go back to the traces and pull
   the hard ones.
5. **Concluding from one run of 30 cases.** That cannot distinguish a real regression from sampling
   noise, and it will be quoted as if it could.

---

## 11. Where everything lives

```
.claude/EVAL-PROFILE.md          the one config file — fill this, not the skills
.claude/EVAL-CONTRACTS.md                when a file disagrees with this, this wins

.evals/system-card.md                what is measured, and what must never happen
.evals/traces/<TB-id>/               pulled traces + open-coding notes — evidence, never edited
.evals/taxonomy/INDEX.md             the ONLY place FM ids are minted
.evals/datasets/DS-<slug>-vN.jsonl   immutable once a run references it
.evals/judges/<slug>/validation.md   TPR/TNR/κ — the trust gate
.evals/suites/<suite>.yaml           dataset + evaluators + repeats + gates
.evals/runs/<suite>/<run-id>/        results, full traces, ctrf.json
.evals/baselines/BASE-<id>.json      what "before" means
.evals/reports/<slug>/…              the scorecard a release decision rests on
.evals/state.json                    DERIVED index for the board and the session brief — never edited, git-ignored
```

`.evals/state.json` is rebuilt by the `Stop` hook after every turn and by the runner after every
run (EVAL-CONTRACTS §15). If it ever disagrees with the files, the files are right:
`python3 .evals/scripts/shared/build_state.py` rebuilds it, and `--check` tells you whether it was
stale.

---

## 12. How it fits the rest of agentic-fx

| Repo | Role | Boundary |
|---|---|---|
| [`stlc`](../../stlc) | defects, quarantine, release sign-off | ai-eval **measures**; it never opens or triages a defect. Findings hand over with the FM id and run path |
| [`verdict`](../../verdict) | run history, flakiness scoring, gates | every run writes CTRF and uploads. Verdict's flaky score **is** the non-determinism measurement — not reimplemented here |
| [`rag-reference-guide`](../../rag-reference-guide) | RAG theory | ai-eval measures against it; it does not restate it |
| [`prompts-guide`](../../prompts-guide) | prompt technique | deliberately out of scope — this bundle measures prompts, it does not teach writing them |

---

## 13. Getting unstuck

```
/eval-status        where am I, what is blocking, which judges can be trusted
/eval-help          the pipeline, or one command, or one concept
/eval-help judge    concept cards: pass^k · wilson · tpr · bias-correction · not-evaluable
/eval-audit         are these numbers safe to act on?
```

Each session also starts with one line from the `SessionStart` hook: the phase, the latest
verdicts, the next command, and an update notice when the installer has seen a newer bundle
(`npx agentic-fx@latest outdated` checks now; `npx agentic-fx@latest update --bundle eval` updates).

`/eval-status` is the fastest way to orient after a break. It reads the filesystem and tells you
the phase, the single next command, and — the thing that is otherwise invisible — any gated suite
currently running on a judge nobody validated.
