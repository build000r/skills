import json
import os
import tempfile
import unittest
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

save_review = SourceFileLoader("save_review", str(SCRIPTS / "save_review.py")).load_module()
show_trend = SourceFileLoader("show_trend", str(SCRIPTS / "show_trend.py")).load_module()
list_weeks = SourceFileLoader("list_weeks", str(SCRIPTS / "list_weeks.py")).load_module()
purge_sessions = SourceFileLoader("purge_sessions", str(SCRIPTS / "purge_sessions.py")).load_module()


class IsoWeekTests(unittest.TestCase):
    def test_known_week(self) -> None:
        dt = datetime(2025, 9, 3)
        self.assertEqual(save_review.iso_week(dt), "2025-W36")

    def test_year_boundary(self) -> None:
        dt = datetime(2025, 1, 1)
        result = save_review.iso_week(dt)
        self.assertTrue(result.startswith("202"))
        self.assertIn("-W", result)


class SaveReviewMainTests(unittest.TestCase):
    def test_saves_record_to_history(self) -> None:
        import io
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history.jsonl"
            with patch.object(save_review, "HISTORY_FILE", history):
                old_argv, old_stdout = sys.argv, sys.stdout
                sys.stdout = io.StringIO()
                try:
                    sys.argv = [
                        "save_review.py",
                        "--composite", "0.74",
                        "--sessions", "5",
                        "--prompts", "32",
                        "--clarity", "2.5",
                        "--context", "2.0",
                        "--autonomy", "1.5",
                        "--constraints", "1.0",
                        "--checkpoints", "1.5",
                        "--followup", "2.0",
                        "--collaboration", "2.5",
                        "--adaptability", "1.5",
                        "--outcome", "2.5",
                        "--week", "2025-W36",
                    ]
                    save_review.main()
                    output = sys.stdout.getvalue()
                finally:
                    sys.argv, sys.stdout = old_argv, old_stdout

            self.assertTrue(history.exists())
            record = json.loads(history.read_text().strip())
            self.assertEqual(record["composite"], 0.74)
            self.assertEqual(record["week"], "2025-W36")
            self.assertEqual(record["axes"]["clarity"], 2.5)
            self.assertIn("saved", output)

    def test_handles_invalid_improvements_json(self) -> None:
        import io
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history.jsonl"
            with patch.object(save_review, "HISTORY_FILE", history):
                old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
                sys.stdout = io.StringIO()
                sys.stderr = io.StringIO()
                try:
                    sys.argv = [
                        "save_review.py",
                        "--composite", "0.5",
                        "--sessions", "1", "--prompts", "1",
                        "--clarity", "1", "--context", "1", "--autonomy", "1",
                        "--constraints", "1", "--checkpoints", "1", "--followup", "1",
                        "--collaboration", "1", "--adaptability", "1", "--outcome", "1",
                        "--improvements", "not-json",
                    ]
                    save_review.main()
                    err = sys.stderr.getvalue()
                finally:
                    sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr

            record = json.loads(history.read_text().strip())
            self.assertIsNone(record["improvements"])
            self.assertIn("Warning", err)


class SparkTests(unittest.TestCase):
    def test_empty_values(self) -> None:
        self.assertEqual(show_trend.spark([]), "")

    def test_all_max(self) -> None:
        result = show_trend.spark([1.0, 1.0, 1.0])
        self.assertEqual(len(result), 3)
        self.assertTrue(all(c == "█" for c in result))

    def test_all_zero(self) -> None:
        result = show_trend.spark([0.0, 0.0])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(c == "▁" for c in result))

    def test_mixed_values(self) -> None:
        result = show_trend.spark([0.0, 0.5, 1.0])
        self.assertEqual(len(result), 3)


class DeltaStrTests(unittest.TestCase):
    def test_no_change(self) -> None:
        self.assertEqual(show_trend.delta_str(0.5, 0.5), "  --")

    def test_positive_delta(self) -> None:
        result = show_trend.delta_str(0.8, 0.5)
        self.assertTrue(result.startswith("+"))

    def test_negative_delta(self) -> None:
        result = show_trend.delta_str(0.3, 0.5)
        self.assertNotIn("+", result)
        self.assertIn("-", result)


class LoadRecordsTests(unittest.TestCase):
    def test_returns_empty_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(show_trend, "HISTORY_FILE", Path(tmpdir) / "missing.jsonl"):
                records = show_trend.load_records()
                self.assertEqual(records, [])

    def test_loads_and_filters_by_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history.jsonl"
            history.write_text(
                json.dumps({"week": "2025-W36", "provider": "claude"}) + "\n"
                + json.dumps({"week": "2025-W36", "provider": "codex"}) + "\n",
                encoding="utf-8",
            )
            with patch.object(show_trend, "HISTORY_FILE", history):
                records = show_trend.load_records(provider_filter="claude")
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["provider"], "claude")

    def test_skips_invalid_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history.jsonl"
            history.write_text(
                "not json\n" + json.dumps({"week": "2025-W36"}) + "\n",
                encoding="utf-8",
            )
            with patch.object(show_trend, "HISTORY_FILE", history):
                records = show_trend.load_records()
                self.assertEqual(len(records), 1)


class HasUserMessagesTests(unittest.TestCase):
    def test_detects_user_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "session.jsonl"
            f.write_text(
                json.dumps({"type": "assistant", "text": "hi"}) + "\n"
                + json.dumps({"type": "user", "text": "hello"}) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(list_weeks.has_user_messages(f))

    def test_returns_false_for_no_user_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "session.jsonl"
            f.write_text(
                json.dumps({"type": "assistant", "text": "hi"}) + "\n",
                encoding="utf-8",
            )
            self.assertFalse(list_weeks.has_user_messages(f))

    def test_returns_false_for_missing_file(self) -> None:
        self.assertFalse(list_weeks.has_user_messages(Path("/nonexistent")))


class WeekToDateRangeTests(unittest.TestCase):
    def test_known_week(self) -> None:
        start, end = purge_sessions.week_to_date_range("2025-W36")
        self.assertEqual(start.weekday(), 0)
        self.assertEqual((end - start).days, 7)
        self.assertTrue(start.month == 9 or start.month == 8)

    def test_week_1(self) -> None:
        start, end = purge_sessions.week_to_date_range("2025-W01")
        self.assertEqual(start.weekday(), 0)
        self.assertEqual((end - start).days, 7)


class ScanClaudeWeeksTests(unittest.TestCase):
    def test_counts_sessions_by_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            projects = claude_dir / "projects" / "test-project"
            projects.mkdir(parents=True)
            session = projects / "session1.jsonl"
            session.write_text(
                json.dumps({"type": "user", "text": "hello"}) + "\n",
                encoding="utf-8",
            )
            weeks = list_weeks.scan_claude_weeks(claude_dir)
            self.assertTrue(len(weeks) >= 1)

    def test_skips_agent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            projects = claude_dir / "projects" / "test-project"
            projects.mkdir(parents=True)
            agent_file = projects / "agent-123.jsonl"
            agent_file.write_text(
                json.dumps({"type": "user", "text": "hello"}) + "\n",
                encoding="utf-8",
            )
            weeks = list_weeks.scan_claude_weeks(claude_dir)
            self.assertEqual(weeks, {})

    def test_returns_empty_for_no_projects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            weeks = list_weeks.scan_claude_weeks(Path(tmpdir))
            self.assertEqual(weeks, {})


if __name__ == "__main__":
    unittest.main()
