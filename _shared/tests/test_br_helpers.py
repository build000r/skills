import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE = SourceFileLoader(
    "br_helpers",
    str((Path(__file__).resolve().parent.parent / "scripts" / "br_helpers.py").resolve()),
).load_module()


ISSUE = {
    "id": "skills-exec-001",
    "title": "Patch contract",
    "status": "in_progress",
    "assignee": "worker-1",
    "description": "Make the worker contract Beads-backed.",
    "acceptance_criteria": "\n".join([
        "Worker prompt renders from br state.",
        "Markdown execution packs are generated views only.",
    ]),
    "notes": "\n".join([
        "validate:",
        "  - python3 -m py_compile _shared/scripts/br_helpers.py",
        "model_route: Codex gpt-5",
        "repo_path: /repo",
        "branch: main",
        "run_dir: /tmp/run",
        "expected_assignee: worker-1",
    ]),
    "design": "\n".join([
        "writes:",
        "  - divide-and-conquer/SKILL.md",
        "stop_rules:",
        "  - Stop if br cannot expose rich fields",
        "non_goals:",
        "  - Do not edit unrelated skills",
        "global_constraints:",
        "  - No remote push",
    ]),
    "labels": ["concern:contract", "repo:skills", "risk:none"],
    "dependencies": [{"depends_on_id": "skills-epic-001"}],
}


