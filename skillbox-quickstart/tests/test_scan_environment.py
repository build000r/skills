from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_environment.py"
SPEC = importlib.util.spec_from_file_location("scan_environment", SCRIPT)
assert SPEC and SPEC.loader
scan_environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_environment)


def git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)


class ScanReposTests(unittest.TestCase):
    def test_scan_repos_detects_git_worktree_with_git_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main"
            worktree = root / "worktree"

            git(["init", "-q", str(main)], root)
            git(["config", "user.email", "test@example.com"], main)
            git(["config", "user.name", "Test User"], main)
            git(["remote", "add", "origin", "git@example.com:demo.git"], main)
            (main / "README.md").write_text("demo\n", encoding="utf-8")
            git(["add", "README.md"], main)
            git(["commit", "-q", "-m", "init"], main)
            git(["worktree", "add", "-q", "-b", "feature", str(worktree)], main)

            repos = scan_environment.scan_repos([worktree])

        self.assertEqual(len(repos), 1)
        self.assertEqual(Path(repos[0]["path"]), worktree.resolve())
        self.assertEqual(repos[0]["name"], "worktree")
        self.assertEqual(repos[0]["remote"], "git@example.com:demo.git")
        self.assertEqual(repos[0]["branch"], "feature")

    def test_scan_repos_ignores_non_repo_with_git_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_repo = root / "fake"
            fake_repo.mkdir()
            (fake_repo / ".git").write_text("not a gitdir pointer\n", encoding="utf-8")

            repos = scan_environment.scan_repos([root])

        self.assertEqual(repos, [])

    def test_scan_repos_ignores_nested_git_file_inside_parent_repo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent"
            nested = parent / "nested"

            git(["init", "-q", str(parent)], root)
            nested.mkdir()
            (nested / ".git").write_text("not this directory's git metadata\n", encoding="utf-8")

            repos = scan_environment.scan_repos([nested])

        self.assertEqual(repos, [])


if __name__ == "__main__":
    unittest.main()
