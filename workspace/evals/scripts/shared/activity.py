"""Append activity events (docs/activity-format.md) to <eval root>/logs/activity.jsonl.

The addons' Activity, Findings and Needs you views, and qa-standup's automatic standup, read this
file. sdlc and stlc write the same format, so every reader shares one parser.

Never raises and never creates the eval root. ACTIVITY_LOG=off stops it. Rolls past MAX_BYTES.

The runner writes three kinds when a run finishes (run_events):

    run      one per run; outcome pass | fail, or info for NOT-EVALUABLE (never shown as either)
    score    the suite's layer score against its baseline; fail when it dropped more than the
             suite's regression_margin (EVAL-CONTRACTS 8, 10)
    finding  outcome fail, one per regression: each failure mode, and the total, that dropped
             more than the margin

A regression title is machine-read by the board, so its shape is fixed:

    regression <FM-id|total> <suite>: <base>% -> <now>% (-<drop> pts)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
KINDS = ["gate", "decision", "run", "stop", "finding", "heal", "lesson", "score"]
OUTCOMES = ["pass", "fail", "changes", "blocked", "stale", "stopped", "info"]
NEEDS = ["approve-ui", "confirm-dec", "sign-off", "push", "merge", "answer-dec", "review-stop"]
SOURCES = ["sdlc", "stlc", "eval"]

_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_ABSOLUTE = re.compile(r"^([a-z]:|/)", re.IGNORECASE)

def event_problems(e) -> list[str]:
    """The problems with one event, as strings; empty when it is valid."""
    if not isinstance(e, dict):
        return ["not an object"]
    out = []
    if e.get("v") != 1 or isinstance(e.get("v"), bool):
        out.append("v must be 1")
    if not isinstance(e.get("at"), str) or not _AT.match(e["at"]):
        out.append("at must be ISO-8601 UTC ending in Z")
    if e.get("source") not in SOURCES:
        out.append(f"source must be one of {', '.join(SOURCES)}")
    if e.get("kind") not in KINDS:
        out.append(f"kind must be one of {', '.join(KINDS)}")
    if "slug" not in e or (e["slug"] is not None and not isinstance(e["slug"], str)):
        out.append("slug must be a string or null")
    if e.get("outcome") not in OUTCOMES:
        out.append(f"outcome must be one of {', '.join(OUTCOMES)}")
    title = e.get("title")
    if not isinstance(title, str) or not title or len(title) > 120:
        out.append("title must be 1-120 characters")
    if e.get("needs") is not None and e.get("needs") not in NEEDS:
        out.append(f"needs must be null or one of {', '.join(NEEDS)}")
    link = e.get("link")
    if link is not None and (not isinstance(link, str) or _ABSOLUTE.match(link)):
        out.append("link must be repository-relative")
    return out

def make_event(now: datetime | None = None, **fields) -> dict:
    """A complete event from the fields a writer knows; `at` defaults to now."""
    when = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "v": 1,
        "at": fields.get("at") or when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": fields.get("source") or "eval",
        "kind": fields.get("kind"),
        "slug": fields.get("slug"),
        "outcome": fields.get("outcome"),
        "title": str(fields.get("title") or "")[:120],
        "link": fields.get("link"),
        "run_id": fields.get("run_id"),
        "needs": fields.get("needs"),
    }

def log_activity(root: Path, events: list[dict], env=None) -> int:
    """Append events; invalid ones are dropped, never written. Returns how many were written."""
    env = os.environ if env is None else env
    root = Path(root)
    if env.get("ACTIVITY_LOG") == "off" or not root.is_dir():
        return 0
    good = [e for e in events if not event_problems(e)]
    if not good:
        return 0
    try:
        d = root / "logs"
        d.mkdir(exist_ok=True)
        f = d / "activity.jsonl"
        if f.exists() and f.stat().st_size > MAX_BYTES:
            f.replace(d / "activity.1.jsonl")
        with f.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in good))
        return len(good)
    except OSError:
        return 0

def read_activity(path: Path) -> list[dict]:
    """Every valid event in a file, oldest first; a bad line is skipped."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn last line from a crash
        if not event_problems(e):
            out.append(e)
    return out

