#!/usr/bin/env python3
"""Derive .evals/state.json from the eval artifacts (EVAL-CONTRACTS section 15).

Pure derivation: it reads what the pipeline wrote and never judges it. Every rule it applies is
one EVAL-CONTRACTS already states (where a run lives, what a judge's verdict line says, which
scorecard is newest); anything it cannot read is reported as null, never guessed.

    python3 .evals/scripts/shared/build_state.py [--root .evals] [--check] [--quiet] [--stdout]

--check exits 1 when the committed or cached state.json is not what the artifacts derive to
(generated_at ignored), so CI can catch a hand-edited index. EVAL_STATE_NOW=<ISO-8601> fixes
the clock, so fixtures derive byte-identical output on any day.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from root import resolve_root, root_arg_help  # noqa: E402
from activity import baseline_score  # noqa: E402
from lint_evals import _parse_suite, _section  # noqa: E402

GENERATOR_VERSION = "1.1.0"
SCHEMA = 1

# The pipeline a system moves through, bottom rung first — the ladder /eval-status prints.
# Sign-off is not here on purpose: release decisions belong to stlc (EVAL-CONTRACTS 12).
PHASES = ["Scope", "Explore", "Data", "Evaluate", "Validate", "Run", "Report"]
LAYERS = ["L0", "L1", "L2", "L3", "L4", "L5", "L6"]

RUN_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}$")
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})-(scorecard|eval-audit)\.md$")
GATE_VERDICTS = ("NOT-EVALUABLE", "PASS", "FAIL")  # longest first: NOT-EVALUABLE contains neither
RATE = re.compile(r"(\d\.\d+)\s*\[(\d\.\d+),\s*(\d\.\d+)\]\s*\(n=(\d+)\)")


class Reader:
    """Reads files under the project and remembers each one for the source hash."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.base = self.root.parent
        self.seen: dict[str, str] = {}

    def rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.base).as_posix()

    def text(self, p: Path) -> str | None:
        try:
            body = p.read_bytes()
        except OSError:
            return None
        self.seen[self.rel(p)] = hashlib.sha256(body).hexdigest()
        return body.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def source_hash(self) -> str:
        lines = "\n".join(f"{k}:{v}" for k, v in sorted(self.seen.items()))
        return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _first_line(body: str | None) -> str | None:
    if body is None:
        return None
    for ln in body.splitlines():
        if ln.strip():
            return ln.strip()
    return None


def _gate_verdict(line: str | None) -> str | None:
    if not line:
        return None
    head = line.lstrip("`* ").upper()
    for v in GATE_VERDICTS:
        if head.startswith(v):
            return v
    return None


def _profile_line(text: str, label: str) -> str | None:
    """`- **Label:** `value`` → value, or None while it is still a `<placeholder>`."""
    m = re.search(rf"^- \*\*{re.escape(label)}:\*\*\s*`([^`]*)`", text, re.M)
    if not m or "<" in m.group(1):
        return None
    return m.group(1).strip()


