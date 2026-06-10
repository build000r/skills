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


if __name__ == "__main__":
    unittest.main()
