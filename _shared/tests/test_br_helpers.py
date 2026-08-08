import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
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
        "patch_artifact: /tmp/run/patches/skills-exec-001.patch",
        "result_artifact: /tmp/run/results/skills-exec-001_RESULT.md",
        "apply_receipt: /tmp/run/receipts/skills-exec-001.apply.json",
        "apply_log: /tmp/run/receipts/skills-exec-001.apply.log",
        "close_receipt: /tmp/run/receipts/skills-exec-001.close.json",
        "close_log: /tmp/run/receipts/skills-exec-001.close.log",
        "transaction_driver: /tmp/run/capture_writer_transaction.py",
        "policy_home: /policy",
        "worker_write_authority:",
        "  - /tmp/run/results/skills-exec-001_RESULT.md",
        "apply_step_json:",
        "  - [\"git\",\"apply\",\"/tmp/run/patches/skills-exec-001.patch\"]",
        "close_step_json:",
        "  - [\"br\",\"close\",\"skills-exec-001\"]",
        "completion_protocol:",
        "  - Validate and close through the transaction driver",
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


PLAN = "loop-indispensable"


def plan_node(
    issue_id: str,
    roles,
    *,
    plan: str = PLAN,
    plan_state: str | None = None,
    plan_evidence: str | None = None,
    supports: str | None = None,
    local_criteria: str | None = None,
    writes=("src/module_a.py",),
    concern: str | None = "contract",
    run_dir: str | None = "/invocations/repo/divide-and-conquer/2026-07-25T00-00-00Z",
    expected_assignee: str | None = "dac-worker-001",
    validate: bool = True,
) -> dict:
    """Build one accepted-plan Beads issue in the canonical vocabulary."""
    labels = [f"plan:{plan}", "risk:none"]
    labels += [f"plan-role:{role}" for role in roles]
    if plan_state:
        labels.append(f"plan-state:{plan_state}")
    if plan_evidence:
        labels.append(f"plan-evidence:{plan_evidence}")
    if concern:
        labels.append(f"concern:{concern}")

    notes = []
    if validate:
        notes += ["validate:", "  - pytest -q"]
    notes += [
        "model_route: Codex gpt-5.6-sol medium",
        "repo_path: /repo",
        "branch: main",
        "planning_parent: none",
        "produces: named proof artifact",
    ]
    if run_dir is not None:
        notes.append(f"run_dir: {run_dir}")
    if expected_assignee is not None:
        notes.append(f"expected_assignee: {expected_assignee}")
    if supports:
        notes.append(f"supports: {supports}")
    if local_criteria:
        notes.append(f"local_criteria: {local_criteria}")

    design = []
    if writes:
        design += ["writes:"] + [f"  - {scope}" for scope in writes]
    design += ["global_constraints:", "  - No remote push"]

    return {
        "id": issue_id,
        "title": f"{issue_id} title",
        "status": "open",
        "labels": labels,
        "notes": "\n".join(notes),
        "design": "\n".join(design),
        "acceptance_criteria": "Named proof exists.",
        "dependencies": [],
    }


@contextmanager
def plan_graph(nodes: list[dict], frontier_ids: list[str]):
    """Patch the br read paths so admission sees one isolated fixture graph."""
    by_id = {node["id"]: node for node in nodes}
    frontier = [by_id[issue_id] for issue_id in frontier_ids]
    with mock.patch.object(MODULE, "list_issues", return_value=list(nodes)), \
         mock.patch.object(MODULE, "ready_frontier", return_value=frontier), \
         mock.patch.object(MODULE, "show_issue", side_effect=lambda iid: by_id[iid]), \
         mock.patch.object(MODULE, "issue_comments", return_value=[]):
        yield


