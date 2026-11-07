#!/usr/bin/env python3
"""Compare two bundle-bench files: did a bundle learn between versions? (EVAL-CONTRACTS 16)

    python3 .evals/scripts/compare_bench.py <a.json> <b.json> [--out report.md] [--min-paired 20]

`a` is the reference (the earlier version, or the `no-lessons` condition), `b` the candidate. Tasks
are paired by `task_id`; the verdict rests on the paired first-pass difference (exact McNemar), so a
task both sides solved, or both failed, carries no weight.

    BETTER                     b solves significantly more tasks first time (p < 0.05)
    WORSE                      b solves significantly fewer
    NO-SIGNIFICANT-DIFFERENCE  the paired test cannot tell them apart
    NOT-EVALUABLE              too few paired tasks, or a paired task has no first_pass

Exit codes: 0 BETTER or NO-SIGNIFICANT-DIFFERENCE · 1 WORSE · 2 usage or unreadable file ·
3 NOT-EVALUABLE.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))

import stats  # noqa: E402

SCHEMA = 1
CONDITIONS = ("lessons", "no-lessons")
ALPHA = 0.05
# Below 20 paired tasks a first-pass interval is wider than any change worth acting on.
MIN_PAIRED = 20
EXIT = {"BETTER": 0, "NO-SIGNIFICANT-DIFFERENCE": 0, "WORSE": 1, "NOT-EVALUABLE": 3}


def load(path: Path) -> dict:
    return load_obj(json.loads(path.read_text(encoding="utf-8")), str(path))


def load_obj(doc, path: str = "<bench>") -> dict:
    """A bench file, with every task carrying the file's bundle/version/condition when it omits them."""
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or not isinstance(doc.get("tasks"), list):
        raise ValueError(f"{path}: not a bundle-bench file (schema {SCHEMA} with a tasks list)")
    if doc.get("condition") not in CONDITIONS:
        raise ValueError(f"{path}: condition must be one of {CONDITIONS}")
    tasks = {}
    for t in doc["tasks"]:
        if not isinstance(t, dict) or not t.get("task_id"):
            raise ValueError(f"{path}: every task needs a task_id")
        tasks[str(t["task_id"])] = {**{k: doc.get(k) for k in ("bundle", "version", "condition")}, **t}
    return {**doc, "tasks": tasks}


def _median(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    # A median over the tasks that happened to report is a different population: report none.
    return statistics.median(nums) if nums and len(nums) == len(values) else None


def _side(tasks: list[dict]) -> dict:
    fp = [t.get("first_pass") for t in tasks]
    known = [x for x in fp if isinstance(x, bool)]
    errs = [t.get("repeat_errors") for t in tasks]
    return {
        "first_pass": stats.wilson(sum(known), len(known)),
        "repeat_errors": sum(e for e in errs if isinstance(e, int)) / len(tasks) if tasks else None,
        "tokens": _median([t.get("tokens") for t in tasks]),
        "duration_s": _median([t.get("duration_s") for t in tasks]),
    }


def compare(a: dict, b: dict, min_paired: int = MIN_PAIRED) -> dict:
    shared = sorted(set(a["tasks"]) & set(b["tasks"]))
    ta = [a["tasks"][k] for k in shared]
    tb = [b["tasks"][k] for k in shared]
    out = {"paired": len(shared), "only_a": len(a["tasks"]) - len(shared),
           "only_b": len(b["tasks"]) - len(shared), "a": _side(ta), "b": _side(tb), "mcnemar": None}
    nulls = [k for k in shared if not isinstance(a["tasks"][k].get("first_pass"), bool)
             or not isinstance(b["tasks"][k].get("first_pass"), bool)]
    if len(shared) < min_paired:
        out["verdict"], out["why"] = "NOT-EVALUABLE", f"{len(shared)} paired task(s), need {min_paired}"
        return out
    if nulls:
        out["verdict"], out["why"] = "NOT-EVALUABLE", f"{len(nulls)} paired task(s) have no first_pass (e.g. {nulls[0]})"
        return out
    p = stats.paired({k: a["tasks"][k]["first_pass"] for k in shared},
                     {k: b["tasks"][k]["first_pass"] for k in shared})
    out["mcnemar"] = p
    if p.p_value < ALPHA and p.c > p.b:
        out["verdict"] = "BETTER"
    elif p.p_value < ALPHA and p.b > p.c:
        out["verdict"] = "WORSE"
    else:
        out["verdict"] = "NO-SIGNIFICANT-DIFFERENCE"
    out["why"] = f"{p.c} task(s) newly first-pass, {p.b} lost, McNemar p={p.p_value:.4f}"
    return out


def _fmt(x, spec: str = ".1f") -> str:
    return "—" if x is None else format(x, spec)


def _delta(x, y, spec: str = "+.1f") -> str:
    return "—" if x is None or y is None else format(y - x, spec)


def report(a: dict, b: dict, r: dict) -> str:
    name = lambda d: f"{d.get('bundle')} {d.get('version')} ({d.get('condition')})"  # noqa: E731
    sa, sb = r["a"], r["b"]
    return (
        f"# Bundle bench — {name(a)} vs {name(b)}\n\n"
        f"## Verdict\n{r['verdict']} — {r['why']}\n\n"
        f"## Results\n| Metric | A | B | Δ |\n|---|---|---|---|\n"
        f"| first-pass rate | {sa['first_pass']} | {sb['first_pass']} | "
        f"{_delta(sa['first_pass'].p, sb['first_pass'].p, '+.3f')} |\n"
        f"| repeat errors per task | {_fmt(sa['repeat_errors'], '.3f')} | {_fmt(sb['repeat_errors'], '.3f')} | "
        f"{_delta(sa['repeat_errors'], sb['repeat_errors'], '+.3f')} |\n"
        f"| median tokens | {_fmt(sa['tokens'], '.0f')} | {_fmt(sb['tokens'], '.0f')} | "
        f"{_delta(sa['tokens'], sb['tokens'], '+.0f')} |\n"
        f"| median duration (s) | {_fmt(sa['duration_s'])} | {_fmt(sb['duration_s'])} | "
        f"{_delta(sa['duration_s'], sb['duration_s'])} |\n\n"
        f"Paired tasks: {r['paired']} · only in A: {r['only_a']} · only in B: {r['only_b']}. "
        f"Rates over paired tasks only; a median is shown only when every paired task reported it.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare two bundle-bench files")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out", help="write the markdown report here as well")
    ap.add_argument("--min-paired", type=int, default=MIN_PAIRED)
    args = ap.parse_args()
    try:
        a, b = load(Path(args.a)), load(Path(args.b))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    r = compare(a, b, args.min_paired)
    text = report(a, b, r)
    print(text, end="")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    return EXIT[r["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
