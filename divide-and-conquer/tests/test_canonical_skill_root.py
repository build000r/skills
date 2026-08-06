import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent


class CanonicalSkillRootTests(unittest.TestCase):
    def test_adjacent_shared_tree_contains_required_helpers(self) -> None:
        shared_root = (SKILL_DIR / ".." / "_shared").resolve()

        self.assertTrue((shared_root / "scripts" / "br_helpers.py").is_file())
        self.assertTrue((shared_root / "scripts" / "resolve_context.py").is_file())
        self.assertTrue(
            (shared_root / "references" / "orchestration-contract.md").is_file()
        )

    def test_operational_docs_do_not_depend_on_an_agent_home(self) -> None:
        docs = [
            SKILL_DIR / "SKILL.md",
            SKILL_DIR / "references" / "workgraph-synthesis.md",
            SKILL_DIR / "references" / "orchestration-contract.md",
        ]

        for path in docs:
            text = path.read_text()
            with self.subTest(path=path.relative_to(SKILL_DIR)):
                self.assertNotIn("~/.claude/skills/_shared", text)
                self.assertNotIn("~/.codex/skills/_shared", text)

    def test_bootstrap_anchors_shared_helpers_to_loaded_skill(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text()

        self.assertIn('export DAC_SKILL_ROOT="<resolved directory', text)
        self.assertIn('realpath "$DAC_SKILL_ROOT/../_shared"', text)
        self.assertIn('test -f "$DAC_SHARED_ROOT/scripts/br_helpers.py"', text)
        self.assertNotIn("BR_HARNESS=claude-code", text)


if __name__ == "__main__":
    unittest.main()
