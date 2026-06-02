import json
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
CHECK_DEPS = SCRIPTS_DIR / "check_skill_deps.py"
RISK_MODULE = SourceFileLoader(
    "skill_risk_classifier_behavior",
    str((SCRIPTS_DIR / "skill_risk_classifier.py").resolve()),
).load_module()


class FrontmatterDependentToolTests(unittest.TestCase):
    def test_check_skill_deps_reads_depends_on_with_closing_delimiter_at_eof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            dependent = root / "dependent"
            source.mkdir()
            dependent.mkdir()
            (source / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: source",
                        "description: Use source skills when testing dependency scans.",
                        "---",
                    ]
                ),
                encoding="utf-8",
            )
            (dependent / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: dependent",
                        "description: Use dependent skills when testing dependency scans.",
                        "depends_on:",
                        "  - source",
                        "---",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_DEPS),
                    "--changed-skill",
                    "source",
                    "--roots",
                    str(root),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["dependents"], ["dependent"])

    def test_check_skill_deps_reads_yaml_flow_depends_on_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            dependent = root / "dependent"
            source.mkdir()
            dependent.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: source\ndescription: Use source skills when testing dependency scans.\n---\n",
                encoding="utf-8",
            )
            (dependent / "SKILL.md").write_text(
                "---\n"
                "name: dependent\n"
                "description: Use dependent skills when testing dependency scans.\n"
                'depends_on: ["source"]\n'
                "---\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_DEPS),
                    "--changed-skill",
                    "source",
                    "--roots",
                    str(root),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["dependents"], ["dependent"])

    def test_check_skill_deps_ignores_scalar_depends_on_rejected_by_validator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            dependent = root / "dependent"
            source.mkdir()
            dependent.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: source\ndescription: Use source skills when testing dependency scans.\n---\n",
                encoding="utf-8",
            )
            (dependent / "SKILL.md").write_text(
                "---\n"
                "name: dependent\n"
                "description: Use dependent skills when testing dependency scans.\n"
                "depends_on: source\n"
                "---\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_DEPS),
                    "--changed-skill",
                    "source",
                    "--roots",
                    str(root),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["dependents"], [])

    def test_check_skill_deps_ignores_malformed_depends_on_entries_rejected_by_validator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            dependent = root / "dependent"
            source.mkdir()
            dependent.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: source\ndescription: Use source skills when testing dependency scans.\n---\n",
                encoding="utf-8",
            )
            (dependent / "SKILL.md").write_text(
                "---\n"
                "name: dependent\n"
                "description: Use dependent skills when testing dependency scans.\n"
                "depends_on:\n"
                '  - " source "\n'
                "---\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_DEPS),
                    "--changed-skill",
                    "source",
                    "--roots",
                    str(root),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["dependents"], [])

    def test_check_skill_deps_rejects_closing_delimiter_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            dependent = root / "dependent"
            source.mkdir()
            dependent.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: source\ndescription: Use source skills when testing dependency scans.\n---\n",
                encoding="utf-8",
            )
            (dependent / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: dependent",
                        "description: Use dependent skills when testing dependency scans.",
                        "depends_on:",
                        "  - source",
                        "---not-a-delimiter",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_DEPS),
                    "--changed-skill",
                    "source",
                    "--roots",
                    str(root),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["dependents"], [])

    def test_risk_classifier_reads_frontmatter_with_closing_delimiter_at_eof(self) -> None:
        old = "\n".join(
            [
                "---",
                "name: sample-skill",
                "description: Use sample skills when testing risk classification.",
                "---",
            ]
        )
        new = old.replace(
            "Use sample skills when testing risk classification.",
            "Use changed sample skills when testing risk classification.",
        )

        tier, reasons = RISK_MODULE.classify(old, new)

        self.assertEqual(tier, "medium")
        self.assertEqual(reasons, ["description field (trigger surface) changed"])

    def test_risk_classifier_reads_folded_yaml_description_changes(self) -> None:
        old = "\n".join(
            [
                "---",
                "name: sample-skill",
                "description: >-",
                "  Use sample skills when testing",
                "  risk classification.",
                "---",
            ]
        )
        new = old.replace(
            "risk classification.",
            "changed risk classification.",
        )

        tier, reasons = RISK_MODULE.classify(old, new)

        self.assertEqual(tier, "medium")
        self.assertEqual(reasons, ["description field (trigger surface) changed"])

    def test_risk_classifier_reads_yaml_allowed_tools_list_changes(self) -> None:
        old = "\n".join(
            [
                "---",
                "name: sample-skill",
                "description: Use sample skills when testing risk classification.",
                "allowed-tools:",
                "  - Read",
                "---",
            ]
        )
        new = old.replace("  - Read", "  - Read\n  - Bash")

        tier, reasons = RISK_MODULE.classify(old, new)

        self.assertEqual(tier, "high")
        self.assertEqual(reasons, ["allowed-tools frontmatter changed"])


if __name__ == "__main__":
    unittest.main()
