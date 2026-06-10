import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock


MODULE = SourceFileLoader(
    "skill_risk_classifier",
    str((Path(__file__).resolve().parent.parent / "scripts" / "skill_risk_classifier.py").resolve()),
).load_module()

OLD_SKILL = """\
---
name: sample-skill
description: "A sample skill for testing risk classification changes."
allowed-tools:
  - Read
  - Write
---

# Sample Skill

This is a sample skill body with prose and examples.
"""


class ClassifyTests(unittest.TestCase):
    def test_prose_only_is_low(self) -> None:
        new = OLD_SKILL.replace("prose and examples", "prose, examples, and more detail")
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "low")
        self.assertIn("prose/examples only", reasons)

    def test_deps_drift_is_high(self) -> None:
        tier, reasons = MODULE.classify(OLD_SKILL, OLD_SKILL, deps_drift=True)
        self.assertEqual(tier, "high")
        self.assertIn("cross-skill dependency", reasons[0])

    def test_allowed_tools_changed_is_high(self) -> None:
        new = OLD_SKILL.replace("  - Write", "  - Write\n  - Bash")
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "high")
        self.assertIn("allowed-tools", reasons[0])

    def test_destructive_command_is_high(self) -> None:
        new = OLD_SKILL + "\n```bash\nrm -rf /tmp/build\n```\n"
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "high")
        self.assertIn("destructive", reasons[0])

    def test_safety_marker_is_high(self) -> None:
        new = OLD_SKILL + "\n## Safety\n\nThis guardrail prevents accidents.\n"
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "high")
        self.assertIn("safety", reasons[0])

    def test_description_changed_is_medium(self) -> None:
        new = OLD_SKILL.replace("A sample skill", "A modified skill")
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "medium")
        self.assertIn("description", reasons[0])

    def test_headers_changed_is_medium(self) -> None:
        new = OLD_SKILL.replace("# Sample Skill", "# Sample Skill\n\n## New Phase")
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "medium")
        self.assertIn("headers", reasons[0])

    def test_code_logic_changed_is_medium(self) -> None:
        new = OLD_SKILL + "\nresult = compute(x)\n"
        tier, reasons = MODULE.classify(OLD_SKILL, new)
        self.assertEqual(tier, "medium")
        self.assertIn("script/code logic", reasons[0])

    def test_no_frontmatter_is_low(self) -> None:
        old = "# Just a body\n\nSome text.\n"
        new = "# Just a body\n\nSome updated text.\n"
        tier, reasons = MODULE.classify(old, new)
        self.assertEqual(tier, "low")


class DepsDriftForTests(unittest.TestCase):
    def test_returns_false_when_script_missing(self) -> None:
        with mock.patch.object(Path, "is_file", return_value=False):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertFalse(result)

    def test_returns_false_on_timeout(self) -> None:
        import subprocess
        with mock.patch.object(MODULE.subprocess, "run", side_effect=subprocess.TimeoutExpired("cmd", 15)):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertFalse(result)

    def test_returns_false_on_bad_json(self) -> None:
        from types import SimpleNamespace
        with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="not json")):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertFalse(result)

    def test_returns_false_on_empty_stdout(self) -> None:
        from types import SimpleNamespace
        with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="")):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertFalse(result)

    def test_returns_true_when_drift_detected(self) -> None:
        from types import SimpleNamespace
        payload = json.dumps({"dependents": ["other-skill"], "interface_drift": True})
        with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=payload)):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertTrue(result)

    def test_returns_false_when_no_dependents(self) -> None:
        from types import SimpleNamespace
        payload = json.dumps({"dependents": [], "interface_drift": True})
        with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=payload)):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertFalse(result)

    def test_passes_roots_argument(self) -> None:
        from types import SimpleNamespace
        payload = json.dumps({"dependents": [], "interface_drift": False})
        with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=payload)) as run:
            MODULE._deps_drift_for("smart", "/old", "/new", roots=["/a", "/b"])
        args = run.call_args[0][0]
        self.assertIn("--roots", args)
        self.assertIn("/a", args)
        self.assertIn("/b", args)

    def test_returns_false_on_negative_returncode(self) -> None:
        from types import SimpleNamespace
        with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=-1, stdout='{"x":1}')):
            result = MODULE._deps_drift_for("smart", "/old", "/new")
        self.assertFalse(result)


class MainTests(unittest.TestCase):
    def test_main_json_output(self) -> None:
        import io
        import sys
        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = Path(tmpdir) / "old.md"
            new_file = Path(tmpdir) / "new.md"
            old_file.write_text(OLD_SKILL, encoding="utf-8")
            new_file.write_text(OLD_SKILL.replace("prose and examples", "updated prose"), encoding="utf-8")
            old_argv, old_stdout = sys.argv, sys.stdout
            sys.stdout = io.StringIO()
            try:
                sys.argv = ["skill_risk_classifier.py", "--old", str(old_file), "--new", str(new_file), "--json"]
                with self.assertRaises(SystemExit) as ctx:
                    MODULE.main()
                output = sys.stdout.getvalue()
            finally:
                sys.argv, sys.stdout = old_argv, old_stdout
            self.assertEqual(ctx.exception.code, 0)
            parsed = json.loads(output)
            self.assertEqual(parsed["tier"], "low")


if __name__ == "__main__":
    unittest.main()
