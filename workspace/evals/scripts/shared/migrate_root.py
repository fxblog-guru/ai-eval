"""Move a project's eval root between `evals/` and `.evals/` (EVAL-CONTRACTS section 2).

    python3 <root>/scripts/shared/migrate_root.py --to .evals [--project .] [--write]
    python3 <root>/scripts/shared/migrate_root.py --to evals  [--project .] [--write]

A dry run by default: it prints every step and changes nothing. With --write it

  1. moves the folder: `git mv` in a git work tree (untracked and ignored files follow), a plain
     rename otherwise;
  2. sets EVAL-PROFILE `Eval root` to the new name;
  3. rewires the files that name the root in a command, a path or a glob: .claude/settings.json,
     .claude/settings.local.json, .gitignore, .gitlab-ci.yml, .github/workflows/*.yml, and the
     root's own ci/ template;
  4. rebuilds state.json under the new root.

Artifacts are not rewritten: a run's summary or a review that names `evals/...` is evidence of what
was true when it was written, and every reader takes a path relative to the root.

Exit 0 on success or a clean dry run, 1 when the move cannot be made, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from root import ROOT_NAMES  # noqa: E402

WIRING = [".claude/settings.json", ".claude/settings.local.json", ".gitignore", ".gitlab-ci.yml"]
WIRING_DIRS = [".github/workflows"]
ROOT_WIRING = ["ci/gitlab-ci.yml"]


def prefix_pattern(name: str) -> re.Pattern:
    """`<name>/` at the start of a path token: not `my-evals/`, `.evals/` for `evals`, or `x/evals/`."""
    return re.compile(rf"(?<![\w./@-]){re.escape(name)}/|(?<=^/){re.escape(name)}/", re.M)


def bare_pattern(name: str) -> re.Pattern:
    """The root named without a slash: `EVAL_ROOT: evals`, `cd evals`, `--root evals`."""
    return re.compile(rf"((?:EVAL_ROOT:|cd|--root|working-directory:)\s+['\"]?){re.escape(name)}(?=['\"]?(?:\s|$|;|&))", re.M)


def rewire(text: str, src: str, dst: str) -> str:
    return bare_pattern(src).sub(rf"\g<1>{dst}", prefix_pattern(src).sub(f"{dst}/", text))


def rewire_settings(text: str, src: str, dst: str) -> str:
    """settings.json grants both folders since 1.3.0, so a rewire would leave each rule twice: drop
    the repeats, keeping order. Not JSON we can parse (comments): the plain text rewire."""
    import json  # noqa: PLC0415
    new = rewire(text, src, dst)
    try:
        doc = json.loads(new)
    except ValueError:
        return new
    for rules in (doc.get("permissions") or {}).values():
        if isinstance(rules, list):
            rules[:] = list(dict.fromkeys(rules))
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def set_profile(text: str, dst: str) -> str:
    line = f"- **Eval root:** `{dst}/` (default) — all evaluation artifacts live under this folder"
    pat = re.compile(r"^- \*\*Eval root:\*\*.*$", re.M | re.I)
    if pat.search(text):
        old = pat.search(text).group(0)
        # Keep the reader's own description; replace only the folder.
        new = re.sub(r"`[^`]*`", f"`{dst}/`", old, count=1) if "`" in old else line
        return text.replace(old, new, 1)
    return text


def is_git(project: Path) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(project), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def main() -> int:
    ap = argparse.ArgumentParser(description="Move the eval root between evals/ and .evals/")
    ap.add_argument("--to", required=True, choices=list(ROOT_NAMES))
    ap.add_argument("--project", default=".")
    ap.add_argument("--write", action="store_true", help="make the change (default: dry run)")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    dst = args.to
    src = next(n for n in ROOT_NAMES if n != dst)
    if not (project / src).is_dir():
        print(f"nothing to move: no {src}/ in {project}")
        return 1
    if (project / dst).exists():
        print(f"{dst}/ already exists in {project}; merge or remove it first")
        return 1

    steps: list[tuple[str, Path, str]] = []
    files = [project / f for f in WIRING]
    for d in WIRING_DIRS:
        files += sorted((project / d).glob("*.yml")) + sorted((project / d).glob("*.yaml"))
    for f in files:
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            new = (rewire_settings if f.name.startswith("settings") else rewire)(text, src, dst)
            if new != text:
                steps.append(("rewire", f, new))
    for rel in ROOT_WIRING:
        f = project / src / rel
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            new = rewire(text, src, dst)
            if new != text:
                steps.append(("rewire", project / dst / rel, new))
    profile = project / ".claude" / "EVAL-PROFILE.md"
    if profile.is_file():
        text = profile.read_text(encoding="utf-8")
        new = set_profile(text, dst)
        if new != text:
            steps.append(("profile", profile, new))

    git = is_git(project)
    print(f"{'Moving' if args.write else 'Would move'} {src}/ -> {dst}/ ({'git mv' if git else 'rename'})")
    for kind, f, _ in steps:
        print(f"  {kind:8} {f.relative_to(project).as_posix()}")
    if not args.write:
        print("Dry run: nothing changed. Re-run with --write.")
        return 0

    if git:
        r = subprocess.run(["git", "-C", str(project), "mv", src, dst], capture_output=True, text=True)
        if r.returncode != 0:
            # An untracked root cannot be git-mv'ed; a rename keeps it as it was.
            shutil.move(str(project / src), str(project / dst))
        elif (project / src).exists():
            # git mv leaves ignored files behind (runs/, state.json, .env.*): bring them along.
            for leftover in sorted((project / src).rglob("*"), reverse=True):
                target = project / dst / leftover.relative_to(project / src)
                if leftover.is_file() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(leftover), str(target))
            shutil.rmtree(project / src, ignore_errors=True)
    else:
        shutil.move(str(project / src), str(project / dst))
    for _, f, new in steps:
        f.write_text(new, encoding="utf-8", newline="")

    builder = project / dst / "scripts" / "shared" / "build_state.py"
    if builder.is_file():
        subprocess.run([sys.executable, str(builder), "--root", str(project / dst), "--quiet"], cwd=str(project))
    print(f"Done. The eval root is {dst}/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
