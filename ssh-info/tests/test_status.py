import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "status.sh"


class SshInfoStatusTests(unittest.TestCase):
    def test_surfaces_resolver_error_when_overlay_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(os.path.realpath(tmpdir))

            result = subprocess.run(
                ["bash", str(SCRIPT), "local"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Legacy transition: no skillbox-config overlay matches", result.stderr)
            self.assertIn("ssh-info requires client.context.deploy", result.stderr)

    def test_reads_deploy_section_from_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "service"
            repo.mkdir()

            overlay = {
                "version": 1,
                "client": {
                    "id": "example",
                    "label": "Example",
                    "default_cwd": str(repo),
                    "repos": [],
                    "logs": [],
                    "context": {
                        "cwd_match": [str(repo)],
                        "deploy": {
                            "services": {
                                "api": {
                                    "label": "Example API",
                                    "compose_service": "api",
                                    "internal_port": 8000,
                                    "health_url": "http://127.0.0.1:1/health",
                                }
                            }
                        },
                    },
                    "checks": [],
                },
            }
            overlay_path = root / "skillbox-config" / "clients" / "example" / "overlay.yaml"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")

            result = subprocess.run(
                ["bash", str(SCRIPT), "local"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("=== Local / Known Health Checks ===", result.stdout)
            self.assertIn("Example API", result.stdout)


if __name__ == "__main__":
    unittest.main()
