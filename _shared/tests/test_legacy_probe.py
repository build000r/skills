import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


MODULE = SourceFileLoader(
    "legacy_probe",
    str((Path(__file__).resolve().parent.parent / "scripts" / "legacy_probe.py").resolve()),
).load_module()


class EnvProbeTests(unittest.TestCase):
    def test_finds_database_url_in_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "APP_KEY=secret\nDATABASE_URL=postgres://user:pass@localhost:5432/mydb\n",
                encoding="utf-8",
            )
            findings = MODULE._env_probe(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].key, "database_url")
            self.assertIn("localhost", findings[0].value)
            self.assertNotIn("pass", findings[0].value)

    def test_finds_exported_database_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "export DATABASE_URL=postgres://u:p@host/db\n",
                encoding="utf-8",
            )
            findings = MODULE._env_probe(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].key, "database_url")

    def test_skips_comments_and_blanks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "# DATABASE_URL=nope\n\n  \nAPP_KEY=val\n",
                encoding="utf-8",
            )
            findings = MODULE._env_probe(root)
            self.assertEqual(findings, [])

    def test_returns_empty_for_no_env_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = MODULE._env_probe(Path(tmpdir))
            self.assertEqual(findings, [])

    def test_checks_production_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env.production").write_text(
                "DATABASE_URL=postgres://u:p@prod/db\n",
                encoding="utf-8",
            )
            findings = MODULE._env_probe(root)
            self.assertEqual(len(findings), 1)


class GitRemoteProbeTests(unittest.TestCase):
    def test_extracts_repo_slug_from_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
            subprocess.run(
                ["git", "-C", str(root), "remote", "add", "origin", "git@github.com:owner/repo.git"],
                capture_output=True,
                check=True,
            )
            findings = MODULE._git_remote_probe(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].key, "repo_slug")
            self.assertEqual(findings[0].value, "owner/repo")

    def test_returns_empty_for_non_git_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = MODULE._git_remote_probe(Path(tmpdir))
            self.assertEqual(findings, [])

    def test_returns_empty_for_no_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
            findings = MODULE._git_remote_probe(root)
            self.assertEqual(findings, [])


class ComposeCandidatesTests(unittest.TestCase):
    def test_returns_standard_names_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docker-compose.yml").write_text("services:\n  web:\n", encoding="utf-8")
            (root / "compose.yml").write_text("services:\n  api:\n", encoding="utf-8")
            candidates = MODULE._compose_candidates(root)
            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0].name, "docker-compose.yml")
            self.assertEqual(candidates[1].name, "compose.yml")

    def test_returns_empty_for_no_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates = MODULE._compose_candidates(Path(tmpdir))
            self.assertEqual(candidates, [])

    def test_includes_glob_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docker-compose.dev.yml").write_text("services:\n  dev:\n", encoding="utf-8")
            candidates = MODULE._compose_candidates(root)
            self.assertEqual(len(candidates), 1)
            self.assertIn("dev", candidates[0].name)


class ComposeProbeTests(unittest.TestCase):
    def test_extracts_services_from_compose(self) -> None:
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("yaml not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docker-compose.yml").write_text(
                "services:\n  web:\n    image: nginx\n  db:\n    image: postgres\n",
                encoding="utf-8",
            )
            findings = MODULE._compose_probe(root)
            self.assertTrue(len(findings) >= 3)
            keys = {f.key for f in findings}
            self.assertIn("surface", keys)
            self.assertIn("compose_file", keys)
            self.assertIn("containers", keys)
            containers = next(f for f in findings if f.key == "containers")
            self.assertIn("web", containers.value)
            self.assertIn("db", containers.value)

    def test_returns_empty_without_yaml(self) -> None:
        with patch.object(MODULE, "yaml", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "docker-compose.yml").write_text(
                    "services:\n  web:\n    image: nginx\n",
                    encoding="utf-8",
                )
                findings = MODULE._compose_probe(root)
                self.assertEqual(findings, [])

    def test_skips_invalid_yaml(self) -> None:
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("yaml not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docker-compose.yml").write_text(
                "{{not: valid: yaml: [",
                encoding="utf-8",
            )
            findings = MODULE._compose_probe(root)
            self.assertEqual(findings, [])

    def test_skips_compose_without_services(self) -> None:
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("yaml not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docker-compose.yml").write_text(
                "version: '3'\n",
                encoding="utf-8",
            )
            findings = MODULE._compose_probe(root)
            self.assertEqual(findings, [])


class ProbeLeSourcesIntegrationTests(unittest.TestCase):
    def test_aggregates_multiple_probes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
            subprocess.run(
                ["git", "-C", str(root), "remote", "add", "origin", "git@github.com:owner/repo.git"],
                capture_output=True,
                check=True,
            )
            (root / ".env").write_text("DATABASE_URL=postgres://u:p@host/db\n", encoding="utf-8")
            findings = MODULE.probe_legacy_sources(str(root))
            keys = {f.key for f in findings}
            self.assertIn("database_url", keys)
            self.assertIn("repo_slug", keys)


if __name__ == "__main__":
    unittest.main()
