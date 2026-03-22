import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "skill_review",
    str((Path(__file__).resolve().parent.parent / "scripts" / "lib" / "skill_review.py").resolve()),
).load_module()


class SkillReviewSignalTests(unittest.TestCase):
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

    def write_jsonl(self, path: Path, entries: list[dict], mtime: datetime) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        timestamp = mtime.timestamp()
        import os

        os.utime(path, (timestamp, timestamp))

    def test_scan_skill_invocations_tracks_risk_gating_cues(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_dir = root / "codex"
            claude_dir = root / "claude"
            session_path = codex_dir / "2026" / "03" / "22" / "rollout-risk-gate.jsonl"

            entries = [
                {
                    "type": "session_meta",
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "payload": {"cwd": "/tmp/demo"},
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
                        "arguments": json.dumps({"cmd": "sed -n '1,40p' skill-issue/SKILL.md"}),
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "It should WAIT until fixes have been made before uploading that part.",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": (
                            "Larry should be able to ask further questions and clarify if required "
                            "before diving in further."
                        ),
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "last_agent_message": "done"},
                },
            ]
            self.write_jsonl(session_path, entries, mtime=now)

            with self.patch_session_dirs(codex_dir, claude_dir):
                report = MODULE.scan_skill_invocations(
                    skill="skill-issue",
                    source="both",
                    since=now - timedelta(days=1),
                    until=now + timedelta(days=1),
                    limit=10,
                )

        self.assertEqual(report["invocations_found"], 1)
        self.assertEqual(report["summary"]["metrics"]["risk_gating_rate"], 1.0)

        invocation = report["invocations"][0]
        self.assertEqual(len(invocation["risk_gating_messages"]), 2)
        self.assertTrue(any("wait until" in message.lower() for message in invocation["risk_gating_messages"]))
        self.assertTrue(any("ask further questions" in message.lower() for message in invocation["risk_gating_messages"]))

        opportunity_ids = [item["id"] for item in report["opportunities"]]
        self.assertIn("risk-gating-gap", opportunity_ids)


if __name__ == "__main__":
    unittest.main()
