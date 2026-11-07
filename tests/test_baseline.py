"""baseline.py: a revert restores the prior baseline, and no baseline file is ever overwritten.

    python3 tests/test_baseline.py      (selfcheck.sh section 9 runs it)
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "workspace" / "evals" / "scripts" / "shared"))

import baseline  # noqa: E402


def root_with(tmp: str, *ids: str) -> Path:
    root = Path(tmp)
    (root / "suites").mkdir()
    (root / "baselines").mkdir()
    (root / "suites" / "s.yaml").write_text("suite: s\nbaseline: BASE-a\n", encoding="utf-8")
    for i in ids:
        (root / "baselines" / f"{i}.json").write_text(json.dumps({"id": i}), encoding="utf-8")
    return root


class PromoteAndRevert(unittest.TestCase):
    def test_a_revert_restores_the_prior_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = root_with(tmp, "BASE-a", "BASE-b")
            before = {p.name: p.read_bytes() for p in (root / "baselines").glob("*.json")}
            baseline.promote(root, "s", "BASE-b", "new model")
            self.assertEqual(baseline.current(root, "s"), "BASE-b")
            baseline.revert(root, "s", "gate result was wrong")
            self.assertEqual(baseline.current(root, "s"), "BASE-a")
            self.assertEqual({p.name: p.read_bytes() for p in (root / "baselines").glob("*.json")},
                             before, "baseline files are frozen")
            self.assertEqual([h["action"] for h in baseline.history(root, "s")], ["promote", "revert"])

    def test_two_promotes_then_one_revert_goes_back_one_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = root_with(tmp, "BASE-a", "BASE-b", "BASE-c")
            baseline.promote(root, "s", "BASE-b")
            baseline.promote(root, "s", "BASE-c")
            baseline.revert(root, "s")
            self.assertEqual(baseline.current(root, "s"), "BASE-b")

    def test_nothing_to_revert_to_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = root_with(tmp, "BASE-a")
            with self.assertRaises(ValueError):
                baseline.revert(root, "s")
            self.assertEqual(baseline.current(root, "s"), "BASE-a")

    def test_promoting_a_baseline_that_was_never_frozen_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = root_with(tmp, "BASE-a")
            with self.assertRaises(ValueError):
                baseline.promote(root, "s", "BASE-missing")


if __name__ == "__main__":
    unittest.main()
