# Changelog

## [Unreleased]

## [0.3.1] — 2026-10-28

### Added
- **Background rebuild**, as in vscode-sdlc: `evalBoard.backgroundRebuild` (off by default) runs the
  project's `build_state.py` with `evalBoard.python` when a dataset, judge, suite, run, baseline,
  red-team case or report changes, at most once per `evalBoard.backgroundRebuildSeconds` (default
  120, minimum 15). The bundle's Stop hook only fires for a Claude session opened inside the
  project; a session opened in a parent folder left the board frozen at the last build.

## [0.3.0] — 2026-10-27

### Changed

- `evalBoard.statePath` defaults to empty, which follows the bundle's root order:
  `.evals/state.json` when the project has `.evals/`, else `evals/state.json`. A set value is used
  as before. The board also activates on a `.evals/` project.
- The update action runs `npx agentic-fx@latest update --bundle eval` for a project installed with
  the public npx package, `afx update --bundle eval` otherwise, picked by the notice's `source`.

### Added

- **Agents tab (0.2.0, 0.2.1).** The full board has a second view, *Agents*, beside *Board*, and the
  sidebar has an *Agents* tab. **Eval: Open Agents** opens the board on it. Each figure is one
  Claude Code subagent, with a name that is unique within its chat, the work items it names, its
  last step and whether it is working, idle or done. Agents that ran together sit at one round
  table. Chats opened in the project, in a parent folder or in a sibling worktree all count.
  Transcripts are read from `~/.claude/projects`, and nothing is written there. The separate
  *Agents* sidebar view of 0.2.0 is gone: the webview's Content-Security-Policy blocked its inline
  styles, so the figures drew as black shapes. `src/agents.ts`, `src/agentsView.ts` and
  `media/agents.{js,css}` are identical copies of the ones in the sdlc addon.
- The board reads `evals/logs/activity.jsonl`, written in the shared activity format, and adds
  five views: **Summary**, **Activity**, **Decisions**, **Findings** and **Needs you**. They are
  sidebar tabs and sections of the full board.
- Summary shows each layer's latest score against its baseline, and the share of compared layers
  at or above baseline. A suite whose judge is not `VALIDATED` is never compared.
- Findings lists regressions by failure-mode severity, then by size of drop, and opens the run's
  summary on click. A later passing score for the suite clears it.
- The log is watched with the index, so a finished run appears without a refresh.

## 0.1.0

- First release. A read-only board for `evals/state.json` (`EVAL-CONTRACTS §15`): the pipeline
  stepper, the next command, warnings, KPI tiles, layers L0–L6, suites with `pass^k` and its
  interval, and the evidence (failure modes, judges, datasets, probes, scorecards).
- The sidebar Overview, the *Suites* and *Evidence* trees, and a status bar item.
- Confirmed terminal commands: run or dry-run a suite, lint the eval root, `afx update --bundle eval`.
- A multi-project picker, and a version pill driven by the installer's update notice.
