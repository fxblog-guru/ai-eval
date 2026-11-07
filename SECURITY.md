# Security

This bundle is a set of Markdown instructions, Python scripts and templates that run inside Claude
Code on your machine, plus an optional read-only VS Code board. It ships no server.

The only network calls come from your own configuration:

- your adapter calls the system under evaluation;
- judge, synthetic-data and simulator calls go to the providers named in `EVAL-PROFILE.md`;
- an upload to `verdict` happens only when `VERDICT_URL` is set.

The hooks and the board never touch the network.

## What the bundle will not do

- Run red-team probes (L4) or load tests (L5) against an environment whose `§Environments` row in
  `EVAL-PROFILE.md` says `no`. CI never authorizes an environment: the `.evals/ci/` templates keep
  L4 and L5 jobs manual.
- Probe a system the profile does not declare as the system under evaluation.
- Commit a credential. `.evals/.env.*` is git-ignored except `.env.example`. A trace is redacted at
  pull time (EVAL-CONTRACTS §4) and the redaction is recorded.
- Run a command it read from a file. The update notice is data: the session line and the board
  print only version-shaped values and https URLs, and the update command is always a fixed one:
  `npx agentic-fx@latest update --bundle eval` (`afx update --bundle eval` for a project installed
  with the internal `afx` CLI).
- Write to the workspace from the board. It starts a terminal only after you confirm the exact
  command it will type.

## Reporting a vulnerability

Open a confidential issue on the GitLab project. Include the bundle version (`VERSION`), the
command that was running, and the run folder (`.evals/runs/<suite>/<run-id>/`) if one was written.
We aim to acknowledge within five working days.
