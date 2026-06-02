import contextlib
import importlib.util
import io
import unittest
from pathlib import Path


RUN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run.py"
SPEC = importlib.util.spec_from_file_location("codex_tmux_run", RUN_PATH)
run = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(run)


class ParseArgsModelPolicyTests(unittest.TestCase):
    def test_default_model_is_gpt_5_5(self) -> None:
        args = run.parse_args(["launch", "--task", "noop", "--cd", "/tmp"])

        self.assertEqual(args.model, "gpt-5.5")

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
            model="gpt-5.5",
            reasoning_effort="high",
            codex_bin="codex",
        )

        self.assertEqual(
            command[:4],
            ["codex", "--search", "exec", "--dangerously-bypass-approvals-and-sandbox"],
        )
        self.assertIn("--cd", command)
        self.assertEqual(command[-1], "noop")


class SkillDocModelPolicyTests(unittest.TestCase):
    def test_skill_docs_only_list_codex_native_models(self) -> None:
        skill_doc = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text()

        self.assertIn("`gpt-5.5`", skill_doc)
        self.assertIn("`gpt-5.4`", skill_doc)
        self.assertIn("`gpt-5.4-mini`", skill_doc)
        self.assertIn("`codex-mini-latest`", skill_doc)
        self.assertNotIn("OpenRouter", skill_doc)
        self.assertNotIn("stepfun/step-3.5-flash:free", skill_doc)


if __name__ == "__main__":
    unittest.main()
