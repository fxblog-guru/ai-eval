"""The eval root resolver and the migration between `evals/` and `.evals/` (EVAL-CONTRACTS section 2).

    python3 tests/test_root.py      (selfcheck.sh runs it)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent
SHARED = BUNDLE / "workspace" / "evals" / "scripts" / "shared"
sys.path.insert(0, str(SHARED))
from root import profile_root, resolve_root  # noqa: E402

MIGRATE = SHARED / "migrate_root.py"


def project() -> Path:
    d = Path(tempfile.mkdtemp(prefix="eval-root-"))
    (d / ".claude").mkdir()
    return d


class Resolve(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop("EVAL_ROOT", None)

    def tearDown(self):
        if self._env is not None:
            os.environ["EVAL_ROOT"] = self._env

    def test_a_new_project_gets_dot_evals(self):
        self.assertEqual(resolve_root(project=project()).name, ".evals")

    def test_an_existing_evals_folder_keeps_working(self):
        p = project()
        (p / "evals").mkdir()
        self.assertEqual(resolve_root(project=p).name, "evals")

    def test_dot_evals_wins_when_both_exist(self):
        p = project()
        (p / "evals").mkdir()
        (p / ".evals").mkdir()
        self.assertEqual(resolve_root(project=p).name, ".evals")

    def test_explicit_then_env_then_profile(self):
        p = project()
        (p / "evals").mkdir()
        (p / ".claude" / "EVAL-PROFILE.md").write_text("- **Eval root:** `quality/evals` — mine\n", encoding="utf-8")
        self.assertEqual(resolve_root(project=p).as_posix(), (p / "quality/evals").as_posix())
        os.environ["EVAL_ROOT"] = "elsewhere"
        self.assertEqual(resolve_root(project=p).name, "elsewhere")
        self.assertEqual(str(resolve_root("given", project=p)), "given")

    def test_an_untouched_or_escaping_profile_line_is_not_a_choice(self):
        self.assertIsNone(profile_root("- **Eval root:** `.evals/` (default) — all artifacts"))
        self.assertIsNone(profile_root("- **Eval root:** `<folder>`"))
        p = project()
        (p / ".claude" / "EVAL-PROFILE.md").write_text("- **Eval root:** `../outside`\n", encoding="utf-8")
        self.assertEqual(resolve_root(project=p).name, ".evals")


def migrate(p: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MIGRATE), "--project", str(p), *args], capture_output=True, text=True)


class Migrate(unittest.TestCase):
    def legacy(self) -> Path:
        p = project()
        (p / "evals" / "suites").mkdir(parents=True)
        (p / "evals" / "suites" / "x.yaml").write_text("suite: x\n", encoding="utf-8")
        (p / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "if [ -f evals/scripts/shared/build_state.py ]; then python3 evals/scripts/shared/build_state.py --quiet; fi"}]}]},
            "permissions": {"allow": ["Bash(python3 .evals/scripts/shared/runner.py*)", "Bash(python3 evals/scripts/shared/runner.py*)", "Bash(my-evals/x)"]}}), encoding="utf-8")
        (p / ".gitignore").write_text("evals/runs/*/\n/evals/state.json\nnot-evals/\n", encoding="utf-8")
        (p / ".claude" / "EVAL-PROFILE.md").write_text("- **Eval root:** `evals/` (default) — all\n", encoding="utf-8")
        return p

    def test_dry_run_changes_nothing(self):
        p = self.legacy()
        r = migrate(p, "--to", ".evals")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((p / "evals" / "suites" / "x.yaml").exists())
        self.assertFalse((p / ".evals").exists())
        self.assertIn("evals/scripts", (p / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_write_moves_the_folder_and_rewires_only_root_paths(self):
        p = self.legacy()
        r = migrate(p, "--to", ".evals", "--write")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((p / ".evals" / "suites" / "x.yaml").exists())
        self.assertFalse((p / "evals").exists())
        s = (p / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn(" evals/", s)
        self.assertIn(".evals/scripts/shared/build_state.py", s)
        self.assertIn("my-evals/x", s, "a name that only contains evals is left alone")
        allow = json.loads(s)["permissions"]["allow"]
        self.assertEqual(len(allow), len(set(allow)), "no rule granted twice")
        gi = (p / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".evals/runs/*/", gi)
        self.assertIn("/.evals/state.json", gi)
        self.assertIn("not-evals/", gi)
        self.assertIn("`.evals/` (default)", (p / ".claude" / "EVAL-PROFILE.md").read_text(encoding="utf-8"))
        self.assertEqual(resolve_root(project=p).name, ".evals")

    def test_a_path_already_under_dot_evals_is_not_rewritten_twice(self):
        from migrate_root import rewire
        self.assertEqual(rewire("python3 .evals/x.py && python3 evals/x.py", "evals", ".evals"),
                         "python3 .evals/x.py && python3 .evals/x.py")
        self.assertEqual(rewire("a/evals/x my-evals/y", "evals", ".evals"), "a/evals/x my-evals/y")
        self.assertEqual(rewire("  EVAL_ROOT: evals\n--root evals --dry-run", "evals", ".evals"),
                         "  EVAL_ROOT: .evals\n--root .evals --dry-run")
        self.assertEqual(rewire("python3 .evals/x.py", ".evals", "evals"), "python3 evals/x.py")

    def test_refuses_when_the_target_exists_or_there_is_nothing_to_move(self):
        p = self.legacy()
        (p / ".evals").mkdir()
        self.assertEqual(migrate(p, "--to", ".evals", "--write").returncode, 1)
        self.assertEqual(migrate(project(), "--to", ".evals", "--write").returncode, 1)


if __name__ == "__main__":
    unittest.main()
