"""runner.py: the verdict it reaches, what it counts, what it spends, and what it writes to disk.

    python3 tests/test_runner.py      (selfcheck.sh section 9 runs it)

Every test runs the shipped runner on a copy of the seed with an adapter written for the case, so
a change that makes a run report PASS for the wrong reason fails here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent
SHARED = BUNDLE / "workspace" / "evals" / "scripts" / "shared"
sys.path.insert(0, str(SHARED))

import redact  # noqa: E402
import runner  # noqa: E402
import stats  # noqa: E402

PASSING = '''
def call(case_input):
    return {"output": {}, "steps": [], "meta": {}, "verdicts": {"a": True}}
'''

# EV-TASK-002 raises on every repeat; the rest pass.
ONE_ERRORS = '''
def call(case_input):
    if "delivery" in str(case_input.get("message", "")):
        raise RuntimeError("upstream 503")
    return {"output": {}, "steps": [], "meta": {}, "verdicts": {"a": True}}
'''

# Attempts alternate pass/fail, so every case is FLAKY: pass^1 is 0.5 and the flaky rate is 1.0.
FLAKY = '''
import itertools
_n = itertools.count()
def call(case_input):
    return {"output": {}, "steps": [], "meta": {}, "verdicts": {"a": next(_n) % 2 == 0}}
'''

SPENDING = '''
def call(case_input):
    return {"output": {}, "steps": [], "meta": {"tokens_in": 400, "tokens_out": 200, "cost": 0.01},
            "verdicts": {"a": True}}
'''

LEAKY = '''
def call(case_input):
    return {"output": {"text": "contact ops@example.com"},
            "steps": [{"type": "llm", "name": "x", "ms": 0,
                       "input": {"headers": {"Authorization": "Bearer abcdefghijklmnop0123"},
                                 "api_key": "whatever-it-is"},
                       "output": {"echo": "key sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA"}}],
            "meta": {}, "verdicts": {"a": True}}
'''


def seed_copy(tmp: str, adapter: str, suite_extra: str = "", cases: int | None = None) -> Path:
    """A copy of the seed whose task-example suite calls `adapter`; `cases` duplicates the seed's
    rows up to that many, for gated runs that need n >= 30."""
    root = Path(tmp) / "evals"
    shutil.copytree(BUNDLE / "workspace" / "evals", root,
                    ignore=shutil.ignore_patterns("runs", "logs", "state.json", "__pycache__"))
    (root / "scripts" / "shared" / "providers" / "t.py").write_text(adapter, encoding="utf-8")
    suite = root / "suites" / "task-example.yaml"
    suite.write_text(suite.read_text(encoding="utf-8").replace(
        "adapter: providers.example:call", "adapter: providers.t:call") + "\n" + suite_extra,
        encoding="utf-8")
    if cases:
        ds = root / "datasets" / "DS-example-v1.jsonl"
        base = [json.loads(x) for x in ds.read_text(encoding="utf-8").splitlines() if x.strip()]
        rows = []
        for i in range(cases):
            row = dict(base[i % len(base)])
            row["case_id"] = f"EV-TASK-{i + 1:03d}"
            rows.append(json.dumps(row))
        ds.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root


def run(root: Path, env: dict | None = None) -> tuple[int, str, str]:
    """Exit code, stdout, and the run's summary.md."""
    e = {**os.environ, "ACTIVITY_LOG": "off", "VERDICT_URL": "", "EVAL_TOKEN_BUDGET": "",
         "EVAL_COST_CEILING": "", **(env or {})}
    p = subprocess.run([sys.executable, str(root / "scripts" / "shared" / "runner.py"), "--suite",
                        "task-example", "--root", str(root), "--no-upload"],
                       env=e, capture_output=True, text=True, timeout=120)
    runs = sorted((root / "runs" / "task-example").glob("*/summary.md"))
    return p.returncode, p.stdout + p.stderr, runs[-1].read_text(encoding="utf-8") if runs else ""


