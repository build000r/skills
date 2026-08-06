import json
import tempfile
import unittest
import unittest.mock
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

    def test_parse_date_accepts_iso_timestamp(self) -> None:
        parsed = MODULE.parse_date("2026-07-22T18:02:00Z")
        self.assertEqual(parsed, datetime(2026, 7, 22, 18, 2, tzinfo=timezone.utc))

    def test_scan_skill_invocations_ingests_grok_chat_history(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            grok_dir = root / "grok"
            session_dir = grok_dir / "%2Ftmp%2Fdemo" / "grok-session-1"
            chat_path = session_dir / "chat_history.jsonl"
            entries = [
                {"type": "user", "content": [{"type": "text", "text": "<user_info>ignore me</user_info>"}]},
                {
                    "type": "user",
                    "content": [{"type": "text", "text": "<user_query>Use colleen-mail-loop in operator mode.</user_query>"}],
                },
                {
                    "type": "assistant",
                    "content": "Using colleen-mail-loop in operator mode. Running validation.",
                    "tool_calls": [
                        {
                            "name": "run_terminal_command",
                            "arguments": {"command": "bash scripts/test-colleen-mail-facilitator.sh"},
                        }
                    ],
                },
                {"type": "assistant", "content": "Terminal receipt: healthy-idle."},
            ]
            self.write_jsonl(chat_path, entries, mtime=now)
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "info": {"id": "grok-session-1", "cwd": "/tmp/demo"},
                        "created_at": now.isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            self.write_jsonl(
                session_dir / "events.jsonl",
                [{"ts": now.isoformat(), "type": "turn_ended"}],
                mtime=now,
            )
            with (session_dir / "events.jsonl").open("a", encoding="utf-8") as events_handle:
                events_handle.write("{malformed-event\n")

            original_grok = MODULE.GROK_SESSIONS_DIR
            MODULE.GROK_SESSIONS_DIR = grok_dir
            try:
                report = MODULE.scan_skill_invocations(
                    skill="colleen-mail-loop",
                    source="grok",
                    since=now - timedelta(days=1),
                    until=now + timedelta(days=1),
                    limit=10,
                )
            finally:
                MODULE.GROK_SESSIONS_DIR = original_grok

        self.assertEqual(report["invocations_found"], 1)
        self.assertEqual(report["summary"]["providers"], {"grok": 1})
        self.assertEqual(report["summary"]["metrics"]["validation_rate"], 1.0)
        invocation = report["invocations"][0]
        self.assertEqual(invocation["session_id"], "grok-session-1")
        self.assertEqual(invocation["project"], "/tmp/demo")
        self.assertTrue(invocation["task_complete"])
        self.assertIn("run_terminal_command", invocation["tool_counts"])
        self.assertIn("bash scripts/test-colleen-mail-facilitator.sh", invocation["validation_commands"])

    def test_grok_turn_completed_skips_malformed_event_lines(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            events_path = Path(tmpdir) / "events.jsonl"
            events_path.write_text(
                "{malformed-event\n"
                + json.dumps({"ts": now.isoformat(), "type": "turn_ended"})
                + "\n",
                encoding="utf-8",
            )

            self.assertTrue(MODULE.grok_turn_completed(events_path))

    def test_scan_skill_invocations_splits_timestamped_recurring_grok_turns(self) -> None:
        base = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            grok_dir = root / "grok"
            session_dir = grok_dir / "%2Ftmp%2Fdemo" / "grok-session-recurring"
            chat_path = session_dir / "chat_history.jsonl"
            recurring_prompt = "Run the hourly facilitator and leave a terminal receipt."
            entries = [
                {"type": "user", "content": "Use colleen-mail-loop in operator mode."},
                {
                    "type": "assistant",
                    "content": "Using colleen-mail-loop in operator mode.",
                    "tool_calls": [
                        {
                            "name": "run_terminal_command",
                            "arguments": {"command": "scripts/colleen-mail-facilitator.sh"},
                        }
                    ],
                },
                {"type": "assistant", "content": "Terminal receipt one."},
                {"type": "user", "content": recurring_prompt},
                {
                    "type": "assistant",
                    "content": "Terminal receipt two.",
                    "tool_calls": [
                        {
                            "name": "run_terminal_command",
                            "arguments": {"command": "scripts/colleen-mail-facilitator.sh"},
                        }
                    ],
                },
                {"type": "user", "content": recurring_prompt},
                {
                    "type": "assistant",
                    "content": "Terminal receipt three.",
                    "tool_calls": [
                        {
                            "name": "run_terminal_command",
                            "arguments": {"command": "scripts/colleen-mail-facilitator.sh"},
                        }
                    ],
                },
            ]
            self.write_jsonl(chat_path, entries, mtime=base + timedelta(hours=3))
            (session_dir / "summary.json").write_text(
                json.dumps({"info": {"id": "grok-session-recurring", "cwd": "/tmp/demo"}}),
                encoding="utf-8",
            )
            event_entries = []
            for turn_number in range(3):
                started = base + timedelta(hours=turn_number)
                event_entries.extend(
                    [
                        {
                            "ts": started.isoformat(),
                            "type": "turn_started",
                            "turn_number": turn_number,
                        },
                        {
                            "ts": (started + timedelta(minutes=1)).isoformat(),
                            "type": "turn_ended",
                            "outcome": "completed",
                        },
                    ]
                )
            event_entries.insert(2, {"malformed": "harmless"})
            self.write_jsonl(session_dir / "events.jsonl", event_entries, mtime=base + timedelta(hours=3))

            original_grok = MODULE.GROK_SESSIONS_DIR
            MODULE.GROK_SESSIONS_DIR = grok_dir
            try:
                report = MODULE.scan_skill_invocations(
                    skill="colleen-mail-loop",
                    source="grok",
                    since=base + timedelta(minutes=30),
                    until=base + timedelta(hours=3),
                    limit=10,
                    validation_patterns=[r"colleen-mail-facilitator\.sh"],
                )
            finally:
                MODULE.GROK_SESSIONS_DIR = original_grok

        self.assertEqual(report["invocations_found"], 2)
        self.assertEqual(report["summary"]["metrics"]["completion_rate"], 1.0)
        self.assertEqual(report["summary"]["metrics"]["validation_rate"], 1.0)
        self.assertEqual(report["summary"]["metrics"]["ack_rate"], 1.0)
        self.assertEqual(
            {item["turn_number"] for item in report["invocations"]},
            {1, 2},
        )
        self.assertTrue(
            all("session_skill_context" in item["matched_on"] for item in report["invocations"])
        )
        self.assertEqual(
            {item["session_id"] for item in report["invocations"]},
            {"grok-session-recurring:turn:1", "grok-session-recurring:turn:2"},
        )

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
        self.assertEqual(report["fact_bundle"]["schema"], "skill_fact_bundle.v1")
        self.assertEqual(report["family_candidates"]["schema"], "family_candidates.v1")
        self.assertEqual(report["llm_interpretation_packet"]["schema"], "llm_interpretation_packet.v1")

        invocation = report["invocations"][0]
        self.assertEqual(invocation["session_id"], "codex:rollout-risk-gate")
        self.assertEqual(len(invocation["risk_gating_messages"]), 2)
        self.assertTrue(any("wait until" in message.lower() for message in invocation["risk_gating_messages"]))
        self.assertTrue(any("ask further questions" in message.lower() for message in invocation["risk_gating_messages"]))

        opportunity_ids = [item["id"] for item in report["opportunities"]]
        self.assertIn("risk-gating-gap", opportunity_ids)
        family_ids = [item["family_id"] for item in report["family_candidates"]["candidates"]]
        self.assertIn("risk-gating-gap", family_ids)

    def test_scan_skill_invocations_handles_list_command_payloads(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_dir = root / "codex"
            claude_dir = root / "claude"
            session_path = codex_dir / "2026" / "03" / "22" / "rollout-list-command.jsonl"

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
                        "arguments": json.dumps({"cmd": ["pytest", "tests/test_skill_review_signals.py"]}),
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
        invocation = report["invocations"][0]
        self.assertEqual(invocation["validation_commands"], ["pytest tests/test_skill_review_signals.py"])
        self.assertEqual(invocation["command_stems"], {"pytest": 1})
        fact_invocation = report["fact_bundle"]["invocations"][0]
        self.assertTrue(fact_invocation["invocation_id"].startswith("inv_"))
        self.assertEqual(fact_invocation["task_type"], "review")
        self.assertTrue(fact_invocation["flags"]["has_validation"])
        llm_packet = report["llm_interpretation_packet"]
        self.assertTrue(llm_packet["top_candidates"])
        self.assertTrue(llm_packet["constraints"]["must_cite_candidate_ids"])

    def test_collect_session_data_returns_empty_record_for_missing_transcript(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        missing = Path("/tmp/skill-review-missing-transcript.jsonl")

        session = MODULE.collect_session_data("claude", missing, now)

        self.assertEqual(session["session_id"], "claude:skill-review-missing-transcript")
        self.assertEqual(session["read_error"], "missing_transcript")
        self.assertEqual(session["user_messages"], [])
        self.assertEqual(session["function_calls"], [])

    def test_correction_detector_requires_post_start_error_signature(self) -> None:
        self.assertFalse(MODULE.is_error_signature_correction("Actually use a tighter operator-evidence loop."))
        self.assertFalse(MODULE.is_error_signature_correction("Do not treat CI red caveats as corrections."))
        self.assertFalse(
            MODULE.is_error_signature_correction(
                "<local-command-caveat>DO NOT respond to generated command messages if a command failed.</local-command-caveat>"
            )
        )
        self.assertFalse(
            MODULE.is_error_signature_correction(
                "Base directory for this skill: /home/skillbox/.claude/skills/lube\n"
                "Do not treat failed examples in bundled instructions as operator corrections."
            )
        )
        self.assertFalse(
            MODULE.is_error_signature_correction(
                "<task-notification><output-file>/tmp/task.jsonl</output-file>wrong failed output</task-notification>"
            )
        )
        self.assertFalse(
            MODULE.is_error_signature_correction(
                "Supervise the datafill agent. Do NOT do DB work. Each tick: check status and report failures."
            )
        )
        self.assertTrue(
            MODULE.is_error_signature_correction(
                "Actually the review crashed with FileNotFoundError; use the transcript path from the session id."
            )
        )

        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_dir = root / "codex"
            claude_dir = root / "claude"
            session_path = codex_dir / "2026" / "03" / "22" / "rollout-correction-signature.jsonl"

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
                        "content": [
                            {
                                "type": "input_text",
                                "text": "$skill-issue review this skill; do not treat CI red caveats as corrections",
                            }
                        ],
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Using `skill-issue` for this review."},
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": (
                            "Actually the review crashed with FileNotFoundError; "
                            "use the transcript path from the session id."
                        ),
                    },
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

        invocation = report["invocations"][0]
        self.assertEqual(len(invocation["user_corrections"]), 1)
        self.assertIn("FileNotFoundError", invocation["user_corrections"][0])


class LoadHistoryTests(unittest.TestCase):
    def test_returns_empty_for_missing_file(self) -> None:
        with unittest.mock.patch.object(MODULE, "REVIEW_HISTORY_FILE", Path("/nonexistent")):
            result = MODULE.load_history()
        self.assertEqual(result, [])

    def test_loads_all_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "history.jsonl"
            f.write_text(
                json.dumps({"skill": "smart", "week": "2025-W36"}) + "\n"
                + json.dumps({"skill": "crap", "week": "2025-W37"}) + "\n",
                encoding="utf-8",
            )
            with unittest.mock.patch.object(MODULE, "REVIEW_HISTORY_FILE", f):
                result = MODULE.load_history()
            self.assertEqual(len(result), 2)

    def test_filters_by_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "history.jsonl"
            f.write_text(
                json.dumps({"skill": "smart", "week": "2025-W36"}) + "\n"
                + json.dumps({"skill": "crap", "week": "2025-W37"}) + "\n",
                encoding="utf-8",
            )
            with unittest.mock.patch.object(MODULE, "REVIEW_HISTORY_FILE", f):
                result = MODULE.load_history(skill="smart")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["skill"], "smart")

    def test_skips_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "history.jsonl"
            f.write_text("bad json\n" + json.dumps({"skill": "ok"}) + "\n", encoding="utf-8")
            with unittest.mock.patch.object(MODULE, "REVIEW_HISTORY_FILE", f):
                result = MODULE.load_history()
            self.assertEqual(len(result), 1)

    def test_skips_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "history.jsonl"
            f.write_text("\n" + json.dumps({"skill": "ok"}) + "\n\n", encoding="utf-8")
            with unittest.mock.patch.object(MODULE, "REVIEW_HISTORY_FILE", f):
                result = MODULE.load_history()
            self.assertEqual(len(result), 1)


class AggregateHistoryByWeekTests(unittest.TestCase):
    def test_empty_records(self) -> None:
        result = MODULE.aggregate_history_by_week([])
        self.assertEqual(result, {})

    def test_groups_by_week(self) -> None:
        records = [
            {"week": "2025-W36", "invocations": 5, "metrics": {"ack_rate": 0.8}},
            {"week": "2025-W36", "invocations": 3, "metrics": {"ack_rate": 0.6}},
            {"week": "2025-W37", "invocations": 10, "metrics": {"ack_rate": 1.0}},
        ]
        result = MODULE.aggregate_history_by_week(records)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["2025-W36"]["reviews"], 2)
        self.assertEqual(result["2025-W36"]["invocations"], 8)
        self.assertAlmostEqual(result["2025-W36"]["metrics"]["ack_rate"], 0.7)
        self.assertEqual(result["2025-W37"]["reviews"], 1)

    def test_missing_week_grouped_as_unknown(self) -> None:
        records = [{"invocations": 1, "metrics": {}}]
        result = MODULE.aggregate_history_by_week(records)
        self.assertIn("unknown", result)

    def test_missing_metrics_default_to_zero(self) -> None:
        records = [{"week": "2025-W36", "invocations": 1}]
        result = MODULE.aggregate_history_by_week(records)
        self.assertEqual(result["2025-W36"]["metrics"]["ack_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
