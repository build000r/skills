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


class InspectRenderTextTests(unittest.TestCase):
    def test_render_text_reports_empty_supported_ecosystems(self) -> None:
        report = MODULE.RepoReport(
            scope="/tmp/sample",
            makefile_present=False,
            make_targets=[],
            coverage_artifacts=[],
            nested_manifests=[],
            lanes=[],
        )

        text = MODULE.render_text(report)

        self.assertIn("Scope: /tmp/sample", text)
        self.assertIn("Makefile: absent", text)
        self.assertIn("Coverage artifacts: none", text)
        self.assertIn("Supported ecosystems: none detected", text)
        self.assertNotIn("Lane:", text)

    def test_render_text_reports_nested_manifests_and_scope_note(self) -> None:
        report = MODULE.RepoReport(
            scope="/tmp/sample",
            makefile_present=True,
            make_targets=["coverage.xml", "test"],
            coverage_artifacts=["coverage.xml"],
            nested_manifests=["packages/api", "tools/cli"],
            lanes=[],
        )

        text = MODULE.render_text(report)

        self.assertIn("Makefile: present", text)
        self.assertIn("Coverage artifacts: coverage.xml", text)
        self.assertIn("Nested manifests: packages/api, tools/cli", text)
        self.assertIn(
            "Scope note: narrow to one manifest-owning package when root automation is too thin",
            text,
        )

    def test_render_text_reports_lane_details_and_actions(self) -> None:
        lane = MODULE.LaneReport(
            ecosystem="python",
            manifest=None,
            tests_present=True,
            runner_present=False,
            coverage_support_present=False,
            machine_artifact_present=True,
            preferred_wrapper="make",
            recommended_mode="ready",
            suggested_targets=["pytest", "pytest-cov-xml"],
            actions=[
                "Reuse the existing pytest baseline and coverage lane for /crap reruns.",
                "Keep scope labels exact when narrowing to a package or path.",
            ],
        )
        report = MODULE.RepoReport(
            scope="/tmp/sample",
            makefile_present=True,
            make_targets=["test"],
            coverage_artifacts=["coverage.xml"],
            nested_manifests=[],
            lanes=[lane],
        )

        text = MODULE.render_text(report)

        self.assertIn("Lane: python", text)
        self.assertIn("  Manifest: not found at scope root", text)
        self.assertIn("  Tests present: yes", text)
        self.assertIn("  Runner present: no", text)
        self.assertIn("  Machine coverage artifact: yes", text)
        self.assertIn("  Preferred wrapper: make", text)
        self.assertIn("  Recommendation: ready", text)
        self.assertIn("  Suggested targets: pytest, pytest-cov-xml", text)
        self.assertIn(
            "  - Reuse the existing pytest baseline and coverage lane for /crap reruns.",
            text,
        )
        self.assertIn(
            "  - Keep scope labels exact when narrowing to a package or path.",
            text,
        )


class InspectSwiftLaneTests(unittest.TestCase):
    def test_no_swift_lane_when_no_swift_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "README.md").write_text("", encoding="utf-8")

            report = MODULE.inspect_repo(repo)

            self.assertNotIn("swift", [lane.ecosystem for lane in report.lanes])

    def test_swift_lane_detected_from_swift_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Sources").mkdir()
            (repo / "Sources" / "App.swift").write_text(
                "func hello() { print(\"hi\") }\n", encoding="utf-8"
            )

            report = MODULE.inspect_repo(repo)

            swift_lanes = [lane for lane in report.lanes if lane.ecosystem == "swift"]
            self.assertEqual(len(swift_lanes), 1)

    def test_swift_lane_detected_from_package_swift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Package.swift").write_text(
                "// swift-tools-version:5.9\n", encoding="utf-8"
            )

            report = MODULE.inspect_repo(repo)

            swift_lanes = [lane for lane in report.lanes if lane.ecosystem == "swift"]
            self.assertEqual(len(swift_lanes), 1)
            self.assertEqual(swift_lanes[0].manifest, "Package.swift")

    def test_swift_lane_ready_when_cobertura_artifact_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Sources").mkdir()
            (repo / "Sources" / "App.swift").write_text(
                "func hello() {}\n", encoding="utf-8"
            )
            (repo / "coverage.xml").write_text(
                "<?xml version='1.0' ?><coverage></coverage>\n", encoding="utf-8"
            )

            report = MODULE.inspect_repo(repo)

            swift_lanes = [lane for lane in report.lanes if lane.ecosystem == "swift"]
            self.assertEqual(len(swift_lanes), 1)
            self.assertEqual(swift_lanes[0].recommended_mode, "ready")
            self.assertTrue(swift_lanes[0].machine_artifact_present)

    def test_swift_lane_recognizes_crap_swift_cobertura_make_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Sources").mkdir()
            (repo / "Sources" / "App.swift").write_text(
                "func hello() {}\n", encoding="utf-8"
            )
            (repo / "Makefile").write_text(
                "crap-swift-cobertura:\n\techo doing swift coverage\n",
                encoding="utf-8",
            )

            report = MODULE.inspect_repo(repo)

            swift_lanes = [lane for lane in report.lanes if lane.ecosystem == "swift"]
            self.assertEqual(len(swift_lanes), 1)
            self.assertEqual(swift_lanes[0].recommended_mode, "ready")
            self.assertEqual(swift_lanes[0].preferred_wrapper, "make")


if __name__ == "__main__":
    unittest.main()