class BrHelpersTests(unittest.TestCase):
    def test_hydrate_node_contract_reads_dispatch_fields_from_beads_issue(self) -> None:
        with mock.patch.object(MODULE, "show_issue", return_value=ISSUE), mock.patch.object(
            MODULE, "issue_comments", return_value=[]
        ):
            contract = MODULE.hydrate_node_contract("skills-exec-001")

        self.assertTrue(contract["dispatch_ready"])
        self.assertEqual(contract["concern"], "contract")
        self.assertEqual(contract["repo"], "skills")
        self.assertEqual(contract["risk_gate"], "none")
        self.assertEqual(contract["writes"], ["divide-and-conquer/SKILL.md"])
        self.assertEqual(contract["validate_cmds"], ["python3 -m py_compile _shared/scripts/br_helpers.py"])
        self.assertEqual(contract["model_route"], "Codex gpt-5")
        self.assertEqual(contract["repo_path"], "/repo")
        self.assertEqual(contract["branch"], "main")
        self.assertEqual(contract["run_dir"], "/tmp/run")
        self.assertEqual(contract["expected_assignee"], "worker-1")
        self.assertEqual(contract["global_constraints"], ["No remote push"])
        self.assertEqual(contract["depends_on"], ["skills-epic-001"])

    def test_render_node_brief_uses_hydrated_contract(self) -> None:
        with mock.patch.object(MODULE, "show_issue", return_value=ISSUE), mock.patch.object(
            MODULE, "issue_comments", return_value=[]
        ):
            brief = MODULE.render_node_brief("skills-exec-001")

        self.assertIn("Source of truth: br", brief)
        self.assertIn("Issue ID: skills-exec-001", brief)
        self.assertIn("- divide-and-conquer/SKILL.md", brief)
        self.assertIn("- python3 -m py_compile _shared/scripts/br_helpers.py", brief)
        self.assertIn("Model route: Codex gpt-5", brief)
        self.assertIn("Expected Beads assignee: worker-1", brief)
        self.assertIn("Repo path: /repo", brief)
        self.assertIn("- No remote push", brief)

    def test_render_node_brief_fails_when_dispatch_fields_are_missing(self) -> None:
        incomplete = dict(ISSUE)
        incomplete["notes"] = "validate:\n  - python3 -m py_compile _shared/scripts/br_helpers.py"
        incomplete["acceptance_criteria"] = ""
        with mock.patch.object(MODULE, "show_issue", return_value=incomplete), mock.patch.object(
            MODULE, "issue_comments", return_value=[]
        ):
            with self.assertRaisesRegex(RuntimeError, "missing done_when, model_route"):
                MODULE.render_node_brief("skills-exec-001")

    def test_render_workgraph_includes_rich_beads_contract_fields(self) -> None:
        with mock.patch.object(
            MODULE, "_json", return_value={"issues": [{"id": "skills-exec-001", "title": "Patch contract"}]}
        ), mock.patch.object(MODULE, "show_issue", return_value=ISSUE):
            rendered = MODULE.render_workgraph()

        self.assertIn("writes: divide-and-conquer/SKILL.md", rendered)
        self.assertIn("done_when: Worker prompt renders from br state.", rendered)
        self.assertIn("validate: python3 -m py_compile _shared/scripts/br_helpers.py", rendered)
        self.assertIn("model_route: Codex gpt-5", rendered)
        self.assertIn("repo_path: /repo", rendered)
        self.assertIn("global_constraints: No remote push", rendered)

    def test_update_node_preserves_existing_notes_on_partial_validate_update(self) -> None:
        calls = []

        def fake_json(args):
            calls.append(args)
            return [ISSUE]

        with mock.patch.object(MODULE, "show_issue", return_value=ISSUE), mock.patch.object(MODULE, "_json", fake_json):
            MODULE.update_node_contract("skills-exec-001", validate=["pytest"])

        update_args = calls[-1]
        notes = update_args[update_args.index("--notes") + 1]
        self.assertIn("validate:\n  - pytest", notes)
        self.assertIn("model_route: Codex gpt-5", notes)
        self.assertIn("repo_path: /repo", notes)
        self.assertIn("branch: main", notes)
        self.assertIn("run_dir: /tmp/run", notes)
        self.assertIn("expected_assignee: worker-1", notes)
        self.assertNotIn("--design", update_args)

    def test_update_node_preserves_existing_design_blocks_on_partial_writes_update(self) -> None:
        calls = []

        def fake_json(args):
            calls.append(args)
            return [ISSUE]

        with mock.patch.object(MODULE, "show_issue", return_value=ISSUE), mock.patch.object(MODULE, "_json", fake_json):
            MODULE.update_node_contract("skills-exec-001", writes=["new/path.py"])

        update_args = calls[-1]
        design = update_args[update_args.index("--design") + 1]
        self.assertIn("writes:\n  - new/path.py", design)
        self.assertIn("stop_rules:\n  - Stop if br cannot expose rich fields", design)
        self.assertIn("non_goals:\n  - Do not edit unrelated skills", design)
        self.assertIn("global_constraints:\n  - No remote push", design)
        self.assertNotIn("--notes", update_args)

    def test_mint_node_writes_full_dispatch_contract(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[0] == "create":
                return SimpleNamespace(stdout='{"id": "skills-exec-002"}')
            return SimpleNamespace(stdout="{}")

        with mock.patch.object(MODULE, "_run", fake_run):
            issue_id = MODULE.mint_node(
                "exec-002",
                "New node",
                description="Do the node",
                writes=["src/**"],
                done_when="Done",
                validate=["pytest"],
                model_route="Codex gpt-5.5",
                repo_path="/repo",
                branch="main",
                run_dir="/run",
                stop_rules=["Stay scoped"],
                global_constraints=["No push"],
                expected_assignee="worker-2",
            )

        self.assertEqual(issue_id, "skills-exec-002")
        update_args = calls[1]
        self.assertIn("--description", update_args)
        self.assertIn("global_constraints:\n  - No push", update_args[update_args.index("--design") + 1])
        notes = update_args[update_args.index("--notes") + 1]
        self.assertIn("model_route: Codex gpt-5.5", notes)
        self.assertIn("repo_path: /repo", notes)
        self.assertIn("branch: main", notes)
        self.assertIn("run_dir: /run", notes)
        self.assertIn("expected_assignee: worker-2", notes)


if __name__ == "__main__":
    unittest.main()
