import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "skill_ship",
    str((Path(__file__).resolve().parent.parent / "scripts" / "lib" / "skill_ship.py").resolve()),
).load_module()


class SkillShipTests(unittest.TestCase):
    def test_build_ship_record_captures_packet_and_baseline_metrics(self) -> None:
        packet_report = {
            "skill": "skill-issue",
            "generated_at": "2026-03-22T07:00:00+00:00",
            "packets": [
                {
                    "packet_id": "verification-gap-global",
                    "issue_type": "verification-gap",
                    "expected_contract": "Run a concrete verification command before handoff.",
                    "watch_metric": "validation_rate",
                    "experiment_unit": "real_invocation_window",
                    "historical_reference_slice": {"holdout_examples": [{"signal": "holdout control"}]},
                    "post_ship_window": {"type": "real_invocation_window", "min_new_invocations": 8, "max_days": 14},
                    "affected_runs": 3,
                    "total_runs": 9,
                }
            ],
        }
        review_report = {
            "generated_at": "2026-03-22T06:50:00+00:00",
            "summary": {"metrics": {"validation_rate": 0.667, "correction_rate": 0.333}},
        }

        record = MODULE.build_ship_record(
            packet_report=packet_report,
            packet_id="verification-gap-global",
            decision="ship",
            notes="tightened verification block",
            skill_path="/tmp/skill-issue",
            review_report=review_report,
        )

        self.assertEqual(record["skill"], "skill-issue")
        self.assertEqual(record["packet_id"], "verification-gap-global")
        self.assertEqual(record["baseline_watch_metric_value"], 0.667)
        self.assertEqual(record["post_ship_window"]["min_new_invocations"], 8)
        self.assertEqual(record["notes"], "tightened verification block")

    def test_append_ship_record_writes_jsonl(self) -> None:
        record = {"skill": "skill-issue", "packet_id": "verification-gap-global"}

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "ledger.jsonl"
            MODULE.append_ship_record(record, output_path)

            written = output_path.read_text().strip().splitlines()
            self.assertEqual(len(written), 1)
            self.assertEqual(json.loads(written[0]), record)


if __name__ == "__main__":
    unittest.main()
