import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "skill_opportunities",
    str((Path(__file__).resolve().parent.parent / "scripts" / "lib" / "skill_opportunities.py").resolve()),
).load_module()


class SkillOpportunityReportTests(unittest.TestCase):
    def test_generate_opportunity_report_uses_shared_family_candidates(self) -> None:
        review_report = {
            "skill": "skill-issue",
            "generated_at": "2026-03-17T12:00:00+00:00",
            "source": "both",
            "since": "2026-03-01T00:00:00+00:00",
            "until": "2026-03-17T12:00:00+00:00",
            "sessions_scanned": 12,
            "invocations_found": 4,
            "summary": {
                "providers": {"codex": 4},
                "metrics": {
                    "ack_rate": 0.75,
                    "validation_rate": 0.25,
                    "checkpoint_rate": 0.25,
                    "risk_gating_rate": 0.5,
                    "correction_rate": 0.5,
                    "completion_rate": 0.5,
                },
                "top_command_stems": [{"stem": "rg", "count": 3}],
            },
            "invocations": [
                {
                    "provider": "codex",
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
                    "provider": "codex",
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
                    "provider": "codex",
                    "timestamp": "2026-03-15T11:00:00+00:00",
                    "project": "/tmp/other-project",
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
                    "provider": "codex",
                    "timestamp": "2026-03-14T11:00:00+00:00",
                    "project": "/tmp/other-project",
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

        report = MODULE.generate_opportunity_report(
            review_report,
            min_runs=2,
            max_cards=10,
            max_evidence=2,
        )

        self.assertEqual(report["skill"], "skill-issue")
        self.assertEqual(report["llm_interpretation_packet"]["schema"], "llm_interpretation_packet.v1")
        self.assertTrue(report["cards"])

        issue_types = [card["issue_type"] for card in report["cards"]]
        self.assertIn("verification-gap", issue_types)
        self.assertIn("contract-clarity", issue_types)

        verification = next(card for card in report["cards"] if card["issue_type"] == "verification-gap")
        self.assertIn(verification["slice"]["label"], {"global", "task_type=review", "project=skill-issue"})
        self.assertEqual(verification["suggested_fix_class"], "tighten-skill-contract")
        self.assertTrue(verification["family_candidate_id"].startswith("verification-gap__"))

    def test_render_opportunity_markdown_includes_scope_and_evidence(self) -> None:
        report = {
            "skill": "skill-issue",
            "source_review": {"sessions_scanned": 8, "invocations_found": 3},
            "cards": [
                {
                    "issue_type": "verification-gap",
                    "score": 42,
                    "slice": {"label": "global", "dimension": "global", "value": "all"},
                    "affected_runs": 2,
                    "total_runs": 3,
                    "prevalence": 0.667,
                    "suggested_fix_class": "tighten-skill-contract",
                    "hypothesis": "Verification is missing too often.",
                    "recommendation": "Add a required verification block.",
                    "target_files": ["SKILL.md", "scripts/"],
                    "skill_issue_brief": "Improve `skill-issue` for `verification-gap`.",
                    "evidence": [
                        {
                            "timestamp": "2026-03-17T11:00:00+00:00",
                            "session_id": "codex:session-1",
                            "signal": "no validation command detected",
                            "user_request": "review this skill",
                        }
                    ],
                }
            ],
        }

        markdown = MODULE.render_opportunity_markdown(report)

        self.assertIn("## Skill Opportunity Funnel (skill-issue)", markdown)
        self.assertIn("verification-gap", markdown)
        self.assertIn("Scope: `global`", markdown)
        self.assertIn("Session IDs: codex:session-1", markdown)
        self.assertIn("codex:session-1 | no validation command detected", markdown)
        self.assertIn("no validation command detected", markdown)


if __name__ == "__main__":
    unittest.main()
