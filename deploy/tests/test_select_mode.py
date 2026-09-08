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
            repo = root / "api-service"
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
                                "api-service": {
                                    "repo_root": str(repo),
                                    "repo_slug": "acme/api-service",
                                    "deploy_root": "/opt/api-service",
                                    "compose_file": "deploy/docker-compose.prod.yml",
                                    "compose_service": "api",
                                    "health_url": "https://api.example.test/health",
                                    "release": {
                                        "command": "make release",
                                        "gate": "make verify",
                                        "ref_policy": "origin/main",
                                        "transport": "registryless",
                                        "manifest_dir": "/var/tmp/api-service-release/manifests",
                                    },
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
            self.assertEqual(payload["MODE_NAME"], "api-service")
            self.assertEqual(payload["MODE_SURFACE"], "docker_compose")
            self.assertEqual(payload["MODE_REPO_SLUG"], "acme/api-service")
            self.assertEqual(payload["MODE_HEALTH_URL"], "https://api.example.test/health")
            self.assertEqual(payload["MODE_RELEASE_COMMAND"], "make release")
            self.assertEqual(payload["MODE_RELEASE_GATE"], "make verify")
            self.assertEqual(payload["MODE_RELEASE_REF_POLICY"], "origin/main")
            self.assertEqual(payload["MODE_RELEASE_TRANSPORT"], "registryless")
            self.assertEqual(
                payload["MODE_RELEASE_MANIFEST_DIR"],
                "/var/tmp/api-service-release/manifests",
            )

    def test_error_path_probes_legacy_sources_and_prints_valid_stub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "DATABASE_URL=postgresql+asyncpg://postgres:secret@db:5432/appdb\n",
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
            self.assertIn("database_url: postgresql+asyncpg://postgres:***@db:5432/appdb", result.stderr)
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
                                    "release": {
                                        "command": "make release",
                                        "gate": "make verify",
                                        "ref_policy": "signed_tag",
                                        "transport": "registry_cli",
                                        "credential_probe": "cargo login --help",
                                        "manifest_dir": "/var/tmp/clawgs-release/manifests",
                                    },
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
            self.assertEqual(payload["MODE_RELEASE_COMMAND"], "make release")
            self.assertEqual(payload["MODE_RELEASE_GATE"], "make verify")
            self.assertEqual(payload["MODE_RELEASE_REF_POLICY"], "signed_tag")
            self.assertEqual(payload["MODE_RELEASE_TRANSPORT"], "registry_cli")
            self.assertEqual(
                payload["MODE_RELEASE_CREDENTIAL_PROBE"],
                "cargo login --help",
            )


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(os.path.realpath(self.tmp.name))
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.path = self.root / "overlay.yaml"
        self.target = {"repo_root": str(self.repo), "release": {
            "command": "make release", "gate": "make verify",
            "behavior_proof": "docs/release.md#behavior",
            "state_proof": "docs/release.md#state", "rollback": "docs/release.md#rollback"}}
        self.context = {"cwd_match": [str(self.repo)], "deploy": {"services": {"prod": self.target}}}

    def write(self):
        self.path.write_text(yaml.safe_dump({"client": {"context": self.context}}))

    def run_selector(self, *flags):
        self.write()
        return subprocess.run(["python3", str(SCRIPT), str(self.repo),
                               "--context", str(self.path), "--format", "json", *flags],
                              text=True, capture_output=True, check=False)

    def test_complete_release_and_provenance(self):
        result = self.run_selector("--require-release")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["MODE_TARGET_ID"], "prod")
        self.assertEqual(data["MODE_CONTEXT_SOURCE"], str(self.path))
        self.assertEqual(data["MODE_RELEASE_ROLLBACK"], "docs/release.md#rollback")

    def test_partial_is_diagnostic_only(self):
        del self.target["release"]["rollback"]
        self.assertEqual(self.run_selector().returncode, 0)
        result = self.run_selector("--require-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("release.rollback", result.stderr)

    def test_missing_and_wrong_target_fail_without_exports(self):
        self.context["deploy"] = {}
        result = self.run_selector("--require-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.context["deploy"] = {"services": {"prod": self.target}}
        self.target["repo_root"] = str(self.root / "different")
        self.assertNotEqual(self.run_selector("--require-release").returncode, 0)

    def test_ambiguous_targets_fail(self):
        self.context["deploy"]["services"]["other"] = dict(self.target)
        result = self.run_selector("--require-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ambiguous deploy target", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_stale_generated_context_fails(self):
        generated = json.loads(json.dumps(self.context))
        generated["deploy"]["services"]["prod"]["release"]["command"] = "old release"
        self.path.with_name("context.yaml").write_text(yaml.safe_dump(generated))
        result = self.run_selector("--require-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Stale or conflicting", result.stderr)

    def test_context_scope_and_absent_path_fail(self):
        self.context["cwd_match"] = [str(self.root / "other")]
        self.assertNotEqual(self.run_selector("--require-release").returncode, 0)
        result = subprocess.run(["python3", str(SCRIPT), str(self.repo), "--require-release",
                                 "--context", str(self.root / "absent.yaml")],
                                text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_checked_assignment_stops_shell_before_continuation(self):
        del self.target["release"]["state_proof"]
        self.write()
        result = subprocess.run(["bash", "-c", 'mode_exports="$(python3 "$1" "$2" --context "$3" --require-release --format shell)" || exit $?; echo CONTINUED',
                                 "selector-test", str(SCRIPT), str(self.repo), str(self.path)],
                                text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("CONTINUED", result.stdout)

    def test_implicit_selection_rejects_ambiguous_and_stale_sources(self):
        import importlib.util
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location("deploy_select_test", SCRIPT)
        selector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(selector)
        selector._load_shared_helpers()
        import resolve_context as shared

        self.write()
        first = self.root / "skillbox-config" / "clients" / "a" / "overlay.yaml"
        first.parent.mkdir(parents=True)
        first.write_text(self.path.read_text())
        second = first.parent.parent / "b" / "overlay.yaml"
        second.parent.mkdir()
        second.write_text(self.path.read_text())
        with patch.dict(os.environ, {"SKILLBOX_CLIENT_CONTEXT": ""}), \
             patch.object(shared, "FOCUS_STATE_PATHS", ()), \
             patch.object(shared, "WORKSPACE_CLIENTS_GLOB", str(self.root / "none")), \
             patch.object(shared, "LOCAL_SKILLBOX_CLIENTS", self.root / "none"):
            with self.assertRaisesRegex(ValueError, "Ambiguous release context"):
                selector.resolve_release_context(str(self.repo))
            first.with_name("context.yaml").write_text(yaml.safe_dump(self.context))
            with self.assertRaisesRegex(ValueError, "Ambiguous release context"):
                selector.resolve_release_context(str(self.repo))
            second.unlink()
            generated = json.loads(json.dumps(self.context))
            generated["deploy"]["services"]["prod"]["release"]["command"] = "stale"
            first.with_name("context.yaml").write_text(yaml.safe_dump(generated))
            with self.assertRaisesRegex(ValueError, "Stale or conflicting"):
                selector.resolve_release_context(str(self.repo))

    def test_malformed_yaml_never_echoes_contents(self):
        self.path.write_text("deploy: [private-secret: malformed")
        result = subprocess.run(["python3", str(SCRIPT), str(self.repo), "--require-release",
                                 "--context", str(self.path)],
                                text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("private-secret", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_client_shapes_fail_without_traceback(self):
        for data in ({"client": []}, {"client": {"context": []}}):
            with self.subTest(data=data):
                self.path.write_text(yaml.safe_dump(data))
                result = subprocess.run(["python3", str(SCRIPT), str(self.repo), "--require-release",
                                         "--context", str(self.path), "--errors-json"],
                                        text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(json.loads(result.stderr)["code"], "deploy_context_invalid")

    def test_strict_references_never_expand_environment_secrets(self):
        from unittest.mock import patch
        self.target["release"]["behavior_proof"] = "probe --password $DEPLOY_TEST_SECRET"
        with patch.dict(os.environ, {"DEPLOY_TEST_SECRET": "ordinary-private-sentinel"}):
            result = self.run_selector("--require-release")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ordinary-private-sentinel", result.stdout + result.stderr)
        self.assertIn("$DEPLOY_TEST_SECRET", result.stdout)

    def test_structured_missing_fields_name_owning_source(self):
        del self.target["release"]["rollback"]
        result = self.run_selector("--require-release", "--errors-json")
        self.assertNotEqual(result.returncode, 0)
        detail = json.loads(result.stderr)
        self.assertEqual(detail["missing_fields"], ["release.rollback"])
        self.assertEqual(detail["context_source"], str(self.path))


if __name__ == "__main__":
    unittest.main()
