import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import skill_portfolio as PORTFOLIO  # noqa: E402


class SkillPortfolioCatalogLoadingTests(unittest.TestCase):
    def write_skill(self, root: Path, name: str, description: str, body: str) -> None:
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

    def test_load_skill_catalog_bundle_supports_multiple_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            public_root = root / "public"
            private_root = root / "private"

            self.write_skill(
                public_root,
                "deploy",
                "Deploy containers and inspect health checks.",
                """
# Deploy

Run deploys and inspect health checks.
""",
            )
            self.write_skill(
                public_root,
                "ask-cascade",
                "Ask dependency-aware questions.",
                """
# Ask Cascade

Order user questions from high-level to detailed.
""",
            )
            self.write_skill(
                private_root,
                "receipts",
                "Process receipt PDFs and transaction attachments.",
                """
# Receipts

Handle OCR and attachments for receipts.
""",
            )
            self.write_skill(
                private_root,
                "deploy",
                "Private duplicate deploy variant that should be shadowed by the first root.",
                """
# Deploy

This duplicate should not be loaded because the public root already defined it.
""",
            )

            bundle = PORTFOLIO.load_skill_catalog_bundle(skills_root=[public_root, private_root])

            self.assertEqual(
                bundle["catalog_roots"],
                [str(public_root.resolve()), str(private_root.resolve())],
            )
            self.assertEqual(bundle["skills_root"], str(public_root.resolve()))
            self.assertEqual([skill["name"] for skill in bundle["catalog"]], ["ask-cascade", "deploy", "receipts"])
            self.assertEqual(
                {skill["name"]: skill["catalog_root"] for skill in bundle["catalog"]},
                {
                    "ask-cascade": str(public_root.resolve()),
                    "deploy": str(public_root.resolve()),
                    "receipts": str(private_root.resolve()),
                },
            )
            self.assertEqual(
                bundle["catalog_root_details"],
                [
                    {
                        "root": str(public_root.resolve()),
                        "skills_loaded": 2,
                        "duplicates_skipped": 0,
                        "invalid_skills_skipped": 0,
                    },
                    {
                        "root": str(private_root.resolve()),
                        "skills_loaded": 1,
                        "duplicates_skipped": 1,
                        "invalid_skills_skipped": 0,
                    },
                ],
            )
            self.assertEqual(len(bundle["duplicate_skills_skipped"]), 1)
            self.assertEqual(bundle["duplicate_skills_skipped"][0]["name"], "deploy")
            self.assertEqual(
                bundle["duplicate_skills_skipped"][0]["conflicting_aliases"],
                ["deploy"],
            )

    def test_load_skill_catalog_preserves_single_root_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "skills"
            self.write_skill(
                root,
                "describe",
                "Turn work into pass/fail test cases.",
                """
# Describe

Define done before patching.
""",
            )

            catalog = PORTFOLIO.load_skill_catalog(skills_root=root)

            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0]["name"], "describe")
            self.assertEqual(catalog[0]["catalog_root"], str(root.resolve()))

    def test_load_skill_catalog_skips_invalid_required_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "skills"
            self.write_skill(
                root,
                "valid-skill",
                "Use valid skills when checking catalog description filtering.",
                "# Valid Skill",
            )
            cases = {
                "empty-description": 'description: ""',
                "whitespace-description": 'description: "   "',
                "number-description": "description: 123",
            }
            for name, description_line in cases.items():
                skill_dir = root / name
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(
                    "\n".join(
                        [
                            "---",
                            f"name: {name}",
                            description_line,
                            "---",
                            "",
                            f"# {name}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            invalid_name_cases = {
                "empty-name": 'name: ""',
                "number-name": "name: 123",
                "mismatch-name": "name: other-name",
            }
            for dirname, name_line in invalid_name_cases.items():
                skill_dir = root / dirname
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(
                    "\n".join(
                        [
                            "---",
                            name_line,
                            "description: Use valid descriptions when checking catalog name filtering.",
                            "---",
                            "",
                            f"# {dirname}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            bundle = PORTFOLIO.load_skill_catalog_bundle(skills_root=root)

            self.assertEqual([skill["name"] for skill in bundle["catalog"]], ["valid-skill"])
            self.assertEqual(
                sorted(Path(skill["path"]).parent.name for skill in bundle["invalid_skills_skipped"]),
                [
                    "empty-description",
                    "empty-name",
                    "mismatch-name",
                    "number-description",
                    "number-name",
                    "whitespace-description",
                ],
            )
            self.assertEqual(bundle["catalog_root_details"][0]["invalid_skills_skipped"], 6)

    def test_load_skill_catalog_skips_validator_invalid_frontmatter_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "skills"
            self.write_skill(
                root,
                "valid-skill",
                "Use valid skills when checking catalog frontmatter validation.",
                "# Valid Skill",
            )
            cases = {
                "unexpected-key": [
                    "name: unexpected-key",
                    "description: Use descriptions with supported frontmatter keys only.",
                    "extra: value",
                ],
                "depends-on-string": [
                    "name: depends-on-string",
                    "description: Use depends_on lists when declaring skill dependencies.",
                    "depends_on: describe",
                ],
                "depends-on-non-string": [
                    "name: depends-on-non-string",
                    "description: Use depends_on lists containing skill id strings only.",
                    "depends_on:",
                    "  - describe",
                    "  - 123",
                ],
            }
            for name, frontmatter_lines in cases.items():
                skill_dir = root / name
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(
                    "\n".join(
                        [
                            "---",
                            *frontmatter_lines,
                            "---",
                            "",
                            f"# {name}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            bundle = PORTFOLIO.load_skill_catalog_bundle(skills_root=root)

            self.assertEqual([skill["name"] for skill in bundle["catalog"]], ["valid-skill"])
            self.assertEqual(
                sorted(Path(skill["path"]).parent.name for skill in bundle["invalid_skills_skipped"]),
                ["depends-on-non-string", "depends-on-string", "unexpected-key"],
            )
            reasons = {
                Path(skill["path"]).parent.name: skill["reason"]
                for skill in bundle["invalid_skills_skipped"]
            }
            self.assertEqual(reasons["unexpected-key"], "unexpected frontmatter keys: extra")
            self.assertEqual(
                reasons["depends-on-string"],
                "depends_on must be a YAML list of skill id strings",
            )
            self.assertEqual(
                reasons["depends-on-non-string"],
                "depends_on must be a YAML list of skill id strings",
            )
            self.assertEqual(bundle["catalog_root_details"][0]["invalid_skills_skipped"], 3)

    def test_load_skill_catalog_skips_invalid_frontmatter_format_and_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "skills"
            self.write_skill(
                root,
                "valid-skill",
                "Use valid skills when checking catalog frontmatter parsing.",
                "# Valid Skill",
            )
            cases = {
                "leading-whitespace": [
                    "",
                    "---",
                    "name: leading-whitespace",
                    "description: Use frontmatter at the start of the skill file.",
                    "---",
                    "",
                    "# Leading Whitespace",
                ],
                "invalid-yaml": [
                    "---",
                    "name: [",
                    "description: Use valid YAML frontmatter for skill metadata.",
                    "---",
                    "",
                    "# Invalid YAML",
                ],
                "list-frontmatter": [
                    "---",
                    "- name",
                    "- description",
                    "---",
                    "",
                    "# List Frontmatter",
                ],
                "closing-delimiter-suffix": [
                    "---",
                    "name: closing-delimiter-suffix",
                    "description: Use exact frontmatter delimiter lines for skill metadata.",
                    "---not-a-delimiter",
                    "",
                    "# Closing Delimiter Suffix",
                ],
            }
            for name, lines in cases.items():
                skill_dir = root / name
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

            bundle = PORTFOLIO.load_skill_catalog_bundle(skills_root=root)

            self.assertEqual([skill["name"] for skill in bundle["catalog"]], ["valid-skill"])
            reasons = {
                Path(skill["path"]).parent.name: skill["reason"]
                for skill in bundle["invalid_skills_skipped"]
            }
            self.assertEqual(reasons["leading-whitespace"], "No YAML frontmatter found")
            self.assertIn("Invalid YAML in frontmatter", reasons["invalid-yaml"])
            self.assertEqual(reasons["list-frontmatter"], "Frontmatter must be a YAML dictionary")
            self.assertEqual(reasons["closing-delimiter-suffix"], "Invalid frontmatter format")
            self.assertEqual(bundle["catalog_root_details"][0]["invalid_skills_skipped"], 4)

    def test_load_skill_catalog_parses_folded_yaml_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "skills"
            skill_dir = root / "folded-description"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: folded-description",
                        "description: >-",
                        "  Use folded YAML descriptions when the trigger surface",
                        "  needs to stay readable across multiple frontmatter lines.",
                        "---",
                        "",
                        "# Folded Description",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            catalog = PORTFOLIO.load_skill_catalog(skills_root=root)

            self.assertEqual(len(catalog), 1)
            self.assertEqual(
                catalog[0]["description"],
                "Use folded YAML descriptions when the trigger surface needs to stay readable across multiple frontmatter lines.",
            )


if __name__ == "__main__":
    unittest.main()
