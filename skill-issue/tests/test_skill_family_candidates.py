import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "skill_families",
    str((Path(__file__).resolve().parent.parent / "scripts" / "lib" / "skill_families.py").resolve()),
).load_module()


class SkillFamilyCandidateTests(unittest.TestCase):
    def test_build_family_candidates_returns_deterministic_global_candidates(self) -> None:
        fact_bundle = {
            "schema": "skill_fact_bundle.v1",
            "skill": "skill-issue",
            "summary": {"providers": {"codex": 2}},
            "invocations": [
                {
                    "invocation_id": "inv_a",
                    "timestamp": "2026-03-17T11:00:00+00:00",
                    "file": "/tmp/session-a.jsonl",
                    "matched_on": ["skill_path"],
                    "flags": {
                        "has_validation": False,
                        "has_checkpoint": False,
                        "has_risk_gate_gap": True,
                        "has_user_correction": False,
                        "task_complete": False,
                    },
                    "command_stems": {"rg": 2},
                    "refs": {
                        "risk_gating_messages": ["wait until fixes are made"],
                        "checkpoint_messages": [],
                        "user_corrections": [],
                    },
                },
                {
                    "invocation_id": "inv_b",
                    "timestamp": "2026-03-16T11:00:00+00:00",
                    "file": "/tmp/session-b.jsonl",
                    "matched_on": ["assistant_ack", "skill_path"],
                    "flags": {
                        "has_validation": False,
                        "has_checkpoint": True,
                        "has_risk_gate_gap": False,
                        "has_user_correction": True,
                        "task_complete": True,
                    },
                    "command_stems": {"sed": 1},
                    "refs": {
                        "risk_gating_messages": [],
                        "checkpoint_messages": ["should I ask first?"],
                        "user_corrections": ["use tighter evidence packets"],
                    },
                },
            ],
        }

        candidates = MODULE.build_family_candidates(fact_bundle, source="both")

        self.assertEqual(candidates["schema"], "family_candidates.v1")
        family_ids = [item["family_id"] for item in candidates["candidates"]]
        self.assertIn("verification-gap", family_ids)
        self.assertIn("risk-gating-gap", family_ids)
        self.assertIn("provider-coverage", family_ids)

        verification = next(item for item in candidates["candidates"] if item["family_id"] == "verification-gap")
        self.assertEqual(verification["affected_runs"], 2)
        self.assertEqual(verification["legacy"]["opportunity_id"], "verification-gap")
        self.assertEqual(verification["slice"], {"label": "global", "dimension": "global", "value": "all"})


if __name__ == "__main__":
    unittest.main()
