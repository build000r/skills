import json
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plan_intake"
MODULE = SourceFileLoader(
    "plan_intake",
    str((SKILL_DIR / "scripts" / "plan_intake.py").resolve()),
).load_module()


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def intake(name: str) -> dict:
    fixture = load_fixture(name)
    return MODULE.intake_plan(
        fixture["issues_payload"],
        fixture["ready_payload"],
        fixture["plan"],
    )


class CanonicalPlanIntakeTests(unittest.TestCase):
    def test_plan_and_plan_role_labels_are_required_exactly_once(self) -> None:
        fixture = load_fixture("valid_handoff.json")
        issues = fixture["issues_payload"]["issues"]
        issues[1]["labels"] = [
            "plan:wrong-plan",
            "plan-role:branch",
            "plan-role:review",
        ]

        receipt = MODULE.intake_plan(
            fixture["issues_payload"],
            fixture["ready_payload"],
            fixture["plan"],
        )

        self.assertFalse(receipt["dispatchable"])
        self.assertIn(
            "fixture-branch: expected exactly one plan:fixture-plan label; "
            "found ['plan:wrong-plan']",
            receipt["defects"],
        )
        self.assertIn(
            "fixture-branch: expected exactly one canonical plan-role label; "
            "found ['plan-role:branch', 'plan-role:review']",
            receipt["defects"],
        )

    def test_valid_handoff_admits_only_execution_integration_and_review(self) -> None:
        receipt = intake("valid_handoff.json")

        self.assertTrue(receipt["dispatchable"])
        self.assertEqual(receipt["defects"], [])
        self.assertEqual(
            receipt["recognized_metadata"],
            {
                "fields": [
                    "planning_parent",
                    "supports",
                    "local_criteria",
                    "produces",
                ],
                "node_count": 5,
                "complete_node_count": 5,
            },
        )
        self.assertEqual(
            receipt["admitted_frontier"],
            [
                {"id": "fixture-leaf", "role": "plan-role:execution-leaf"},
                {"id": "fixture-integration", "role": "plan-role:integration"},
                {"id": "fixture-review", "role": "plan-role:review"},
            ],
        )

    def test_flat_raw_ready_payload_does_not_dispatch_grouping_epics(self) -> None:
        receipt = intake("flattening.json")

        self.assertTrue(receipt["dispatchable"])
        self.assertEqual(
            receipt["excluded_ready_grouping_ids"],
            ["fixture-root", "fixture-branch"],
        )
        self.assertEqual(
            receipt["admitted_frontier"],
            [{"id": "fixture-leaf", "role": "plan-role:execution-leaf"}],
        )
        hierarchy = {item["id"]: item for item in receipt["planning_hierarchy"]}
        self.assertEqual(hierarchy["fixture-leaf"]["planning_parent"], "fixture-branch")
        self.assertEqual(hierarchy["fixture-branch"]["planning_parent"], "fixture-root")

    def test_draft_state_keeps_candidate_leaf_out_of_admitted_frontier(self) -> None:
        receipt = intake("draft_state.json")

        self.assertFalse(receipt["dispatchable"])
        self.assertEqual(receipt["root"]["state"], "plan-state:draft")
        self.assertEqual(
            receipt["candidate_frontier"],
            [{"id": "fixture-leaf", "role": "plan-role:execution-leaf"}],
        )
        self.assertEqual(receipt["admitted_frontier"], [])
        self.assertIn(
            "root state is plan-state:draft; required plan-state:handoff-ready",
            receipt["gate_reasons"],
        )

    def test_valid_synthesized_hierarchy_is_recognized_but_not_dispatched(self) -> None:
        receipt = intake("valid_synthesized.json")

        self.assertEqual(receipt["defects"], [])
        self.assertEqual(receipt["recognized_metadata"]["complete_node_count"], 3)
        self.assertEqual(
            receipt["excluded_ready_grouping_ids"],
            ["fixture-root", "fixture-branch"],
        )
        self.assertEqual(
            receipt["candidate_frontier"],
            [{"id": "fixture-leaf", "role": "plan-role:execution-leaf"}],
        )
        self.assertEqual(receipt["admitted_frontier"], [])
        self.assertFalse(receipt["dispatchable"])

    def test_missing_canonical_field_fails_closed_without_defaulting(self) -> None:
        receipt = intake("missing_field.json")

        self.assertFalse(receipt["dispatchable"])
        self.assertEqual(receipt["admitted_frontier"], [])
        self.assertIn(
            "fixture-leaf: missing canonical notes field produces",
            receipt["defects"],
        )
        hierarchy = {item["id"]: item for item in receipt["planning_hierarchy"]}
        self.assertIsNone(hierarchy["fixture-leaf"]["produces"])


if __name__ == "__main__":
    unittest.main()
