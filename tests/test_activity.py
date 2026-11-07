"""activity.py: the shared event format (docs/activity-format.md) and the events a run writes.

    python3 -m unittest tests/test_activity.py      (selfcheck.sh section 9 runs it)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent
SHARED = BUNDLE / "workspace" / "evals" / "scripts" / "shared"
sys.path.insert(0, str(SHARED))

import activity  # noqa: E402
from stats import pass_hat_k  # noqa: E402

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)

def baseline(p: float, per_fm: dict | None = None) -> dict:
    return {"id": "BASE-2026-10-01-x", "results": {"task_success": {"p": p, "ci": [p - 0.05, p], "n": 100}},
            "per_fm": {k: {"p": v} for k, v in (per_fm or {}).items()}}

def events_for(outcomes: list[list[bool]], **kw) -> list[dict]:
    args = dict(suite="task-x", layer="L2", run_id="2026-10-22-0900", verdict="PASS",
                pass_k=pass_hat_k(outcomes), link="evals/runs/task-x/2026-10-22-0900/summary.md",
                baseline=None, fms={}, margin=0.05, now=NOW)
    args.update(kw)
    return activity.run_events(**args)

class Format(unittest.TestCase):
    def test_documented_example_is_valid_and_each_broken_field_is_named(self):
        doc = (BUNDLE / "docs" / "activity-format.md").read_text(encoding="utf-8")
        example = json.loads(re.search(r"```json\n(.+)\n```", doc).group(1))
        self.assertEqual(activity.event_problems(example), [])
        for field, value, pattern in [
            ("v", 2, "v must be 1"), ("at", "2026-10-22 09:14", "at must"), ("source", "jira", "source"),
            ("kind", "commit", "kind"), ("outcome", "ok", "outcome"), ("title", "x" * 121, "title"),
            ("needs", "coffee", "needs"), ("link", "C:/x.md", "link"), ("slug", 3, "slug"),
        ]:
            self.assertRegex(" | ".join(activity.event_problems({**example, field: value})), pattern, field)

    def test_log_appends_valid_events_only_never_creates_the_root_and_honours_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = activity.make_event(kind="run", slug="task-x", outcome="pass", title="task-x PASS")
            self.assertEqual(activity.log_activity(root, [good, {**good, "kind": "nope"}], env={}), 1)
            self.assertEqual(activity.log_activity(root, [good], env={"ACTIVITY_LOG": "off"}), 0)
            log = root / "logs" / "activity.jsonl"
            self.assertEqual(len(activity.read_activity(log)), 1)
            with log.open("a", encoding="utf-8") as fh:
                fh.write('{"v":1,"at":"2026-10')  # a torn last line
            self.assertEqual(len(activity.read_activity(log)), 1)
            self.assertEqual(activity.log_activity(root / "missing", [good], env={}), 0)
            self.assertFalse((root / "missing").exists())

class RunEvents(unittest.TestCase):
    def test_a_run_with_no_baseline_writes_only_its_run_event(self):
        ev = events_for([[True]] * 10)
        self.assertEqual([e["kind"] for e in ev], ["run"])
        self.assertEqual(ev[0]["outcome"], "pass")
        self.assertIn("n=10", ev[0]["title"])

    def test_not_evaluable_is_info_never_pass_or_fail(self):
        ev = events_for([[True]] * 10, verdict="NOT-EVALUABLE")
        self.assertEqual(ev[0]["outcome"], "info")

    def test_score_passes_within_the_margin(self):
        ev = events_for([[True]] * 9 + [[False]], baseline=baseline(0.92))
        score = [e for e in ev if e["kind"] == "score"]
        self.assertEqual(len(score), 1)
        self.assertEqual(score[0]["outcome"], "pass")
        self.assertRegex(score[0]["title"], r"^L2 task-x 90\.0% vs baseline 92\.0%")
        self.assertFalse([e for e in ev if e["kind"] == "finding"])

    def test_a_drop_past_the_margin_fails_the_score_and_writes_one_finding_per_regression(self):
        ev = events_for([[True]] * 7 + [[False]] * 3, baseline=baseline(0.9, {"FM-001": 0.95, "FM-002": 0.5}),
                        fms={"FM-001": 0.6, "FM-002": 0.5})
        self.assertEqual(next(e for e in ev if e["kind"] == "score")["outcome"], "fail")
        findings = [e for e in ev if e["kind"] == "finding"]
        self.assertEqual([f["title"].split()[1] for f in findings], ["total", "FM-001"])
        self.assertTrue(all(f["outcome"] == "fail" for f in findings))
        self.assertEqual(findings[1]["title"], "regression FM-001 task-x: 95.0% -> 60.0% (-35.0 pts)")
        for e in ev:
            self.assertEqual(activity.event_problems(e), [], e)

    def test_an_unvalidated_judge_writes_no_score_and_no_regression(self):
        ev = events_for([[False]] * 10, baseline=baseline(0.9), trusted=False, verdict="NOT-EVALUABLE")
        self.assertEqual([e["kind"] for e in ev], ["run"])

    def test_fm_rates_count_a_case_only_when_every_repeat_passed(self):
        cases = [{"case_id": "a", "fm": ["FM-1"]}, {"case_id": "b", "fm": ["FM-1"]}, {"case_id": "c", "fm": []}]
        self.assertEqual(activity.fm_rates(cases, {"a": [True, True], "b": [True, False], "c": [True]}), {"FM-1": 0.5})

FAILING_ADAPTER = '''
def call(case_input):
    bad = "order" in str(case_input.get("message", ""))
    return {"output": {}, "steps": [], "meta": {}, "verdicts": {"no-invented-ids": not bad}}
'''

class RunnerWritesTheLog(unittest.TestCase):
    """The shipped runner, on a copy of the seed, against a baseline it regresses from."""

    def test_a_regressing_run_logs_run_score_and_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evals"
            shutil.copytree(BUNDLE / "workspace" / "evals", root,
                            ignore=shutil.ignore_patterns("runs", "logs", "state.json", "__pycache__"))
            (root / "scripts" / "shared" / "providers" / "failing.py").write_text(FAILING_ADAPTER, encoding="utf-8")
            (root / "baselines" / "BASE-2026-10-01-x.json").write_text(
                json.dumps(baseline(1.0, {"FM-001": 1.0})), encoding="utf-8")
            suite = root / "suites" / "task-example.yaml"
            suite.write_text(suite.read_text(encoding="utf-8").replace(
                "adapter: providers.example:call", "adapter: providers.failing:call")
                + "\nbaseline: BASE-2026-10-01-x\n", encoding="utf-8")
            env = {**os.environ, "ACTIVITY_LOG": "", "VERDICT_URL": ""}
            subprocess.run([sys.executable, str(root / "scripts" / "shared" / "runner.py"), "--suite",
                            "task-example", "--root", str(root), "--no-upload"],
                           env=env, capture_output=True, text=True, timeout=120)
            ev = activity.read_activity(root / "logs" / "activity.jsonl")
            kinds = [e["kind"] for e in ev]
            self.assertEqual(kinds[0], "run", ev)
            self.assertEqual(next(e for e in ev if e["kind"] == "score")["outcome"], "fail", ev)
            self.assertEqual(sorted(e["title"].split()[1] for e in ev if e["kind"] == "finding"), ["FM-001", "total"])
            self.assertTrue(all(e["source"] == "eval" and e["slug"] == "task-example" for e in ev))
            self.assertTrue(ev[0]["link"].startswith("evals/runs/task-example/"), ev[0]["link"])

if __name__ == "__main__":
    unittest.main()


class ProjectLink(unittest.TestCase):
    # The board opens a link from the project folder; with `--root a/evals` the link must keep `a/`.
    def test_a_nested_eval_root_keeps_its_prefix_and_a_plain_one_is_unchanged(self):
        import runner  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            nested = proj / "a" / "evals"
            (nested / "runs").mkdir(parents=True)
            here = os.getcwd()
            try:
                os.chdir(proj)
                self.assertEqual(runner._project_link(nested / "runs" / "summary.md", nested), "a/evals/runs/summary.md")
                plain = proj / "evals"
                plain.mkdir()
                self.assertEqual(runner._project_link(plain / "summary.md", plain), "evals/summary.md")
            finally:
                os.chdir(here)