# ---- the runner's events ------------------------------------------------------------------------

def load_baseline(root: Path, baseline_id: str | None) -> dict | None:
    """`baselines/<id>.json`, or None when the suite names none or the file does not parse."""
    if not baseline_id or not re.match(r"^BASE-[A-Za-z0-9-]+$", baseline_id):
        return None
    try:
        doc = json.loads((Path(root) / "baselines" / f"{baseline_id}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None

def baseline_score(base: dict) -> float | None:
    """The baseline's headline rate: `results.task_success.p`, else the first result with a p."""
    results = base.get("results") if isinstance(base.get("results"), dict) else {}
    pick = results.get("task_success") or next(
        (v for v in results.values() if isinstance(v, dict) and "p" in v), None)
    p = pick.get("p") if isinstance(pick, dict) else None
    return float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) else None

def fm_rates(cases: list[dict], outcomes: dict[str, list[bool]]) -> dict[str, float]:
    """Per failure mode, the share of its cases that passed on every repeat (pass^k)."""
    seen: dict[str, list[bool]] = {}
    for c in cases:
        runs = outcomes.get(c.get("case_id"), [])
        if not runs:
            continue
        for fm in c.get("fm") or []:
            seen.setdefault(str(fm), []).append(all(runs))
    return {fm: sum(v) / len(v) for fm, v in seen.items()}

def _pct(p: float) -> str:
    return f"{p * 100:.1f}"

def _regression(what: str, suite: str, base: float, now: float) -> str:
    return f"regression {what} {suite}: {_pct(base)}% -> {_pct(now)}% (-{_pct(base - now)} pts)"

def run_events(*, suite: str, layer: str, run_id: str, verdict: str, pass_k, link: str | None,
               baseline: dict | None, fms: dict[str, float], margin: float = 0.0,
               trusted: bool = True, now: datetime | None = None) -> list[dict]:
    """The events one finished run writes. `pass_k` has p, lo, hi, n.

    A run whose judges are not VALIDATED writes only its run event: its numbers decide nothing
    (EVAL-CONTRACTS 5.4), so they cannot be a score or a regression either.
    """
    outcome = {"PASS": "pass", "FAIL": "fail"}.get(verdict, "info")
    rate = f"pass^k {_pct(pass_k.p)}% [{_pct(pass_k.lo)}-{_pct(pass_k.hi)}] n={pass_k.n}"
    common = {"slug": suite, "run_id": run_id, "link": link}
    out = [make_event(now, kind="run", outcome=outcome, title=f"{suite} {verdict} {rate}", **common)]
    base_p = baseline_score(baseline) if baseline else None
    if not trusted or base_p is None or pass_k.n == 0:
        return out
    drop = base_p - pass_k.p
    failed = drop > margin + 1e-9
    out.append(make_event(now, kind="score", outcome="fail" if failed else "pass",
                          title=f"{layer} {suite} {_pct(pass_k.p)}% vs baseline {_pct(base_p)}% "
                                f"({'-' if drop > 0 else '+'}{_pct(abs(drop))} pts)", **common))
    if failed:
        out.append(make_event(now, kind="finding", outcome="fail",
                              title=_regression("total", suite, base_p, pass_k.p), **common))
    per_fm = baseline.get("per_fm") if isinstance(baseline.get("per_fm"), dict) else {}
    for fm in sorted(per_fm):
        b = per_fm[fm].get("p") if isinstance(per_fm[fm], dict) else None
        if not isinstance(b, (int, float)) or fm not in fms:
            continue
        if b - fms[fm] > margin + 1e-9:
            out.append(make_event(now, kind="finding", outcome="fail",
                                  title=_regression(fm, suite, float(b), fms[fm]), **common))
    return out
