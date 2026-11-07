"""The runner spends as few tokens as the question allows, says up front what a run will cost, and
asks a human instead of guessing.

    python3 tests/test_economy.py      (selfcheck.sh section 9 runs it)

Each test is written so that removing the mechanism it covers makes it fail: a cache that never
hits, a judge called on an already-failed attempt, a sample that never shrinks, an estimate that
never refuses, a gate that runs without its owner.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "workspace" / "evals" / "scripts" / "shared"))

import economy  # noqa: E402
import runner  # noqa: E402
from test_runner import run, seed_copy, verdict_line  # noqa: E402

# Every call reports 100 tokens; the assertion fails on the case that asks about a delivery.
METERED = '''
def call(case_input):
    ok = "delivery" not in str(case_input.get("message", "")).lower()
    return {"output": {}, "steps": [], "meta": {"tokens_in": 60, "tokens_out": 40},
            "verdicts": {"a": ok}}

CALLS = {"judge": 0}
def judge(case_input, result, jid):
    return {"pass": True, "meta": {"tokens_in": 300, "tokens_out": 200}}
'''
JUDGED = "evaluators:\n  - assert:a\n  - judge:JDG-g-v1\njudge_adapter: providers.t:judge\n"


def cost_rows(summary: str) -> dict[str, str]:
    body = summary.split("## Cost\n", 1)[1].split("\n\n", 1)[0]
    return {r.split("|")[1].strip(): r.split("|")[2].strip() for r in body.splitlines()[2:]}


class Cache(unittest.TestCase):
    def test_an_unchanged_case_is_not_run_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = seed_copy(tmp, METERED)
            run(root)
            _, _, second = run(root)
            rows = cost_rows(second)
            self.assertIn("saved by the cache (9 attempts reused)", rows, rows)
            self.assertEqual(rows["actual"], "unknown", "a fully cached run calls nothing")

    def test_a_new_system_version_misses_the_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = seed_copy(tmp, METERED)
            run(root)
            suite = root / "suites" / "task-example.yaml"
            suite.write_text(suite.read_text(encoding="utf-8") + "system_version: 9.9.9\n", encoding="utf-8")
            _, _, second = run(root)
            self.assertIn("saved by the cache (0 attempts reused)", cost_rows(second))

    def test_an_error_is_never_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = economy.Cache(Path(tmp), "s", {}, enabled=True)
            c.put({"case_id": "EV-TASK-001"}, 1, {"outcome": "ERROR"})
            self.assertIsNone(c.get({"case_id": "EV-TASK-001"}, 1))


class CheapChecksFirst(unittest.TestCase):
    def test_the_judge_is_skipped_where_an_assertion_already_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            # One of the seed's 3 cases asks about a delivery, so 1 case x 3 repeats skip the judge.
            _, out, summary = run(seed_copy(tmp, METERED, JUDGED.replace("evaluators:\n  - assert:no-invented-ids\n", "")))
            rows = cost_rows(summary)
            skipped = next(k for k in rows if k.startswith("saved by cheap checks first"))
            self.assertNotIn("(0 judge calls", skipped, summary)
            self.assertEqual(rows[skipped], f"{int(skipped.split('(')[1].split()[0]) * 500}")


class SampleToPower(unittest.TestCase):
    CASES = [{"case_id": f"EV-TASK-{i:03d}", "fm": ["FM-001"] if i < 300 else ["FM-002"]}
             for i in range(400)]

    def test_the_smallest_sample_that_meets_the_interval_is_run(self):
        plan = economy.sample_to_power(self.CASES, {"ci_half_width": 0.1}, gated=True)
        self.assertEqual(plan.needed, 97)   # 1.96^2 * 0.25 / 0.01, rounded up
        self.assertEqual(len(plan.cases), 97)
        self.assertEqual(plan.skipped, 303)
        self.assertEqual({fm for c in plan.cases for fm in c["fm"]}, {"FM-001", "FM-002"},
                         "every failure mode keeps at least one case")

    def test_a_gated_suite_never_drops_below_30(self):
        plan = economy.sample_to_power(self.CASES, {"ci_half_width": 0.4}, gated=True)
        self.assertEqual(len(plan.cases), 30)

    def test_no_declared_width_runs_everything(self):
        self.assertEqual(economy.sample_to_power(self.CASES, {}, gated=True).skipped, 0)


class Estimate(unittest.TestCase):
    def test_the_estimate_counts_judges(self):
        self.assertEqual(economy.estimate(10, 3, 1, 100, 500), 18000)
        self.assertIsNone(economy.estimate(10, 3, 1, None, None), "unknown is never guessed")

    def test_a_run_over_budget_is_refused_until_a_human_confirms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = seed_copy(tmp, METERED, "tokens_per_call: 1000\n")
            code, out, summary = run(root, {"EVAL_TOKEN_BUDGET": "5000"})
            self.assertEqual(code, 5, out)
            self.assertIn("needs human: the estimate of 9000 tokens is over", out)
            self.assertEqual(summary, "", "a refused run writes no results")

    def test_summary_shows_the_estimate_against_the_actual(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary = run(seed_copy(tmp, METERED, "tokens_per_call: 100\n"))
            rows = cost_rows(summary)
            self.assertEqual(rows["estimate before the run"], "900")
            self.assertEqual(rows["actual"], "900")


class NeedsHuman(unittest.TestCase):
    def test_a_gate_without_its_system_version_is_not_evaluable(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out, summary = run(seed_copy(tmp, METERED, "gates:\n  task_success_ci_lower: 0.10\n", cases=30))
            self.assertTrue(verdict_line(summary).startswith("NOT-EVALUABLE — decided by `needs human: system_version"),
                            summary)

    def test_a_judged_gate_without_a_labels_owner_is_not_evaluable(self):
        pf = runner.preflight(seed_copy(tempfile.mkdtemp(), METERED),
                              {"model": "m", "temperature": 0, "dataset": "DS-example-v1",
                               "system_version": "1", "evaluators": ["judge:JDG-g-v1"]},
                              "staging", gated=True)
        self.assertTrue(any(h.startswith("labels_owner") for h in pf.needs_human), pf.needs_human)

    def test_a_placeholder_counts_as_unset(self):
        self.assertTrue(runner._unset("<build id>"))
        self.assertFalse(runner._unset("2.0.0"))


if __name__ == "__main__":
    unittest.main()
