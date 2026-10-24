import json
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPT = (Path(__file__).resolve().parent.parent / "scripts" / "lube_evidence_miner.py").resolve()
MODULE = SourceFileLoader("lube_evidence_miner", str(SCRIPT)).load_module()


FAKE_BACKEND = """#!/usr/bin/env python3
import json
import sys

term = sys.argv[1]
hits = []
if "permission" in term:
    hits = [
        {
            "agent": "claude_code",
            "line_number": 7,
            "source_path": "/tmp/projects/session-a.jsonl",
            "content": "Permission denied while writing settings; asked user to approve." * 4,
        },
        {
            "agent": "claude_code",
            "line_number": 9,
            "source_path": "/tmp/projects/session-b.jsonl",
            "content": "requires approval before running rm",
        },
    ]
print(json.dumps({"result": {"hits": hits, "total_matches": len(hits) * 10}}))
"""


class FrequencyModeUnitTests(unittest.TestCase):
    def test_aggregate_pattern_dedupes_hits_and_ranks_by_sessions_and_tokens(self) -> None:
        pattern = {"pattern": "timeout", "terms": ["timed out"], "lube_target": "weak defaults"}
        hit = {"source_path": "/tmp/projects/s1.jsonl", "line_number": 3, "content": "x" * 40}
        searches = [
            {"hits": [hit, dict(hit)], "total_matches": 5},
            {"hits": [{"source_path": "/tmp/projects/s2.jsonl", "line_number": 1, "content": "y" * 80}], "total_matches": 2},
            {"error": "exit 1: boom"},
        ]
        row = MODULE.aggregate_pattern(pattern, searches)
        self.assertEqual(row["session_count"], 2)
        self.assertEqual(row["session_ids"], ["s1", "s2"])
        self.assertEqual(row["total_matches"], 7)
        self.assertEqual(row["approx_match_tokens"], 30)
        self.assertEqual(row["score"], 60)
        self.assertEqual(row["errors"], ["exit 1: boom"])
        self.assertFalse(row["complete"])
        self.assertTrue(row["sample_snippet"].startswith("x"))

    def test_classify_lube_target_maps_known_signals(self) -> None:
        self.assertEqual(MODULE.classify_lube_target("permission denied"), "weak defaults")
        self.assertEqual(MODULE.classify_lube_target("missing API key"), "absent API key")
        self.assertEqual(MODULE.classify_lube_target("agent doesn't see the skill"), "missing skill trigger")
        self.assertEqual(MODULE.classify_lube_target("something novel"), "missing automation")

    def test_frequency_patterns_appends_custom_terms(self) -> None:
        patterns = MODULE.frequency_patterns(["rate limit hit"])
        self.assertEqual(patterns[-1]["terms"], ["rate limit hit"])
        self.assertEqual(patterns[-1]["pattern"], "rate-limit-hit")
        self.assertEqual(patterns[-1]["lube_target"], "missing runbook")

    def test_parse_terms_keeps_multi_word_terms(self) -> None:
        self.assertEqual(MODULE.parse_terms("rate limit, timed out ,"), ["rate limit", "timed out"])

    def test_search_rejects_errors_and_malformed_success_envelopes(self) -> None:
        invalid = [
            {"ok": False, "result": {"hits": [], "total_matches": 0}},
            {"status": "partial", "result": {"hits": [], "total_matches": 0}},
            {"status": "error", "exit_code": 0, "result": {"hits": [], "total_matches": 0}},
            {"status": "ok", "exit_code": 75, "result": {"hits": [], "total_matches": 0}},
            {"status": "ok", "exit_code": "0", "result": {"hits": [], "total_matches": 0}},
            {"status": "ok", "exit_code": False, "result": {"hits": [], "total_matches": 0}},
            {"status": "ok", "lineage_lookup_failed": True, "result": {"hits": [], "total_matches": 0}},
            {"result": {"error": "busy", "hits": [], "total_matches": 0}},
            {"result": {"status": "partial", "hits": [], "total_matches": 0}},
            {"result": {"lineage_lookup_failed": True, "hits": [], "total_matches": 0}},
            {"result": {"hits": "not a list", "total_matches": 0}},
            {"result": {"hits": [{"line_number": []}], "total_matches": 1}},
            {"result": {"hits": [], "total_matches": "unknown"}},
            {"result": {"hits": [], "total_matches": -1}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), mock.patch.object(MODULE, "run", return_value=(0, json.dumps(payload))):
                self.assertIn("error", MODULE.cass_search("term", 20, 1))

    def test_search_reports_cap_without_inventing_window_flags(self) -> None:
        payload = {"status": "ok", "exit_code": 0,
                   "result": {"hits": [{"source_path": "/sessions/a.jsonl", "content": "timeout"}], "total_matches": 12}}
        with mock.patch.object(MODULE, "run", return_value=(0, json.dumps(payload))) as backend:
            result = MODULE.cass_search("term", 1, 3)
        self.assertTrue(result["sample_may_be_capped"])
        self.assertEqual(backend.call_args.args[0], ["sbp", "cass", "search", "term", "--json",
                                                   "--limit", "1", "--fields", "all", "--timeout-seconds", "3"])
        self.assertEqual(backend.call_args.kwargs["timeout_seconds"], 18)


class FrequencyEvidenceContractTests(unittest.TestCase):
    def test_evidence_mode_keeps_default_month(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lube-evidence-default-") as tmpdir:
            scripts = Path(tmpdir) / "scripts"
            scripts.mkdir()
            for name in ("generate_skill_portfolio_opportunities.py", "review_skill_usage.py",
                         "generate_skill_opportunities.py"):
                (scripts / name).touch()
            argv = [str(SCRIPT), "--skills", "", "--skill-issue-root", tmpdir]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(MODULE, "run", return_value=(0, '{"cards": [{}]}')) as backend, \
                    redirect_stdout(StringIO()):
                self.assertEqual(MODULE.main(), 0)
        backend.assert_called_once()
        command = backend.call_args.args[0]
        self.assertEqual(command[command.index("--since") + 1], "month")

    def report(self, results, *, since=None, patterns=None, top=10):
        patterns = patterns or [{"pattern": "timeout", "terms": ["timed out"], "lube_target": "weak defaults"}]
        args = Namespace(since=since, terms="", per_term_limit=20, timeout_seconds=1,
                         cass_command="unused mock backend", top=top)
        output, errors = StringIO(), StringIO()
        with mock.patch.object(MODULE, "frequency_patterns", return_value=patterns), \
                mock.patch.object(MODULE, "cass_search", side_effect=results) as backend, \
                redirect_stdout(output), redirect_stderr(errors):
            code = MODULE.run_frequency_mode(args)
        return code, json.loads(output.getvalue()), backend

    def test_default_and_explicit_all_history_are_labeled(self) -> None:
        for since in (None, "all-history"):
            with self.subTest(since=since):
                code, report, backend = self.report([{"hits": [], "total_matches": 0}], since=since)
                self.assertEqual(code, 0)
                self.assertTrue(report["complete"])
                self.assertEqual(report["status"], "complete")
                self.assertEqual(report["window"]["effective"], "all-history")
                self.assertEqual(report["window"]["defaulted"], since is None)
                self.assertFalse(report["monthly_acceptance_eligible"])
                self.assertFalse(report["sampling"]["population_complete"])
                self.assertEqual(report["patterns"][0]["session_count"], 0)
                self.assertEqual(report["query_counts"]["succeeded"], 1)
                backend.assert_called_once()

    def test_unsupported_windows_refuse_without_any_search(self) -> None:
        for since in ("month", "week", "2026-10-01", ""):
            with self.subTest(since=since):
                code, report, backend = self.report([], since=since)
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], "unsupported_window")
                self.assertEqual(report["window"]["requested"], since)
                self.assertIsNone(report["window"]["effective"])
                self.assertFalse(report["complete"])
                self.assertEqual(report["patterns"], [])
                backend.assert_not_called()

    def test_error_outside_top_results_keeps_useful_ranking_partial(self) -> None:
        patterns = [{"pattern": name, "terms": [name], "lube_target": "weak defaults"}
                    for name in ("success", "failure")]
        code, report, _ = self.report([
            {"hits": [{"source_path": "/sessions/good.jsonl", "content": "timed out"}],
             "total_matches": 21, "sample_may_be_capped": True},
            {"error": "exit 75: busy"},
        ], patterns=patterns, top=1)
        self.assertEqual(code, 2)
        self.assertFalse(report["complete"])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["patterns"][0]["session_ids"], ["good"])
        self.assertTrue(report["patterns"][0]["complete"])
        self.assertEqual(report["incomplete_patterns"], [{"pattern": "failure", "errors": ["exit 75: busy"]}])
        self.assertEqual(report["query_counts"], {"requested": 2, "attempted": 2, "succeeded": 1, "failed": 1, "skipped": 0})
        self.assertEqual(report["sampling"]["possibly_capped_queries"], 1)

    def test_circuit_skips_are_incomplete_even_after_successful_hits(self) -> None:
        patterns = [{"pattern": "mixed", "terms": ["good", "timeout1", "timeout2", "skipped"], "lube_target": "weak defaults"}]
        code, report, backend = self.report([
            {"hits": [{"source_path": "/sessions/good.jsonl", "content": "timeout"}], "total_matches": 1},
            {"error": "exit 124: process timed out"}, {"error": "exit 124: process timed out"},
        ], patterns=patterns)
        self.assertEqual(code, 2)
        self.assertEqual(backend.call_count, 3)
        self.assertFalse(report["complete"])
        self.assertEqual(report["query_counts"], {"requested": 4, "attempted": 3, "succeeded": 1, "failed": 2, "skipped": 1})
        self.assertEqual(report["patterns"][0]["session_ids"], ["good"])
        self.assertEqual(len(report["patterns"][0]["errors"]), 3)

    def test_all_failed_queries_return_partial_nonzero(self) -> None:
        code, report, _ = self.report([{"error": "exit 1: unavailable"}])
        self.assertEqual(code, 2)
        self.assertFalse(report["complete"])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["query_counts"]["failed"], 1)


