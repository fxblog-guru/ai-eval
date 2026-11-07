"""calibrate.py and lint E023: a judge's rates are computed from its test split, never trusted.

    python3 tests/test_calibrate.py      (selfcheck.sh section 9 runs it)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent
SHARED = BUNDLE / "workspace" / "evals" / "scripts" / "shared"
sys.path.insert(0, str(SHARED))

import calibrate  # noqa: E402
import lint_evals  # noqa: E402

GATED = "suite: s\nlayer: L2\ndataset: DS-x-v1\nmodel: gpt-5\ntemperature: 0\nrepeats: 1\n" \
        "evaluators:\n  - judge:JDG-g-v1\ngates:\n  task_success_ci_lower: 0.8\n"


def judge(tmp: str, *, tp: int, fn: int, tn: int, fp: int, rates: str, verdict: str,
          predictions: bool = True, gated: bool = False) -> Path:
    """An eval root with one judge `JDG-g-v1` whose test split yields the given confusion."""
    root = Path(tmp) / "evals"
    j = root / "judges" / "g"
    (j / "labels").mkdir(parents=True)
    (root / "judges" / "JDG-g-v1.md").write_text("# JDG-g-v1\n\n## Judge\nJudge model: claude-x\n",
                                                encoding="utf-8")
    labels, preds, i = [], [], 0
    for human, said, n in (("fail", "fail", tp), ("fail", "pass", fn),
                           ("pass", "pass", tn), ("pass", "fail", fp)):
        for _ in range(n):
            i += 1
            labels.append({"case_id": f"EV-TASK-{i:03d}", "label": human, "annotator": "ANN-LN"})
            preds.append({"case_id": f"EV-TASK-{i:03d}", "judge": said})
    for split in ("dev", "test"):
        (j / "labels" / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in labels) + "\n", encoding="utf-8")
    if predictions:
        (j / "predictions").mkdir()
        (j / "predictions" / "test.jsonl").write_text(
            "\n".join(json.dumps(r) for r in preds) + "\n", encoding="utf-8")
    heads = "".join(f"## {h}\nx\n\n" for h in ("Judge", "Labels", "Confusion", "Disagreements", "Correction"))
    (j / "validation.md").write_text(f"{heads}## Rates\n{rates}\n\n## Verdict\n{verdict}\n",
                                     encoding="utf-8")
    if gated:
        (root / "suites").mkdir()
        (root / "suites" / "s.yaml").write_text(GATED, encoding="utf-8")
    return root


def e023(root: Path) -> list[str]:
    return [f.message for f in lint_evals.Linter(root).run() if f.code == "E023"]


class Computed(unittest.TestCase):
    def test_rates_and_verdict_come_from_the_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2, rates="", verdict="VALIDATED")
            cal = calibrate.compute(root, "JDG-g-v1")
            self.assertIsNone(cal.problem)
            self.assertAlmostEqual(cal.confusion.tpr, 0.9)
            self.assertAlmostEqual(cal.confusion.tnr, 0.95)
            self.assertEqual(cal.verdict, "VALIDATED")
            self.assertEqual(len(cal.disagreements), 6)

    def test_a_missing_prediction_is_a_problem_not_a_smaller_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2, rates="", verdict="VALIDATED")
            p = root / "judges" / "g" / "predictions" / "test.jsonl"
            p.write_text("\n".join(p.read_text(encoding="utf-8").splitlines()[1:]) + "\n", encoding="utf-8")
            self.assertIn("no judge verdict", calibrate.compute(root, "JDG-g-v1").problem)


class LintE023(unittest.TestCase):
    def test_honest_numbers_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2,
                         rates="TPR 0.900 · TNR 0.950 · kappa 0.850", verdict="VALIDATED")
            self.assertEqual(e023(root), [])

    def test_inflated_rates_are_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2,
                         rates="TPR 0.950 · TNR 0.950 · kappa 0.850", verdict="VALIDATED")
            self.assertTrue(any("TPR stated 0.950, computed 0.900" in m for m in e023(root)))

    def test_rounding_is_not_a_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            # kappa computes to 0.85; 0.851 is within the third-decimal rounding a writer may apply.
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2,
                         rates="TPR 0.9 · TNR 0.950 · kappa 0.851", verdict="VALIDATED")
            self.assertEqual(e023(root), [])

    def test_a_validated_verdict_the_numbers_do_not_support_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            # TPR 0.7 is below the 0.80 threshold, but the file still says VALIDATED.
            root = judge(tmp, tp=28, fn=12, tn=38, fp=2,
                         rates="TPR 0.700 · TNR 0.950", verdict="VALIDATED")
            self.assertTrue(any("verdict stated VALIDATED, computed UNVALIDATED" in m for m in e023(root)))

    def test_a_gating_judge_without_predictions_cannot_be_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2, rates="TPR 0.900 · TNR 0.950",
                         verdict="VALIDATED", predictions=False, gated=True)
            self.assertTrue(any("cannot be recomputed" in m for m in e023(root)))

    def test_an_exploratory_judge_without_predictions_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = judge(tmp, tp=36, fn=4, tn=38, fp=2, rates="TPR 0.900 · TNR 0.950",
                         verdict="VALIDATED", predictions=False)
            self.assertEqual(e023(root), [])


if __name__ == "__main__":
    unittest.main()
