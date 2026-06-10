from __future__ import annotations

import importlib.util
import shlex
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_overlay.py"
SPEC = importlib.util.spec_from_file_location("generate_overlay", SCRIPT)
assert SPEC and SPEC.loader
generate_overlay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_overlay)


class FirstBoxCommandTests(unittest.TestCase):
    def test_shell_quotes_set_values_with_spaces(self) -> None:
        command = generate_overlay.build_first_box_cmd(
            "demo-client",
            {
                "blueprint": "git-repo-http-service",
                "set_args": {
                    "PRIMARY_REPO_ID": "demo",
                    "SERVICE_COMMAND": "npm run dev",
                },
            },
        )

        argv = shlex.split(command)

        self.assertIn("SERVICE_COMMAND=npm run dev", argv)
        self.assertEqual(argv.count("--set"), 2)
        self.assertNotIn("run", argv)
        self.assertNotIn("dev", argv)


class OverlayGenerationTests(unittest.TestCase):
    def test_overlay_uses_service_repo_as_primary(self) -> None:
        scan = {
            "repos": [
                {
                    "name": "library",
                    "path": "/tmp/library",
                    "remote": "git@example.com:library.git",
                    "branch": "main",
                    "stacks": ["python"],
                },
                {
                    "name": "app",
                    "path": "/tmp/app",
                    "remote": "git@example.com:app.git",
                    "branch": "main",
                    "stacks": ["node"],
                    "service": {
                        "command": "npm run dev",
                        "source": "package.json scripts.dev",
                    },
                },
            ]
        }

        blueprint = generate_overlay.pick_blueprint(scan)
        overlay = generate_overlay.build_overlay("demo", scan, blueprint)

        repos = {repo["id"]: repo for repo in overlay["client"]["repos"]}
        self.assertEqual(overlay["client"]["default_cwd"], "${CLIENT_ROOT}/app")
        self.assertFalse(repos["library"]["required"])
        self.assertTrue(repos["app"]["required"])
        self.assertEqual(overlay["client"]["services"][0]["repo"], "app")
        self.assertFalse(overlay["client"]["services"][0]["required"])
        self.assertNotIn("cwd", overlay["client"]["services"][0])

    def test_first_included_repo_is_required_when_earlier_repos_are_skipped(self) -> None:
        scan = {
            "repos": [
                {
                    "name": "local-only",
                    "path": "/tmp/local-only",
                    "remote": None,
                    "branch": "main",
                    "stacks": ["python"],
                },
                {
                    "name": "remote",
                    "path": "/tmp/remote",
                    "remote": "git@example.com:remote.git",
                    "branch": "main",
                    "stacks": ["python"],
                },
            ]
        }

        blueprint = generate_overlay.pick_blueprint(scan)
        overlay = generate_overlay.build_overlay("demo", scan, blueprint)

        self.assertEqual(blueprint["blueprint"], "git-repo")
        self.assertEqual(blueprint["primary_repo"]["name"], "remote")
        self.assertEqual(overlay["client"]["default_cwd"], "${CLIENT_ROOT}/remote")
        self.assertEqual(
            [(repo["id"], repo["required"]) for repo in overlay["client"]["repos"]],
            [("remote", True)],
        )

    def test_local_primary_service_repo_is_included_with_file_url(self) -> None:
        scan = {
            "repos": [
                {
                    "name": "local-app",
                    "path": "/tmp/local-app",
                    "remote": None,
                    "branch": "main",
                    "stacks": ["node"],
                    "service": {
                        "command": "npm run dev",
                        "source": "package.json scripts.dev",
                    },
                }
            ]
        }

        blueprint = generate_overlay.pick_blueprint(scan)
        overlay = generate_overlay.build_overlay("demo", scan, blueprint)

        self.assertEqual(overlay["client"]["default_cwd"], "${CLIENT_ROOT}/local-app")
        self.assertEqual(
            overlay["client"]["repos"][0]["source"]["url"],
            "file:///tmp/local-app",
        )
        self.assertTrue(overlay["client"]["repos"][0]["required"])
        self.assertEqual(overlay["client"]["services"][0]["repo"], "local-app")
        self.assertNotIn("cwd", overlay["client"]["services"][0])

    def test_service_is_not_emitted_for_skipped_local_only_repo(self) -> None:
        scan = {
            "repos": [
                {
                    "name": "local-primary",
                    "path": "/tmp/local-primary",
                    "remote": None,
                    "branch": "main",
                    "stacks": ["node"],
                    "service": {
                        "command": "npm run dev",
                        "source": "package.json scripts.dev",
                    },
                },
                {
                    "name": "local-secondary",
                    "path": "/tmp/local-secondary",
                    "remote": None,
                    "branch": "main",
                    "stacks": ["node"],
                    "service": {
                        "command": "npm run start",
                        "source": "package.json scripts.start",
                    },
                },
            ]
        }

        blueprint = generate_overlay.pick_blueprint(scan)
        overlay = generate_overlay.build_overlay("demo", scan, blueprint)

        self.assertEqual(
            [service["id"] for service in overlay["client"]["services"]],
            ["local-primary-dev"],
        )
        self.assertEqual(overlay["client"]["services"][0]["repo"], "local-primary")


class ComputeDecisionsTests(unittest.TestCase):
    def test_single_repo_no_repo_decisions(self) -> None:
        scan = {"repos": [{"name": "app"}], "gaps": []}
        decisions = generate_overlay.compute_decisions(scan, {})
        questions = [d["question"] for d in decisions]
        self.assertFalse(any("repos" in q.lower() for q in questions))

    def test_multiple_repos_prompts_selection_and_primary(self) -> None:
        scan = {
            "repos": [{"name": "frontend"}, {"name": "backend"}],
            "gaps": [],
        }
        decisions = generate_overlay.compute_decisions(scan, {})
        questions = [d["question"] for d in decisions]
        self.assertTrue(any("included" in q.lower() or "which repo" in q.lower() for q in questions))
        self.assertTrue(any("primary" in q.lower() for q in questions))

    def test_do_token_gap_prompts_provisioning(self) -> None:
        scan = {
            "repos": [{"name": "app"}],
            "gaps": [{"tool": "do_token", "severity": "recommended"}],
        }
        decisions = generate_overlay.compute_decisions(scan, {})
        questions = [d["question"] for d in decisions]
        self.assertTrue(any("digitalocean" in q.lower() or "provision" in q.lower() for q in questions))

    def test_no_gaps_no_provisioning_decision(self) -> None:
        scan = {"repos": [{"name": "app"}], "gaps": []}
        decisions = generate_overlay.compute_decisions(scan, {})
        self.assertEqual(decisions, [])

    def test_non_do_gap_ignored(self) -> None:
        scan = {
            "repos": [{"name": "app"}],
            "gaps": [{"tool": "docker", "severity": "recommended"}],
        }
        decisions = generate_overlay.compute_decisions(scan, {})
        self.assertEqual(decisions, [])

    def test_primary_repo_default_from_blueprint(self) -> None:
        scan = {
            "repos": [{"name": "frontend"}, {"name": "backend"}],
            "gaps": [],
        }
        blueprint_rec = {"primary_repo": {"name": "backend"}}
        decisions = generate_overlay.compute_decisions(scan, blueprint_rec)
        primary_decision = [d for d in decisions if "primary" in d["question"].lower()][0]
        self.assertEqual(primary_decision["default"], "backend")


if __name__ == "__main__":
    unittest.main()
