import subprocess
import sys
import tempfile
import unittest
import zipfile
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

PACKAGE_MODULE = SourceFileLoader(
    "package_skill",
    str((SCRIPTS_DIR / "package_skill.py").resolve()),
).load_module()
VALIDATE_MODULE = SourceFileLoader(
    "quick_validate",
    str((SCRIPTS_DIR / "quick_validate.py").resolve()),
).load_module()


class PackageSkillTests(unittest.TestCase):
    def test_package_skill_excludes_repo_and_local_gitignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            self._init_git_repo(repo)
            (repo / ".gitignore").write_text("*/modes/\n*.log\n", encoding="utf-8")

            skill_dir = repo / "sample-skill"
            self._write_skill(skill_dir)
            (skill_dir / ".gitignore").write_text("secrets.txt\n", encoding="utf-8")
            (skill_dir / "references" / "guide.md").write_text("public guide\n", encoding="utf-8")
            (skill_dir / "assets").mkdir(parents=True, exist_ok=True)
            (skill_dir / "assets" / "template.txt").write_text("ship me\n", encoding="utf-8")
            (skill_dir / "modes" / "private.local.md").write_text("private mode\n", encoding="utf-8")
            (skill_dir / "debug.log").write_text("ignore me\n", encoding="utf-8")
            (skill_dir / "secrets.txt").write_text("ignore me too\n", encoding="utf-8")

            output_dir = repo / "dist"
            archive_path = PACKAGE_MODULE.package_skill(skill_dir, output_dir)

            self.assertIsNotNone(archive_path)
            archive_members = self._read_archive_members(archive_path)

            self.assertIn("sample-skill/SKILL.md", archive_members)
            self.assertIn("sample-skill/references/guide.md", archive_members)
            self.assertIn("sample-skill/assets/template.txt", archive_members)
            self.assertNotIn("sample-skill/modes/private.local.md", archive_members)
            self.assertNotIn("sample-skill/debug.log", archive_members)
            self.assertNotIn("sample-skill/secrets.txt", archive_members)

    def test_package_skill_falls_back_to_skill_local_gitignore_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "sample-skill"
            self._write_skill(skill_dir)
            (skill_dir / ".gitignore").write_text("modes/\n", encoding="utf-8")
            (skill_dir / "references" / "guide.md").write_text("public guide\n", encoding="utf-8")
            (skill_dir / "modes" / "private.local.md").write_text("private mode\n", encoding="utf-8")

            output_dir = Path(tmpdir) / "dist"
            archive_path = PACKAGE_MODULE.package_skill(skill_dir, output_dir)

            self.assertIsNotNone(archive_path)
            archive_members = self._read_archive_members(archive_path)

            self.assertIn("sample-skill/SKILL.md", archive_members)
            self.assertIn("sample-skill/references/guide.md", archive_members)
            self.assertNotIn("sample-skill/modes/private.local.md", archive_members)

    def test_validate_skill_skips_repo_gitignored_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            self._init_git_repo(repo)
            (repo / ".gitignore").write_text("*/modes/\n", encoding="utf-8")

            skill_dir = repo / "sample-skill"
            self._write_skill(skill_dir)
            (skill_dir / "modes" / "private.local.md").write_text(
                "Operator home: /Users/alice/private/\n",
                encoding="utf-8",
            )

            valid, message = VALIDATE_MODULE.validate_skill(skill_dir)

            self.assertTrue(valid)
            self.assertEqual(message, "Skill is valid!")

    def _init_git_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    def _write_skill(self, skill_dir: Path) -> None:
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "modes").mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: sample-skill\n"
            "description: Package a sample skill for tests and use when validating gitignored bundle safety.\n"
            "---\n\n"
            "# Sample Skill\n",
            encoding="utf-8",
        )
        (skill_dir / "references" / "overview.md").write_text("public reference\n", encoding="utf-8")

    def _read_archive_members(self, archive_path: Path) -> list[str]:
        with zipfile.ZipFile(archive_path, "r") as archive:
            return sorted(archive.namelist())


if __name__ == "__main__":
    unittest.main()
