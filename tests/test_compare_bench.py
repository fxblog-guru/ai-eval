"""compare_bench.py: a bundle that got worse is reported WORSE and exits 1; thin data is NOT-EVALUABLE.

    python3 tests/test_compare_bench.py      (selfcheck.sh section 9 runs it)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent
SCRIPT = BUNDLE / "workspace" / "evals" / "scripts" / "compare_bench.py"
sys.path.insert(0, str(SCRIPT.parent))

import compare_bench  # noqa: E402


def bench(version: str, passes: list, *, condition: str = "lessons", tokens=1000) -> dict:
    return {"schema": 1, "bundle": "sdlc", "version": version, "condition": condition,
            "tasks": [{"task_id": f"T-{i:03d}", "first_pass": p, "repeat_errors": 0 if p else 1,
                       "tokens": tokens, "duration_s": 60.0} for i, p in enumerate(passes)]}


def run(a: dict, b: dict) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        pa, pb, out = Path(tmp) / "a.json", Path(tmp) / "b.json", Path(tmp) / "r.md"
        pa.write_text(json.dumps(a), encoding="utf-8")
        pb.write_text(json.dumps(b), encoding="utf-8")
        p = subprocess.run([sys.executable, str(SCRIPT), str(pa), str(pb), "--out", str(out)],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        return p.returncode, out.read_text(encoding="utf-8") if out.exists() else p.stderr


class Verdicts(unittest.TestCase):
    def test_a_version_that_loses_tasks_is_worse_and_exits_1(self):
        # 30 tasks: the earlier version solved 28, the later one 16 — 12 lost, none gained.
        code, md = run(bench("1.0.0", [True] * 28 + [False] * 2),
                       bench("1.1.0", [True] * 16 + [False] * 14))
        self.assertEqual(code, 1, md)
        self.assertIn("## Verdict\nWORSE", md)

    def test_a_version_that_gains_tasks_is_better(self):
        code, md = run(bench("1.0.0", [True] * 16 + [False] * 14),
                       bench("1.1.0", [True] * 28 + [False] * 2))
        self.assertEqual(code, 0, md)
        self.assertIn("## Verdict\nBETTER", md)

    def test_a_small_change_is_no_significant_difference(self):
        code, md = run(bench("1.0.0", [True] * 20 + [False] * 10),
                       bench("1.1.0", [True] * 21 + [False] * 9))
        self.assertEqual(code, 0, md)
        self.assertIn("NO-SIGNIFICANT-DIFFERENCE", md)

    def test_too_few_paired_tasks_is_not_evaluable(self):
        code, md = run(bench("1.0.0", [True] * 10), bench("1.1.0", [False] * 10))
        self.assertEqual(code, 3, md)
        self.assertIn("NOT-EVALUABLE — 10 paired task(s), need 20", md)

    def test_a_null_first_pass_is_not_evaluable_rather_than_guessed(self):
        b = bench("1.1.0", [False] * 30)
        b["tasks"][3]["first_pass"] = None
        code, md = run(bench("1.0.0", [True] * 30), b)
        self.assertEqual(code, 3, md)
        self.assertIn("have no first_pass", md)

    def test_lessons_vs_no_lessons_on_one_version(self):
        code, md = run(bench("1.2.0", [True] * 15 + [False] * 15, condition="no-lessons"),
                       bench("1.2.0", [True] * 29 + [False] * 1))
        self.assertEqual(code, 0, md)
        self.assertIn("(no-lessons) vs sdlc 1.2.0 (lessons)", md)

    def test_a_partial_metric_has_no_median(self):
        b = bench("1.1.0", [True] * 30)
        b["tasks"][0]["tokens"] = None
        _, md = run(bench("1.0.0", [True] * 30), b)
        self.assertIn("| median tokens | 1000 | — | — |", md)


class TheWorseCheckCanFail(unittest.TestCase):
    def test_a_mutant_that_flips_the_worse_branch_is_caught(self):
        # Rebuild the module with the WORSE comparison reversed; the losing bundle must then
        # escape WORSE. If it did not, the WORSE test above would pass on broken code.
        src = SCRIPT.read_text(encoding="utf-8")
        target = "elif p.p_value < ALPHA and p.b > p.c:"
        self.assertIn(target, src)
        mutant: dict = {"__name__": "mutant", "__file__": str(SCRIPT)}
        exec(compile(src.replace(target, "elif p.p_value < ALPHA and p.b < p.c:"), "mutant", "exec"), mutant)
        a = compare_bench.load_obj(bench("1.0.0", [True] * 28 + [False] * 2))
        b = compare_bench.load_obj(bench("1.1.0", [True] * 16 + [False] * 14))
        self.assertEqual(compare_bench.compare(a, b)["verdict"], "WORSE")
        self.assertNotEqual(mutant["compare"](a, b)["verdict"], "WORSE")


if __name__ == "__main__":
    unittest.main()