class FrequencyModeSmokeTests(unittest.TestCase):
    def test_frequency_mode_with_mocked_backend_emits_ranked_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lube-fake-cass-") as tmpdir:
            backend = Path(tmpdir) / "fake_cass.py"
            backend.write_text(FAKE_BACKEND)
            backend.chmod(backend.stat().st_mode | stat.S_IXUSR)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--mode",
                    "frequency",
                    "--top",
                    "3",
                    "--cass-command",
                    f"{sys.executable} {backend}",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["mode"], "frequency")
        self.assertTrue(report["complete"])
        self.assertEqual(report["window"]["effective"], "all-history")
        self.assertTrue(report["window"]["defaulted"])
        self.assertFalse(report["monthly_acceptance_eligible"])
        self.assertGreater(report["sampling"]["possibly_capped_queries"], 0)
        self.assertEqual(len(report["patterns"]), 3)
        top = report["patterns"][0]
        self.assertEqual(top["pattern"], "permission-prompt-friction")
        self.assertEqual(top["lube_target"], "weak defaults")
        self.assertEqual(top["session_count"], 2)
        self.assertEqual(sorted(top["session_ids"]), ["session-a", "session-b"])
        self.assertIn("Permission denied", top["sample_snippet"])
        scores = [row["score"] for row in report["patterns"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_help_mentions_frequency_mode(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("frequency", proc.stdout)
        self.assertIn("all-history", proc.stdout)
        self.assertIn("dated windows are refused", " ".join(proc.stdout.split()))

    def test_month_refusal_reaches_cli_without_starting_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lube-window-") as tmpdir:
            marker = Path(tmpdir) / "backend-ran"
            backend = Path(tmpdir) / "backend.py"
            backend.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
            proc = subprocess.run([sys.executable, str(SCRIPT), "--mode", "frequency", "--since", "month",
                                   "--cass-command", f"{sys.executable} {backend}"],
                                  text=True, capture_output=True, check=False)
            self.assertFalse(marker.exists())
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "unsupported_frequency_window")


if __name__ == "__main__":
    unittest.main()
