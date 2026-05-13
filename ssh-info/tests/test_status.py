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

    def test_prod_status_prefers_upstream_container_over_compose_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "service"
            repo.mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()

            docker_log = root / "docker.log"
            docker_sh = bin_dir / "docker"
            docker_sh.write_text(
                f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {docker_log}
if [[ "$1" == "ps" ]]; then
  printf 'NAMES\\tSTATUS\\tPORTS\\nexample-api\\tUp 1 minute\\t8000/tcp\\n'
  exit 0
fi
if [[ "$1" == "exec" ]]; then
  printf '200'
  exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            docker_sh.chmod(0o755)
            ssh_sh = bin_dir / "ssh"
            ssh_sh.write_text(
                """#!/usr/bin/env bash
host="$1"
shift
bash -c "$*"
""",
                encoding="utf-8",
            )
            ssh_sh.chmod(0o755)

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
                            "droplet_ssh": "example-host",
                            "services": {
                                "api": {
                                    "label": "Example API",
                                    "compose_service": "api",
                                    "upstream_container": "example-api",
                                    "internal_port": 8000,
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

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(SCRIPT), "prod"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("[ok]   Example API", result.stdout)
            self.assertIn("example-api", docker_log.read_text(encoding="utf-8"))
            self.assertNotIn("exec api ", docker_log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
