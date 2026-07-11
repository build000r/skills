import json
import stat
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
