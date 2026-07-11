import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


RUN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run.py"
SPEC = importlib.util.spec_from_file_location("codex_tmux_run", RUN_PATH)
run = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(run)


def capture_status(args) -> tuple[int, dict, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = run.cmd_status(args)
    return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()


class ParseArgsModelPolicyTests(unittest.TestCase):
    def test_default_model_is_gpt_5_6_sol(self) -> None:
        args = run.parse_args(["launch", "--task", "noop", "--cd", "/tmp"])

        self.assertEqual(args.model, "gpt-5.6-sol")
        self.assertEqual(args.reasoning_effort, "medium")

    def test_terra_ultra_fallback_is_allowed(self) -> None:
        args = run.parse_args(
            [
                "launch",
                "--task",
                "noop",
                "--cd",
                "/tmp",
                "--model",
                "gpt-5.6-terra",
                "--reasoning-effort",
                "ultra",
            ]
        )

        self.assertEqual(args.model, "gpt-5.6-terra")
        self.assertEqual(args.reasoning_effort, "ultra")

    def test_gpt_5_4_is_allowed(self) -> None:
        args = run.parse_args(
            ["launch", "--task", "noop", "--cd", "/tmp", "--model", "gpt-5.4"]
        )

        self.assertEqual(args.model, "gpt-5.4")

    def test_gpt_5_4_mini_is_allowed(self) -> None:
        args = run.parse_args(
            ["launch", "--task", "noop", "--cd", "/tmp", "--model", "gpt-5.4-mini"]
        )

        self.assertEqual(args.model, "gpt-5.4-mini")

    def test_codex_mini_latest_is_allowed(self) -> None:
        args = run.parse_args(
            ["launch", "--task", "noop", "--cd", "/tmp", "--model", "codex-mini-latest"]
        )

        self.assertEqual(args.model, "codex-mini-latest")

    def test_openrouter_model_is_rejected(self) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                run.parse_args(
                    [
                        "launch",
                        "--task",
                        "noop",
                        "--cd",
                        "/tmp",
                        "--model",
                        "stepfun/step-3.5-flash:free",
                    ]
                )

        self.assertEqual(exc.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())


class CodexCommandTests(unittest.TestCase):
    def test_command_uses_search_and_non_interactive_approvals(self) -> None:
        command = run._build_codex_command(
            prompt="noop",
            repo="/tmp/repo",
            model="gpt-5.6-sol",
            reasoning_effort="high",
            codex_bin="codex",
        )

        self.assertEqual(
            command[:4],
            ["codex", "--search", "exec", "--dangerously-bypass-approvals-and-sandbox"],
        )
        self.assertIn("--cd", command)
        self.assertEqual(command[-1], "noop")


class StatusCommandTests(unittest.TestCase):
    def test_status_reports_running_session_with_tail(self) -> None:
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["tmux", "has-session"]:
                return SimpleNamespace(returncode=0)
            return SimpleNamespace(returncode=0, stdout="older\nlatest\n")

        args = SimpleNamespace(session="codex-status", result_dir=None)

        with mock.patch.object(run.subprocess, "run", fake_run):
            exit_code, payload, stderr = capture_status(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["session"], "codex-status")
        self.assertFalse(payload["has_result"])
        self.assertEqual(payload["tail"], "older\nlatest")
        self.assertIn(["tmux", "capture-pane", "-p", "-t", "codex-status", "-S", "-30"], calls)
        self.assertIn("codex-status: RUNNING", stderr)
        self.assertIn("Attach: tmux a -t codex-status", stderr)
        self.assertIn("latest", stderr)

    def test_status_reports_completed_session_with_result_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp)
            result_file = result_dir / "codex-done.json"
            result_file.write_text(
                json.dumps(
                    {
                        "session": "codex-done",
                        "exit_code": 0,
                        "commit_hash": "abcdef1234567890",
                        "commit_message": "finish",
                    }
                ),
                encoding="utf-8",
            )

            def fake_run(cmd, **kwargs):
                self.assertEqual(cmd, ["tmux", "has-session", "-t", "codex-done"])
                return SimpleNamespace(returncode=1)

            args = SimpleNamespace(session="codex-done", result_dir=str(result_dir))
            with mock.patch.object(run.subprocess, "run", fake_run):
                exit_code, payload, stderr = capture_status(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["has_result"])
        self.assertIn("codex-done: COMPLETED", stderr)
        self.assertIn("Commit: abcdef123456", stderr)

    def test_status_reports_session_without_result_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(session="codex-missing", result_dir=tmp)

            with mock.patch.object(
                run.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1),
            ):
                exit_code, payload, stderr = capture_status(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "completed_no_result")
        self.assertFalse(payload["has_result"])
        self.assertIn("codex-missing: ended with no result file", stderr)


class SkillDocModelPolicyTests(unittest.TestCase):
    def test_skill_docs_only_list_codex_native_models(self) -> None:
        skill_doc = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text()

        self.assertIn("`gpt-5.6-sol`", skill_doc)
        self.assertIn("`gpt-5.4`", skill_doc)
        self.assertIn("`gpt-5.4-mini`", skill_doc)
        self.assertIn("`codex-mini-latest`", skill_doc)
        self.assertNotIn("OpenRouter", skill_doc)
        self.assertNotIn("stepfun/step-3.5-flash:free", skill_doc)


if __name__ == "__main__":
    unittest.main()