def verdict_line(summary: str) -> str:
    return summary.split("## Verdict\n", 1)[1].split("\n", 1)[0]


class NoGateIsNotPass(unittest.TestCase):
    def test_an_ungated_suite_reports_not_evaluable_with_the_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, summary = run(seed_copy(tmp, PASSING))
            self.assertEqual(verdict_line(summary), "NOT-EVALUABLE — decided by `no gate declared`", out)
            self.assertNotEqual(code, 0, "an ungated run must not exit as a pass")

    def test_an_unvalidated_judge_never_produces_pass_even_without_a_gate(self):
        pf = runner.Preflight(unvalidated_judges=["JDG-x-v1"])
        self.assertEqual(runner.decide([], gated=False, unvalidated=pf.unvalidated_judges,
                                       not_run=0, budget_stop=None)[0], "NOT-EVALUABLE")


class ErroredCasesAreCounted(unittest.TestCase):
    def test_a_case_that_only_errored_is_named_and_blocks_pass(self):
        gate = "system_version: 2.0.0\ngates:\n  task_success_ci_lower: 0.10\n"
        with tempfile.TemporaryDirectory() as tmp:
            code, out, summary = run(seed_copy(tmp, ONE_ERRORS, gate, cases=30))
            self.assertIn("| not run (every repeat ERROR) | 10 — EV-TASK-002", summary, summary)
            self.assertIn("errored attempts | 30 |", summary)
            self.assertTrue(verdict_line(summary).startswith("NOT-EVALUABLE"), summary)
            self.assertIn("10 case(s) not run", verdict_line(summary))
            self.assertIn("NOT RUN: 10", out)
            self.assertEqual(code, 3)


class EveryGateDecides(unittest.TestCase):
    def test_a_failing_second_gate_fails_the_run(self):
        # pass^1 0.5 on 90 attempts clears 0.10; the flaky rate is 1.0, far over 0.05.
        gate = "system_version: 2.0.0\ngates:\n  pass_1_ci_lower: 0.10\n  flaky_rate_max: 0.05\n"
        with tempfile.TemporaryDirectory() as tmp:
            code, out, summary = run(seed_copy(tmp, FLAKY, gate, cases=30))
            self.assertIn("| `pass_1_ci_lower` | 0.1 | PASS |", summary, summary)
            self.assertIn("| `flaky_rate_max` | 0.05 | FAIL |", summary)
            self.assertEqual(verdict_line(summary), "FAIL — decided by `flaky_rate_max`")
            self.assertEqual(code, 1)

    def test_each_gate_reads_the_metric_it_names(self):
        rates = {"pass_1": stats.wilson(90, 100), "pass_k": stats.wilson(10, 100),
                 "flaky": stats.wilson(0, 100)}
        got = {g.key: g.verdict for g in runner.evaluate_gates(
            {"pass_1_ci_lower": 0.8, "task_success_ci_lower": 0.8, "mystery_ci_lower": 0.5},
            rates, baseline=None, pass_k_p=0.1, fms={})}
        self.assertEqual(got, {"pass_1_ci_lower": "PASS", "task_success_ci_lower": "FAIL",
                               "mystery_ci_lower": "NOT-EVALUABLE"})

    def test_all_gates_passing_is_the_only_pass(self):
        g = runner.GateResult
        ok = [g("a", 0.8, "PASS", ""), g("b", 0.8, "PASS", "")]
        self.assertEqual(runner.decide(ok, gated=True, unvalidated=[], not_run=0, budget_stop=None)[0], "PASS")
        mixed = ok + [g("c", 0.8, "NOT-EVALUABLE", "")]
        self.assertEqual(runner.decide(mixed, gated=True, unvalidated=[], not_run=0, budget_stop=None),
                         ("NOT-EVALUABLE", "c"))