def reasons(result: dict) -> list[str]:
    return [rejection["reason"] for rejection in result["rejected"]]


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
        self.assertEqual(contract["result_artifact"], "/tmp/run/results/skills-exec-001_RESULT.md")
        self.assertEqual(contract["patch_artifact"], "/tmp/run/patches/skills-exec-001.patch")
        self.assertEqual(contract["apply_receipt"], "/tmp/run/receipts/skills-exec-001.apply.json")
        self.assertEqual(contract["apply_log"], "/tmp/run/receipts/skills-exec-001.apply.log")
        self.assertEqual(contract["close_receipt"], "/tmp/run/receipts/skills-exec-001.close.json")
        self.assertEqual(contract["close_log"], "/tmp/run/receipts/skills-exec-001.close.log")
        self.assertEqual(contract["transaction_driver"], "/tmp/run/capture_writer_transaction.py")
        self.assertEqual(contract["policy_home"], "/policy")
        self.assertEqual(contract["worker_write_authority"], ["/tmp/run/results/skills-exec-001_RESULT.md"])
        self.assertEqual(contract["apply_step_json"], ['["git","apply","/tmp/run/patches/skills-exec-001.patch"]'])
        self.assertEqual(contract["close_step_json"], ['["br","close","skills-exec-001"]'])
        self.assertEqual(contract["completion_protocol"], ["Validate and close through the transaction driver"])
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
        self.assertIn("Protected completion contract:", brief)
        self.assertIn("Transaction driver: /tmp/run/capture_writer_transaction.py", brief)
        self.assertIn("Result artifact: /tmp/run/results/skills-exec-001_RESULT.md", brief)
        self.assertIn("Patch artifact: /tmp/run/patches/skills-exec-001.patch", brief)
        self.assertIn("Apply receipt: /tmp/run/receipts/skills-exec-001.apply.json", brief)
        self.assertIn("Apply log: /tmp/run/receipts/skills-exec-001.apply.log", brief)
        self.assertIn("Close receipt: /tmp/run/receipts/skills-exec-001.close.json", brief)
        self.assertIn("Close log: /tmp/run/receipts/skills-exec-001.close.log", brief)
        self.assertIn('- ["git","apply","/tmp/run/patches/skills-exec-001.patch"]', brief)
        self.assertIn('- ["br","close","skills-exec-001"]', brief)
        self.assertIn("Do not call `br close` or `br update` directly", brief)
        self.assertIn("Pass validation only through the rendered apply step JSON", brief)
        self.assertIn("Invoke the transaction driver in apply mode", brief)
        self.assertNotIn("`--close-only`", brief)
        self.assertNotIn("Run your validate commands before declaring success", brief)
        self.assertNotIn("On done: `br close", brief)

    def test_render_node_brief_preserves_legacy_direct_completion(self) -> None:
        legacy = dict(ISSUE)
        legacy["design"] = "\n".join([
            "writes:",
            "  - divide-and-conquer/SKILL.md",
            "stop_rules:",
            "  - Stop if br cannot expose rich fields",
            "non_goals:",
            "  - Do not edit unrelated skills",
            "global_constraints:",
            "  - No remote push",
        ])
        with mock.patch.object(MODULE, "show_issue", return_value=legacy), mock.patch.object(
            MODULE, "issue_comments", return_value=[]
        ):
            brief = MODULE.render_node_brief("skills-exec-001")

        self.assertNotIn("Protected completion contract:", brief)
        self.assertIn("On done: `br close", brief)
        self.assertIn("On blocked: `br update", brief)
        self.assertIn("Run your validate commands before declaring success", brief)

    def test_render_node_brief_routes_read_only_close_through_driver(self) -> None:
        read_only = dict(ISSUE)
        read_only["design"] = "\n".join([
            "result_artifact: /tmp/run/results/review_RESULT.md",
            "close_receipt: /tmp/run/receipts/review.close.json",
            "close_log: /tmp/run/receipts/review.close.log",
            "transaction_driver: /tmp/run/capture_writer_transaction.py",
            "worker_write_authority:",
            "  - /tmp/run/results/review_RESULT.md",
            "close_step_json:",
            "  - [\"br\",\"close\",\"review\"]",
            "completion_protocol:",
            "  - Validate read-only evidence then close through the driver",
            "writes:",
            "  - /tmp/run/results/review_RESULT.md",
            "global_constraints:",
            "  - No remote push",
        ])
        with mock.patch.object(MODULE, "show_issue", return_value=read_only), mock.patch.object(
            MODULE, "issue_comments", return_value=[]
        ):
            brief = MODULE.render_node_brief("skills-exec-001")

        self.assertIn("Protected completion contract:", brief)
        self.assertIn("Invoke the transaction driver with `--close-only`", brief)
        self.assertNotIn("On done: `br close", brief)
        self.assertNotIn("Run your validate commands before declaring success", brief)

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

    def test_render_workgraph_unions_plan_labeled_external_nodes(self) -> None:
        root = {
            "id": "skills-epic-001",
            "title": "Epic",
            "status": "open",
            "labels": ["plan:repo-atlas", "plan-role:root"],
        }
        child = {
            "id": "skills-child-001",
            "title": "Child",
            "status": "open",
            "labels": ["plan:repo-atlas", "plan-role:execution-leaf"],
        }
        external = {
            "id": "skills-external-001",
            "title": "External consumer",
            "status": "open",
            "labels": ["plan:repo-atlas", "plan-role:integration"],
        }

        def fake_list_issues(**kwargs):
            if kwargs.get("parent") == "skills-epic-001":
                return [root, child]
            if kwargs.get("labels") == ("plan:repo-atlas",):
                return [root, child, external]
            return []

        issues = {item["id"]: item for item in (root, child, external)}
        with mock.patch.object(MODULE, "list_issues", side_effect=fake_list_issues), \
             mock.patch.object(MODULE, "show_issue", side_effect=lambda iid: issues[iid]):
            rendered = MODULE.render_workgraph(epic="skills-epic-001")

        self.assertEqual(rendered.count("skills-external-001"), 1)
        self.assertEqual(rendered.count("skills-epic-001"), 1)
        self.assertEqual(rendered.count("skills-child-001"), 1)
        self.assertIn("External consumer", rendered)

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


