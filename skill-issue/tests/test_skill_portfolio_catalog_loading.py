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
                    {"root": str(public_root.resolve()), "skills_loaded": 2, "duplicates_skipped": 0},
                    {"root": str(private_root.resolve()), "skills_loaded": 1, "duplicates_skipped": 1},
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


if __name__ == "__main__":
    unittest.main()
