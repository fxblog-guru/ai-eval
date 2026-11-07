#!/usr/bin/env python3
"""Run an eval suite: preflight, k repeats per case, evidence, CTRF.

    python3 scripts/shared/runner.py --suite task-example --env staging [--dry-run]

The preflight checks are the point of this file. Each one is cheaper to fail now than to
discover in a scorecard three weeks later. See EVAL-CONTRACTS.md section 8.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import importlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from root import resolve_root, root_arg_help  # noqa: E402
import activity  # noqa: E402
import ctrf  # noqa: E402
import economy  # noqa: E402
import learnings  # noqa: E402
import redact  # noqa: E402
import stats  # noqa: E402
import verdict as verdict_hub  # noqa: E402
from lint_evals import _parse_suite, _section  # noqa: E402


@dataclass
class Preflight:
    """Every check that must pass before the first model call."""

    stops: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unvalidated_judges: list[str] = field(default_factory=list)
    needs_human: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stops

    @property
    def gate_is_evaluable(self) -> bool:
        return not self.unvalidated_judges


def _project_link(path, root):
    """`path` relative to the project the board opens it from: the working directory when the eval
    root lies inside it (`--root a/evals` run from the project), else the eval root's parent."""
    full = Path(path).resolve()
    for base in (Path.cwd().resolve(), Path(root).resolve().parent):
        try:
            return full.relative_to(base).as_posix()
        except ValueError:
            continue
    return full.name


def preflight(root: Path, suite: dict, env: str, gated: bool) -> Preflight:
    pf = Preflight()

    model = str(suite.get("model") or "")
    if not model or model.endswith("latest") or "<" in model:
        pf.stops.append(
            "model id is unpinned. A run whose model cannot be identified is unattributable "
            "and comparable to nothing (EVAL-CONTRACTS 8.2)."
        )
    if "temperature" not in suite:
        pf.warnings.append("temperature is not pinned in the suite")

    ds_id = suite.get("dataset")
    ds_path = root / "datasets" / f"{ds_id}.jsonl"
    if not ds_path.exists():
        pf.stops.append(f"dataset {ds_id} does not exist at {ds_path}")
        return pf

    cases = load_dataset(ds_path)
    n = len(cases)
    if gated and n < 30:
        pf.stops.append(
            f"gated suite runs on {n} cases. Below 30, a gate cannot distinguish a real "
            f"regression from sampling noise (EVAL-CONTRACTS 8.3)."
        )
    elif gated and n < 100:
        pf.warnings.append(f"gated suite runs on {n} cases; 100 is the minimum for a stable gate")

    declared_hash = suite.get("dataset_sha256")
    actual_hash = sha256(ds_path)
    if declared_hash and declared_hash != actual_hash:
        pf.stops.append(
            f"dataset hash mismatch: the suite declares {declared_hash[:12]}, the file is "
            f"{actual_hash[:12]}. A frozen dataset was edited; every run referencing it is now "
            f"incomparable (EVAL-CONTRACTS 7.1)."
        )

    judged = False
    for ev in suite.get("evaluators") or []:
        if not str(ev).startswith("judge:"):
            continue
        judged = True
        jid = str(ev).split(":", 1)[1]
        if judge_verdict(root, jid) != "VALIDATED":
            pf.unvalidated_judges.append(jid)

    # A gate is a promise to someone about something. Who and what are facts only a human holds;
    # the runner asks for them and never fills them in (EVAL-CONTRACTS 8.3).
    if gated:
        if _unset(suite.get("system_version")):
            pf.needs_human.append("system_version: which build of the system this gate is about")
        if judged and _unset(suite.get("labels_owner")):
            pf.needs_human.append("labels_owner: the annotator (ANN-xx) who owns the judge's labels")

    missing_fixtures = [c["case_id"] for c in cases
                        if c.get("fixture") and not (root / c["fixture"]).exists()]
    if missing_fixtures:
        pf.stops.append(
            f"{len(missing_fixtures)} case(s) declare a fixture that does not exist "
            f"(e.g. {missing_fixtures[0]}). Without it the case silently tests a state it did "
            f"not intend."
        )
    return pf


