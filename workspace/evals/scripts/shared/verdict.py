"""Send an eval run to the `verdict` report hub.

Two paths, in order of preference:

1. **The `verdict` CLI**, when it is on PATH. It uploads evidence too — the full traces for every
   case — through presigned URLs. For an eval run that matters more than for an e2e run: the
   artifact someone needs when a case fails is the model's actual output and the steps that
   produced it, and a message field cannot carry it.
2. **Direct HTTP**, stdlib only, when the CLI is absent. Sends the CTRF JSON to
   `POST {server}/api/v1/projects/{key}/reports`. **No evidence** — say so rather than letting
   anyone assume the traces are in the hub.

An upload failure is reported with the retry command, never swallowed. The run is still valid and
its local artifacts are complete; that is what the message says.

See EVAL-CONTRACTS.md section 11 for the CTRF mapping.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class UploadResult:
    ok: bool
    run_id: str = ""
    url: str = ""
    evidence_uploaded: bool = False
    detail: str = ""
    retry_command: str = ""


def _server() -> str:
    return (os.environ.get("VERDICT_URL")
            or os.environ.get("VERDICT_SERVER")
            or "http://localhost:8080").rstrip("/")


def command(*, ctrf_path: str | Path, project: str, env: str, test_type: str = "eval",
            name: str = "", tags: Iterable[str] = (), evidence_dir: str | Path | None = None) -> str:
    """The exact CLI invocation — printed on success and on failure, so a retry is copy-paste."""
    parts = ["verdict upload", f"--project {project}", f"--type {test_type}", f"--env {env}"]
    if name:
        parts.append(f'--name "{name}"')
    parts += [f"--tag {t}" for t in tags]
    parts.append(str(ctrf_path))
    if evidence_dir:
        parts.append(f"--evidence {evidence_dir}")
    return " ".join(parts)


def upload(*, ctrf_path: str | Path, project: str, env: str, test_type: str = "eval",
           name: str = "", tags: Iterable[str] = (), evidence_dir: str | Path | None = None,
           idempotency_key: str = "", out: str | Path | None = ".verdict-run.json",
           timeout: int = 600) -> UploadResult:
    ctrf_path = Path(ctrf_path)
    tags = list(tags)
    retry = command(ctrf_path=ctrf_path, project=project, env=env, test_type=test_type,
                    name=name, tags=tags, evidence_dir=evidence_dir)

    if not ctrf_path.exists():
        return UploadResult(False, detail=f"no CTRF report at {ctrf_path}", retry_command=retry)
    if not project:
        return UploadResult(False, detail="no project key (set VERDICT_PROJECT or pass --project)",
                            retry_command=retry)

    if shutil.which("verdict"):
        result = _via_cli(ctrf_path, project, env, test_type, name, tags, evidence_dir,
                          idempotency_key, out, timeout)
    else:
        result = _via_http(ctrf_path, project, env, test_type, name, tags, idempotency_key, timeout)

    result.retry_command = retry
    if result.ok and out:
        Path(out).write_text(
            json.dumps({"run_id": result.run_id, "url": result.url}, indent=2), encoding="utf-8")
    return result


# --------------------------------------------------------------------------- CLI path

def _via_cli(ctrf: Path, project: str, env: str, test_type: str, name: str, tags: list[str],
             evidence_dir, idempotency_key: str, out, timeout: int) -> UploadResult:
    cmd = ["verdict", "upload", "--project", project, "--type", test_type, "--env", env]
    if name:
        cmd += ["--name", name]
    for t in tags:
        cmd += ["--tag", t]
    if idempotency_key:
        cmd += ["--idempotency-key", idempotency_key]
    if out:
        cmd += ["--out", str(out)]
    cmd.append(str(ctrf))
    if evidence_dir:
        cmd += ["--evidence", str(evidence_dir)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UploadResult(False, detail=f"verdict CLI failed to run: {exc}")

    if proc.returncode != 0:
        return UploadResult(False, detail=(proc.stderr or proc.stdout).strip()[:500])

    run_id = url = ""
    for line in proc.stdout.splitlines():
        if line.startswith("VERDICT_RUN_ID="):
            run_id = line.split("=", 1)[1].strip()
        elif line.startswith("VERDICT_RUN_URL="):
            url = line.split("=", 1)[1].strip()
    return UploadResult(True, run_id=run_id, url=url, evidence_uploaded=bool(evidence_dir),
                        detail=proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "")


# --------------------------------------------------------------------------- HTTP path

def _via_http(ctrf: Path, project: str, env: str, test_type: str, name: str, tags: list[str],
              idempotency_key: str, timeout: int) -> UploadResult:
    query = [("type", test_type), ("env", env)]
    if name:
        query.append(("name", name))
    query += [("tag", t) for t in tags]
    url = f"{_server()}/api/v1/projects/{project}/reports?{urllib.parse.urlencode(query)}"

    req = urllib.request.Request(url, data=ctrf.read_bytes(), method="POST")
    req.add_header("Content-Type", "application/json")
    if key := os.environ.get("VERDICT_API_KEY"):
        req.add_header("Authorization", f"Bearer {key}")
    if idempotency_key:
        req.add_header("Idempotency-Key", idempotency_key)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:500]
        return UploadResult(False, detail=f"HTTP {exc.code}: {detail}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return UploadResult(False, detail=f"{type(exc).__name__}: {exc}")

    return UploadResult(
        True,
        run_id=str(body.get("run_id") or body.get("id") or ""),
        url=str(body.get("url") or ""),
        evidence_uploaded=False,
        detail="uploaded without evidence (the `verdict` CLI is not on PATH — install it to "
               "send the per-case traces too)",
    )


def report(result: UploadResult) -> str:
    """One block a human reads, whichever path ran and whether or not it worked."""
    if result.ok:
        lines = [f"verdict: {result.url or result.run_id or 'accepted'}"]
        if not result.evidence_uploaded:
            lines.append(f"  note: {result.detail}" if result.detail else
                         "  note: no evidence uploaded")
        return "\n".join(lines)
    return "\n".join([
        f"verdict upload FAILED: {result.detail}",
        "  the run itself is valid and its local artifacts are complete.",
        f"  retry: {result.retry_command}",
    ])
