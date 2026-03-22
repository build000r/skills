import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "skill_evidence",
    str((Path(__file__).resolve().parent.parent / "scripts" / "lib" / "skill_evidence.py").resolve()),
).load_module()


class SkillEvidencePacketTests(unittest.TestCase):
    def test_generate_evidence_report_builds_packets_from_repeated_failures(self) -> None:
        review_report = {
            "skill": "skill-issue",
            "generated_at": "2026-03-17T12:00:00+00:00",
            "source": "both",
            "since": "2026-03-01T00:00:00+00:00",
            "until": "2026-03-17T12:00:00+00:00",
            "sessions_scanned": 12,
            "invocations_found": 4,
            "invocations": [
                {
                    "timestamp": "2026-03-17T11:00:00+00:00",
                    "project": "/tmp/skill-issue",
                    "file": "/tmp/codex/session-1.jsonl",
                    "matched_on": ["assistant_ack", "skill_path"],
                    "user_request": "review this skill and improve the flow",
                    "validation_commands": [],
                    "checkpoint_messages": [],
                    "user_corrections": ["focus on transcript evidence, not just heuristics"],
                    "risk_gating_messages": ["it should wait until fixes are made before uploading"],
                    "command_stems": {"rg": 2, "sed": 1},
                    "task_complete": False,
                },
                {
                    "timestamp": "2026-03-16T11:00:00+00:00",
                    "project": "/tmp/skill-issue",
                    "file": "/tmp/codex/session-2.jsonl",
                    "matched_on": ["assistant_ack", "skill_path"],
                    "user_request": "review this skill again",
                    "validation_commands": [],
                    "checkpoint_messages": ["should I ask more questions first?"],
                    "user_corrections": ["use a tighter operator-evidence loop"],
                    "risk_gating_messages": ["ask further questions before diving in further"],
                    "command_stems": {"rg": 1},
                    "task_complete": True,
                },
                {
                    "timestamp": "2026-03-15T11:00:00+00:00",
                    "project": "/tmp/skill-issue",
                    "file": "/tmp/codex/session-3.jsonl",
                    "matched_on": ["assistant_ack", "skill_path"],
                    "user_request": "improve this skill",
                    "validation_commands": ["python3 scripts/quick_validate.py skill-issue"],
                    "checkpoint_messages": [],
                    "user_corrections": [],
                    "risk_gating_messages": [],
                    "command_stems": {"python3": 1},
                    "task_complete": True,
                },
                {
                    "timestamp": "2026-03-14T11:00:00+00:00",
                    "project": "/tmp/skill-issue",
                    "file": "/tmp/codex/session-4.jsonl",
                    "matched_on": ["skill_path"],
                    "user_request": "review this skill one more time",
                    "validation_commands": [],
                    "checkpoint_messages": [],
                    "user_corrections": [],
                    "risk_gating_messages": [],
                    "command_stems": {"ls": 1},
                    "task_complete": False,
                },
            ],
        }

        report = MODULE.generate_evidence_report(
            review_report,
            min_occurrences=2,
            max_packets=5,
            max_examples=2,
            max_controls=1,
        )

        self.assertEqual(report["skill"], "skill-issue")
        self.assertGreaterEqual(report["summary"]["packets_generated"], 3)

        packet_types = [packet["issue_type"] for packet in report["packets"]]
        self.assertIn("verification-gap", packet_types)
        self.assertIn("risk-gating-gap", packet_types)
        self.assertIn("contract-clarity", packet_types)

        contract_packet = next(packet for packet in report["packets"] if packet["issue_type"] == "contract-clarity")
        self.assertEqual(contract_packet["watch_metric"], "correction_rate")
        self.assertEqual(len(contract_packet["representative_traces"]), 2)
        self.assertEqual(len(contract_packet["historical_reference_slice"]["holdout_examples"]), 1)
        self.assertTrue(
            contract_packet["historical_reference_slice"]["holdout_examples"][0]["signal"].startswith(
                "holdout control:"
            )
        )
        self.assertEqual(contract_packet["experiment_unit"], "real_invocation_window")
        self.assertEqual(contract_packet["post_ship_window"]["type"], "real_invocation_window")
        self.assertIs(contract_packet["replay_slice"], contract_packet["historical_reference_slice"])

        risk_packet = next(packet for packet in report["packets"] if packet["issue_type"] == "risk-gating-gap")
        self.assertEqual(risk_packet["watch_metric"], "risk_gating_rate")
        self.assertEqual(risk_packet["representative_traces"][0]["signal"], "it should wait until fixes are made before uploading")

    def test_render_evidence_markdown_includes_packet_details(self) -> None:
        report = {
            "skill": "skill-issue",
            "source_review": {"sessions_scanned": 8, "invocations_found": 3},
            "packets": [
                {
                    "issue_type": "verification-gap",
                    "failure_family": "The skill reaches closeout without enough verification evidence.",
                    "why_now": "Unverified runs let the maintainer overestimate reliability.",
                    "expected_contract": "Run a concrete verification command before handoff.",
                    "target_files": ["SKILL.md", "scripts/"],
                    "watch_metric": "validation_rate",
                    "affected_runs": 2,
                    "total_runs": 3,
                    "prevalence": 0.667,
                    "suggested_fix_class": "tighten-skill-contract",
                    "skill_issue_brief": "Improve `skill-issue` for `verification-gap`.",
                    "representative_traces": [
                        {
                            "timestamp": "2026-03-17T11:00:00+00:00",
                            "signal": "no validation command detected",
                            "user_request": "review this skill",
                        }
                    ],
                    "experiment_unit": "real_invocation_window",
                    "post_ship_window": {"min_new_invocations": 5, "max_days": 14},
                    "historical_reference_slice": {"holdout_examples": []},
                }
            ],
        }

        markdown = MODULE.render_evidence_markdown(report)

        self.assertIn("## Operator Evidence Packets (skill-issue)", markdown)
        self.assertIn("verification-gap", markdown)
        self.assertIn("validation_rate", markdown)
        self.assertIn("Historical reference slice", markdown)
        self.assertIn("next 5 real invocations or 14 days", markdown)


if __name__ == "__main__":
    unittest.main()
