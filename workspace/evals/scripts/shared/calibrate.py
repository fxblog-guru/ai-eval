#!/usr/bin/env python3
"""Compute a judge's calibration from its held-out test split (EVAL-CONTRACTS 5.3).

    python3 .evals/scripts/shared/calibrate.py JDG-<slug>-vN [--root .evals] [--json]

Reads the human labels in `judges/<slug>/labels/test.jsonl` and the judge's own verdicts on the
same cases in `judges/<slug>/predictions/test.jsonl` (`{"case_id", "judge": "pass"|"fail"}`), and
prints the confusion matrix, TPR / TNR / FPR / FNR / kappa, every disagreement, and the verdict
against EVAL-PROFILE §Judge thresholds. `/eval-validate` pastes this output into validation.md;
lint (E023) recomputes it and refuses a validation.md whose numbers or verdict differ.

Exit codes: 0 = computed, 1 = cannot be computed (the reason is printed), 2 = bad judge id.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from root import resolve_root, root_arg_help  # noqa: E402
import stats  # noqa: E402

JDG = re.compile(r"^JDG-(.+)-v\d+$")
# A validation.md rounds to 3 decimals (EVAL-CONTRACTS 5.3); anything further off was not computed
# from these files.
TOLERANCE = 0.0015
DEFAULTS = {"tpr": 0.80, "tnr": 0.80, "kappa": 0.60, "separation": 0.50, "per_class": 30}


@dataclass
class Calibration:
    confusion: stats.Confusion | None = None
    verdict: str | None = None
    reasons: list[str] = field(default_factory=list)
    disagreements: list[tuple[str, str, str]] = field(default_factory=list)  # (case, human, judge)
    problem: str | None = None    # why it could not be computed


def _rows(path: Path) -> list[dict] | None:
    if not path.is_file():
        return None
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return None
            if isinstance(row, dict):
                out.append(row)
    return out


def thresholds(root: Path) -> dict:
    """EVAL-PROFILE §Judge thresholds, falling back to the documented defaults per row."""
    t = dict(DEFAULTS)
    project = Path(root).resolve().parent
    for cand in (project / ".claude" / "EVAL-PROFILE.md", project / "EVAL-PROFILE.md"):
        if not cand.is_file():
            continue
        text = cand.read_text(encoding="utf-8")
        body = text.split("## Judge thresholds", 1)[-1].split("\n## ", 1)[0] if "## Judge thresholds" in text else ""
        for line in body.splitlines():
            m = re.match(r"^\|\s*([^|]+?)\s*\|\s*`?(\d+(?:\.\d+)?)`?", line)
            if not m:
                continue
            name, value = m.group(1).lower(), float(m.group(2))
            # `TPR - FPR` names both rates, so it is tested before plain TPR.
            key = ("separation" if "fpr" in name else "tpr" if "tpr" in name else
                   "tnr" if "tnr" in name else "kappa" if "kappa" in name else
                   "per_class" if "labels" in name else None)
            if key:
                t[key] = int(value) if key == "per_class" else value
        break
    return t


def compute(root: Path, judge_id: str) -> Calibration:
    m = JDG.match(judge_id)
    if not m:
        return Calibration(problem=f"{judge_id!r} is not a judge id")
    jdir = Path(root) / "judges" / m.group(1)
    labels = _rows(jdir / "labels" / "test.jsonl")
    preds = _rows(jdir / "predictions" / "test.jsonl")
    if labels is None:
        return Calibration(problem="labels/test.jsonl is missing or not valid JSON lines")
    if preds is None:
        return Calibration(problem="predictions/test.jsonl is missing or not valid JSON lines: "
                                   "the judge's own verdicts on the test split were not kept")
    judged = {str(r.get("case_id")): r.get("judge") for r in preds}
    pairs, missing = [], []
    cal = Calibration()
    for row in labels:
        human, cid = row.get("label"), str(row.get("case_id"))
        if human not in ("pass", "fail"):
            continue
        verdict = judged.get(cid)
        if verdict not in ("pass", "fail"):
            missing.append(cid)
            continue
        pairs.append((human, verdict))
        if human != verdict:
            cal.disagreements.append((cid, human, verdict))
    if missing:
        return Calibration(problem=f"{len(missing)} labelled test case(s) have no judge verdict "
                                   f"(e.g. {missing[0]}): rates over a subset are not the test split")
    if not pairs:
        return Calibration(problem="the test split has no pass/fail labels")
    t = thresholds(root)
    cal.confusion = stats.confusion_from_pairs(pairs)
    cal.verdict, cal.reasons = stats.judge_verdict(
        cal.confusion, min_tpr=t["tpr"], min_tnr=t["tnr"], min_kappa=t["kappa"],
        min_separation=t["separation"], min_pass=t["per_class"], min_fail=t["per_class"])
    return cal


def stated(vtext: str) -> dict:
    """The TPR / TNR / kappa and verdict a validation.md claims; absent values are None."""
    def section(h: str) -> str:
        return vtext.split(h, 1)[1].split("\n## ", 1)[0] if h in vtext else ""
    rates = section("## Rates")
    out: dict = {}
    for key in ("TPR", "TNR", "kappa"):
        mm = re.search(rf"\b{key}\b\s*[:=]?\s*(\d?\.\d+|[01])\b", rates, re.I)
        out[key.lower()] = float(mm.group(1)) if mm else None
    v = section("## Verdict").strip()
    out["verdict"] = "VALIDATED" if re.match(r"^VALIDATED\b", v) else (
        "UNVALIDATED" if "UNVALIDATED" in v else None)
    return out


def mismatches(cal: Calibration, claim: dict) -> list[str]:
    """Where a validation.md disagrees with the computed calibration, beyond rounding."""
    c = cal.confusion
    if c is None:
        return []
    out = []
    for key, value in (("tpr", c.tpr), ("tnr", c.tnr), ("kappa", c.kappa)):
        said = claim.get(key)
        if said is None and key != "kappa":
            out.append(f"{key.upper()} is not stated (computed {value:.3f})")
        elif said is not None and abs(said - value) > TOLERANCE:
            out.append(f"{key.upper() if key != 'kappa' else 'kappa'} stated {said:.3f}, computed {value:.3f}")
    if claim.get("verdict") and claim["verdict"] != cal.verdict:
        why = f" ({'; '.join(cal.reasons)})" if cal.reasons else ""
        out.append(f"verdict stated {claim['verdict']}, computed {cal.verdict}{why}")
    return out


def markdown(judge_id: str, cal: Calibration) -> str:
    c = cal.confusion
    lines = [
        "## Confusion",
        "| | Human: fail | Human: pass |", "|---|---|---|",
        f"| Judge: fail | {c.tp} | {c.fp} |", f"| Judge: pass | {c.fn} | {c.tn} |", "",
        "## Rates",
        f"TPR {c.tpr:.3f} · TNR {c.tnr:.3f} · FPR {c.fpr:.3f} · FNR {c.fnr:.3f} · kappa {c.kappa:.3f}",
        "", "## Disagreements",
    ]
    lines += [f"- {cid}: human {h}, judge {j} — <why>" for cid, h, j in cal.disagreements] or ["none"]
    lines += ["", "## Verdict", cal.verdict + (f" — {'; '.join(cal.reasons)}" if cal.reasons else "")]
    return f"<!-- computed by calibrate.py for {judge_id} -->\n" + "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute a judge's TPR/TNR/kappa and verdict")
    ap.add_argument("judge", help="JDG-<slug>-vN")
    ap.add_argument("--root", default=None, help=root_arg_help())
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not JDG.match(args.judge):
        print(f"not a judge id: {args.judge}", file=sys.stderr)
        return 2
    cal = compute(resolve_root(args.root), args.judge)
    if cal.problem:
        print(f"cannot compute {args.judge}: {cal.problem}", file=sys.stderr)
        return 1
    c = cal.confusion
    if args.json:
        print(json.dumps({"judge": args.judge, "tp": c.tp, "fp": c.fp, "tn": c.tn, "fn": c.fn,
                          "tpr": round(c.tpr, 3), "tnr": round(c.tnr, 3), "kappa": round(c.kappa, 3),
                          "verdict": cal.verdict, "reasons": cal.reasons,
                          "disagreements": [list(d) for d in cal.disagreements]}, indent=2))
    else:
        print(markdown(args.judge, cal), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
