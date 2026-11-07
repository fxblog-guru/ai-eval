"""Where the eval root is (EVAL-CONTRACTS section 2).

A new project keeps every eval artifact in `.evals/`, beside the dev bundle's `.sdlc/` and the qa
bundle's `.stlc/`; a project installed before 1.3.0 keeps `evals/`, which goes on working unchanged.
Every script resolves the root here, in one order:

  1. an explicit `--root <path>`;
  2. `EVAL_ROOT` (env), relative to the project;
  3. EVAL-PROFILE `Eval root`, unless the line still carries the template's `(default)` marker:
     an untouched default is not a choice;
  4. whichever of `.evals/` or `evals/` exists, `.evals/` first;
  5. `.evals`.

The same order as the installers' resolve_workspace_dst, so a script and an update agree.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_ROOT = ".evals"
LEGACY_ROOT = "evals"
ROOT_NAMES = (DEFAULT_ROOT, LEGACY_ROOT)


def profile_root(text: str) -> str | None:
    """The profile's eval root, or None when the line is missing, a placeholder, or `(default)`."""
    m = re.search(r"^- \*\*Eval root:\*\*(.*)$", text.replace("\r\n", "\n"), re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    head = re.split(r"\s[—–]\s", m.group(1))[0]
    if re.search(r"\(default\)", head, re.IGNORECASE):
        return None
    v = re.search(r"`([^`]+)`", head)
    value = v.group(1).strip() if v else ""
    if not value or value.startswith("<"):
        return None
    value = value.replace("\\", "/")
    if value.startswith("./") and len(value) > 2:
        value = value[2:]
    return value.rstrip("/") or None


def _profile_text(project: Path) -> str:
    for p in (project / ".claude" / "EVAL-PROFILE.md", project / "EVAL-PROFILE.md"):
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def resolve_root(explicit: str | None = None, project: Path | None = None) -> Path:
    """The eval root as a path relative to (or under) `project`, the working directory by default."""
    if explicit:
        return Path(explicit)
    project = Path(project) if project is not None else Path.cwd()
    env = os.environ.get("EVAL_ROOT", "").strip()
    if env:
        return project / env
    configured = profile_root(_profile_text(project))
    if configured:
        base = project.resolve()
        target = (project / configured).resolve()
        if target != base and base in target.parents:
            return project / configured
    for name in ROOT_NAMES:
        if (project / name).is_dir():
            return project / name
    return project / DEFAULT_ROOT


def root_arg_help() -> str:
    return ("the eval root (default: EVAL_ROOT, then EVAL-PROFILE `Eval root`, "
            "then .evals/ or evals/, whichever exists)")
