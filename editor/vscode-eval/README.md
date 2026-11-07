# Agentic AI Eval — VS Code board

A live, read-only board for the [`agentic-fx-ai-eval`](https://gitlab.com/agentic-fx/ai-eval)
pipeline. It shows where an LLM feature is in evaluation, what each suite's latest run said and
how sure that verdict is, which judges can be trusted, and what to run next. You never open a
markdown file to get this, and the board never writes one.

It is the third member of the family: **Agentic SDLC** (lavender) builds, **Agentic STLC** (teal)
tests, **Agentic AI Eval** (coral) measures the model. All three share the layout, pills, stepper
and tiles, so a team running all three bundles reads them the same way.

## What it shows

**Board** (`Eval: Open Board`)

- **The pipeline**: Scope → Explore → Data → Evaluate → Validate → Run → Report, with the current
  rung filled. The rung comes from `.evals/state.json`. It is the furthest step whose artifact
  exists, never a guess about intent. There is no sign-off rung, because release decisions go to
  `stlc` (`EVAL-CONTRACTS §12`).
- **Next**: the one `/eval-*` command that advances the pipeline, with a Copy button. The board
  never runs it.
- **Warnings** it raises without being asked:
  - the system card is still the shipped seed;
  - a gated suite uses a judge that is not `VALIDATED`, so it can only report `NOT-EVALUABLE` (§5.4);
  - a blocking failure mode is open;
  - the index is older than the files it cites.
- **KPI tiles**: suites passing on their latest run, suites `NOT-EVALUABLE`, judges validated,
  and open failure modes, with the blocking count.
- **Layers L0–L6**: each layer's worst latest verdict. A layer that is disabled in
  `EVAL-PROFILE §Layers` and has no suite shows *OFF*.
- **Suites**: layer, verdict, `pass^k` **with its 95% interval and n** (a rate is never shown
  without one), why the verdict is what it is, a trend arrow against the previous run, and
  **Dry-run…**. A dry run calls no model.
- **Evidence**: failure modes (open first, blocking in red), judges (TPR · TNR · κ), datasets
  (cases, share from real traces, hash), red-team probes (red when a probe has no
  `## Authorization`) and scorecards. Every row opens its file.

**The activity log** (`.evals/logs/activity.jsonl`, in the format of the bundle's
`docs/activity-format.md`): the runner appends a run event, a score against the suite's baseline,
and one finding per regression. The board reads it into five views, as tabs in the sidebar and as
sections on the page:

- **Summary**: what the suites evaluate, the latest run, each layer's score against its baseline
  (at or above it, below it, no baseline, or judge not validated), the share of compared layers at
  or above baseline, and the next command.
- **Activity**: the log, newest first, filterable by kind.
- **Decisions**: always empty with a note. ai-eval keeps no decision ledger.
- **Findings**: regressions, by failure-mode severity and then by size of drop. Click one to open
  the run's summary. A later passing score for the suite clears it.
- **Needs you**: what the log asks a person for, such as a sign-off, until a later pass clears it.

**Sidebar**: the Overview (the five tabs above, at sidebar width), *Suites* (each suite, then its
rates and failing cases) and *Evidence*.

**Status bar**: the phase and the latest verdicts, e.g. `Run · 3✓ 1✗ 1?`. `?` means
NOT-EVALUABLE. Click it to open the board.

**Version pill**: the installed `eval` bundle version, from `.claude/.agentic-fx.json`. When the
installer's no-network notice `.claude/.agentic-fx-updates.json` names a newer version, the pill
turns amber. Click it to open the changelog, update in a terminal (you confirm the exact command
first), or dismiss that version. The command is fixed: `npx agentic-fx@latest update --bundle eval`
(a project installed with the internal `afx` CLI gets `afx update --bundle eval`). Text in the
notice file is never run.

## What it never does

- Write a file. The index is built by the bundle's `build_state.py`, never by the board.
- Turn `NOT-EVALUABLE` into a pass or a fail.
- Run anything you did not confirm. Each command (`Eval: Run a Suite…`, `Eval: Dry-run a Suite…`,
  `Eval: Lint the Eval Root…`, `Eval: Bundle Update…`) opens a quick pick that shows the exact
  command line. It types it into a new terminal only when you pick *Run in a terminal*. A full run
  calls the model and costs tokens, and the quick pick says so.
- Open a path outside the selected project.

## Requirements

- The ai-eval bundle in the project, version 1.1.0 or later. It ships `build_state.py` and the
  `Stop` hook that keeps `.evals/state.json` current. Install it with
  `npx agentic-fx@latest install --bundle eval`, which installs this board too.
- Python 3.9+ for the commands you choose to run. The board itself needs nothing.

If `.evals/state.json` is missing, the board says how to build it:

```bash
python3 .evals/scripts/shared/build_state.py
```

## Several projects in one workspace

Every `.evals/state.json` under the workspace is found, newest first. Dot folders, `node_modules`
and virtualenvs are skipped. **Eval: Select Project** pins one; *Most recently updated* follows
whichever project changed last.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `evalBoard.statePath` | `.evals/state.json` | where the index is, relative to the project; must match the eval root in `EVAL-PROFILE.md` |
| `evalBoard.python` | *(empty)* | the interpreter the confirmed commands use; empty means `python3`, or `python` on Windows |
| `evalBoard.showStatusBar` | `true` | the status bar item |
| `evalBoard.accent` | `coral` | `coral` · `violet` · `theme` |

## Install

`npx agentic-fx@latest install --bundle eval` installs the board with the bundle into VS Code,
Cursor or Windsurf, whichever it finds; `npx agentic-fx@latest update --bundle eval` keeps it
current.

From a release vsix:

```bash
code --install-extension vscode-eval-<version>.vsix
```

From a checkout:

```bash
cd editor/vscode-eval
npm ci
npm run compile
npm run package          # → vscode-eval-<version>.vsix
code --install-extension vscode-eval-0.1.0.vsix
```

## Develop

```bash
npm ci && npm run compile && npm test     # PYTHON=python on Windows
```

The tests build `.evals/state.json` from the bundle's own seed and its broken fixture, using the
shipped `build_state.py`. A change to the builder's output that the board does not understand
fails here, and in the bundle's CI `editor` job, before it reaches anyone's editor.
`npm run icon` regenerates `media/icon.png` from `media/make-icon.mjs`.
