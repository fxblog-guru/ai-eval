#!/usr/bin/env python3
"""Move a suite's baseline forward, or back, without losing where it was (EVAL-CONTRACTS 10).

    python3 .evals/scripts/shared/baseline.py promote --suite <s> --to BASE-<id> [--why "..."]
    python3 .evals/scripts/shared/baseline.py revert  --suite <s> [--why "..."]
    python3 .evals/scripts/shared/baseline.py history --suite <s>

`promote` points the suite's `baseline:` at an existing `baselines/BASE-<id>.json`; `revert` points
it back at the one it replaced. Neither writes nor deletes a baseline file: they are frozen. Every
move is appended to `baselines/HISTORY.jsonl`, so a revert is itself a recorded event and can be
undone by the next promote.

Exit codes: 0 done · 1 refused (the reason is printed) · 2 usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root import resolve_root, root_arg_help  # noqa: E402

BASE_ID = re.compile(r"^BASE-[A-Za-z0-9-]+$")
LINE = re.compile(r"^baseline:\s*(\S*)\s*$", re.M)


def _suite(root: Path, suite: str) -> Path:
    return root / "suites" / f"{suite}.yaml"


def current(root: Path, suite: str) -> str | None:
    m = LINE.search(_suite(root, suite).read_text(encoding="utf-8"))
    return m.group(1) if m and m.group(1) else None


def history(root: Path, suite: str) -> list[dict]:
    p = root / "baselines" / "HISTORY.jsonl"
    if not p.is_file():
        return []
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if r.get("suite") == suite]


def _set(root: Path, suite: str, base_id: str, action: str, why: str | None) -> dict:
    spath = _suite(root, suite)
    text = spath.read_text(encoding="utf-8")
    before = current(root, suite)
    text = LINE.sub(f"baseline: {base_id}", text, count=1) if LINE.search(text) else \
        text.rstrip("\n") + f"\nbaseline: {base_id}\n"
    spath.write_text(text, encoding="utf-8", newline="\n")
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "suite": suite,
             "action": action, "from": before, "to": base_id, "why": why}
    hist = root / "baselines" / "HISTORY.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def promote(root: Path, suite: str, base_id: str, why: str | None = None) -> dict:
    if not BASE_ID.match(base_id):
        raise ValueError(f"{base_id!r} is not a baseline id (BASE-<id>)")
    if not (root / "baselines" / f"{base_id}.json").is_file():
        raise ValueError(f"baselines/{base_id}.json does not exist; a baseline is frozen from a run first")
    if current(root, suite) == base_id:
        raise ValueError(f"{suite} already uses {base_id}")
    return _set(root, suite, base_id, "promote", why)


def revert(root: Path, suite: str, why: str | None = None) -> dict:
    """Back to the baseline the current one replaced. Walking the log backwards, rather than
    keeping a stack, means revert-of-a-revert restores the newer one, as a human would expect."""
    now = current(root, suite)
    for row in reversed(history(root, suite)):
        if row.get("to") == now and row.get("from"):
            if not (root / "baselines" / f"{row['from']}.json").is_file():
                raise ValueError(f"the previous baseline {row['from']} no longer exists")
            return _set(root, suite, row["from"], "revert", why)
    raise ValueError(f"{suite} has no recorded baseline before {now}: nothing to revert to")


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote or revert a suite's baseline")
    ap.add_argument("action", choices=["promote", "revert", "history"])
    ap.add_argument("--suite", required=True)
    ap.add_argument("--to")
    ap.add_argument("--why")
    ap.add_argument("--root", default=None, help=root_arg_help())
    args = ap.parse_args()
    root = resolve_root(args.root)
    if not _suite(root, args.suite).is_file():
        print(f"no such suite: {args.suite}", file=sys.stderr)
        return 2
    try:
        if args.action == "history":
            for r in history(root, args.suite):
                print(f"{r['ts']}  {r['action']:<8} {r['from']} -> {r['to']}  {r.get('why') or ''}")
            return 0
        if args.action == "promote" and not args.to:
            print("promote needs --to BASE-<id>", file=sys.stderr)
            return 2
        e = promote(root, args.suite, args.to, args.why) if args.action == "promote" \
            else revert(root, args.suite, args.why)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(f"{args.suite}: baseline {e['from']} -> {e['to']} ({e['action']}, recorded in baselines/HISTORY.jsonl)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