class Budget(unittest.TestCase):
    def test_the_run_aborts_past_the_token_ceiling(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, summary = run(seed_copy(tmp, SPENDING), {"EVAL_TOKEN_BUDGET": "1500"})
            self.assertEqual(code, 4, out)
            self.assertIn("budget exceeded (1800 tokens > ceiling 1500) after 3 call(s)", out)
            self.assertTrue(verdict_line(summary).startswith("NOT-EVALUABLE — decided by `budget exceeded"))
            self.assertIn("| not reached (budget stop) | 2 |", summary)

    def test_the_cost_ceiling_is_read_from_the_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = seed_copy(tmp, SPENDING)
            (root.parent / "EVAL-PROFILE.md").write_text(
                "## Budget\n\n- **Per-run token budget:** `<tokens>`\n"
                "- **Per-run cost ceiling:** `$0.025`\n", encoding="utf-8")
            code, out, _ = run(root)
            self.assertEqual(code, 4, out)
            self.assertIn("cost 0.0300 > ceiling 0.0250", out)

    def test_an_adapter_that_reports_no_usage_says_the_budget_was_not_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, summary = run(seed_copy(tmp, PASSING), {"EVAL_TOKEN_BUDGET": "10"})
            self.assertNotEqual(code, 4, out)
            self.assertIn("tokens ceiling 10 NOT ENFORCED: the adapter reported no tokens usage", summary)


class TracesAreRedacted(unittest.TestCase):
    def test_keys_tokens_and_emails_never_reach_the_trace_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = seed_copy(tmp, LEAKY)
            _, out, summary = run(root)
            text = "".join(p.read_text(encoding="utf-8") for p in root.glob("runs/**/traces/**/*.json"))
            self.assertTrue(text, out)
            for secret in ("ops@example.com", "abcdefghijklmnop0123", "whatever-it-is", "sk-ant-api03"):
                self.assertNotIn(secret, text)
            self.assertIn("[REDACTED:email]", text)
            self.assertIn("redacted from traces:", summary)
            self.assertIn("anthropic-key", summary)

    def test_ordinary_text_is_left_alone(self):
        obj = {"message": "where is order 881234", "token_count": 12, "steps": ["retrieval"]}
        self.assertEqual(redact.redact(obj), (obj, {}))


class BiasCorrection(unittest.TestCase):
    def _root(self, tmp: str, rates: str) -> Path:
        root = Path(tmp)
        (root / "judges" / "g").mkdir(parents=True)
        (root / "judges" / "g" / "validation.md").write_text(
            f"## Rates\n{rates}\n\n## Verdict\nVALIDATED\n", encoding="utf-8")
        return root

    def test_a_single_validated_judge_corrects_the_pass_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, "TPR 0.900 · TNR 0.900 · kappa 0.800")
            # Observed fail rate 0.26; true fail = (0.26 - 0.10) / 0.80 = 0.20, so pass = 0.80.
            theta, note = runner.bias_corrected(root, {"evaluators": ["judge:JDG-g-v1"]},
                                                runner.Preflight(), stats.wilson(74, 100))
            self.assertAlmostEqual(theta, 0.80, places=6)
            self.assertIn("JDG-g-v1", note)

    def test_it_is_refused_where_it_is_not_defined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, "TPR 0.600 · TNR 0.700")
            p = stats.wilson(74, 100)
            self.assertIsNone(runner.bias_corrected(root, {"evaluators": ["judge:JDG-g-v1"]},
                                                    runner.Preflight(), p)[0])
            self.assertIsNone(runner.bias_corrected(root, {"evaluators": ["assert:x", "judge:JDG-g-v1"]},
                                                    runner.Preflight(), p)[0])
            self.assertIsNone(runner.bias_corrected(root, {"evaluators": ["judge:JDG-g-v1"]},
                                                    runner.Preflight(unvalidated_judges=["JDG-g-v1"]), p)[0])


if __name__ == "__main__":
    unittest.main()
