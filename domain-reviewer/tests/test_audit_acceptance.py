import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("audit_loop", SCRIPTS / "run_codex_audit_loop.py")
LOOP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LOOP)


class AcceptanceTests(unittest.TestCase):
    def test_default_requires_acceptance_and_checks_not_score(self):
        report = "Acceptance: PASS\nRequired checks: PASS\n"
        self.assertTrue(LOOP._acceptance_passed(report))
        self.assertFalse(LOOP._acceptance_passed(report + "## Agent Handoffs\n### For Backend Issues\n```\nRemaining defect\n```\n"))
        self.assertFalse(LOOP._acceptance_passed(report.replace("checks: PASS", "checks: FAIL")))
        self.assertFalse(LOOP._acceptance_passed(report.replace("Acceptance: PASS", "Acceptance: FAIL")))
        for invalid in ("Score: 100/100", report + "Acceptance: PASS\n"):
            with self.assertRaises(ValueError):
                LOOP._acceptance_passed(invalid)

    def test_explicit_threshold_remains_binding(self):
        report = "Acceptance: PASS\nRequired checks: PASS\n### Overall Compliance Score: **95/100**\n"
        self.assertTrue(LOOP._acceptance_passed(report, 90))
        self.assertFalse(LOOP._acceptance_passed(report, 100))
        self.assertFalse(LOOP._acceptance_passed(report.replace("Acceptance: PASS", "Acceptance: FAIL"), 90))
        with self.assertRaises(ValueError):
            LOOP._acceptance_passed(report.replace("95/100", "101/100"), 90)

    def run_main(self, reports, extra=()):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mode = SimpleNamespace(name="fixture", plan_root=str(root), plan_index=str(root / "INDEX.md"),
                                   session_plan_index=str(root / "SESSIONS.md"))
            observed = []
            def worker(**kwargs):
                observed.append(kwargs)
                if kwargs["worker"] in {"audit", "re-review"}:
                    Path(kwargs["report_path"]).write_text(reports.pop(0))
                return 0
            with mock.patch.object(LOOP.launcher, "discover_modes", return_value={}), \
                 mock.patch.object(LOOP.launcher, "detect_mode", return_value=mode), \
                 mock.patch.object(LOOP, "_run_worker_sync", side_effect=worker):
                result = LOOP.main(["--slice", "fixture", *extra])
            self.assertFalse((root / "fixture" / "AUDIT_REPORT.md").exists())
            scratch = Path(observed[0]["report_path"]).parent
            exists = scratch.exists()
            if exists:
                shutil.rmtree(scratch)
            return result, observed, exists

    def test_clean_review_stops_once_and_removes_its_scratch(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result, workers, retained = self.run_main(["Acceptance: PASS\nRequired checks: PASS\nChecks: unit tests passed\n"])
        self.assertIn("Checks: unit tests passed", output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual([worker["worker"] for worker in workers], ["audit"])
        self.assertFalse(retained)

    def test_unchanged_findings_stop_instead_of_repeating_repairs(self):
        failure = "Acceptance: FAIL\nRequired checks: PASS\n## Agent Handoffs\n### For Backend Issues\n```\nFix required behavior\n```\n"
        result, workers, retained = self.run_main([failure, failure])
        self.assertEqual(result, 2)
        self.assertEqual([worker["worker"] for worker in workers], ["audit", "fix-backend", "re-review"])
        self.assertTrue(retained)

    def test_stale_pass_is_refused_without_deleting_retained_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "retained.md"
            previous = "Acceptance: PASS\nRequired checks: PASS\n"
            report.write_text(previous)
            scratch = root / "scratch"
            scratch.mkdir()
            mode = SimpleNamespace(name="fixture", plan_root=str(root), plan_index=str(root / "INDEX.md"),
                                   session_plan_index=str(root / "SESSIONS.md"))
            with mock.patch.object(LOOP.launcher, "discover_modes", return_value={}), \
                 mock.patch.object(LOOP.launcher, "detect_mode", return_value=mode), \
                 mock.patch.object(LOOP.tempfile, "mkdtemp", return_value=str(scratch)), \
                 mock.patch.object(LOOP, "_run_worker_sync", return_value=0):
                result = LOOP.main(["--slice", "fixture", "--report-path", str(report)])
            self.assertEqual(result, 1)
            self.assertEqual(report.read_text(), previous)

    def test_configured_model_is_inherited_unless_explicitly_selected(self):
        launcher = LOOP.launcher
        model, effort = launcher.resolve_model_config("audit")
        command = launcher._build_codex_command("codex", Path("/tmp"), "review", model, effort)
        self.assertNotIn("-m", command)
        selected = launcher._build_codex_command("codex", Path("/tmp"), "review", "chosen", effort)
        self.assertEqual(selected[2:4], ["-m", "chosen"])


if __name__ == "__main__":
    unittest.main()
