import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "init_skill",
    str((Path(__file__).resolve().parent.parent / "scripts" / "init_skill.py").resolve()),
).load_module()


class InitSkillTests(unittest.TestCase):
    def test_init_skill_rejects_invalid_name_before_creating_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = MODULE.init_skill("Bad_Skill", tmpdir, minimal=True)

            self.assertIsNone(result)
            self.assertFalse((Path(tmpdir) / "Bad_Skill").exists())

    def test_init_skill_rejects_names_outside_documented_cli_requirements(self) -> None:
        invalid_names = [
            "-bad-skill",
            "bad-skill-",
            "bad--skill",
            "a" * 41,
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            for name in invalid_names:
                with self.subTest(name=name):
                    result = MODULE.init_skill(name, tmpdir, minimal=True)

                    self.assertIsNone(result)
                    self.assertFalse((Path(tmpdir) / name).exists())

    def test_init_skill_accepts_valid_hyphen_case_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = MODULE.init_skill("valid-skill-1", tmpdir, minimal=True)

            self.assertEqual(result, Path(tmpdir).resolve() / "valid-skill-1")
            self.assertTrue((result / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
