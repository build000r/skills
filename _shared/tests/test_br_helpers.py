import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
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


def run_cli(argv: list[str]) -> tuple[int, str]:
    stdout = StringIO()
    with redirect_stdout(stdout):
        exit_code = MODULE.main(argv)
    return exit_code, stdout.getvalue()


class BrHelpersTests(unittest.TestCase):
    def test_main_ready_dispatches_and_emits_json(self) -> None:
        ready = [{"id": "skills-exec-001"}]

        with mock.patch.object(MODULE, "ready_frontier", return_value=ready) as ready_frontier:
            exit_code, stdout = run_cli(["ready", "--limit", "5", "--label", "chain:smart"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), ready)
        ready_frontier.assert_called_once_with(limit=5, labels=["chain:smart"])

    def test_main_mint_update_and_hydrate_commands_delegate_with_flags(self) -> None:
        with mock.patch.object(MODULE, "mint_node", return_value="skills-exec-002") as mint_node:
            exit_code, stdout = run_cli(
                [
                    "mint-node",
                    "exec-002",
                    "New node",
                    "--description",
                    "Do the node",
                    "--writes",
                    "src/**",
                    "--done-when",
                    "Done",
                    "--validate",
                    "pytest",
                    "--risk",
                    "medium",
                    "--depends-on",
                    "skills-epic-001",
                    "--label",
                    "chain:smart",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), {"id": "skills-exec-002"})
        mint_node.assert_called_once()
        self.assertEqual(mint_node.call_args.kwargs["slug"], "exec-002")
        self.assertEqual(mint_node.call_args.kwargs["writes"], ["src/**"])
        self.assertEqual(mint_node.call_args.kwargs["validate"], ["pytest"])
        self.assertEqual(mint_node.call_args.kwargs["depends_on"], ["skills-epic-001"])
        self.assertEqual(mint_node.call_args.kwargs["labels"], ["chain:smart"])

        with mock.patch.object(MODULE, "update_node_contract", return_value={"id": "skills-exec-002"}) as update_node:
            exit_code, stdout = run_cli(["update-node", "skills-exec-002", "--validate", "pytest"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), {"id": "skills-exec-002"})
        update_node.assert_called_once_with(
            "skills-exec-002",
            description=None,
            writes=[],
            done_when=None,
            validate=["pytest"],
            model_route=None,
            repo_path=None,
            branch=None,
            run_dir=None,
            stop_rules=[],
            non_goals=[],
            global_constraints=[],
            expected_assignee=None,
        )

        with mock.patch.object(MODULE, "hydrate_node_contract", return_value={"id": "skills-exec-002"}) as hydrate:
            exit_code, stdout = run_cli(["hydrate-node", "skills-exec-002", "--no-comments"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), {"id": "skills-exec-002"})
        hydrate.assert_called_once_with("skills-exec-002", include_comments=False)

    def test_main_claim_block_done_and_flush_emit_json(self) -> None:
        cases = [
            ("claim", ["claim", "skills-exec-001"], ("skills-exec-001",)),
            ("block", ["block", "skills-exec-001", "waiting"], ("skills-exec-001", "waiting")),
            ("done", ["done", "skills-exec-001", "finished"], ("skills-exec-001", "finished")),
            ("flush", ["flush"], ()),
        ]

        for command, argv, expected_args in cases:
            with self.subTest(command=command), mock.patch.object(
                MODULE,
                command,
                return_value={"command": command},
            ) as handler:
                exit_code, stdout = run_cli(argv)

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout), {"command": command})
            handler.assert_called_once_with(*expected_args)

    def test_main_render_commands_write_stdout_or_files(self) -> None:
        with mock.patch.object(MODULE, "render_node_brief", return_value="brief\n") as render_node:
            exit_code, stdout = run_cli(["render-node-brief", "skills-exec-001"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "brief\n")
        render_node.assert_called_once_with("skills-exec-001")

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "WORKGRAPH.md"
            with mock.patch.object(MODULE, "render_workgraph", return_value="# Workgraph\n") as render_workgraph:
                exit_code, stdout = run_cli(["render-workgraph", "--epic", "skills-epic-001", "--out", str(out_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(out_path.read_text(encoding="utf-8"), "# Workgraph\n")
            self.assertEqual(json.loads(stdout)["wrote"], str(out_path))
            render_workgraph.assert_called_once_with(epic="skills-epic-001")

    def test_main_render_mmdx_forwards_to_bridge_script(self) -> None:
        with mock.patch.object(MODULE.subprocess, "call", return_value=7) as call:
            exit_code = MODULE.main(
                [
                    "render-mmdx",
                    "--repo",
                    "/repo",
                    "--scan",
                    "/scan",
                    "--label",
                    "chain:smart",
                    "--out",
                    "graph.mmdx",
                    "--open",
                    "--print",
                ]
            )

        self.assertEqual(exit_code, 7)
        forwarded = call.call_args.args[0]
        self.assertEqual(forwarded[0], MODULE.sys.executable)
        self.assertTrue(forwarded[1].endswith("br_to_mmdx.py"))
        self.assertIn("--repo", forwarded)
        self.assertIn("/repo", forwarded)
        self.assertIn("--scan", forwarded)
        self.assertIn("/scan", forwarded)
        self.assertIn("--open", forwarded)
        self.assertIn("--print", forwarded)

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

    def test_list_issues_normalizes_br_list_envelope_with_cwd_and_labels(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='{"issues": [{"id": "skills-exec-001"}]}')

        repo = Path("/repo")
        with mock.patch.object(MODULE, "_run", fake_run):
            issues = MODULE.list_issues(cwd=repo, labels=["chain:smart"], include_closed=True)

        self.assertEqual(issues, [{"id": "skills-exec-001"}])
        self.assertEqual(calls[0][0], ["list", "--all", "--label", "chain:smart", "--json"])
        self.assertEqual(calls[0][1]["cwd"], repo)

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
                model_route="Codex gpt-5.6-sol",
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
        self.assertIn("model_route: Codex gpt-5.6-sol", notes)
        self.assertIn("repo_path: /repo", notes)
        self.assertIn("branch: main", notes)
        self.assertIn("run_dir: /run", notes)
        self.assertIn("expected_assignee: worker-2", notes)

    def test_ensure_initialized_preserves_curated_agents_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".beads").mkdir()
            agents = repo / "AGENTS.md"
            original = "\n".join([
                "# Project Agents",
                "",
                "<!-- bv-agent-instructions-v2 -->",
                "custom bv workflow",
                "<!-- end-bv-agent-instructions -->",
                "",
            ])
            agents.write_text(original, encoding="utf-8")
            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                if args == ["where"]:
                    return SimpleNamespace(stdout=str(repo), stderr="", returncode=0)
                return SimpleNamespace(stdout="", stderr="", returncode=0)

            with mock.patch.object(MODULE, "_run", fake_run):
                result = MODULE.ensure_initialized(repo)

            self.assertEqual(agents.read_text(encoding="utf-8"), original)
            self.assertNotIn(["agents", "--add", "--force"], calls)
            self.assertFalse(result["agents_updated"])
            self.assertIn("existing_curated_agents_block", result["agents_skip_reason"])

    def test_ensure_initialized_runs_br_commands_in_target_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            calls = []

            def fake_run(args, **kwargs):
                calls.append((args, kwargs))
                if args == ["where"]:
                    return SimpleNamespace(stdout=str(repo), stderr="", returncode=0)
                return SimpleNamespace(stdout="", stderr="", returncode=0)

            with mock.patch.object(MODULE, "_run", fake_run):
                result = MODULE.ensure_initialized(repo)

            self.assertEqual(result["where"], str(repo))
            self.assertEqual(calls[0][0], ["init"])
            self.assertEqual(calls[0][1]["cwd"], repo)
            self.assertEqual(calls[1][0], ["agents", "--add", "--force"])
            self.assertEqual(calls[1][1]["cwd"], repo)
            self.assertEqual(calls[2][0], ["where"])
            self.assertEqual(calls[2][1]["cwd"], repo)


class RenderWorkgraphFallbackTests(unittest.TestCase):
    def test_fallback_to_br_show_on_list_failure(self) -> None:
        import subprocess

        def fake_list_issues(**kwargs):
            raise subprocess.CalledProcessError(1, "br list --parent")

        root_issue = {
            "id": "skills-epic-001",
            "title": "Epic",
            "status": "open",
            "dependents": [{"id": "skills-child-001"}],
        }
        child_issue = {
            "id": "skills-child-001",
            "title": "Child task",
            "status": "in_progress",
        }

        def fake_json(args):
            if "skills-epic-001" in args:
                return root_issue
            if "skills-child-001" in args:
                return child_issue
            return {}

        with mock.patch.object(MODULE, "list_issues", side_effect=fake_list_issues), \
             mock.patch.object(MODULE, "_json", side_effect=fake_json), \
             mock.patch.object(MODULE, "show_issue", side_effect=lambda iid: {"id": iid}):
            rendered = MODULE.render_workgraph(epic="skills-epic-001")

        self.assertIn("skills-epic-001", rendered)
        self.assertIn("skills-child-001", rendered)

    def test_render_workgraph_without_epic(self) -> None:
        minimal = {
            "id": "skills-solo-001",
            "title": "Solo task",
            "status": "open",
        }
        with mock.patch.object(MODULE, "list_issues", return_value=[minimal]), \
             mock.patch.object(MODULE, "show_issue", return_value=minimal):
            rendered = MODULE.render_workgraph()

        self.assertIn("skills-solo-001", rendered)
        self.assertIn("WORKGRAPH", rendered)

    def test_render_workgraph_shows_labels_and_deps(self) -> None:
        issue = {
            "id": "skills-dep-001",
            "title": "Task with deps",
            "status": "open",
            "labels": ["chain:smart", "concern:test"],
            "dependencies": [{"depends_on_id": "skills-dep-000"}],
        }
        with mock.patch.object(MODULE, "list_issues", return_value=[issue]), \
             mock.patch.object(MODULE, "show_issue", return_value=issue):
            rendered = MODULE.render_workgraph()

        self.assertIn("chain:smart", rendered)
        self.assertIn("depends_on: skills-dep-000", rendered)

    def test_render_workgraph_include_closed_false(self) -> None:
        with mock.patch.object(MODULE, "list_issues", return_value=[]) as list_issues:
            MODULE.render_workgraph(include_closed=False)

        list_issues.assert_called_once_with(parent=None, include_closed=False)

    def test_fallback_with_list_envelope_return(self) -> None:
        import subprocess

        def fake_list_issues(**kwargs):
            raise subprocess.CalledProcessError(1, "br list --parent")

        root_issue = [{
            "id": "skills-epic-002",
            "title": "Epic 2",
            "status": "open",
            "dependents": [],
        }]

        with mock.patch.object(MODULE, "list_issues", side_effect=fake_list_issues), \
             mock.patch.object(MODULE, "_json", return_value=root_issue), \
             mock.patch.object(MODULE, "show_issue", return_value=root_issue[0]):
            rendered = MODULE.render_workgraph(epic="skills-epic-002")

        self.assertIn("skills-epic-002", rendered)


if __name__ == "__main__":
    unittest.main()
