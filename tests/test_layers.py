"""lint E024: a layer EVAL-PROFILE §Risk tier makes mandatory may not be disabled in §Layers.

    python3 tests/test_layers.py      (selfcheck.sh section 9 runs it)

Every profile here is the shipped EVAL-PROFILE.md with its Tier line and §Layers rows edited, so
the check is tested against the format a project actually fills in.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent
SHARED = BUNDLE / "workspace" / "evals" / "scripts" / "shared"
sys.path.insert(0, str(SHARED))

import lint_evals  # noqa: E402

TEMPLATE = (BUNDLE / "EVAL-PROFILE.md").read_text(encoding="utf-8")
ALL = ("L0", "L1", "L2", "L3", "L4", "L5", "L6")


def profile(tier: str | None, enabled: tuple[str, ...]) -> str:
    """The shipped profile with `tier` chosen (None keeps the placeholder) and exactly `enabled` on."""
    text = TEMPLATE
    if tier:
        text = re.sub(r"^- \*\*Tier:\*\*.*$", f"- **Tier:** `{tier}`", text, count=1, flags=re.M)
    for layer in ALL:
        text = re.sub(rf"^(\| `{layer}` [^|]*\| )(yes|no)( \|)",
                      lambda m, on=layer in enabled: m.group(1) + ("yes" if on else "no") + m.group(3),
                      text, count=1, flags=re.M)
    return text


def project(tmp: str, text: str, where: str = ".claude/EVAL-PROFILE.md") -> Path:
    """An empty eval root `.evals/` whose project holds `text` as its profile at `where`."""
    base = Path(tmp)
    (base / ".evals").mkdir()
    (base / where).parent.mkdir(parents=True, exist_ok=True)
    (base / where).write_text(text, encoding="utf-8")
    return base / ".evals"


def e024(root: Path) -> list[str]:
    return [f.message for f in lint_evals.Linter(root).run() if f.code == "E024"]


class MandatoryLayers(unittest.TestCase):
    def test_the_template_edits_hold(self):
        # Guards the helper: if the template's rows stop matching, every other test is vacuous.
        text = profile("high", ("L0", "L4"))
        self.assertIn("- **Tier:** `high`", text)
        self.assertEqual(lint_evals._enabled_layers(lint_evals._section(text, "## Layers")), {"L0", "L4"})

    def test_a_disabled_mandatory_layer_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp, profile("medium", ("L0", "L1", "L2", "L3")))
            found = e024(root)
            self.assertEqual(len(found), 1, found)
            self.assertIn("L4 is mandatory for risk tier 'medium'", found[0])

    def test_each_disabled_mandatory_layer_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp, profile("high", ("L0", "L1", "L2", "L3", "L4")))
            self.assertEqual([m.split()[0] for m in e024(root)], ["L5", "L6"])

    def test_a_layer_the_tier_leaves_optional_may_be_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            # low makes L0-L2 mandatory; L3-L6 off is a choice, not a gap.
            root = project(tmp, profile("low", ("L0", "L1", "L2")))
            self.assertEqual(e024(root), [])

    def test_every_mandatory_layer_on_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp, profile("high", ALL))
            self.assertEqual(e024(root), [])

    def test_the_profile_at_the_project_root_is_read_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp, profile("medium", ("L0", "L1", "L2")), where="EVAL-PROFILE.md")
            self.assertEqual([m.split()[0] for m in e024(root)], ["L3", "L4"])

    def test_a_tier_left_at_its_placeholder_makes_nothing_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp, profile(None, ("L0",)))
            self.assertEqual(e024(root), [])

    def test_a_tier_with_no_mapping_row_cannot_be_decided(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = re.sub(r"^\| `medium` .*\n", "", profile("medium", ALL), flags=re.M)
            self.assertTrue(any("cannot be decided" in m for m in e024(project(tmp, text))))

    def test_the_mapping_is_read_from_the_profile_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A team that makes L5 mandatory for low is held to its own table.
            text = re.sub(r"^(\| `low` .*\| )L0 L1 L2( \|)$", r"\1L0 L1 L2 L5\2",
                          profile("low", ("L0", "L1", "L2")), count=1, flags=re.M)
            self.assertEqual([m.split()[0] for m in e024(project(tmp, text))], ["L5"])


if __name__ == "__main__":
    unittest.main()
