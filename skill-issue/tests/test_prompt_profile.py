import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import skill_review as REVIEW  # noqa: E402

MODULE = SourceFileLoader(
    "extract_prompt_profile",
    str((Path(__file__).resolve().parent.parent / "scripts" / "extract_prompt_profile.py").resolve()),
).load_module()


class PromptProfileTests(unittest.TestCase):
    @contextmanager
    def patch_session_dirs(self, codex_dir: Path, claude_dir: Path):
        original_codex = REVIEW.CODEX_SESSIONS_DIR
        original_claude = REVIEW.CLAUDE_PROJECTS_DIR
        REVIEW.CODEX_SESSIONS_DIR = codex_dir
        REVIEW.CLAUDE_PROJECTS_DIR = claude_dir
        try:
            yield
        finally:
            REVIEW.CODEX_SESSIONS_DIR = original_codex
            REVIEW.CLAUDE_PROJECTS_DIR = original_claude

    def write_jsonl(self, path: Path, entries: list[dict], mtime: datetime) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        timestamp = mtime.timestamp()
        import os

        os.utime(path, (timestamp, timestamp))

    def test_build_report_extracts_sessions_and_style_cues(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_dir = root / "codex"
            claude_dir = root / "claude"

            self.write_jsonl(
                codex_dir / "2026" / "03" / "22" / "rollout-portrait.jsonl",
                [
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
                            "content": [
                                {"type": "input_text", "text": "fix README.md and keep exact scope"},
                            ],
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "run make test and verify the behavior"},
                            ],
                        },
                    },
                ],
                mtime=now,
            )

            claude_time = now - timedelta(minutes=5)
            self.write_jsonl(
                claude_dir / "-tmp-demo" / "session.jsonl",
                [
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "plan the slice before editing"},
                            ],
                        },
                    },
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "use `app.ts` and keep it inside the frame"},
                            ],
                        },
                    },
                ],
                mtime=claude_time,
            )

            with self.patch_session_dirs(codex_dir, claude_dir):
                report = MODULE.build_report(
                    source="both",
                    since=now - timedelta(days=1),
                    until=now + timedelta(days=1),
                    limit=10,
                )

        self.assertEqual(report["summary"]["sessions"], 2)
        self.assertEqual(report["summary"]["prompts"], 4)
        cues = report["summary"]["style_cues"]
        self.assertTrue(any("brief, directive asks" in cue for cue in cues))
        self.assertTrue(any("starts from clear action verbs" in cue for cue in cues))
        self.assertTrue(any("verification" in cue for cue in cues))
        self.assertTrue(any("files, commands, and repo paths" in cue for cue in cues))
        self.assertEqual(report["summary"]["common_openers"][0]["token"], "fix")

    def test_render_markdown_handles_empty_reports(self) -> None:
        report = {
            "since": "2026-03-22T00:00:00+00:00",
            "until": "2026-03-29T00:00:00+00:00",
            "source": "both",
            "summary": {
                "sessions": 0,
                "prompts": 0,
                "avg_prompt_length": 0.0,
                "style_cues": ["no recent prompts were available"],
                "top_terms": [],
                "common_openers": [],
            },
            "sessions": [],
        }

        markdown = MODULE.render_markdown(report)

        self.assertIn("## Recent Prompt Profile", markdown)
        self.assertIn("No matching sessions found", markdown)


if __name__ == "__main__":
    unittest.main()
