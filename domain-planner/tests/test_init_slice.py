import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "init_slice",
    str((Path(__file__).resolve().parent.parent / "scripts" / "init_slice.py").resolve()),
).load_module()


class FindRepoRootTests(unittest.TestCase):
    def test_finds_marker_in_current_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            result = MODULE.find_repo_root(root, ["pyproject.toml"])
            self.assertEqual(result, root.resolve())

    def test_finds_marker_in_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child = root / "src" / "nested"
            child.mkdir(parents=True)
            result = MODULE.find_repo_root(child, [".git"])
            self.assertEqual(result, root.resolve())

    def test_returns_none_when_no_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = MODULE.find_repo_root(Path(tmpdir), ["nonexistent-marker"])
            self.assertIsNone(result)


class FindSiblingRepoTests(unittest.TestCase):
    def test_finds_sibling_with_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            repo_a = parent / "repo-a"
            repo_b = parent / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            (repo_b / ".git").mkdir()
            result = MODULE.find_sibling_repo(repo_a, "repo-b")
            self.assertEqual(result, repo_b)

    def test_returns_none_for_missing_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo-a"
            repo.mkdir()
            result = MODULE.find_sibling_repo(repo, "repo-b")
            self.assertIsNone(result)

    def test_returns_none_for_sibling_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            repo_a = parent / "repo-a"
            repo_b = parent / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            result = MODULE.find_sibling_repo(repo_a, "repo-b")
            self.assertIsNone(result)


class ParseModeMarkdownTests(unittest.TestCase):
    def test_extracts_key_value_from_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text(
                "# Mode\n\n```\nplan_root: ~/repos/project/plans\nrepos_root: ~/repos\n```\n",
                encoding="utf-8",
            )
            config = MODULE.parse_mode_markdown(md)
            self.assertIn("repos/project/plans", config.get("plan_root", ""))
            self.assertIn("repos", config.get("repos_root", ""))

    def test_extracts_json_from_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text(
                '# Mode\n\n```json\n{"plan_root": "/tmp/plans"}\n```\n',
                encoding="utf-8",
            )
            config = MODULE.parse_mode_markdown(md)
            self.assertEqual(config.get("plan_root"), "/tmp/plans")

    def test_returns_empty_for_no_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text("# Mode\n\nNo code blocks here.\n", encoding="utf-8")
            config = MODULE.parse_mode_markdown(md)
            self.assertEqual(config, {})


if __name__ == "__main__":
    unittest.main()