class AcceptedPlanIntakeTests(unittest.TestCase):
    """`no-ragrets` handoff-ready graphs are consumed, never reminted."""

    def accepted_root(self, **kwargs) -> dict:
        return plan_node(
            "plan-root",
            ["root"],
            plan_state="handoff-ready",
            writes=(),
            concern=None,
            **kwargs,
        )

    def test_admits_ready_execution_leaf_integration_and_review(self) -> None:
        nodes = [
            self.accepted_root(),
            plan_node("plan-leaf-1", ["execution-leaf"], writes=("src/a.py",)),
            plan_node("plan-int-1", ["integration"], writes=("src/b.py",)),
            plan_node("plan-rev-1", ["review"], writes=()),
        ]
        with plan_graph(nodes, ["plan-leaf-1", "plan-int-1", "plan-rev-1"]):
            result = MODULE.plan_admission(PLAN)

        self.assertTrue(result["ok"], result["rejected"])
        self.assertTrue(result["handoff_ready"])
        self.assertEqual(result["root"]["id"], "plan-root")
        self.assertEqual(
            [node["id"] for node in result["admitted"]],
            ["plan-leaf-1", "plan-int-1", "plan-rev-1"],
        )
        self.assertEqual(
            sorted(node["plan_role"] for node in result["admitted"]),
            ["execution-leaf", "integration", "review"],
        )
        # Consumed, not reminted: admission is a read path only.
        self.assertTrue(all(node["dispatch_ready"] for node in result["admitted"]))

    def test_root_and_branch_never_dispatch_even_when_otherwise_ready(self) -> None:
        nodes = [
            self.accepted_root(),
            plan_node("plan-branch-1", ["branch"], writes=()),
            plan_node("plan-leaf-1", ["execution-leaf"]),
        ]
        # Both grouping nodes are fully hydrated and returned by `br ready`.
        with plan_graph(nodes, ["plan-root", "plan-branch-1", "plan-leaf-1"]):
            result = MODULE.plan_admission(PLAN)

        admitted_ids = [node["id"] for node in result["admitted"]]
        self.assertEqual(admitted_ids, ["plan-leaf-1"])
        self.assertNotIn("plan-root", admitted_ids)
        self.assertNotIn("plan-branch-1", admitted_ids)
        self.assertFalse(result["ok"])
        self.assertEqual(reasons(result), ["plan_role_not_dispatchable"] * 2)
        for rejection in result["rejected"]:
            self.assertIn("never dispatch", rejection["repair"])

    def test_draft_and_synthesized_plans_reject_with_repair(self) -> None:
        for state in ("draft", "synthesized", None):
            with self.subTest(state=state):
                nodes = [
                    plan_node("plan-root", ["root"], plan_state=state, writes=(), concern=None),
                    plan_node("plan-leaf-1", ["execution-leaf"]),
                ]
                with plan_graph(nodes, ["plan-leaf-1"]):
                    result = MODULE.plan_admission(PLAN)

                self.assertFalse(result["ok"])
                self.assertFalse(result["handoff_ready"])
                self.assertIn("plan_state_not_handoff_ready", reasons(result))
                repair = result["rejected"][0]["repair"]
                self.assertIn("plan-state:handoff-ready", repair)

    def test_allow_draft_plan_inspects_without_enforcing_the_gate(self) -> None:
        nodes = [
            plan_node("plan-root", ["root"], plan_state="draft", writes=(), concern=None),
            plan_node("plan-leaf-1", ["execution-leaf"]),
        ]
        with plan_graph(nodes, ["plan-leaf-1"]):
            result = MODULE.plan_admission(PLAN, require_handoff_ready=False)

        self.assertTrue(result["ok"])
        self.assertFalse(result["handoff_ready"])
        self.assertEqual(result["plan_state"], "draft")

    def test_missing_and_duplicate_accepted_roots_reject(self) -> None:
        leaf_only = [plan_node("plan-leaf-1", ["execution-leaf"])]
        with plan_graph(leaf_only, ["plan-leaf-1"]):
            missing = MODULE.plan_admission(PLAN)
        self.assertFalse(missing["ok"])
        self.assertIn("plan_root_missing", reasons(missing))
        self.assertIsNone(missing["root"])

        duplicated = [
            self.accepted_root(),
            plan_node("plan-root-2", ["root"], plan_state="handoff-ready", writes=(), concern=None),
            plan_node("plan-leaf-1", ["execution-leaf"]),
        ]
        with plan_graph(duplicated, ["plan-leaf-1"]):
            duplicate = MODULE.plan_admission(PLAN)
        self.assertFalse(duplicate["ok"])
        self.assertIn("plan_root_duplicate", reasons(duplicate))
        self.assertIn("plan-role:branch", duplicate["rejected"][0]["repair"])

    def test_missing_and_ambiguous_plan_roles_reject(self) -> None:
        nodes = [
            self.accepted_root(),
            plan_node("plan-norole-1", []),
            plan_node("plan-dual-1", ["execution-leaf", "branch"]),
            plan_node("plan-bogus-1", ["executable"]),
        ]
        with plan_graph(nodes, ["plan-norole-1", "plan-dual-1", "plan-bogus-1"]):
            result = MODULE.plan_admission(PLAN)

        self.assertEqual(result["admitted"], [])
        self.assertEqual(
            reasons(result),
            ["plan_role_missing", "plan_role_ambiguous", "plan_role_unknown"],
        )
        self.assertIn("plan-role:execution-leaf", result["rejected"][0]["repair"])

    def test_missing_run_dir_assignee_or_concern_rejects_with_repair(self) -> None:
        cases = [
            ("plan-noconcern", {"concern": None}, "concern_label_missing", "concern:"),
            ("plan-norun", {"run_dir": None}, "hydration_incomplete", "--run-dir"),
            ("plan-placeholder-run", {"run_dir": "<absolute-run-dir>"}, "run_dir_placeholder", "--run-dir"),
            ("plan-relative-run", {"run_dir": "run/dir"}, "run_dir_placeholder", "--run-dir"),
            ("plan-noassignee", {"expected_assignee": None}, "hydration_incomplete", "--expected-assignee"),
            (
                "plan-placeholder-assignee",
                {"expected_assignee": "TBD"},
                "expected_assignee_placeholder",
                "--expected-assignee",
            ),
            ("plan-novalidate", {"validate": False}, "hydration_incomplete", "--validate"),
        ]
        for issue_id, overrides, expected_reason, repair_hint in cases:
            with self.subTest(case=issue_id):
                nodes = [self.accepted_root(), plan_node(issue_id, ["execution-leaf"], **overrides)]
                with plan_graph(nodes, [issue_id]):
                    result = MODULE.plan_admission(PLAN)

                self.assertEqual(result["admitted"], [])
                self.assertFalse(result["ok"])
                self.assertEqual(reasons(result), [expected_reason])
                rejection = result["rejected"][0]
                self.assertEqual(rejection["id"], issue_id)
                self.assertIn(repair_hint, rejection["repair"])
                self.assertTrue(rejection["detail"])

    def test_historical_evidence_never_dispatches_or_inflates_coverage(self) -> None:
        nodes = [
            self.accepted_root(local_criteria="SC-1,SC-2"),
            plan_node("plan-leaf-1", ["execution-leaf"], supports="SC-1"),
            plan_node("plan-hist-role", ["historical-evidence"], supports="SC-2", writes=()),
            plan_node(
                "plan-hist-label",
                ["execution-leaf"],
                plan_evidence="historical-only",
                supports="SC-2",
                writes=(),
            ),
        ]
        with plan_graph(nodes, ["plan-leaf-1", "plan-hist-role", "plan-hist-label"]):
            result = MODULE.plan_admission(PLAN)

        self.assertEqual([node["id"] for node in result["admitted"]], ["plan-leaf-1"])
        self.assertEqual(
            sorted(node["id"] for node in result["excluded_historical"]),
            ["plan-hist-label", "plan-hist-role"],
        )
        # Excluded, not rejected: historical provenance is legitimate, just not work.
        self.assertEqual(result["rejected"], [])
        self.assertTrue(result["ok"])
        # SC-2 is supported ONLY by historical nodes, so it must still read uncovered.
        self.assertEqual(result["coverage"]["declared"], ["SC-1", "SC-2"])
        self.assertEqual(result["coverage"]["covered"], ["SC-1"])
        self.assertEqual(result["coverage"]["uncovered"], ["SC-2"])
        self.assertEqual(result["coverage"]["by_criterion"]["SC-1"], ["plan-leaf-1"])
        self.assertEqual(result["coverage"]["by_criterion"]["SC-2"], [])

    def test_overlapping_exact_and_glob_writes_cannot_be_concurrently_admitted(self) -> None:
        nodes = [
            self.accepted_root(),
            plan_node("plan-leaf-exact", ["execution-leaf"], writes=("divide-and-conquer/SKILL.md",)),
            plan_node("plan-leaf-glob", ["execution-leaf"], writes=("divide-and-conquer/**",)),
            plan_node("plan-leaf-clear", ["execution-leaf"], writes=("_shared/scripts/br_helpers.py",)),
        ]
        with plan_graph(nodes, ["plan-leaf-exact", "plan-leaf-glob", "plan-leaf-clear"]):
            result = MODULE.plan_admission(PLAN)

        admitted_ids = [node["id"] for node in result["admitted"]]
        self.assertIn("plan-leaf-exact", admitted_ids)
        self.assertIn("plan-leaf-clear", admitted_ids)
        self.assertNotIn("plan-leaf-glob", admitted_ids)

        # No admitted pair may share a write scope.
        for left in result["admitted"]:
            for right in result["admitted"]:
                if left["id"] == right["id"]:
                    continue
                for a in left["writes"]:
                    for b in right["writes"]:
                        self.assertFalse(
                            MODULE._scopes_overlap(a, b),
                            f"{left['id']} and {right['id']} share {a!r}/{b!r}",
                        )

        self.assertEqual([entry["id"] for entry in result["deferred"]], ["plan-leaf-glob"])
        self.assertEqual(result["deferred"][0]["reason"], "write_scope_overlap")
        edge = result["serialization_edges"][0]
        self.assertEqual(edge["blocked"], "plan-leaf-glob")
        self.assertEqual(edge["blocked_by"], "plan-leaf-exact")
        self.assertFalse(edge["materialized"])
        self.assertEqual(edge["repair"], "br dep add plan-leaf-glob plan-leaf-exact")

    def test_materialize_serialization_writes_the_ordering_edge(self) -> None:
        nodes = [
            self.accepted_root(),
            plan_node("plan-leaf-exact", ["execution-leaf"], writes=("skill/SKILL.md",)),
            plan_node("plan-leaf-glob", ["execution-leaf"], writes=("skill/**",)),
        ]
        with plan_graph(nodes, ["plan-leaf-exact", "plan-leaf-glob"]), \
             mock.patch.object(MODULE, "_run") as run:
            result = MODULE.plan_admission(PLAN, materialize_serialization=True)

        run.assert_called_once_with(
            ["dep", "add", "plan-leaf-glob", "plan-leaf-exact"], capture=True
        )
        self.assertTrue(result["serialization_edges"][0]["materialized"])

    def test_helper_side_filtering_ignores_foreign_plan_labels(self) -> None:
        foreign = plan_node("other-leaf", ["execution-leaf"], plan="other-plan")
        nodes = [self.accepted_root(), plan_node("plan-leaf-1", ["execution-leaf"]), foreign]
        by_id = {node["id"]: node for node in nodes}
        with mock.patch.object(MODULE, "list_issues", return_value=nodes), \
             mock.patch.object(MODULE, "ready_frontier", return_value=[by_id["plan-leaf-1"], foreign]), \
             mock.patch.object(MODULE, "show_issue", side_effect=lambda iid: by_id[iid]), \
             mock.patch.object(MODULE, "issue_comments", return_value=[]):
            result = MODULE.plan_admission(PLAN)

        self.assertEqual([node["id"] for node in result["admitted"]], ["plan-leaf-1"])
        self.assertTrue(result["ok"])

    def test_thin_ready_rows_are_hydrated_before_the_label_filter(self) -> None:
        """`br ready --json` omits labels/notes on some versions.

        Filtering the raw row would silently drop the entire frontier, so thin
        rows must be resolved through `br show` first.
        """
        nodes = [self.accepted_root(), plan_node("plan-leaf-1", ["execution-leaf"])]
        by_id = {node["id"]: node for node in nodes}
        thin_row = {"id": "plan-leaf-1", "title": "plan-leaf-1 title", "status": "open"}
        with mock.patch.object(MODULE, "list_issues", return_value=[]), \
             mock.patch.object(MODULE, "ready_frontier", return_value=[thin_row]), \
             mock.patch.object(MODULE, "show_issue", side_effect=lambda iid: by_id[iid]), \
             mock.patch.object(MODULE, "issue_comments", return_value=[]):
            result = MODULE.plan_admission(PLAN, require_handoff_ready=False)

        self.assertEqual([node["id"] for node in result["admitted"]], ["plan-leaf-1"])

    def test_scopes_overlap_matrix(self) -> None:
        overlapping = [
            ("src/a.py", "src/a.py"),
            ("src/a.py", "src/**"),
            ("src/**", "src/nested/deep.py"),
            ("./src/a.py", "src/a.py"),
            ("src", "src/a.py"),
            ("src/", "src/a.py"),
        ]
        disjoint = [
            ("src/a.py", "src/b.py"),
            ("src/**", "docs/**"),
            ("_shared/scripts/br_helpers.py", "divide-and-conquer/SKILL.md"),
            ("", "src/a.py"),
        ]
        for left, right in overlapping:
            with self.subTest(pair=(left, right)):
                self.assertTrue(MODULE._scopes_overlap(left, right))
                self.assertTrue(MODULE._scopes_overlap(right, left))
        for left, right in disjoint:
            with self.subTest(pair=(left, right)):
                self.assertFalse(MODULE._scopes_overlap(left, right))
                self.assertFalse(MODULE._scopes_overlap(right, left))


