# Upgrading agentic-fx-ai-eval

Written for: someone whose project already has the bundle installed and who has been told an
update exists, by the session-start line, the VS Code board, or `npx agentic-fx@latest outdated`.
What changed is in [CHANGELOG.md](CHANGELOG.md); this file says what to *do*.

## How you hear about an update

The installer records the installed version in `.claude/.agentic-fx.json` and, when it checks,
writes `.claude/.agentic-fx-updates.json`. The bundle only reads that file and never goes to the
network:

- the SessionStart hook (`.evals/scripts/shared/status.py --brief`) prints one line, for example
  `[agentic-fx-ai-eval] agentic-fx-ai-eval 1.4.0 available (installed 1.3.0, minor) — npx agentic-fx@latest update --bundle eval`;
- the VS Code board ("Agentic AI Eval") turns its version pill amber.

Set `AFX_NO_UPDATE_CHECK=1` to silence both.

## Every upgrade

1. Commit or stash your work.
2. `npx agentic-fx@latest outdated`: which bundles are behind, and by how much.
3. Read the CHANGELOG entries between your version and the new one. For a MAJOR, read its section
   below first.
4. `npx agentic-fx@latest update --bundle eval`. Add `--dry-run` first to see which files a new
   version no longer ships, without writing anything.
5. `npx agentic-fx@latest doctor` checks the machine and the install. Then prove the scaffold
   (`python` instead of `python3` on Windows; use `evals` if your root is still `evals/`):

   ```bash
   python3 .evals/scripts/shared/lint_evals.py --root .evals
   python3 .evals/scripts/shared/runner.py --suite <a suite> --root .evals --dry-run
   python3 .evals/scripts/shared/build_state.py --root .evals --quiet
   ```

What the installer replaces:

- everything under `.claude/{agents,commands,skills}` that the bundle ships;
- `.claude/EVAL-CONTRACTS.md`;
- the shared scripts under `.evals/scripts/shared/` that the bundle ships.

What it never touches: your system card, taxonomy, datasets, judges and labels, suites, runs,
baselines, reports, adapter (`providers/`), assertions, `.env.<env>` files and `EVAL-PROFILE.md`.

## 1.3.0 → 1.4.0 (minor)

Lint has a new error, **E024**: a layer that `EVAL-PROFILE §Risk tier` makes mandatory is
disabled in `§Layers`. A project whose profile names a tier (`low`, `medium` or `high`) and leaves
one of that tier's mandatory layers at `no` now fails lint, and CI with it.

1. Run the lint. Each E024 names the layer and the tier.
2. Either enable the layer in `§Layers` and build its suite, or, if the tier is wrong, change the
   tier and say why in the system card's `## Risk tier`.
3. A profile whose tier is still the `low | medium | high` placeholder is not checked; choose one.

## 1.2.0 → 1.3.0 (minor)

Nothing breaks. A new project's eval root is `.evals/`; yours stays `evals/` and every script,
hook and the board still find it. To move it:

1. Update the bundle first, so the hooks and permissions know both names.
2. `python3 evals/scripts/shared/migrate_root.py --to .evals` shows what it would change.
3. Add `--write` to move the folder (with `git mv` in a git repo) and rewire `.claude/settings.json`,
   `.gitignore` and your CI files. Run artifacts that mention `evals/...` are left as they were.
4. If you set `evalBoard.statePath` by hand, clear it or point it at `.evals/state.json`.

## 1.1.0 → 1.2.0 (minor)

1. **Judges.** Save each judge's test verdicts to `judges/<slug>/predictions/test.jsonl`, then run
   `calibrate.py JDG-<slug>-vN` and paste its output into `validation.md`. Until you do, lint
   reports E023 on any judge a gated suite uses.
2. **Gated suites.** Add `system_version:`, and `labels_owner:` when a judge decides the suite.
   Without them the verdict is NOT-EVALUABLE ("needs human").
3. **Budget.** Set `tokens_per_call:` in a suite (or let one run measure it) so the up-front
   estimate is known. A run over the token budget now stops with exit 5 unless you pass
   `--confirm-cost`.
4. **Settings.** If your `settings.json` came from a hint file, copy the new `deny` list across and
   remove `Bash(python3 -c *)`.

## 1.0.0 → 1.1.0 (minor)

Nothing breaks, and no artifact changes shape. To get the new parts:

1. **Hooks.** If ai-eval was the first bundle installed, `.claude/settings.json` already has them.
   If another bundle's settings were installed first, the eval settings arrived as
   `.claude/settings.ai-eval.json`. Merge its `hooks` block (`Stop`, `SessionStart`) and its two
   new permissions into `settings.json`. `npx agentic-fx@latest doctor` reminds you to merge it
   while `settings.ai-eval.json` is there.
2. **The shared scripts.** `npx agentic-fx@latest update --bundle eval` replaces the shared
   scripts the bundle owns (`build_state.py`, `ctrf.py`, `lint_evals.py`, `migrate_root.py`,
   `root.py`, `runner.py`, `stats.py`, `status.py`, `verdict.py`); `providers/` and `assertions/`
   are yours and stay as they are. If you have edited one of those scripts by hand, move
   the change into an adapter or an assertion before you update, because the update overwrites it.
3. **`.gitignore`.** If `evals/.gitignore` did not exist, it does now. If you committed
   `state.json` while trying the board, remove it from the index: `git rm --cached evals/state.json`.
4. **The board.** `npx agentic-fx@latest update --bundle eval` installs it into VS Code, Cursor or
   Windsurf unless you pass `--no-addons`; to install a vsix by hand, see
   `editor/vscode-eval/README.md`.
