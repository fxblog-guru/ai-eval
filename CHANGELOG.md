# Changelog

All notable changes to the agentic-fx-ai-eval bundle. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the version is the one in `VERSION`.
`EVAL-CONTRACTS.md` is versioned with the bundle:

- a MAJOR bump renumbers or removes a section, or changes an id format, a required heading, a
  vocabulary token (§14) or a `state.json` key (§15);
- a MINOR bump adds a section, a rule or a key;
- a PATCH bump changes wording.

## [Unreleased]

## [1.4.0] — 2026-10-30

A layer your risk tier makes mandatory can no longer be switched off without lint saying so, and
the docs install with `npx agentic-fx@latest`.

### Added
- Lint **E024**: a layer that EVAL-PROFILE `§Risk tier` makes mandatory is disabled in `§Layers`.
  The tier comes from the profile's `Tier:` line and the mandatory layers from that section's
  table, so a project that tightens the table is held to it. A tier still at its placeholder is
  not checked. This can fail lint in a project that worked on 1.3.0; see UPGRADE.md.
- EVAL-CONTRACTS §8.1 and §13 describe how E024 decides.

### Changed
- README opens with a Quick Start; README, the user guide, UPGRADE.md, SECURITY.md, the showcase
  and the board's README install, check and update with `npx agentic-fx@latest install`,
  `doctor`, `outdated` and `update` instead of `pipx`, `cli-afx` and `afx`.
- The user guide's `§Layers` advice now says to turn on every layer the tier makes mandatory.
- `ctrf.py` reports tool version 1.4.0 (it still said 1.2.0 in 1.3.0).

## [1.3.0] — 2026-10-27

The eval root is `.evals/` for a new project, beside the dev bundle's `.sdlc/` and the qa bundle's
`.stlc/`. A project with `evals/` keeps working without a change.

### Added
- `scripts/shared/root.py`: one resolver for the eval root, in the installers' order: `--root`,
  `EVAL_ROOT`, EVAL-PROFILE `Eval root` (unless still `(default)`), then `.evals/` or `evals/`,
  whichever exists, then `.evals`. Every script's `--root` now defaults to it.
- `scripts/shared/migrate_root.py --to .evals`: moves an `evals/` root and rewires
  `.claude/settings.json`, `.gitignore` and CI files that name it. A dry run unless `--write`;
  artifacts are not rewritten.

### Changed
- EVAL-CONTRACTS §2: the default eval root is `.evals/`; `evals/` stays a valid root.
- `settings.json`: the `Stop` and `SessionStart` hooks look in `$EVAL_ROOT`, `.evals/`, then
  `evals/`; the script permissions are granted for both folders.
- Every command, agent, skill and template names `.evals/` in its paths.
- The SessionStart update line says `npx agentic-fx@latest update --bundle eval` for a project
  installed with the public npx package (notice `source` starting `npm:`), and
  `afx update --bundle eval` otherwise.

## [1.2.0] — 2026-10-26

Eval results you can trust and check, at a cost known before the run.

### Added

- **Judge calibration is computed.** `calibrate.py` derives TPR, TNR, kappa and the verdict from the
  test labels and the judge's saved predictions. Lint **E023** fails when `validation.md` disagrees.
- **Cost before the run.** The runner prints a token estimate and refuses a run over budget unless
  you pass `--confirm-cost`. `summary.md` shows the estimate against the actual.
- **Fewer tokens by design.** It samples only the cases a declared interval needs and reuses
  unchanged attempts from a cache. It also skips the judge when a code check has already failed.
  `summary.md` shows what each of these saved.
- **Bundle bench.** `compare_bench.py` compares two bundle versions, or a bundle with and without
  its lessons, using a paired test. A WORSE result exits 1. Too little data is NOT-EVALUABLE.
- **Lessons and rollback.** The runner shows lessons from past runs, and withholds any that contain
  unsafe text. `baseline.py` promotes or reverts a suite's baseline and keeps the full history.
- The run log for the VS Code board, and the Summary, Activity, Findings and Needs you views.

### Changed

- A gated suite with no `system_version`, or a judged one with no `labels_owner`, is
  NOT-EVALUABLE with "needs human". The runner never fills these in.
- `settings.json` now denies force pushes, `rm -rf`, `--no-verify` and `.env` reads, and no longer
  allows inline `python3 -c`.

### Fixed

- A suite with no gate, a case that only errored, an unevaluated gate, or a budget overrun can no
  longer produce PASS. Traces are redacted before they are written. Lint adds four audit checks
  (E019–E022).

## [1.1.0] — 2026-10-16

A derived state index, session hooks, a VS Code board and versioned releases.

### Added

- `evals/state.json`, built from the eval files by `build_state.py`; `--check` detects a stale copy.
- A one-line status at session start, and an index rebuild when the session stops.
- The VS Code board "Agentic AI Eval" 0.1.0.
- `VERSION`, this changelog, an upgrade guide, contributing and security notes, MIT licence.

### Changed

- `afx update` keeps the shared scripts current; your adapter and assertions are never touched.

## [1.0.0] — 2026-09-16

First release: 8 agents, 17 commands, 30 skills, evaluation layers L0–L5.