class ReadyCliPlanModeTests(unittest.TestCase):
    def test_generic_ready_slice_behavior_is_unchanged(self) -> None:
        ready = [{"id": "skills-exec-001"}]
        with mock.patch.object(MODULE, "ready_frontier", return_value=ready) as frontier, \
             mock.patch.object(MODULE, "plan_admission") as admission:
            exit_code, stdout = run_cli(["ready", "--label", "slice:demo"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), ready)
        frontier.assert_called_once_with(limit=20, labels=["slice:demo"])
        admission.assert_not_called()

    def test_plan_mode_emits_admission_and_exits_zero_when_ok(self) -> None:
        payload = {"plan": PLAN, "ok": True, "admitted": []}
        with mock.patch.object(MODULE, "plan_admission", return_value=payload) as admission:
            exit_code, stdout = run_cli(
                ["ready", "--plan", PLAN, "--require-handoff-ready", "--limit", "5"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), payload)
        admission.assert_called_once_with(
            PLAN, limit=5, require_handoff_ready=True, materialize_serialization=False
        )

    def test_plan_mode_exits_nonzero_when_admission_is_rejected(self) -> None:
        payload = {"plan": PLAN, "ok": False, "rejected": [{"reason": "plan_root_missing"}]}
        with mock.patch.object(MODULE, "plan_admission", return_value=payload):
            exit_code, stdout = run_cli(["ready", "--plan", PLAN, "--require-handoff-ready"])

        self.assertEqual(exit_code, 2)
        self.assertFalse(json.loads(stdout)["ok"])

    def test_plan_flags_are_rejected_without_a_plan_and_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            run_cli(["ready", "--require-handoff-ready"])
        with self.assertRaises(SystemExit):
            run_cli(["ready", "--plan", PLAN, "--require-handoff-ready", "--allow-draft-plan"])


