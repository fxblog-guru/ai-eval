"""settings.json grants the least the bundle needs: a real deny list, and no allow rule that runs
arbitrary code.

    python3 tests/test_settings.py      (selfcheck.sh section 9 runs it)
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / "settings.json"

# The destructive or secret-reading actions that must stay denied however `allow` grows.
REQUIRED_DENY = [
    "Bash(git push --force*)", "Bash(git push -f*)",
    "Bash(rm -rf /*)", "Bash(rm -rf ~*)",
    "Bash(git commit --no-verify*)", "Bash(git push --no-verify*)",
    "Bash(git reset --hard origin/*)",
    "Read(.env)", "Read(**/.env)", "Write(**/.env)", "Edit(**/.env)",
]
# An interpreter given code on the command line (`python3 -c`, `node -e`, `bash -c`, `eval`) can do
# anything a deny rule forbids, so allowing it would void the whole list.
CODE_FLAG = re.compile(r"^Bash\((?:python3?|py|node|deno|bun|ruby|perl|php|bash|sh|zsh|pwsh|powershell)"
                       r"(?:\.exe)?\s+(?:-[A-Za-z]*[ceE]\b|--eval|--command|-Command)|^Bash\((?:eval|exec)\b|^Bash\(\*?\)$")


def problems(doc: dict) -> list[str]:
    perms = doc.get("permissions") or {}
    deny, allow = perms.get("deny") or [], perms.get("allow") or []
    out = [] if deny else ["deny list is empty"]
    out += [f"deny lacks {r}" for r in REQUIRED_DENY if r not in deny]
    out += [f"allow runs arbitrary code: {r}" for r in allow if CODE_FLAG.search(r)]
    return out


class LeastPrivilege(unittest.TestCase):
    def test_the_shipped_settings_hold(self):
        self.assertEqual(problems(json.loads(SETTINGS.read_text(encoding="utf-8"))), [])

    def test_the_check_fails_on_the_old_settings(self):
        # The 1.1.0 shape: blanket deny-nothing plus an inline-code allow. Both must be reported.
        old = {"permissions": {"allow": ["Write", "Bash(python3 -c *)"], "deny": []}}
        found = problems(old)
        self.assertIn("deny list is empty", found)
        self.assertTrue(any("python3 -c" in p for p in found))

    def test_other_interpreters_are_caught_too(self):
        for rule in ("Bash(node -e *)", "Bash(bash -c *)", "Bash(python -c*)", "Bash(eval *)",
                     "Bash(pwsh -Command *)", "Bash(*)"):
            doc = {"permissions": {"allow": [rule], "deny": REQUIRED_DENY}}
            self.assertTrue(problems(doc), rule)

    def test_script_paths_are_not_mistaken_for_inline_code(self):
        doc = {"permissions": {"allow": ["Bash(python3 evals/scripts/shared/runner.py*)"],
                               "deny": REQUIRED_DENY}}
        self.assertEqual(problems(doc), [])


if __name__ == "__main__":
    sys.exit(unittest.main())