def _table_rows(body: str | None) -> list[list[str]]:
    rows: list[list[str]] = []
    for ln in (body or "").splitlines():
        t = ln.strip()
        if not t.startswith("|"):
            continue
        cells = [c.replace("`", "").replace("*", "").strip() for c in t.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


# --------------------------------------------------------------------------------------- profile

def read_profile(r: Reader, project_dir: Path) -> dict:
    """EVAL-PROFILE.md lives in .claude/ once installed; the bundle checkout keeps it at its root."""
    for cand in (project_dir / ".claude" / "EVAL-PROFILE.md", project_dir / "EVAL-PROFILE.md"):
        text = r.text(cand)
        if text is None:
            continue
        tier = None
        m = re.search(r"^- \*\*Tier:\*\*\s*`([a-z]+)`", text, re.M)
        if m and m.group(1) in ("low", "medium", "high"):
            tier = m.group(1)
        layers = []
        for row in _table_rows(_section(text, "## Layers")):
            if len(row) >= 2 and row[1].lower() == "yes":
                code = row[0].split()[0]
                if code in LAYERS:
                    layers.append(code)
        return {"path": r.rel(cand), "name": _profile_line(text, "Name"),
                "system_slug": _profile_line(text, "System slug"), "risk_tier": tier,
                "layers_enabled": layers}
    return {"path": None, "name": None, "system_slug": None, "risk_tier": None,
            "layers_enabled": None}


# --------------------------------------------------------------------------------------- readers

def read_system_card(r: Reader, root: Path) -> dict | None:
    p = root / "system-card.md"
    text = r.text(p)
    if text is None:
        return None
    title = _first_line(text) or ""
    m = re.match(r"^#\s*System card\s*[—-]\s*(.+)$", title)
    tier = re.match(r"`?(low|medium|high)\b", _first_line(_section(text, "## Risk tier")) or "")
    return {"path": r.rel(p), "system": m.group(1).strip() if m else None,
            "seed": "This is the seed" in text,
            "risk_tier": tier.group(1) if tier else None}


def read_failure_modes(r: Reader, root: Path) -> list[dict]:
    out = []
    tax = root / "taxonomy"
    for p in sorted(tax.glob("FM-*.md")) if tax.is_dir() else []:
        m = re.match(r"^(FM-\d{3,})-", p.name)
        if not m:
            continue
        text = r.text(p) or ""
        title = _first_line(text) or ""
        status = (_first_line(_section(text, "## Status")) or "").split(" ")[0].lower() or None
        severity = (_first_line(_section(text, "## Severity")) or "").split(" ")[0].lower() or None
        detector = (_first_line(_section(text, "## Detector")) or "").split(" ")[0] or None
        out.append({
            "id": m.group(1),
            "title": re.sub(r"^#\s*FM-\d+\s*[—-]\s*", "", title).strip() or None,
            "severity": severity if severity in ("blocking", "major", "minor") else None,
            "status": status if status in ("open", "mitigated", "retired") else None,
            "detector": detector,
            "frequency": _first_line(_section(text, "## Frequency")),
            "path": r.rel(p),
        })
    return out


def read_datasets(r: Reader, root: Path) -> list[dict]:
    out = []
    ddir = root / "datasets"
    for p in sorted(ddir.glob("DS-*.jsonl")) if ddir.is_dir() else []:
        text = r.text(p) or ""
        rows = []
        for ln in text.splitlines():
            if ln.strip():
                try:
                    rows.append(json.loads(ln))
                except json.JSONDecodeError:
                    rows.append({})
        n = len(rows)
        traced = sum(1 for x in rows if isinstance(x, dict) and x.get("origin") == "trace")
        meta = p.with_name(p.name[:-len(".jsonl")] + ".meta.md")
        out.append({
            "id": p.name[:-len(".jsonl")],
            "path": r.rel(p),
            "meta": r.rel(meta) if meta.exists() else None,
            "retrieval": bool(re.search(r"-retrieval-v\d+$", p.name[:-len(".jsonl")])),
            "cases": n,
            "trace_share": round(traced / n, 3) if n else None,
            "sha256": r.seen[r.rel(p)],
        })
    return out


def read_judges(r: Reader, root: Path) -> list[dict]:
    out = []
    jdir = root / "judges"
    for p in sorted(jdir.glob("JDG-*.md")) if jdir.is_dir() else []:
        m = re.match(r"^JDG-(.+)-v(\d+)\.md$", p.name)
        if not m:
            continue
        r.text(p)
        vpath = jdir / m.group(1) / "validation.md"
        vtext = r.text(vpath)
        verdict = tpr = tnr = kappa = None
        if vtext is not None:
            line = (_first_line(_section(vtext, "## Verdict")) or "").upper()
            verdict = "UNVALIDATED" if "UNVALIDATED" in line else (
                "VALIDATED" if line.startswith("VALIDATED") else None)
            rates = _section(vtext, "## Rates") or ""
            for key in ("TPR", "TNR", "kappa"):
                mm = re.search(rf"{key}\s*[:=]?\s*(\d?\.\d+)", rates, re.I)
                val = float(mm.group(1)) if mm else None
                if key == "TPR":
                    tpr = val
                elif key == "TNR":
                    tnr = val
                else:
                    kappa = val
        out.append({"id": p.name[:-3], "path": r.rel(p),
                    "validation": r.rel(vpath) if vtext is not None else None,
                    "verdict": verdict, "tpr": tpr, "tnr": tnr, "kappa": kappa})
    return out


def read_run(r: Reader, run_dir: Path) -> dict:
    summary = run_dir / "summary.md"
    text = r.text(summary)
    verdict = deciding = None
    rates: dict[str, dict | None] = {"pass_1": None, "pass_k": None, "flaky": None}
    if text is not None:
        line = _first_line(_section(text, "## Verdict"))
        verdict = _gate_verdict(line)
        mm = re.search(r"decided by `([^`]+)`", line or "")
        deciding = mm.group(1) if mm else None
        for row in _table_rows(_section(text, "## Results")):
            if not row:
                continue
            key = ("pass_1" if row[0].startswith("pass^1") else
                   "pass_k" if row[0].startswith("pass^") else
                   "flaky" if row[0].startswith("flaky") else None)
            rm = RATE.search(row[1]) if key and len(row) > 1 else None
            if key and rm:
                rates[key] = {"p": float(rm.group(1)), "lo": float(rm.group(2)),
                              "hi": float(rm.group(3)), "n": int(rm.group(4))}
    failed = errors = 0
    results = run_dir / "results.jsonl"
    rtext = r.text(results)
    failing: list[str] = []
    for ln in (rtext or "").splitlines():
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if row.get("outcome") == "FAIL":
            failed += 1
            if row.get("case_id") and row["case_id"] not in failing:
                failing.append(row["case_id"])
        elif row.get("outcome") == "ERROR":
            errors += 1
    ctrf = run_dir / "ctrf.json"
    return {
        "run_id": run_dir.name,
        "path": r.rel(run_dir),
        "summary": r.rel(summary) if text is not None else None,
        "ctrf": r.rel(ctrf) if ctrf.exists() else None,
        "verdict": verdict,
        "decided_by": deciding,
        **rates,
        "failed_attempts": failed if rtext is not None else None,
        "errors": errors if rtext is not None else None,
        "failing_cases": failing[:20],
    }


def _run_dirs(suite_runs: Path) -> list[Path]:
    """Run folders of one suite, oldest first, ordered by run id.

    The runner writes `runs/<suite>/<run-id>/`; EVAL-CONTRACTS 2 also allows
    `runs/<suite>/<slug>/<run-id>/`. Both are read, one level deep, never further.
    """
    if not suite_runs.is_dir():
        return []
    found: list[Path] = []
    for d in suite_runs.iterdir():
        if not d.is_dir():
            continue
        if RUN_ID.match(d.name):
            found.append(d)
        else:
            found += [x for x in d.iterdir() if x.is_dir() and RUN_ID.match(x.name)]
    return sorted(found, key=lambda p: (p.name, p.as_posix()))


def _baseline_p(r: Reader, root: Path, base_id: str | None) -> float | None:
    if not base_id or not re.match(r"^BASE-[A-Za-z0-9-]+$", base_id):
        return None
    text = r.text(root / "baselines" / f"{base_id}.json")
    try:
        doc = json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        return None
    return baseline_score(doc) if isinstance(doc, dict) else None

def _margin(gates) -> float:
    try:
        return float((gates or {}).get("regression_margin", 0) or 0) if isinstance(gates, dict) else 0.0
    except (TypeError, ValueError):
        return 0.0

def read_suites(r: Reader, root: Path, judges: dict[str, dict]) -> list[dict]:
    out = []
    sdir = root / "suites"
    for p in sorted(sdir.glob("*.yaml")) if sdir.is_dir() else []:
        text = r.text(p) or ""
        suite = _parse_suite(text)
        name = str(suite.get("suite") or p.stem)
        evaluators = [str(e) for e in (suite.get("evaluators") or [])]
        jids = [e.split(":", 1)[1] for e in evaluators if e.startswith("judge:")]
        run_dirs = _run_dirs(root / "runs" / name)
        latest = read_run(r, run_dirs[-1]) if run_dirs else None
        previous = read_run(r, run_dirs[-2]) if len(run_dirs) > 1 else None
        gates = suite.get("gates") or {}
        base_id = str(suite.get("baseline")) if suite.get("baseline") else None
        out.append({
            "suite": name,
            "path": r.rel(p),
            "layer": str(suite.get("layer")) if suite.get("layer") else None,
            "dataset": str(suite.get("dataset")) if suite.get("dataset") else None,
            "model": str(suite.get("model")) if suite.get("model") else None,
            "repeats": suite.get("repeats"),
            "gated": bool(gates),
            "gates": {str(k): v for k, v in gates.items()} if isinstance(gates, dict) else {},
            "baseline": base_id,
            # The baseline's headline rate and the allowed drop, so a reader compares without
            # opening the JSON. The runner's score event uses the same two numbers.
            "baseline_p": _baseline_p(r, root, base_id),
            "regression_margin": _margin(gates),
            "evaluators": evaluators,
            # A gated suite deciding with a judge that is not VALIDATED can only be NOT-EVALUABLE.
            "unvalidated_judges": [j for j in jids if (judges.get(j) or {}).get("verdict") != "VALIDATED"],
            "runs": len(run_dirs),
            "latest_run": latest,
            "previous_run": {"run_id": previous["run_id"], "verdict": previous["verdict"],
                             "pass_k": previous["pass_k"]} if previous else None,
        })
    return out


def read_redteam(r: Reader, root: Path) -> list[dict]:
    out = []
    rdir = root / "redteam"
    for p in sorted(rdir.glob("RT-*.md")) if rdir.is_dir() else []:
        m = re.match(r"^(RT-(?:LLM|ASI)\d{2}-\d{3,})", p.name)
        if not m:
            continue
        text = r.text(p) or ""
        sev = (_first_line(_section(text, "## Severity")) or "").split(" ")[0].lower() or None
        out.append({"id": m.group(1), "code": _first_line(_section(text, "## Code")),
                    "severity": sev if sev in ("critical", "high", "medium", "low") else None,
                    "authorized": _section(text, "## Authorization") is not None,
                    "path": r.rel(p)})
    return out


def read_reports(r: Reader, root: Path) -> tuple[list[dict], dict | None]:
    scorecards: list[dict] = []
    audit = None
    rep = root / "reports"
    if not rep.is_dir():
        return scorecards, audit
    for sub in sorted(d for d in rep.iterdir() if d.is_dir()):
        dated = sorted(f for f in sub.iterdir() if f.is_file() and DATED.match(f.name))
        if sub.name == "audits":
            if dated:
                f = dated[-1]
                text = r.text(f) or ""
                blocking = len(re.findall(r"\bblocking\b", text, re.I))
                audit = {"date": DATED.match(f.name).group(1), "path": r.rel(f),
                         "mentions_blocking": blocking}
            continue
        cards = [f for f in dated if DATED.match(f.name).group(2) == "scorecard"]
        if not cards:
            continue
        f = cards[-1]
        text = r.text(f) or ""
        scorecards.append({"slug": sub.name, "date": DATED.match(f.name).group(1),
                           "path": r.rel(f),
                           "verdict": _gate_verdict(_first_line(_section(text, "## Verdict")))})
    return scorecards, audit


# --------------------------------------------------------------------------------------- derive

def phase_of(card, fms, datasets, judges, suites, scorecards) -> str:
    """The furthest rung whose artifact exists. Never inferred from intent, only from files."""
    phase = "Scope"
    if fms:
        phase = "Explore"
    if datasets:
        phase = "Data"
    if any(s["evaluators"] for s in suites):
        phase = "Evaluate"
    judged = [s for s in suites if any(e.startswith("judge:") for e in s["evaluators"])]
    # A suite deciding only with code assertions needs no validation step: it is already trusted.
    if suites and all(not s["unvalidated_judges"] for s in (judged or suites)):
        phase = "Validate" if phase == "Evaluate" else phase
    if any(s["runs"] for s in suites):
        phase = "Run"
    if scorecards:
        phase = "Report"
    return phase


def next_command(card, fms, datasets, judges, suites, scorecards) -> str:
    if card is None:
        return "/eval-scope"
    if card.get("seed"):
        return "/eval-scope --refresh"
    if not fms:
        return "/eval-explore --from-profile"
    if not datasets:
        return "/eval-data"
    if any(not j["verdict"] or j["verdict"] == "UNVALIDATED" for j in judges):
        bad = next(j for j in judges if j["verdict"] != "VALIDATED")
        return f"/eval-validate {bad['id']}"
    if not any(s["runs"] for s in suites):
        return f"/eval-run {suites[0]['suite']}" if suites else "/eval-judge"
    if not scorecards:
        return "/eval-report"
    return "/eval-status"


def build_state(root: Path, now: datetime | None = None) -> dict:
    root = Path(root)
    r = Reader(root)
    project_dir = root.resolve().parent
    profile = read_profile(r, project_dir)
    card = read_system_card(r, root)
    fms = read_failure_modes(r, root)
    datasets = read_datasets(r, root)
    judges = read_judges(r, root)
    suites = read_suites(r, root, {j["id"]: j for j in judges})
    redteam = read_redteam(r, root)
    scorecards, audit = read_reports(r, root)
    baselines = sorted(p.stem for p in (root / "baselines").glob("BASE-*.json")) \
        if (root / "baselines").is_dir() else []

    stamp = os.environ.get("EVAL_STATE_NOW")
    when = stamp or (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    open_fms = [f for f in fms if f["status"] == "open"]
    latest = [s["latest_run"] for s in suites if s["latest_run"]]
    return {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "generated_at": when,
        "source_hash": r.source_hash(),
        "root": r.rel(root),
        "project": profile["name"] or (card or {}).get("system") or project_dir.name,
        "system_slug": profile["system_slug"],
        "risk_tier": profile["risk_tier"] or (card or {}).get("risk_tier"),
        "layers_enabled": profile["layers_enabled"],
        "profile": profile["path"],
        "phase": phase_of(card, fms, datasets, judges, suites, scorecards),
        "next_command": next_command(card, fms, datasets, judges, suites, scorecards),
        "system_card": card,
        "totals": {
            "failure_modes_open": len(open_fms),
            "failure_modes_blocking_open": sum(1 for f in open_fms if f["severity"] == "blocking"),
            "datasets": len(datasets),
            "judges": len(judges),
            "judges_validated": sum(1 for j in judges if j["verdict"] == "VALIDATED"),
            "suites": len(suites),
            "suites_gated": sum(1 for s in suites if s["gated"]),
            "runs": sum(s["runs"] for s in suites),
            "latest_pass": sum(1 for x in latest if x["verdict"] == "PASS"),
            "latest_fail": sum(1 for x in latest if x["verdict"] == "FAIL"),
            "latest_not_evaluable": sum(1 for x in latest if x["verdict"] == "NOT-EVALUABLE"),
            "redteam_probes": len(redteam),
        },
        "failure_modes": fms,
        "datasets": datasets,
        "judges": judges,
        "suites": suites,
        "redteam": redteam,
        "baselines": baselines,
        "scorecards": scorecards,
        "audit": audit,
    }


def _comparable(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "generated_at"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive .evals/state.json from the eval artifacts")
    ap.add_argument("--root", default=None, help=root_arg_help())
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when state.json differs from what the artifacts derive to")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing state.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = resolve_root(args.root)
    if not root.is_dir():
        # The Stop hook runs this in every project; one without an eval root is not an error.
        if not args.quiet:
            print(f"no eval root at {root}", file=sys.stderr)
        return 0 if args.quiet else 2

    doc = build_state(root)
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    target = root / "state.json"
    if args.stdout:
        sys.stdout.write(body)
        return 0
    if args.check:
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(f"{target}: missing or not JSON — run build_state.py", file=sys.stderr)
            return 1
        if _comparable(current) != _comparable(doc):
            print(f"{target} is stale: the artifacts derive to a different index", file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"{target} matches the artifacts")
        return 0
    target.write_text(body, encoding="utf-8", newline="\n")
    if not args.quiet:
        t = doc["totals"]
        print(f"{target} — {doc['project']} [{doc['phase']}] · {t['suites']} suite(s), "
              f"{t['runs']} run(s), {t['failure_modes_open']} open FM(s), "
              f"{t['judges_validated']}/{t['judges']} judge(s) VALIDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
