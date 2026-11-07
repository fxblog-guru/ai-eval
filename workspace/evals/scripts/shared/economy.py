"""Spend as few tokens as the question allows, and say up front what a run will cost.

Three levers, each reported in summary.md as tokens saved (EVAL-CONTRACTS 8.5):

- **Sample to power.** A suite that declares `ci_half_width` runs only as many cases as that
  interval needs (stats.n_for, at p = 0.5 unless `expected_pass` is set), keeping one case per
  failure mode first so no FM goes unmeasured, and never fewer than 30 on a gated suite.
- **Cache.** A (system version, case id, prompt hash, input, model, repeat) whose outcome is known
  is not run or judged again. A new system or prompt version changes the key, so nothing stale
  is reused.
- **Cheap first.** A code assertion that fails decides the attempt; the judge is not called.

The estimate is cases x repeats x (1 + judges) x tokens per call, taken from the suite or from the
last run's measured cost.json. Unknown stays unknown: it is printed as such, never guessed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import stats

MIN_GATED_CASES = 30


@dataclass
class Plan:
    cases: list[dict]
    skipped: int
    needed: int | None
    note: str


def sample_to_power(cases: list[dict], suite: dict, gated: bool) -> Plan:
    """The smallest stable subset of `cases` whose interval half-width meets `ci_half_width`."""
    margin = suite.get("ci_half_width")
    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or margin <= 0:
        return Plan(cases, 0, None, "all cases (no ci_half_width declared)")
    p = suite.get("expected_pass")
    # 0.5 maximises p(1-p): the sample is big enough whatever the true rate turns out to be.
    p = p if isinstance(p, (int, float)) and 0 < p < 1 else 0.5
    needed = stats.n_for(p, float(margin))
    if gated:
        needed = max(needed, MIN_GATED_CASES)
    if needed >= len(cases):
        return Plan(cases, 0, needed, f"all {len(cases)} cases (power needs {needed})")
    # Hash order, not file order: stable across runs, and not biased to whoever wrote the top rows.
    order = sorted(cases, key=lambda c: hashlib.sha256(str(c.get("case_id")).encode()).hexdigest())
    picked, seen_fm = [], set()
    for c in order:
        fms = set(c.get("fm") or [])
        if fms - seen_fm:
            picked.append(c)
            seen_fm |= fms
    for c in order:
        if len(picked) >= needed:
            break
        if c not in picked:
            picked.append(c)
    ids = {id(c) for c in picked}
    kept = [c for c in cases if id(c) in ids]
    return Plan(kept, len(cases) - len(kept), needed,
                f"{len(kept)} of {len(cases)} cases: ±{margin} at p={p} needs {needed}; "
                f"{len(cases) - len(kept)} skipped, every failure mode kept")


def tokens_per_call(root: Path, suite_name: str, suite: dict) -> tuple[float | None, float | None, str]:
    """(system call, judge call) token averages: the suite's declared ones, else the last run's."""
    sys_t, judge_t = suite.get("tokens_per_call"), suite.get("tokens_per_judge_call")
    if isinstance(sys_t, (int, float)) and not isinstance(sys_t, bool):
        jt = judge_t if isinstance(judge_t, (int, float)) and not isinstance(judge_t, bool) else sys_t
        return float(sys_t), float(jt), "the suite"
    runs = root / "runs" / suite_name
    for cost in sorted(runs.glob("*/cost.json"), reverse=True) if runs.is_dir() else []:
        try:
            doc = json.loads(cost.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        s, j = doc.get("tokens_per_call"), doc.get("tokens_per_judge_call")
        if isinstance(s, (int, float)):
            return float(s), float(j) if isinstance(j, (int, float)) else float(s), f"run {cost.parent.name}"
    return None, None, "unknown: no tokens_per_call in the suite and no earlier run measured it"


def estimate(n_cases: int, repeats: int, n_judges: int, per_call: float | None,
             per_judge: float | None) -> float | None:
    if per_call is None:
        return None
    return n_cases * repeats * (per_call + n_judges * (per_judge if per_judge is not None else per_call))


def over_budget(est: float | None, ceiling: float | None) -> bool:
    return est is not None and ceiling is not None and est > ceiling


# --------------------------------------------------------------------------------------- cache

def _h(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


def prompt_hash(root: Path, suite: dict) -> str:
    ref = suite.get("prompt_path")
    for base in (root, root.parent):
        if ref and (base / str(ref)).is_file():
            return hashlib.sha256((base / str(ref)).read_bytes()).hexdigest()
    return _h(suite.get("prompt_version"))


class Cache:
    """`<root>/cache/<suite>/<key>.json`. A miss is cheap; a wrong hit is not, so every input that
    could change the answer is in the key."""

    def __init__(self, root: Path, suite_name: str, suite: dict, enabled: bool):
        self.dir = root / "cache" / suite_name
        self.enabled = enabled
        self.base = {"system": suite.get("system_version") or suite.get("prompt_version"),
                     "prompt": prompt_hash(root, suite), "model": suite.get("model"),
                     "temperature": suite.get("temperature"),
                     "evaluators": suite.get("evaluators")}
        self.hits = 0
        self.saved_tokens = 0.0

    def key(self, case: dict, repeat: int) -> str:
        return _h({**self.base, "case": case.get("case_id"), "input": case.get("input"), "repeat": repeat})

    def get(self, case: dict, repeat: int) -> dict | None:
        if not self.enabled:
            return None
        p = self.dir / f"{self.key(case, repeat)}.json"
        try:
            hit = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        self.hits += 1
        self.saved_tokens += float(hit.get("tokens") or 0)
        return hit

    def put(self, case: dict, repeat: int, entry: dict) -> None:
        if not self.enabled or entry.get("outcome") == "ERROR":
            return  # an error is not an answer; caching it would stop the case being retried
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{self.key(case, repeat)}.json").write_text(json.dumps(entry), encoding="utf-8")


def call_tokens(meta) -> float:
    meta = meta if isinstance(meta, dict) else {}
    return float(sum(v for k in ("tokens_in", "tokens_out")
                     if isinstance(v := meta.get(k), (int, float)) and not isinstance(v, bool)))


def fmt(x: float | None) -> str:
    return "unknown" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.0f}"
