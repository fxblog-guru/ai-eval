#!/usr/bin/env python3
"""The eval posture in the terminal (SessionStart hook; /eval-status may run it).

Read-only: it derives the state in memory with build_state.py and prints it; it never writes
state.json, so it can never show an index older than the artifacts.

--brief (the SessionStart hook) also prints one line when `afx` has recorded a newer ai-eval in
the project's .claude/.agentic-fx-updates.json. It never goes to the network, and nothing here
may fail a session start: any error prints nothing.

    python3 .evals/scripts/shared/status.py [--root .evals] [--brief]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from root import resolve_root, root_arg_help  # noqa: E402
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]{1,40})?$")
HTTPS = re.compile(r"^https://[^\s<>\"'`]{1,300}$")
TAG = "[agentic-fx-ai-eval]"


def update_line(project_dir: Path) -> str:
    """The update line for the eval bundle, or '' when there is nothing certain to say.

    The notice file's text lands in the session context, so only a version-shaped value and an
    https URL are ever printed, and the command is always the fixed one.
    """
    try:
        if os.environ.get("AFX_NO_UPDATE_CHECK") == "1":
            return ""
        f = project_dir / ".claude" / ".agentic-fx-updates.json"
        if not f.is_file():
            return ""
        b = (json.loads(f.read_text(encoding="utf-8")).get("bundles") or {}).get("eval")
        if not isinstance(b, dict) or b.get("kind") not in ("patch", "minor", "major"):
            return ""
        latest, installed = b.get("latest"), b.get("installed")
        if not (isinstance(latest, str) and isinstance(installed, str)
                and SEMVER.match(latest) and SEMVER.match(installed)):
            return ""
        # One of two fixed commands, by the installer that wrote the notice (npm: = the public package).
        src = b.get("source")
        cmd = ("npx agentic-fx@latest update --bundle eval"
               if isinstance(src, str) and src.startswith("npm:") else "afx update --bundle eval")
        line = f"agentic-fx-ai-eval {latest} available (installed {installed}, {b['kind']}) — {cmd}"
        url = b.get("changelog_url")
        if isinstance(url, str) and HTTPS.match(url):
            line += f" · {url}"
        if b["kind"] == "major":
            line += " — MAJOR: read UPGRADE.md first"
        return line
    except Exception:  # noqa: BLE001
        return ""


def brief(state: dict) -> str:
    t = state["totals"]
    parts = [f"{state['project']} [{state['phase']}]"]
    if t["runs"]:
        parts.append(f"{t['latest_pass']} pass · {t['latest_fail']} fail · "
                     f"{t['latest_not_evaluable']} not-evaluable")
    if t["judges"]:
        parts.append(f"{t['judges_validated']}/{t['judges']} judge(s) VALIDATED")
    if t["failure_modes_blocking_open"]:
        parts.append(f"{t['failure_modes_blocking_open']} blocking FM open")
    if state.get("next_command"):
        parts.append(f"next: {state['next_command']}")
    return f"{TAG} " + " · ".join(parts)


def full(state: dict) -> str:
    from build_state import PHASES  # noqa: PLC0415
    cur = PHASES.index(state["phase"]) if state["phase"] in PHASES else 0
    ladder = "  ".join(f"[{p}]" if i == cur else (p if i < cur else p.lower()) for i, p in enumerate(PHASES))
    lines = [f"{state['project']} — risk tier {state.get('risk_tier') or '?'}", ladder, ""]
    for s in state["suites"]:
        run = s["latest_run"]
        verdict = (run or {}).get("verdict") or "NO RUN"
        pk = (run or {}).get("pass_k")
        rate = f"pass^k {pk['p']:.3f} [{pk['lo']:.3f}, {pk['hi']:.3f}] n={pk['n']}" if pk else ""
        gate = "gated" if s["gated"] else "ungated"
        lines.append(f"  {s['suite']:<28} {s['layer'] or '?':<3} {verdict:<14} {gate:<8} {rate}")
        if s["unvalidated_judges"]:
            lines.append(f"  {'':<28} judge(s) not VALIDATED: {', '.join(s['unvalidated_judges'])}")
    if not state["suites"]:
        lines.append("  no suites yet")
    t = state["totals"]
    lines += ["", f"failure modes open: {t['failure_modes_open']} ({t['failure_modes_blocking_open']} blocking)"
              f" · datasets: {t['datasets']} · judges VALIDATED: {t['judges_validated']}/{t['judges']}"
              f" · red-team probes: {t['redteam_probes']}"]
    if state.get("next_command"):
        lines.append(f"next: {state['next_command']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Print the eval posture")
    ap.add_argument("--root", default=None, help=root_arg_help())
    ap.add_argument("--brief", action="store_true", help="one line, for the SessionStart hook")
    args = ap.parse_args()
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    root = resolve_root(args.root)
    try:
        if not root.is_dir():
            if not args.brief:
                print(f"No eval root at {root}. Start with /eval-scope.")
            return 0
        from build_state import build_state  # noqa: PLC0415
        state = build_state(root)
        print(brief(state) if args.brief else full(state))
    except Exception as exc:  # noqa: BLE001
        if not args.brief:
            print(f"could not derive the eval state: {exc}", file=sys.stderr)
            return 1
    finally:
        if args.brief:
            line = update_line(project)
            if line:
                print(f"{TAG} {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
