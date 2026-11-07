# Activity events — one format for sdlc, stlc, ai-eval and qa-standup

Each bundle appends what happened to one file under its own root, and every addon reads that file
for its Activity and Needs you views. qa-standup reads all three and writes the standup from them.
The format is deliberately small, so the four copies cannot drift apart without a test noticing.

## Where

| Bundle | File |
|---|---|
| sdlc | `<sdlc root>/logs/activity.jsonl` (`.sdlc/` or `dev/`) |
| stlc | `<qa root>/logs/activity.jsonl` (`.stlc/` or `qa/`) |
| ai-eval | `<eval root>/logs/activity.jsonl` (`evals/` by default) |

One JSON object per line, appended and never rewritten. The file rolls to `activity.1.jsonl` past
5 MB. It is git-ignored like the rest of `logs/`: it records what happened on this machine. The
committed artifacts stay the source of truth.

## One event

```json
{"v":1,"at":"2026-10-22T09:14:03Z","source":"sdlc","kind":"gate","slug":"recall-dk","outcome":"pass","title":"G3 data PASS","link":".sdlc/reviews/recall-dk/G3-data-20261022-091403-a1b2.md","run_id":"20261022-091403-a1b2","needs":null}
```

| Field | Required | Meaning |
|---|---|---|
| `v` | yes | `1`. A reader skips a line with another value. |
| `at` | yes | ISO-8601 UTC, ending in `Z`. |
| `source` | yes | `sdlc` · `stlc` · `eval` |
| `kind` | yes | one of the kinds below |
| `slug` | yes | the initiative, test plan or eval suite; `null` for a project-wide event |
| `outcome` | yes | `pass` · `fail` · `changes` · `blocked` · `stale` · `stopped` · `info` |
| `title` | yes | one line a person reads, at most 120 characters, with no secrets and no file contents |
| `link` | no | a repository-relative path the addon opens on click |
| `run_id` | no | the run-id that produced it |
| `needs` | no | `null`, or what a human must do: `approve-ui` · `confirm-dec` · `sign-off` · `push` · `merge` · `answer-dec` · `review-stop` |

## Kinds

| Kind | Written by | When |
|---|---|---|
| `gate` | sdlc `build-state` | a gate's derived state changed (PASS, CHANGES_REQUESTED, BLOCKED, STALE, …) |
| `decision` | sdlc `build-state` | a DEC row appeared or changed status (`open`, `assumed`, `answered`) |
| `run` | stlc runner, ai-eval run, sdlc autonomy run | a test, eval or pipeline run finished |
| `stop` | any autonomy run | the run stopped at a hard stop; `needs` says who must act |
| `finding` | stlc triage, ai-eval regressions | a new defect, flaky test or regression |
| `heal` | stlc | a locator healed (outcome `pass`) or refused by the guard (`fail`) |
| `lesson` | stlc | a lesson learned or retired |
| `score` | ai-eval | a layer score against its baseline |

Commits are not written here: every addon already reads them from git.

## Rules for writers

- Never throw and never create the root: no root on disk means no event.
- `ACTIVITY_LOG=off` turns writing off.
- An event is only ever added, never edited. A later event supersedes an earlier one.
- The reader is the source of "Needs you": an event with `needs` set stays there until a later
  event for the same `slug` and `needs` reports `outcome: pass`.
