import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "skill_review",
    str((Path(__file__).resolve().parent.parent / "scripts" / "lib" / "skill_review.py").resolve()),
).load_module()


class ToolInvocationCountTests(unittest.TestCase):
    @contextmanager
    def patch_session_dirs(self, codex_dir: Path, claude_dir: Path):
        original_codex = MODULE.CODEX_SESSIONS_DIR
        original_claude = MODULE.CLAUDE_PROJECTS_DIR
        MODULE.CODEX_SESSIONS_DIR = codex_dir
        MODULE.CLAUDE_PROJECTS_DIR = claude_dir
        try:
            yield
        finally:
            MODULE.CODEX_SESSIONS_DIR = original_codex
            MODULE.CLAUDE_PROJECTS_DIR = original_claude

    def write_jsonl(self, path: Path, entries: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )

    def test_scan_tool_invocations_counts_tools_across_both_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_dir = root / "codex"
            claude_dir = root / "claude"

            self.write_jsonl(
                codex_dir / "2026" / "03" / "17" / "rollout-codex.jsonl",
                [
                    {
                        "type": "session_meta",
                        "timestamp": "2026-03-17T12:00:00Z",
                        "payload": {"cwd": "/tmp/codex-demo"},
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "functions.exec_command",
                            "arguments": json.dumps({"cmd": "rg skill-issue"}),
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "functions.exec_command",
                            "arguments": json.dumps({"cmd": "sed -n 1,20p skill-issue/SKILL.md"}),
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "multi_tool_use.parallel",
                            "arguments": json.dumps({"tool_uses": []}),
                        },
                    },
                ],
            )

            self.write_jsonl(
                claude_dir / "-tmp-demo" / "session.jsonl",
                [
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "functions.exec_command",
                                    "input": {"cmd": "python3 skill-issue/scripts/quick_validate.py skill-issue"},
                                },
                                {
                                    "type": "tool_use",
                                    "name": "functions.exec_command",
                                    "input": {"cmd": "python3 skill-issue/tests/test_tool_invocation_counts.py"},
                                },
                                {
                                    "type": "tool_use",
                                    "name": "apply_patch",
                                    "input": {"patch": "*** Begin Patch\n*** End Patch\n"},
                                },
                            ],
                        },
                    }
                ],
            )

            since = MODULE.parse_date("month")
            until = datetime.now(timezone.utc)
            with self.patch_session_dirs(codex_dir, claude_dir):
                report = MODULE.scan_tool_invocations(source="both", since=since, until=until)

            self.assertEqual(report["sessions_scanned"], 2)
            self.assertEqual(report["sessions_matched"], 2)
            self.assertEqual(report["sessions_with_tool_calls"], 2)
            self.assertEqual(report["summary"]["total_tool_calls"], 6)
            self.assertEqual(report["summary"]["unique_tools"], 3)
            self.assertEqual(
                report["tool_counts"],
                [
                    {
                        "tool": "functions.exec_command",
                        "count": 4,
                        "providers": {"claude": 2, "codex": 2},
                    },
                    {
                        "tool": "apply_patch",
                        "count": 1,
                        "providers": {"claude": 1},
                    },
                    {
                        "tool": "multi_tool_use.parallel",
                        "count": 1,
                        "providers": {"codex": 1},
                    },
                ],
            )

    def test_skill_filter_excludes_unmatched_sessions_and_surfaces_review_tool_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_dir = root / "codex"
            claude_dir = root / "claude"

            self.write_jsonl(
                codex_dir / "2026" / "03" / "17" / "rollout-matched.jsonl",
                [
                    {
                        "type": "session_meta",
                        "timestamp": "2026-03-17T12:00:00Z",
                        "payload": {"cwd": "/tmp/codex-demo"},
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "$skill-issue review this skill"}],
                        },
                    },
                    {
                        "type": "event_msg",
                        "payload": {"type": "agent_message", "message": "Using `skill-issue` for this review."},
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "functions.exec_command",
                            "arguments": json.dumps({"cmd": "python3 skill-issue/scripts/review_skill_usage.py --skill skill-issue"}),
                        },
                    },
                ],
            )

            self.write_jsonl(
                codex_dir / "2026" / "03" / "17" / "rollout-unmatched.jsonl",
                [
                    {
                        "type": "session_meta",
                        "timestamp": "2026-03-17T11:00:00Z",
                        "payload": {"cwd": "/tmp/other-demo"},
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "show me unrelated counts"}],
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "apply_patch",
                            "arguments": json.dumps({"patch": "*** Begin Patch\n*** End Patch\n"}),
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "apply_patch",
                            "arguments": json.dumps({"patch": "*** Begin Patch\n*** End Patch\n"}),
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "apply_patch",
                            "arguments": json.dumps({"patch": "*** Begin Patch\n*** End Patch\n"}),
                        },
                    },
                ],
            )

            self.write_jsonl(
                claude_dir / "-tmp-demo" / "session.jsonl",
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "$skill-issue improve this skill"},
                    },
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "Using skill-issue to tighten the review flow."},
                                {
                                    "type": "tool_use",
                                    "name": "apply_patch",
                                    "input": {"patch": "*** Begin Patch\n*** End Patch\n"},
                                },
                                {
                                    "type": "tool_use",
                                    "name": "apply_patch",
                                    "input": {"patch": "*** Begin Patch\n*** End Patch\n"},
                                },
                            ],
                        },
                    },
                ],
            )

            since = MODULE.parse_date("month")
            until = datetime.now(timezone.utc)
            with self.patch_session_dirs(codex_dir, claude_dir):
                count_report = MODULE.scan_tool_invocations(
                    source="both",
                    since=since,
                    until=until,
                    skill="skill-issue",
                )
                review_report = MODULE.scan_skill_invocations(
                    skill="skill-issue",
                    source="both",
                    since=since,
                    until=until,
                    limit=10,
                )

            self.assertEqual(count_report["sessions_scanned"], 3)
            self.assertEqual(count_report["sessions_matched"], 2)
            self.assertEqual(count_report["sessions_with_tool_calls"], 2)
            self.assertEqual(count_report["summary"]["total_tool_calls"], 3)
            self.assertEqual(
                count_report["tool_counts"],
                [
                    {
                        "tool": "apply_patch",
                        "count": 2,
                        "providers": {"claude": 2},
                    },
                    {
                        "tool": "functions.exec_command",
                        "count": 1,
                        "providers": {"codex": 1},
                    },
                ],
            )

            self.assertEqual(review_report["summary"]["total_tool_calls"], 3)
            self.assertEqual(review_report["summary"]["unique_tools"], 2)
            self.assertEqual(review_report["tool_counts"], count_report["tool_counts"])
            self.assertEqual(review_report["invocations_found"], 2)
            self.assertEqual(review_report["invocations"][0]["tool_counts"], {"apply_patch": 2})


if __name__ == "__main__":
    unittest.main()