class MintSubgoalTests(unittest.TestCase):
    def test_mint_subgoal_writes_the_controller_contract(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[0] == "create":
                return SimpleNamespace(stdout='{"id": "skills-subgoal-auth"}')
            return SimpleNamespace(stdout="{}")

        with mock.patch.object(MODULE, "_run", fake_run):
            issue_id = MODULE.mint_subgoal(
                "auth",
                "Subgoal: auth hardening",
                slice_slug="loop",
                writes=["backend/auth/**"],
                shared_files=["backend/migrations/**"],
                stop_rules=["Escalate cross-subgoal edits to the root"],
                escalation=["Root planning authority"],
                parent_run_dir="/inv/run",
                subgoal_run_dir="/inv/run/subgoals/auth",
                max_workers=3,
                status_artifact="/inv/run/subgoals/auth/SUBGOAL_RESULT.md",
                depends_on=["skills-epic-001"],
                epic="skills-epic-001",
            )

        self.assertEqual(issue_id, "skills-subgoal-auth")
        create_args = calls[0]
        self.assertEqual(create_args[0], "create")
        labels = create_args[create_args.index("--labels") + 1]
        self.assertIn("slice:loop", labels)
        self.assertIn("subgoal:auth", labels)
        self.assertIn("subgoal-role:controller", labels)
        self.assertEqual(create_args[create_args.index("--slug") + 1], "subgoal-auth")

        update_args = calls[1]
        design = update_args[update_args.index("--design") + 1]
        self.assertIn("writes:\n  - backend/auth/**", design)
        self.assertIn("shared_files:\n  - backend/migrations/**", design)
        self.assertIn("escalation:\n  - Root planning authority", design)
        notes = update_args[update_args.index("--notes") + 1]
        self.assertIn("subgoal_id: auth", notes)
        self.assertIn("parent_slice: loop", notes)
        self.assertIn("frontier_filter: slice:loop,subgoal:auth", notes)
        self.assertIn("subgoal_run_dir: /inv/run/subgoals/auth", notes)
        self.assertIn("max_workers: 3", notes)
        self.assertIn("isolation: checkout", notes)
        self.assertEqual(calls[2], ["dep", "add", "skills-subgoal-auth", "skills-epic-001"])

    def test_main_mint_subgoal_delegates_with_flags(self) -> None:
        with mock.patch.object(MODULE, "mint_subgoal", return_value="skills-subgoal-auth") as mint:
            exit_code, stdout = run_cli(
                [
                    "mint-subgoal",
                    "auth",
                    "Subgoal: auth hardening",
                    "--slice", "loop",
                    "--writes", "backend/auth/**",
                    "--shared-file", "backend/migrations/**",
                    "--max-workers", "3",
                    "--isolation", "worktree",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout), {"id": "skills-subgoal-auth"})
        kwargs = mint.call_args.kwargs
        self.assertEqual(kwargs["slug"], "auth")
        self.assertEqual(kwargs["slice_slug"], "loop")
        self.assertEqual(kwargs["writes"], ["backend/auth/**"])
        self.assertEqual(kwargs["shared_files"], ["backend/migrations/**"])
        self.assertEqual(kwargs["max_workers"], 3)
        self.assertEqual(kwargs["isolation"], "worktree")


if __name__ == "__main__":
    unittest.main()
