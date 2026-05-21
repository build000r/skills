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

    def test_health_check_label_falls_back_to_service_id(self) -> None:
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
                                "site": {
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
            self.assertIn("site", result.stdout)
            self.assertNotIn("unknown", result.stdout)

    def test_local_status_can_scope_to_one_service(self) -> None:
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
                                    "health_url": "http://127.0.0.1:1/health",
                                },
                                "worker": {
                                    "label": "Example Worker",
                                    "health_url": "http://127.0.0.1:1/worker-health",
                                },
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
                ["bash", str(SCRIPT), "local", "api"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Example API", result.stdout)
            self.assertNotIn("Example Worker", result.stdout)

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
  printf 'NAMES\\tSTATUS\\tPORTS\\nexample-api\\tUp 1 minute\\t8000/tcp\\nother-api\\tUp 1 minute\\t9000/tcp\\n'
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
while [[ "$1" == "-o" ]]; do
  shift 2
done
if [[ "$1" == "-i" ]]; then
  shift 2
fi
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
            self.assertIn("example-api", result.stdout)
            self.assertNotIn("other-api", result.stdout)
            self.assertIn("example-api", docker_log.read_text(encoding="utf-8"))
            self.assertNotIn("exec api ", docker_log.read_text(encoding="utf-8"))

    def test_prod_container_health_falls_back_to_python_when_curl_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "service"
            repo.mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()

            docker_sh = bin_dir / "docker"
            docker_sh.write_text(
                """#!/usr/bin/env bash
if [[ "$1" == "ps" ]]; then
  printf 'NAMES\\tSTATUS\\tPORTS\\nexample-api\\tUp 1 minute\\t8000/tcp\\n'
  exit 0
fi
if [[ "$1" == "exec" ]]; then
  if [[ "$5" == *"command -v curl"* && "$5" == *"command -v python"* ]]; then
    printf '200'
    exit 0
  fi
  printf '000'
  exit 1
fi
exit 1
""",
                encoding="utf-8",
            )
            docker_sh.chmod(0o755)
            ssh_sh = bin_dir / "ssh"
            ssh_sh.write_text(
                f"""#!/usr/bin/env bash
while [[ "$1" == "-o" ]]; do
  shift 2
done
if [[ "$1" == "-i" ]]; then
  shift 2
fi
host="$1"
shift
PATH={bin_dir}:$PATH bash -c "$*"
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

    def test_prod_status_uses_explicit_deploy_lane_and_temp_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "service"
            repo.mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()

            ssh_log = root / "ssh.log"
            ssh_sh = bin_dir / "ssh"
            ssh_sh.write_text(
                f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {ssh_log}
while [[ "$1" == "-o" ]]; do
  shift 2
done
if [[ "$1" == "-i" ]]; then
  test -f "$2" || exit 42
  shift 2
fi
host="$1"
shift
if [[ "$host" != "root@104.131.188.214" ]]; then
  exit 43
fi
if [[ "$*" == *"docker ps"* ]]; then
  printf 'NAMES\\tSTATUS\\tPORTS\\nexample-api\\tUp 1 minute\\t8000/tcp\\n'
  exit 0
fi
if [[ "$*" == *"docker exec"* ]]; then
  printf '200'
  exit 0
fi
exit 1
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
                            "droplet_ssh": "aiops@sweet-potato-prod",
                            "services": {
                                "api": {
                                    "label": "Example API",
                                    "upstream_container": "example-api",
                                    "internal_port": 8000,
                                }
                            },
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
            env["DO_DROPLET_IP"] = "104.131.188.214"
            env["DO_SSH_USER"] = "root"
            env["DO_SSH_PRIVATE_KEY_B64"] = "ZHVtbXkta2V5"
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
            ssh_args = ssh_log.read_text(encoding="utf-8")
            self.assertIn("BatchMode=yes", ssh_args)
            self.assertIn("ConnectTimeout=", ssh_args)
            self.assertIn("-i ", ssh_args)
            self.assertIn("root@104.131.188.214", ssh_args)
            self.assertNotIn("aiops@sweet-potato-prod", ssh_args)
            self.assertNotIn("ZHVtbXkta2V5", ssh_args)

    def test_prod_status_requires_user_when_droplet_ip_overrides_overlay(self) -> None:
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
                            "droplet_ssh": "aiops@sweet-potato-prod",
                            "services": {},
                        },
                    },
                    "checks": [],
                },
            }
            overlay_path = root / "skillbox-config" / "clients" / "example" / "overlay.yaml"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")

            env = os.environ.copy()
            env["DO_DROPLET_IP"] = "104.131.188.214"
            result = subprocess.run(
                ["bash", str(SCRIPT), "prod"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("DO_SSH_USER is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
