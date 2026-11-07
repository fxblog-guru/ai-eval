# Contributing

Written for: someone changing the bundle itself: a command, an agent, a skill, a script, the
board. Using the bundle in a project is [docs/user-guide.md](docs/user-guide.md).

## Before you start

```bash
bash tests/selfcheck.sh                                         # PYTHON=python on Windows
cd editor/vscode-eval && npm ci && npm run compile && npm test  # the board
```

CI runs three jobs, `selfcheck`, `lint-fixture-is-still-broken` and `editor`. All three must be
green before and after your change. The editor tests build `state.json` from `tests/fixture/`
too, so a change to the fixture can fail the editor job when the other two pass.

`EVAL-CONTRACTS.md` is the authority. If your change needs a rule the contract does not have,
change the contract first, in its own commit, and cite the section from the file that depends
on it.

## Where a change goes

| You want to… | Edit | Not |
|---|---|---|
| change what one command does | `commands/eval-<name>.md` and the skill it invokes | the orchestrator |
| change a rule, an id, a path, a vocabulary word | `EVAL-CONTRACTS.md`, then `lint_evals.py` | anywhere else |
| catch a new violation mechanically | `lint_evals.py`, plus a violation in `tests/fixture/evals/` and its code in `selfcheck.sh` | prose in a skill |
| show something new on the board | `build_state.py` (the key, documented in §15) → `editor/vscode-eval/src/model.ts` → `viewmodel.ts` | parsing markdown in the board |
| change statistics | `stats.py`, with a numeric assertion in `selfcheck.sh` step 4 | a skill's arithmetic |

The board reads `state.json` and nothing else from `.evals/`. If it needs a fact, the builder
derives it, so CI, the session brief and the board can never disagree.

## Rules for the shared scripts

- **Standard library only.** The contract checks must run in CI without an install step.
- **Every script that prints** reconfigures stdout and stderr to UTF-8 on startup. A Windows
  console otherwise kills the SessionStart banner with a `charmap` traceback.
- **Hooks never fail a session.** `status.py --brief` prints nothing on any error.
- **The index never judges.** `build_state.py` copies verdicts and intervals from what the runner
  wrote. If a value cannot be read, it is `null`.

## Releasing

Every release updates `CHANGELOG.md`: move `[Unreleased]` into the new version, written in plain
English for the people who use the bundle. Give one summary line and at most about eight bullets
under Added / Changed / Fixed / Removed. Say what changed for them, not how the work was organised.

1. Move `[Unreleased]` in `CHANGELOG.md` under a version and date; bump `VERSION` (MAJOR /
   MINOR / PATCH, as the changelog header defines them) and `TOOL_VERSION` in `ctrf.py`.
2. If `build_state.py`'s derivation changed, bump `GENERATOR_VERSION`. If a `state.json` key
   changed meaning or went away, bump `SCHEMA` and the board's `SUPPORTED_SCHEMA` together.
3. If the board changed, bump `editor/vscode-eval/package.json` and its `CHANGELOG.md`, then run
   `npm run package`.
4. Merge, then tag `vX.Y.Z` on main. `afx outdated` compares against tags, so an untagged
   release shows as *unknown* in every project.

Commits to `gitlab.com/agentic-fx/*` use the personal identity, and no employer is named in
files, commit messages or branch names. Example systems stay neutral: orders, refunds, support.
