import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = SourceFileLoader(
    "inspect_test_stack",
    str(ROOT / "scripts" / "inspect_test_stack.py"),
).load_module()


class InspectTestStackTests(unittest.TestCase):
    def test_python_scope_without_tests_requires_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "pyproject.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        "name = 'sample'",
                        "dependencies = []",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "src").mkdir()
            (repo / "src" / "sample.py").write_text("def sample():\n    return 1\n", encoding="utf-8")

            report = MODULE.inspect_repo(repo)

            self.assertEqual(len(report.lanes), 1)
            lane = report.lanes[0]
            self.assertEqual(lane.ecosystem, "python")
            self.assertEqual(lane.recommended_mode, "bootstrap-tests")
            self.assertIn("pytest", lane.suggested_targets)
            self.assertIn("coverage.xml", lane.suggested_targets)

    def test_python_scope_with_pytest_but_no_xml_artifact_requests_additive_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Makefile").write_text(
                "\n".join(
                    [
                        ".PHONY: pytest",
                        "pytest:",
                        "\tpytest tests",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "pyproject.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        "name = 'sample'",
                        "dependencies = []",
                        "",
                        "[project.optional-dependencies]",
                        "dev = ['pytest']",
                        "",
                        "[tool.pytest.ini_options]",
                        "testpaths = ['tests']",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "tests").mkdir()
            (repo / "tests" / "test_sample.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")

            report = MODULE.inspect_repo(repo)

            lane = report.lanes[0]
            self.assertEqual(lane.recommended_mode, "add-coverage-target")
            self.assertEqual(lane.preferred_wrapper, "make")
            self.assertIn("pytest-cov-xml", lane.suggested_targets)

    def test_typescript_scope_with_lcov_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "test": "vitest run",
                            "test:cov": "vitest run --coverage.enabled true --coverage.reporter=lcov",
                        },
                        "devDependencies": {
                            "vitest": "^4.0.0",
                            "@vitest/coverage-v8": "^4.0.0",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "src").mkdir()
            (repo / "src" / "sample.test.ts").write_text("import { expect, test } from 'vitest'\n", encoding="utf-8")
            (repo / "coverage").mkdir()
            (repo / "coverage" / "lcov.info").write_text("TN:\n", encoding="utf-8")

            report = MODULE.inspect_repo(repo)

            lane = report.lanes[0]
            self.assertEqual(lane.ecosystem, "typescript")
            self.assertEqual(lane.recommended_mode, "ready")
            self.assertTrue(lane.machine_artifact_present)

    def test_nested_manifests_are_reported_for_scope_narrowing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "packages").mkdir()
            (repo / "packages" / "api").mkdir()
            (repo / "packages" / "api" / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")

            report = MODULE.inspect_repo(repo)

            self.assertEqual(report.nested_manifests, ["packages/api"])


if __name__ == "__main__":
    unittest.main()
