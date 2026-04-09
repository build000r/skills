import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "select_mode.py"


class SelectModeTests(unittest.TestCase):
    def test_resolves_service_target_from_shared_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "htma_server"
            repo.mkdir()

            overlay = {
                "version": 1,
                "client": {
                    "id": "personal",
                    "label": "Personal",
                    "default_cwd": str(repo),
                    "repos": [],
                    "logs": [],
                    "context": {
                        "cwd_match": [str(repo)],
                        "deploy": {
                            "droplet_ssh": "ops@example",
                            "services": {
                                "htma": {
                                    "repo_root": str(repo),
                                    "repo_slug": "acme/htma_server",
                                    "deploy_root": "/opt/htma-server",
                                    "compose_file": "deploy/docker-compose.prod.yml",
                                    "compose_service": "api",
                                    "health_url": "https://api.example.test/health",
                                }
                            },
                        },
                    },
                    "checks": [],
                },
            }
            overlay_path = root / "skillbox-config" / "clients" / "personal" / "overlay.yaml"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo), "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["MODE_NAME"], "htma_server")
            self.assertEqual(payload["MODE_SURFACE"], "docker_compose")
            self.assertEqual(payload["MODE_REPO_SLUG"], "acme/htma_server")
            self.assertEqual(payload["MODE_HEALTH_URL"], "https://api.example.test/health")

    def test_error_path_probes_legacy_sources_and_prints_valid_stub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "DATABASE_URL=postgresql+asyncpg://postgres:secret@db:5432/htma\n",
                encoding="utf-8",
            )
            workflow = root / ".github" / "workflows" / "deploy.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: deploy\n", encoding="utf-8")
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: api\n  db:\n    image: postgres\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(root), "init"], capture_output=True, text=True, check=True)
            subprocess.run(
                ["git", "-C", str(root), "remote", "add", "origin", "git@github.com:acme/widgets.git"],
                capture_output=True,
                text=True,
                check=True,
            )

            result = subprocess.run(
                ["python3", str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Legacy transition: no skillbox-config overlay matches ", result.stderr)
            self.assertIn("database_url: postgresql+asyncpg://postgres:***@db:5432/htma", result.stderr)
            self.assertNotIn("secret", result.stderr)
            self.assertIn("repo_slug: acme/widgets", result.stderr)
            self.assertIn("ci_workflow: .github/workflows/deploy.yml", result.stderr)
            self.assertIn("containers: api,db", result.stderr)

            block = result.stderr.split("---\n", 1)[1].split("\n---", 1)[0]
            stub = yaml.safe_load(block)
            self.assertEqual(stub["client"]["context"]["cwd_match"], [os.path.realpath(str(root))])
            self.assertIn("deploy", stub["client"]["context"])

    def test_resolves_package_target_from_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "clawgs"
            repo.mkdir()

            overlay = {
                "version": 1,
                "client": {
                    "id": "clawgs",
                    "label": "Clawgs",
                    "default_cwd": str(repo),
                    "repo_roots": [],
                    "logs": [],
                    "context": {
                        "cwd_match": [str(repo)],
                        "deploy": {
                            "surface": "package_publish",
                            "packages": {
                                "clawgs": {
                                    "repo_root": str(repo),
                                    "repo_slug": "acme/clawgs",
                                    "crates_io_url": "https://crates.io/crates/clawgs",
                                }
                            },
                        },
                    },
                    "checks": [],
                },
            }
            overlay_path = root / "skillbox-config" / "clients" / "clawgs" / "overlay.yaml"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo), "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["MODE_NAME"], "clawgs")
            self.assertEqual(payload["MODE_SURFACE"], "package_publish")
            self.assertEqual(payload["MODE_REPO_SLUG"], "acme/clawgs")


if __name__ == "__main__":
    unittest.main()
