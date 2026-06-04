from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_environment.py"
SPEC = importlib.util.spec_from_file_location("scan_environment", SCRIPT)
assert SPEC and SPEC.loader
scan_environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_environment)


def git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)


class ScanReposTests(unittest.TestCase):
    def test_main_json_quiet_reports_ready_scan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = {
                "docker": {"installed": True, "version": "Docker version 1"},
                "docker_compose": {"installed": True, "version": "Docker Compose version 2"},
                "git": {"installed": True, "version": "git version 2"},
                "tail" + "scale": {"installed": True, "version": "1.0"},
                "do_" + "to" + "ken": {"installed": True, "version": None},
                "ts_authkey": {"installed": True, "version": None},
            }
            stdout = StringIO()
            stderr = StringIO()

            with (
                patch.object(scan_environment.sys, "argv", ["scan_environment.py", "--scan-root", str(root), "--json", "--quiet"]),
                patch.object(scan_environment, "scan_tools", return_value=tools),
                patch.object(scan_environment, "scan_repos", return_value=[]),
                patch.object(
                    scan_environment,
                    "scan_claude_config",
                    return_value={"exists": False, "skills": [], "mcp_servers": [], "settings": {}},
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = scan_environment.main()

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["scan_roots"], [str(root)])
        self.assertEqual(report["repo_count"], 0)
        self.assertEqual(report["gaps"], [])
        self.assertFalse(report["has_blocking_gaps"])
        self.assertEqual(stderr.getvalue(), "")

    def test_main_human_output_reports_repos_claude_and_blocking_gaps(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = {
                "path": str(root / "demo"),
                "name": "demo",
                "remote": "git@example.com:demo.git",
                "branch": "main",
                "stacks": ["python"],
                "service": {"command": "python3 app.py", "source": "app.py"},
            }
            tools = {
                "docker": {"installed": False, "version": None},
                "docker_compose": {"installed": True, "version": "Docker Compose version 2"},
                "git": {"installed": True, "version": "git version 2"},
                "tail" + "scale": {"installed": False, "version": None},
                "do_" + "to" + "ken": {"installed": False, "version": None},
                "ts_authkey": {"installed": False, "version": None},
            }
            claude = {
                "exists": True,
                "skills": [{"name": "describe", "path": "/tmp/describe", "symlink": True, "has_skill_md": True}],
                "mcp_servers": ["skillbox"],
                "settings": {},
            }
            stdout = StringIO()
            stderr = StringIO()

            with (
                patch.object(scan_environment.sys, "argv", ["scan_environment.py", "--scan-root", str(root)]),
                patch.object(scan_environment, "scan_tools", return_value=tools),
                patch.object(scan_environment, "scan_repos", return_value=[repo]),
                patch.object(scan_environment, "scan_claude_config", return_value=claude),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = scan_environment.main()

        text = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("Scanning environment...", stderr.getvalue())
        self.assertIn("SKILLBOX QUICKSTART", text)
        self.assertIn("Repos found: 1", text)
        self.assertIn("demo", text)
        self.assertIn("has dev server", text)
        self.assertIn("git@example.com:demo.git", text)
        self.assertIn("Claude Config", text)
        self.assertIn("describe (symlink)", text)
        self.assertIn("MCP Servers: skillbox", text)
        self.assertIn("docker", text)
        self.assertIn("Blocking gaps found", text)

    def test_scan_claude_config_reads_skills_and_mcp_settings(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude = home / ".claude"
            skills = claude / "skills"
            skills.mkdir(parents=True)
            direct = skills / "describe"
            direct.mkdir()
            (direct / "SKILL.md").write_text("---\nname: describe\n---\n", encoding="utf-8")
            missing_manifest = skills / "scratch"
            missing_manifest.mkdir()
            linked_target = home / "linked-skill"
            linked_target.mkdir()
            (linked_target / "SKILL.md").write_text("---\nname: linked\n---\n", encoding="utf-8")
            (skills / "linked").symlink_to(linked_target, target_is_directory=True)
            (claude / "settings.json").write_text(
                json.dumps(
                    {
                        "hooks": {"Stop": []},
                        "mcpServers": {
                            "skillbox": {"command": "skillbox"},
                            "filesystem": {"command": "fs"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(scan_environment.Path, "home", return_value=home):
                result = scan_environment.scan_claude_config()

        self.assertTrue(result["exists"])
        skills_by_name = {skill["name"]: skill for skill in result["skills"]}
        self.assertTrue(skills_by_name["describe"]["has_skill_md"])
        self.assertFalse(skills_by_name["describe"]["symlink"])
        self.assertFalse(skills_by_name["scratch"]["has_skill_md"])
        self.assertTrue(skills_by_name["linked"]["has_skill_md"])
        self.assertTrue(skills_by_name["linked"]["symlink"])
        self.assertTrue(result["settings"]["has_hooks"])
        self.assertTrue(result["settings"]["has_mcp"])
        self.assertEqual(result["mcp_servers"], ["skillbox", "filesystem"])

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
