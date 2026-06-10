import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

VALIDATE_MODULE = SourceFileLoader(
    "quick_validate_behavior",
    str((SCRIPTS_DIR / "quick_validate.py").resolve()),
).load_module()
INIT_MODULE = SourceFileLoader(
    "init_skill_behavior",
    str((SCRIPTS_DIR / "init_skill.py").resolve()),
).load_module()


class QuickValidateBehaviorContractTests(unittest.TestCase):
    def write_skill(self, root: Path, name: str, description: str, body: str) -> Path:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    f"name: {name}",
                    f'description: "{description}"',
                    "---",
                    "",
                    body.strip(),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return skill_dir

    def test_non_analysis_skill_is_not_forced_into_analysis_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "sample-skill",
                "Package a sample skill for tests and use when validating gitignored bundle safety.",
                "# Sample Skill",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertTrue(valid)
        self.assertEqual(message, "Skill is valid!")

    def test_depends_on_frontmatter_list_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "sample-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: sample-skill",
                        'description: "Package a sample skill for tests and validate dependency metadata."',
                        "depends_on:",
                        "  - mmdx",
                        "---",
                        "",
                        "# Sample Skill",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertTrue(valid)
        self.assertEqual(message, "Skill is valid!")

    def test_depends_on_entries_must_be_skill_ids(self) -> None:
        cases = {
            "empty": '  - ""',
            "whitespace": '  - " mmdx "',
            "underscore": "  - bad_id",
            "consecutive-hyphen": "  - bad--id",
        }
        for label, dep_line in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                skill_dir = Path(tmpdir) / "sample-skill"
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(
                    "\n".join(
                        [
                            "---",
                            "name: sample-skill",
                            'description: "Package a sample skill for tests and validate dependency metadata."',
                            "depends_on:",
                            dep_line,
                            "---",
                            "",
                            "# Sample Skill",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

            self.assertFalse(valid)
            self.assertEqual(message, "'depends_on' entries must be non-empty hyphen-case skill id strings")

    def test_empty_frontmatter_name_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "empty-name"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        'name: ""',
                        'description: "Package a sample skill for tests and use when validating empty name safety."',
                        "---",
                        "",
                        "# Empty Name",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertEqual(message, "Missing or empty 'name' in frontmatter")

    def test_frontmatter_name_must_match_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "directory-name",
                "Package a sample skill for tests and use when validating name mismatch safety.",
                "# Directory Name",
            )
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8").replace("name: directory-name", "name: other-name"),
                encoding="utf-8",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertEqual(message, "Name 'other-name' must match skill directory name 'directory-name'")

    def test_empty_frontmatter_description_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "empty-description"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: empty-description",
                        'description: ""',
                        "---",
                        "",
                        "# Empty Description",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertEqual(message, "Missing or empty 'description' in frontmatter")

    def test_malformed_frontmatter_closing_delimiter_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "sample-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: sample-skill",
                        'description: "Package a sample skill for tests and validate delimiter safety."',
                        "---not-a-delimiter",
                        "",
                        "# Sample Skill",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertEqual(message, "Invalid frontmatter format")

    def test_minimal_scaffold_todo_placeholders_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "todo-skill",
                "TODO - describe what this skill does and when to use it",
                """
# Todo Skill

TODO: Add instructions here.
""",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertEqual(message, "Description contains TODO placeholder text")

    def test_default_scaffold_todo_description_is_valid_yaml_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = INIT_MODULE.init_skill("todo-skill", tmpdir)
            self.assertIsNotNone(skill_dir)

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertEqual(message, "Description contains TODO placeholder text")

    def test_body_todo_placeholder_lines_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "todo-skill",
                "Package a sample skill for tests and use when validating placeholder safety.",
                """
# Todo Skill

TODO: Add instructions here.
""",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertIn("Incomplete skill: found TODO marker(s): TODO: Add instructions here.", message)

    def test_machine_readable_final_todo_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "sample-skill",
                "Package a sample skill for tests and use when validating placeholder safety.",
                """
# Sample Skill

Keep the final line machine-readable and unique: `FINAL_TODO: <value>`.
""",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertTrue(valid)
        self.assertEqual(message, "Skill is valid!")

    def test_analysis_skill_requires_stable_marker_and_verification_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "smart",
                "Ask the single most accretive question about the current project/conversation.",
                """
# Smart

This is analysis-only text with no stable marker or verification section.
""",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertIn("Missing stable first progress marker", message)
        self.assertIn("Missing explicit verification/closeout contract", message)

    def test_prerequisite_degraded_mode_guidance_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "cass",
                "Mine past agent sessions for working prompts, decisions, and patterns.",
                """
# cass

`Using cass` starts the workflow.

## Validation

```bash
cass status --json
```

This skill depends on cass search and cass index for history access.
""",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertFalse(valid)
        self.assertIn("Missing degraded-mode guidance", message)

    def test_analysis_skill_with_contracts_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "divide-and-conquer",
                "Decompose complex work into an executable WORKGRAPH.md, then run an NTM-style swarm by ready frontier with no write overlap.",
                """
# Divide and Conquer

`Using divide-and-conquer` to build the ready frontier.

If ntm is missing or broken, stop and surface the prerequisite gap.

## Validation

The orchestrator must independently run each node's `validate_cmds` and do not mark a node done until that passes.

```bash
python3 scripts/workgraph_ready.py --file "$WORKGRAPH"
ntm deps -v
```
""",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

        self.assertTrue(valid)
        self.assertEqual(message, "Skill is valid!")


class ValidateSkillEdgeCaseTests(unittest.TestCase):
    def _write_skill(self, root: Path, name: str, description: str, body: str = "# Skill\n") -> Path:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: \"{description}\"\n---\n\n{body}\n",
            encoding="utf-8",
        )
        return skill_dir

    def test_missing_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "no-skill"
            skill_dir.mkdir()
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertEqual(message, "SKILL.md not found")

    def test_no_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "no-fm"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# No frontmatter\n", encoding="utf-8")
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertEqual(message, "No YAML frontmatter found")

    def test_description_with_angle_brackets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self._write_skill(
                Path(tmpdir), "bracket-test",
                "Skill with <angle> brackets should fail validation cleanly."
            )
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertIn("angle brackets", message)

    def test_description_too_long(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = "A" * 1025
            skill_dir = self._write_skill(Path(tmpdir), "long-desc", desc)
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertIn("too long", message)

    def test_name_too_long(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            name = "a" * 65
            skill_dir = Path(tmpdir) / name
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: \"A valid description that is long enough for the validator to accept.\"\n---\n\n# Skill\n",
                encoding="utf-8",
            )
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertIn("too long", message)

    def test_unexpected_frontmatter_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "bad-key"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                '---\nname: bad-key\ndescription: "A valid description that is long enough for validation."\nfoo: bar\n---\n\n# Skill\n',
                encoding="utf-8",
            )
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertIn("Unexpected key", message)

    def test_strict_mode_fails_on_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = "Short desc but just over fifty chars for the validator."
            skill_dir = self._write_skill(Path(tmpdir), "strict-test", desc)
            (skill_dir / "scripts").mkdir()
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir, strict=True)
        self.assertFalse(valid)
        self.assertIn("Strict mode", message)

    def test_short_description_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self._write_skill(Path(tmpdir), "short-desc", "A short description under fifty.")
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertTrue(valid)
        self.assertIn("short", message.lower())

    def test_empty_resource_dir_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = "A valid description that is long enough for the validator to accept."
            skill_dir = self._write_skill(Path(tmpdir), "empty-dirs", desc)
            (skill_dir / "scripts").mkdir()
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertTrue(valid)
        self.assertIn("Empty directory", message)

    def test_privacy_ip_address_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = "A valid description that is long enough for the validator to accept."
            skill_dir = self._write_skill(Path(tmpdir), "ip-test", desc)
            refs = skill_dir / "references"
            refs.mkdir()
            (refs / "notes.md").write_text("Connect to 192.168.1.100 for testing.\n", encoding="utf-8")
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertTrue(valid)
        self.assertIn("Privacy", message)
        self.assertIn("IP address", message)

    def test_privacy_hardcoded_path_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = "A valid description that is long enough for the validator to accept."
            skill_dir = self._write_skill(Path(tmpdir), "path-test", desc)
            refs = skill_dir / "references"
            refs.mkdir()
            (refs / "notes.md").write_text("See /Users/admin/project for details.\n", encoding="utf-8")
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertTrue(valid)
        self.assertIn("Hardcoded user path", message)

    def test_long_skill_md_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = "A valid description that is long enough for the validator to accept."
            body = "\n".join([f"Line {i}" for i in range(501)])
            skill_dir = self._write_skill(Path(tmpdir), "long-md", desc, body)
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertTrue(valid)
        self.assertIn("lines", message)

    def test_name_with_consecutive_hyphens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            name = "bad--name"
            skill_dir = Path(tmpdir) / name
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f'---\nname: {name}\ndescription: "A valid description that is long enough."\n---\n\n# Skill\n',
                encoding="utf-8",
            )
            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)
        self.assertFalse(valid)
        self.assertIn("consecutive hyphens", message)


if __name__ == "__main__":
    unittest.main()