def _unset(v) -> bool:
    return v is None or str(v).strip() == "" or "<" in str(v)

def judge_verdict(root: Path, judge_id: str) -> str | None:
    """Read `## Verdict` from a judge's validation.md. Missing file means no validation."""
    m = re.match(r"^JDG-(.+)-v\d+$", judge_id)
    if not m:
        return None
    vpath = root / "judges" / m.group(1) / "validation.md"
    if not vpath.exists():
        return None
    body = (_section(vpath.read_text(encoding="utf-8"), "## Verdict") or "").strip()
    if body.startswith("VALIDATED"):
        return "VALIDATED"
    if "UNVALIDATED" in body:
        return "UNVALIDATED"
    return None


def load_dataset(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_adapter(dotted: str):
    """`providers.example:call` -> the callable. It takes a case input and returns
    {output, steps, meta}."""
    module_name, _, fn_name = dotted.partition(":")
    return getattr(importlib.import_module(module_name), fn_name)


# ---------------------------------------------------------------------------- gates

# Which measured rate a gate key names. A `*_ci_lower` key is compared on the Wilson lower bound
# (EVAL-CONTRACTS 8.3); `flaky_rate_max` on the upper bound, since it is a ceiling.
GATE_METRICS = {
    "task_success_ci_lower": "pass_k",
    "pass_k_ci_lower": "pass_k",
    "agent_pass_k_ci_lower": "pass_k",
    "pass_1_ci_lower": "pass_1",
    "pass_at_1_ci_lower": "pass_1",
    "contract_pass_rate_ci_lower": "pass_1",
    "flaky_rate_max": "flaky",
}


@dataclass
class GateResult:
    key: str
    threshold: object
    verdict: str          # PASS | FAIL | NOT-EVALUABLE
    detail: str


def _ceiling(rate: stats.Rate, threshold: float) -> str:
    """The mirror of Rate.gate for a maximum: PASS when the whole interval sits at or under it."""
    if rate.n == 0:
        return "NOT-EVALUABLE"
    if rate.hi <= threshold:
        return "PASS"
    if rate.lo > threshold:
        return "FAIL"
    return "NOT-EVALUABLE"


def evaluate_gates(gates: dict, rates: dict, *, baseline: dict | None,
                   pass_k_p: float | None, fms: dict[str, float]) -> list[GateResult]:
    """Every declared gate, each on the metric it names. A gate this runner cannot measure is
    NOT-EVALUABLE with the reason, never skipped: a skipped gate reads as a passed one."""
    out: list[GateResult] = []
    for key, raw in gates.items():
        key = str(key)
        try:
            threshold = float(raw)
        except (TypeError, ValueError):
            out.append(GateResult(key, raw, "NOT-EVALUABLE", f"threshold {raw!r} is not a number"))
            continue
        if key == "regression_margin":
            base_p = activity.baseline_score(baseline) if baseline else None
            if base_p is None or pass_k_p is None:
                out.append(GateResult(key, threshold, "NOT-EVALUABLE",
                                      "no readable baseline to regress against"))
                continue
            drops = {"total": base_p - pass_k_p}
            per_fm = baseline.get("per_fm") if isinstance(baseline.get("per_fm"), dict) else {}
            for fm, info in per_fm.items():
                b = info.get("p") if isinstance(info, dict) else None
                if isinstance(b, (int, float)) and fm in fms:
                    drops[fm] = float(b) - fms[fm]
            worst = max(drops, key=drops.get)
            failed = drops[worst] > threshold + 1e-9
            out.append(GateResult(key, threshold, "FAIL" if failed else "PASS",
                                  f"largest drop {drops[worst]:+.3f} ({worst}) vs margin {threshold}"))
            continue
        metric = GATE_METRICS.get(key)
        if metric is None:
            out.append(GateResult(key, threshold, "NOT-EVALUABLE",
                                  "this runner does not measure that metric"))
            continue
        rate = rates[metric]
        ceiling = key.endswith("_max")
        verdict = _ceiling(rate, threshold) if ceiling else rate.gate(threshold)
        bound = "upper" if ceiling else "lower"
        out.append(GateResult(key, threshold, verdict, f"{metric} {rate} ({bound} bound decides)"))
    return out


def decide(gate_results: list[GateResult], *, gated: bool, unvalidated: list[str],
           not_run: int, budget_stop: str | None,
           needs_human: list[str] | None = None) -> tuple[str, str]:
    """(verdict, deciding reason). PASS needs every gate to pass and every case to be measured.

    An ungated suite is NOT-EVALUABLE, never PASS: nothing was asked of it, so nothing passed.
    """
    if budget_stop:
        return "NOT-EVALUABLE", f"budget exceeded: {budget_stop}"
    if not gated:
        return "NOT-EVALUABLE", "no gate declared"
    if needs_human:
        return "NOT-EVALUABLE", "needs human: " + "; ".join(needs_human)
    if unvalidated:
        return "NOT-EVALUABLE", "judge not validated"
    failed = [g for g in gate_results if g.verdict == "FAIL"]
    if failed:
        return "FAIL", failed[0].key
    if not_run:
        return "NOT-EVALUABLE", f"{not_run} case(s) not run: every repeat was ERROR"
    unsettled = [g for g in gate_results if g.verdict != "PASS"]
    if unsettled:
        return "NOT-EVALUABLE", unsettled[0].key
    return "PASS", ", ".join(g.key for g in gate_results)


# ---------------------------------------------------------------------------- budget

def _profile_text(root: Path) -> str | None:
    """EVAL-PROFILE.md lives in .claude/ once installed; the bundle checkout keeps it at its root."""
    project = Path(root).resolve().parent
    for cand in (project / ".claude" / "EVAL-PROFILE.md", project / "EVAL-PROFILE.md"):
        if cand.exists():
            return cand.read_text(encoding="utf-8")
    return None


def _number(text: str | None) -> float | None:
    """`200,000` or `$25.50` or `25 USD` -> the number; a `<placeholder>` or blank -> None."""
    if not text or "<" in text:
        return None
    m = re.search(r"\d[\d,_]*(?:\.\d+)?", text)
    return float(m.group(0).replace(",", "").replace("_", "")) if m else None


@dataclass
class Budget:
    max_tokens: float | None = None
    max_cost: float | None = None
    tokens: float = 0.0
    cost: float = 0.0
    calls: int = 0
    calls_with_tokens: int = 0
    calls_with_cost: int = 0
    source: str = ""

    @classmethod
    def load(cls, root: Path, env=None) -> "Budget":
        """The per-run ceilings: `EVAL_TOKEN_BUDGET` / `EVAL_COST_CEILING` when set (they vary by
        environment), else the per-run lines of EVAL-PROFILE §Budget."""
        env = os.environ if env is None else env
        text = _profile_text(root) or ""

        def line(label: str) -> str | None:
            m = re.search(rf"^- \*\*{re.escape(label)}:\*\*\s*`([^`]*)`", text, re.M)
            return m.group(1) if m else None

        b = cls()
        env_t, env_c = _number(env.get("EVAL_TOKEN_BUDGET")), _number(env.get("EVAL_COST_CEILING"))
        b.max_tokens = env_t if env_t is not None else _number(line("Per-run token budget"))
        b.max_cost = env_c if env_c is not None else _number(line("Per-run cost ceiling"))
        b.source = "environment" if (env_t is not None or env_c is not None) else "EVAL-PROFILE §Budget"
        return b

    def add(self, meta) -> str | None:
        """Count one call's reported usage. Returns why the run must stop, or None."""
        self.calls += 1
        meta = meta if isinstance(meta, dict) else {}
        toks = [meta.get(k) for k in ("tokens_in", "tokens_out")]
        toks = [t for t in toks if isinstance(t, (int, float)) and not isinstance(t, bool)]
        if toks:
            self.calls_with_tokens += 1
            self.tokens += sum(toks)
        cost = meta.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            self.calls_with_cost += 1
            self.cost += cost
        if self.max_tokens is not None and self.tokens > self.max_tokens:
            return f"{self.tokens:.0f} tokens > ceiling {self.max_tokens:.0f}"
        if self.max_cost is not None and self.cost > self.max_cost:
            return f"cost {self.cost:.4f} > ceiling {self.max_cost:.4f}"
        return None

    def report(self) -> str:
        """One line for summary.md. Says plainly when a ceiling could not be enforced."""
        parts = []
        for name, ceiling, used, seen, fmt in (
                ("tokens", self.max_tokens, self.tokens, self.calls_with_tokens, "{:.0f}"),
                ("cost", self.max_cost, self.cost, self.calls_with_cost, "{:.4f}")):
            spent = fmt.format(used) if seen else "not reported"
            if ceiling is None:
                parts.append(f"{name} {spent} (no ceiling set)")
            elif not seen:
                parts.append(f"{name} ceiling {fmt.format(ceiling)} NOT ENFORCED: the adapter "
                             f"reported no {name} usage")
            elif seen < self.calls:
                parts.append(f"{name} {spent} of {fmt.format(ceiling)} (partly enforced: "
                             f"{self.calls - seen} of {self.calls} calls reported no usage)")
            else:
                parts.append(f"{name} {spent} of {fmt.format(ceiling)}")
        return " · ".join(parts)


# ---------------------------------------------------------------------------- bias correction

def judge_rates(root: Path, judge_id: str) -> tuple[float, float] | None:
    """(TPR, TNR) from a judge's validation.md `## Rates`, or None when unreadable."""
    m = re.match(r"^JDG-(.+)-v\d+$", judge_id)
    vpath = root / "judges" / m.group(1) / "validation.md" if m else None
    if not vpath or not vpath.exists():
        return None
    body = _section(vpath.read_text(encoding="utf-8"), "## Rates") or ""
    got = {}
    for key in ("TPR", "TNR"):
        mm = re.search(rf"\b{key}\b\s*[:=]?\s*(\d?\.\d+|[01])\b", body)
        if mm:
            got[key] = float(mm.group(1))
    return (got["TPR"], got["TNR"]) if len(got) == 2 else None


def bias_corrected(root: Path, suite: dict, pf: Preflight, p1: stats.Rate) -> tuple[float | None, str]:
    """EVAL-CONTRACTS 5.5, applied to the per-attempt pass rate.

    Only defined when one judge alone decided each attempt: with several evaluators the observed
    rate mixes the errors of each, and no single TPR/TNR describes it. Applied to pass^1, not
    pass^k, because a judge decides one attempt; pass^k is a product over k decisions and the
    linear correction does not carry over.

    Fail is the positive class, so TPR/FPR describe how the judge reports FAILS. The formula runs
    on the observed fail rate and the corrected pass rate is one minus its result.
    """
    evaluators = [str(e) for e in (suite.get("evaluators") or [])]
    judges = [e.split(":", 1)[1] for e in evaluators if e.startswith("judge:")]
    if not judges:
        return None, "not applicable: no judge decides this suite"
    if len(evaluators) != 1:
        return None, ("not applied: the outcome combines several evaluators, and one judge's "
                      "TPR/TNR does not describe the combined rate")
    jid = judges[0]
    if jid in pf.unvalidated_judges:
        return None, f"not applied: {jid} is not VALIDATED"
    rates = judge_rates(root, jid)
    if rates is None:
        return None, f"not applied: {jid} validation.md has no readable TPR and TNR"
    if p1.n == 0:
        return None, "not applied: no attempts were scored"
    tpr, tnr = rates
    fail_true = stats.bias_correct(1.0 - p1.p, tpr=tpr, fpr=1.0 - tnr)
    if fail_true is None:
        return None, f"not applied: {jid} TPR-FPR < 0.5, the correction would amplify noise"
    return 1.0 - fail_true, f"{jid} TPR {tpr:.3f} TNR {tnr:.3f}"


# ---------------------------------------------------------------------------- run

def run(root: Path, suite_name: str, env: str, dry_run: bool = False,
        repeats_override: int | None = None, upload: bool = True,
        confirm_cost: bool = False, use_cache: bool = True) -> int:
    spath = root / "suites" / f"{suite_name}.yaml"
    if not spath.exists():
        print(f"no such suite: {spath}", file=sys.stderr)
        return 2
    suite = _parse_suite(spath.read_text(encoding="utf-8"))
    gates = suite.get("gates") or {}
    gated = bool(gates)
    repeats = repeats_override or int(suite.get("repeats", 1))

    pf = preflight(root, suite, env, gated)
    # What past runs taught, before this one spends anything. Unsafe lessons are withheld, not shown.
    for line in learnings.brief(root, suite_name, str(suite.get("layer") or "")):
        print(line)
    for w in pf.warnings:
        print(f"warning: {w}")
    for h in pf.needs_human:
        print(f"needs human: {h}. The gate verdict is NOT-EVALUABLE until it is set.")
    for j in pf.unvalidated_judges:
        print(f"warning: {j} is not VALIDATED. Every number it decides is marked UNVALIDATED "
              f"and the gate verdict will be NOT-EVALUABLE (EVAL-CONTRACTS 5.4).")
    if not pf.ok:
        for s in pf.stops:
            print(f"STOP: {s}", file=sys.stderr)
        return 1

    ds_path = root / "datasets" / f"{suite['dataset']}.jsonl"
    all_cases = load_dataset(ds_path)
    plan = economy.sample_to_power(all_cases, suite, gated)
    cases = plan.cases
    budget = Budget.load(root)
    judge_ids = [str(e).split(":", 1)[1] for e in (suite.get("evaluators") or [])
                 if str(e).startswith("judge:")]
    per_call, per_judge, per_src = economy.tokens_per_call(root, suite_name, suite)
    est = economy.estimate(len(cases), repeats, len(judge_ids), per_call, per_judge)
    est_full = economy.estimate(len(all_cases), repeats, len(judge_ids), per_call, per_judge)
    print(f"estimate: {economy.fmt(est)} tokens ({len(cases)} cases x {repeats} repeats x "
          f"(1 + {len(judge_ids)} judge(s)); per-call tokens from {per_src})")
    print(f"sample: {plan.note}")
    if economy.over_budget(est, budget.max_tokens) and not confirm_cost:
        print(f"STOP: needs human: the estimate of {economy.fmt(est)} tokens is over the "
              f"{budget.max_tokens:.0f} token budget. Shrink the suite, or re-run with "
              f"--confirm-cost once someone accepts the spend.", file=sys.stderr)
        return 5

    if dry_run:
        print(f"\n{suite_name}: {len(cases)} cases x {repeats} repeats = "
              f"{len(cases) * repeats} calls")
        print(f"dataset {suite['dataset']} sha256 {sha256(ds_path)[:12]}")
        print(f"model {suite.get('model')} temperature {suite.get('temperature')}")
        print(f"gate evaluable: {pf.gate_is_evaluable and gated}"
              + ("" if gated else " (no gate declared)"))
        print(f"budget: tokens {budget.max_tokens or 'no ceiling'} · "
              f"cost {budget.max_cost or 'no ceiling'}")
        print("dry run: no model calls made.")
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    out = root / "runs" / suite_name / run_id
    (out / "traces").mkdir(parents=True, exist_ok=True)

    adapter = load_adapter(suite.get("adapter", "providers.example:call"))
    judge_fn = load_adapter(suite["judge_adapter"]) if suite.get("judge_adapter") else None
    cache = economy.Cache(root, suite_name, suite, enabled=use_cache)
    judge_calls = judge_skipped = sys_calls = 0
    sys_tokens = judge_tokens = 0.0
    rows: list[dict] = []
    ctrf_tests: list[dict] = []
    outcomes: dict[str, list[bool]] = {}
    redacted: dict[str, int] = {}
    budget_stop: str | None = None
    start_ms = int(time.time() * 1000)

    for case in cases:
        if budget_stop:
            break
        cid = case["case_id"]
        outcomes[cid] = []
        for r in range(1, repeats + 1):
            t0 = time.time()
            hit = cache.get(case, r)
            if hit is not None:
                result, outcome, message, ms = {"cached": True}, hit["outcome"], hit.get("message", ""), 0
            else:
                try:
                    result = adapter(case["input"])
                    sys_calls += 1
                    sys_tokens += economy.call_tokens(result.get("meta"))
                    # The adapter returns the code assertions' outcomes in `verdicts`.
                    failed = [k for k, v in dict(result.get("verdicts", {})).items() if not v]
                    if judge_fn and judge_ids and failed:
                        # A deterministic check already failed the attempt; no judge can reverse it.
                        judge_skipped += len(judge_ids)
                    elif judge_fn:
                        for jid in judge_ids:
                            j = judge_fn(case["input"], result, jid) or {}
                            judge_calls += 1
                            judge_tokens += economy.call_tokens(j.get("meta"))
                            budget.add(j.get("meta"))
                            if not j.get("pass"):
                                failed.append(f"judge:{jid}")
                                break
                    outcome = "FAIL" if failed else "PASS"
                    message = f"{failed[0]} failed" if failed else ""
                except Exception as exc:                        # noqa: BLE001
                    result, outcome, message = {}, "ERROR", f"{type(exc).__name__}: {exc}"
                ms = int((time.time() - t0) * 1000)
                cache.put(case, r, {"outcome": outcome, "message": message,
                                    "tokens": economy.call_tokens((result or {}).get("meta"))})

            if outcome != "ERROR":
                outcomes[cid].append(outcome == "PASS")

            # Traces are uploaded as evidence, and an adapter that echoes its request carries
            # the API key with it. Mask before the first byte reaches disk.
            trace, hits = redact.redact({"case": case, "result": result})
            message, more = redact.redact(message)
            for k, v in list(hits.items()) + list(more.items()):
                redacted[k] = redacted.get(k, 0) + v
            trace_path = out / "traces" / cid / f"{r}.json"
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")

            rows.append({"case_id": cid, "repeat": r, "outcome": outcome,
                         "message": message, "ms": ms})
            ctrf_tests.append(ctrf.result_row(
                case_id=cid, outcome=outcome, duration_ms=ms, suite=suite_name,
                layer=str(suite.get("layer", "L2")), repeat=r, of=repeats,
                fm=case.get("fm", []),
                judges=[e.split(":", 1)[1] for e in (suite.get("evaluators") or [])
                        if str(e).startswith("judge:")],
                dataset=str(suite["dataset"]), model=str(suite.get("model")),
                message=message, trace=str(trace_path.relative_to(root)),
                unvalidated=bool(pf.unvalidated_judges)))

            budget_stop = None if hit is not None else budget.add((result or {}).get("meta"))
            if budget_stop:
                print(f"ERROR: budget exceeded ({budget_stop}) after {budget.calls} call(s). "
                      f"The run stops here; no gate verdict is reported from a truncated run.",
                      file=sys.stderr)
                break

    stop_ms = int(time.time() * 1000)
    (out / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    # A case whose every repeat errored was never measured. It stays out of the rates (there is
    # no outcome to count) but it is counted and named, and it keeps the run from reading PASS.
    not_run = sorted(cid for cid, v in outcomes.items() if not v)
    not_reached = len(cases) - len(outcomes)
    errored_attempts = sum(1 for row in rows if row["outcome"] == "ERROR")
    per_case = [v for v in outcomes.values() if v]
    p1 = stats.pass_at_1(per_case)
    pk = stats.pass_hat_k(per_case)
    flaky = stats.flaky_rate(per_case)
    fms = activity.fm_rates(cases, outcomes)
    baseline = activity.load_baseline(root, suite.get("baseline"))

    gate_results = evaluate_gates(gates, {"pass_1": p1, "pass_k": pk, "flaky": flaky},
                                  baseline=baseline, pass_k_p=pk.p if pk.n else None, fms=fms)
    verdict, deciding = decide(gate_results, gated=gated, unvalidated=pf.unvalidated_judges,
                               not_run=len(not_run), budget_stop=budget_stop,
                               needs_human=pf.needs_human)
    avg_sys = sys_tokens / sys_calls if sys_calls and sys_tokens else per_call
    avg_judge = judge_tokens / judge_calls if judge_calls and judge_tokens else per_judge
    actual = (sys_tokens + judge_tokens) if (sys_tokens or judge_tokens) else None
    saved_sample = (est_full - est) if est is not None and est_full is not None else None
    saved_cheap = judge_skipped * avg_judge if avg_judge is not None else None
    if sys_tokens:
        # The next run's estimate reads this when the suite declares no tokens_per_call.
        (out / "cost.json").write_text(json.dumps(
            {"tokens_per_call": avg_sys, "tokens_per_judge_call": avg_judge}), encoding="utf-8")
    theta, theta_note = bias_corrected(root, suite, pf, p1)

    gate_rows = "".join(f"| `{g.key}` | {g.threshold} | {g.verdict} | {g.detail} |\n"
                        for g in gate_results) or "| — | — | — | no gate declared |\n"
    corrected = f"{theta:.3f} (raw {p1.p:.3f}; {theta_note})" if theta is not None else theta_note
    not_run_line = f"{len(not_run)} — {', '.join(not_run[:20])}" if not_run else "0"
    reached_row = (f"| not reached (budget stop) | {not_reached} | {len(cases)} |\n"
                   if not_reached else "")
    redacted_line = ", ".join(f"{k} {v}" for k, v in sorted(redacted.items())) or "nothing"
    judges_line = ("no — " + ", ".join(pf.unvalidated_judges)) if pf.unvalidated_judges else "yes"
    (out / "summary.md").write_text(
        f"# {suite_name} — {run_id}\n\n"
        f"## Verdict\n{verdict} — decided by `{deciding}`\n\n"
        f"## Configuration\n"
        f"- dataset: {suite['dataset']} (sha256 {sha256(ds_path)[:12]})\n"
        f"- model: {suite.get('model')} · temperature {suite.get('temperature')}\n"
        f"- repeats: {repeats} · env: {env}\n"
        f"- judges validated: {judges_line}\n"
        f"- budget ({budget.source}): {budget.report()}\n"
        f"- redacted from traces: {redacted_line}\n\n"
        f"## Cost\n| | Tokens |\n|---|---|\n"
        f"| estimate before the run | {economy.fmt(est)} |\n"
        f"| actual | {economy.fmt(actual)} |\n"
        f"| saved by sampling to power ({plan.skipped} cases skipped) | {economy.fmt(saved_sample)} |\n"
        f"| saved by the cache ({cache.hits} attempts reused) | {economy.fmt(cache.saved_tokens)} |\n"
        f"| saved by cheap checks first ({judge_skipped} judge calls skipped) | {economy.fmt(saved_cheap)} |\n\n"
        f"Sample: {plan.note}.\n\n"
        f"## Results\n"
        f"| Metric | Value | n |\n|---|---|---|\n"
        f"| pass^1 (per attempt) | {p1} | {p1.n} |\n"
        f"| pass^{repeats} (per case) | {pk} | {pk.n} |\n"
        f"| flaky rate | {flaky} | {flaky.n} |\n"
        f"| not run (every repeat ERROR) | {not_run_line} | {len(cases)} |\n"
        f"| errored attempts | {errored_attempts} | {len(rows)} |\n"
        f"{reached_row}\n"
        f"pass^1 bias-corrected (EVAL-CONTRACTS 5.5): {corrected}\n\n"
        f"## Gates\n| Gate | Threshold | Result | Measured |\n|---|---|---|---|\n{gate_rows}\n"
        f"Gates compare the interval's LOWER BOUND, never the point estimate.\n",
        encoding="utf-8")

    ctrf.write(out / "ctrf.json", ctrf.report(
        tests=ctrf_tests, start_ms=start_ms, stop_ms=stop_ms, env=env,
        build=str(suite.get("prompt_version", ""))))

    try:
        margin = float(gates.get("regression_margin", 0) or 0)
    except (TypeError, ValueError):
        margin = 0.0
    # The activity log feeds the board's Activity, Findings and Needs you; it never fails a run.
    try:
        activity.log_activity(root, activity.run_events(
            suite=suite_name, layer=str(suite.get("layer", "L2")), run_id=run_id, verdict=verdict,
            pass_k=pk, link=_project_link(out / "summary.md", root),
            baseline=baseline, fms=fms, margin=margin,
            trusted=not pf.unvalidated_judges))
    except Exception as exc:  # noqa: BLE001
        print(f"warning: activity not logged ({exc})", file=sys.stderr)

    # The board and the session brief read .evals/state.json; a run is the moment it goes stale.
    try:
        import build_state  # noqa: PLC0415
        doc = build_state.build_state(root)
        (root / "state.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8", newline="\n")
    except Exception as exc:  # noqa: BLE001 — the run's evidence is written; the index is a cache
        print(f"warning: state.json not rebuilt ({exc})", file=sys.stderr)

    print(f"\n{verdict} — {suite_name} {run_id} (decided by {deciding})")
    print(f"pass^1 {p1}\npass^{repeats} {pk}\nflaky  {flaky}")
    if not_run:
        print(f"NOT RUN: {len(not_run)} case(s) errored on every repeat: {', '.join(not_run[:10])}")
    for g in gate_results:
        print(f"gate {g.key} {g.threshold}: {g.verdict} — {g.detail}")
    print(f"budget: {budget.report()}")
    print(f"\n{out}")
    project = str(suite.get("project") or os.environ.get("VERDICT_PROJECT", ""))
    tags = [suite_name, f"layer:{suite.get('layer', 'L2')}", f"dataset:{suite['dataset']}"]
    if pf.unvalidated_judges:
        # The hub must not show a green run whose numbers came from an uncalibrated judge.
        tags.append("unvalidated")
    if budget_stop:
        tags.append("truncated")

    if upload and os.environ.get("VERDICT_URL"):
        res = verdict_hub.upload(
            ctrf_path=out / "ctrf.json", project=project, env=env, test_type="eval",
            name=f"{suite_name} {run_id}", tags=tags, evidence_dir=out,
            idempotency_key=f"{suite_name}-{run_id}",
            out=str(out / ".verdict-run.json"))
        print()
        print(verdict_hub.report(res))
    else:
        print()
        print("upload:")
        print("  " + verdict_hub.command(
            ctrf_path=out / "ctrf.json", project=project or "<project>", env=env,
            tags=tags, evidence_dir=out))
        if upload:
            print("  (skipped: VERDICT_URL is not set)")

    if budget_stop:
        return 4
    return 0 if verdict == "PASS" else (1 if verdict == "FAIL" else 3)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run an eval suite")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--root", default=None, help=root_arg_help())
    ap.add_argument("--env", default="staging")
    ap.add_argument("--repeats", type=int, default=None,
                    help="override the suite's repeat count. A repeat count chosen after seeing "
                         "results is not a measurement -- prefer editing the suite.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm-cost", action="store_true",
                    help="run even when the up-front estimate is over the token budget: a human "
                         "accepting the spend, never a default")
    ap.add_argument("--no-cache", action="store_true",
                    help="re-run every attempt even when an identical one is cached")
    ap.add_argument("--no-upload", action="store_true",
                    help="do not send the run to verdict, even when VERDICT_URL is set")
    args = ap.parse_args()
    return run(resolve_root(args.root), args.suite, args.env, args.dry_run, args.repeats,
               upload=not args.no_upload, confirm_cost=args.confirm_cost,
               use_cache=not args.no_cache)


if __name__ == "__main__":
    raise SystemExit(main())
