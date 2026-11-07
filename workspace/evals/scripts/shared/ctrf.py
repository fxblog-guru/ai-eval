"""Write CTRF JSON from eval results, for upload to the `verdict` report hub.

One CTRF test result per case PER REPEAT -- not one per case. The repeats are the point:
collapsing them discards the flakiness signal, which for an LLM system is the non-determinism
measurement verdict is built to compute. See EVAL-CONTRACTS.md section 11.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

TOOL_NAME = "agentic-fx-ai-eval"
TOOL_VERSION = "1.4.0"

# ERROR maps to "other", never to "failed". A provider timeout is not a quality signal, and
# burying it in the fail count corrupts both numbers.
STATUS = {"PASS": "passed", "FAIL": "failed", "ERROR": "other", "SKIPPED": "skipped"}


def result_row(
    *,
    case_id: str,
    outcome: str,
    duration_ms: int,
    suite: str,
    layer: str,
    repeat: int,
    of: int,
    fm: Iterable[str],
    judges: Iterable[str],
    dataset: str,
    model: str,
    message: str = "",
    trace: str = "",
    unvalidated: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict:
    """One CTRF test result.

    The tags are the whole reason this integration is worth doing: without them the hub shows a
    pass rate, with them it answers "which failure mode regressed when we changed model".
    """
    tags = [f"fm:{f}" for f in fm]
    tags += [f"judge:{j}" for j in judges]
    tags += [f"dataset:{dataset}", f"model:{model}", f"layer:{layer}", f"repeat:{repeat}"]
    if unvalidated:
        tags.append("unvalidated")

    row = {
        "name": case_id,
        "status": STATUS.get(outcome, "other"),
        "duration": duration_ms,
        "suite": suite,
        "tags": tags,
        "extra": {"repeat": repeat, "of": of, **(extra or {})},
    }
    if message:
        # What a person reads first, and often the only thing they read: name the assertion or
        # judge id and the specific value that failed.
        row["message"] = message
    if trace:
        row["trace"] = trace
    return row


def report(
    *,
    tests: list[dict],
    start_ms: int,
    stop_ms: int,
    env: str,
    build: str = "",
    commit: str = "",
    branch: str = "",
) -> dict:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "pending": 0, "other": 0}
    for t in tests:
        counts[t["status"]] = counts.get(t["status"], 0) + 1

    return {
        "results": {
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "summary": {"tests": len(tests), **counts, "start": start_ms, "stop": stop_ms},
            "tests": tests,
            "environment": {
                "testEnvironment": env,
                **({"buildName": build} if build else {}),
                **({"commit": commit} if commit else {}),
                **({"branch": branch} if branch else {}),
            },
        }
    }


def write(path: str | Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def upload_command(*, ctrf_path: str | Path, project: str, env: str, suite: str,
                   layer: str, dataset: str, evidence_dir: str | Path) -> str:
    """The exact command to run, printed on success and on failure so a retry is copy-paste."""
    return (
        f"verdict upload --project {project} --type eval --env {env} "
        f"--tag {suite} --tag layer:{layer} --tag dataset:{dataset} "
        f"{ctrf_path} --evidence {evidence_dir}"
    )
