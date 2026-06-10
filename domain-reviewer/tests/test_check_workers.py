import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "check_workers",
    str((Path(__file__).resolve().parent.parent / "scripts" / "check_workers.py").resolve()),
).load_module()


class ReadStatusesTests(unittest.TestCase):
    def test_reads_json_status_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "worker1.json").write_text(
                json.dumps({"label": "w1", "status": "DONE", "exit_code": 0}),
                encoding="utf-8",
            )
            (status_dir / "worker2.json").write_text(
                json.dumps({"label": "w2", "status": "RUNNING", "pid": 99999}),
                encoding="utf-8",
            )
            results = MODULE._read_statuses(status_dir)
            self.assertEqual(len(results), 2)

    def test_filters_by_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "alpha", "status": "DONE"}),
                encoding="utf-8",
            )
            (status_dir / "w2.json").write_text(
                json.dumps({"label": "beta", "status": "DONE"}),
                encoding="utf-8",
            )
            results = MODULE._read_statuses(status_dir, label_filter="alpha")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["label"], "alpha")

    def test_returns_empty_for_missing_dir(self) -> None:
        results = MODULE._read_statuses(Path("/nonexistent/status/dir"))
        self.assertEqual(results, [])

    def test_skips_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "bad.json").write_text("not json!", encoding="utf-8")
            (status_dir / "good.json").write_text(
                json.dumps({"label": "ok", "status": "DONE"}),
                encoding="utf-8",
            )
            results = MODULE._read_statuses(status_dir)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["label"], "ok")


class IsProcessAliveTests(unittest.TestCase):
    def test_none_pid_returns_false(self) -> None:
        self.assertFalse(MODULE._is_process_alive(None))

    def test_own_pid_returns_true(self) -> None:
        import os
        self.assertTrue(MODULE._is_process_alive(os.getpid()))

    def test_invalid_pid_returns_false(self) -> None:
        self.assertFalse(MODULE._is_process_alive(999999999))


class PrintSummaryTests(unittest.TestCase):
    def test_empty_statuses(self) -> None:
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            MODULE._print_summary([])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("No workers found", output)

    def test_done_worker_summary(self) -> None:
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            MODULE._print_summary([
                {"label": "audit", "status": "DONE", "exit_code": 0, "artifacts": ["/tmp/report.md"]},
            ])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("audit", output)
        self.assertIn("DONE", output)


class ClearDoneTests(unittest.TestCase):
    def test_removes_done_and_failed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "w1", "status": "DONE"}), encoding="utf-8",
            )
            (status_dir / "w2.json").write_text(
                json.dumps({"label": "w2", "status": "FAILED"}), encoding="utf-8",
            )
            (status_dir / "w3.json").write_text(
                json.dumps({"label": "w3", "status": "RUNNING", "pid": 99999}), encoding="utf-8",
            )
            removed = MODULE._clear_done(status_dir)
            self.assertEqual(removed, 2)
            self.assertTrue((status_dir / "w3.json").exists())

    def test_skips_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "bad.json").write_text("nope", encoding="utf-8")
            removed = MODULE._clear_done(status_dir)
            self.assertEqual(removed, 0)


class MainTests(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> tuple[int, str]:
        import io
        import sys

        old_argv, old_stdout = sys.argv, sys.stdout
        sys.stdout = io.StringIO()
        try:
            sys.argv = ["check_workers.py"] + argv
            rc = MODULE.main()
            return rc, sys.stdout.getvalue()
        finally:
            sys.argv, sys.stdout = old_argv, old_stdout

    def test_main_no_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rc, out = self._run_main(["--status-dir", tmpdir])
            self.assertEqual(rc, 0)
            self.assertIn("No workers found", out)

    def test_main_clear_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "w1", "status": "DONE"}), encoding="utf-8",
            )
            rc, out = self._run_main(["--status-dir", tmpdir, "--clear"])
            self.assertEqual(rc, 0)
            self.assertIn("Cleared 1", out)

    def test_main_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "w1", "status": "DONE", "exit_code": 0, "_log_file": "/tmp/log"}),
                encoding="utf-8",
            )
            rc, out = self._run_main(["--status-dir", tmpdir, "--json"])
            self.assertEqual(rc, 0)
            parsed = json.loads(out)
            self.assertEqual(len(parsed), 1)
            self.assertNotIn("_log_file", parsed[0])

    def test_main_json_verbose_includes_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "w1", "status": "DONE", "exit_code": 0, "_log_file": "/tmp/log"}),
                encoding="utf-8",
            )
            rc, out = self._run_main(["--status-dir", tmpdir, "--json", "--verbose"])
            parsed = json.loads(out)
            self.assertIn("_log_file", parsed[0])

    def test_main_returns_1_for_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "w1", "status": "FAILED", "exit_code": 1}),
                encoding="utf-8",
            )
            rc, _ = self._run_main(["--status-dir", tmpdir])
            self.assertEqual(rc, 1)

    def test_main_returns_2_for_running(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "w1", "status": "RUNNING", "pid": os.getpid()}),
                encoding="utf-8",
            )
            rc, _ = self._run_main(["--status-dir", tmpdir])
            self.assertEqual(rc, 2)

    def test_main_with_label_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_dir = Path(tmpdir)
            (status_dir / "w1.json").write_text(
                json.dumps({"label": "alpha", "status": "DONE", "exit_code": 0}),
                encoding="utf-8",
            )
            (status_dir / "w2.json").write_text(
                json.dumps({"label": "beta", "status": "DONE", "exit_code": 0}),
                encoding="utf-8",
            )
            rc, out = self._run_main(["--status-dir", tmpdir, "--label", "alpha", "--json"])
            parsed = json.loads(out)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0]["label"], "alpha")


if __name__ == "__main__":
    unittest.main()
