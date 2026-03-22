import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import skill_portfolio as PORTFOLIO  # noqa: E402
from lib import skill_review as REVIEW  # noqa: E402


class SkillPortfolioOpportunityTests(unittest.TestCase):
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
        path.chmod(0o644)
        import os

        os.utime(path, (timestamp, timestamp))

    def write_skill(self, root: Path, name: str, description: str, body: str) -> None:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    f"name: {name}",
                    f'description: "{description}"',
                    "---",
                    "",
                    body.strip(),
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_generate_portfolio_report_surfaces_creation_discoverability_and_consolidation(self) -> None:
        now = datetime.now(timezone.utc)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_root = root / "skills"
            codex_dir = root / "codex"
            claude_dir = root / "claude"

            shared_body = """
# Deploy & Debug

## Mode Selection

This skill supports project-specific modes via local `modes/*.md` files.

## Health Checks

Check health endpoints, container logs, rollbacks, and deploy status.
"""
            self.write_skill(
                skills_root,
                "deploy",
                "Deploy and debug Docker infrastructure with health checks, container logs, rollbacks, and environment sync.",
                shared_body,
            )
            self.write_skill(
                skills_root,
                "deploy-approval",
                'Deploy and debug the approval api infrastructure. Use when handling "approval api", "api.example.com", "app.example.com", container logs, rollbacks, or health checks.',
                shared_body,
            )
            self.write_skill(
                skills_root,
                "ask-cascade",
                "Ask high-level questions first, then detail questions only when needed.",
                """
# Ask Cascade

Order user questions from strategic decisions to implementation details.
""",
            )

            session_time = now.replace(microsecond=0)
            sessions = [
                (
                    "rollout-deploy-1.jsonl",
                    "check approval api health and container logs after deploy",
                    'ssh root@example-host "docker logs approval-api-1 --since 30m"',
                ),
                (
                    "rollout-deploy-2.jsonl",
                    "rollback approval api deploy and inspect container logs",
                    'curl -s https://api.example.com/health',
                ),
                (
                    "rollout-create-1.jsonl",
                    "process vendor invoice pdf from dropbox and attach to transaction",
                    "python3 scripts/receipt_attach.py",
                ),
                (
                    "rollout-create-2.jsonl",
                    "ocr receipt pdf and attach it to bookkeeping transaction",
                    "python3 scripts/bookkeeping_attach.py",
                ),
            ]

            for index, (filename, user_request, command) in enumerate(sessions):
                timestamp = session_time - timedelta(minutes=index)
                self.write_jsonl(
                    codex_dir / "2026" / "03" / "22" / filename,
                    [
                        {
                            "type": "session_meta",
                            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                            "payload": {"cwd": "/tmp/demo"},
                        },
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": user_request}],
                            },
                        },
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "function_call",
                                "name": "functions.exec_command",
                                "arguments": json.dumps({"cmd": command}),
                            },
                        },
                    ],
                    mtime=timestamp,
                )

            with self.patch_session_dirs(codex_dir, claude_dir):
                portfolio = PORTFOLIO.scan_skill_portfolio(
                    source="both",
                    since=now - timedelta(days=1),
                    until=now + timedelta(days=1),
                    limit=20,
                    skills_root=skills_root,
                )
                report = PORTFOLIO.generate_portfolio_opportunity_report(
                    portfolio,
                    min_cluster_runs=2,
                    max_cards=10,
                    max_evidence=2,
                )

            issue_types = [card["issue_type"] for card in report["cards"]]
            self.assertIn("skill-discoverability-gap", issue_types)
            self.assertIn("skill-creation-opportunity", issue_types)
            self.assertIn("skill-consolidation-opportunity", issue_types)

            discoverability = next(card for card in report["cards"] if card["issue_type"] == "skill-discoverability-gap")
            self.assertEqual(discoverability["scope"], "deploy-approval")
            self.assertEqual(discoverability["affected_runs"], 2)

            creation = next(card for card in report["cards"] if card["issue_type"] == "skill-creation-opportunity")
            self.assertEqual(creation["affected_runs"], 2)
            self.assertIn("pdf", creation["supporting_metrics"]["top_request_tokens"])

            consolidation = next(card for card in report["cards"] if card["issue_type"] == "skill-consolidation-opportunity")
            self.assertIn("deploy", consolidation["scope"])
            self.assertIn("deploy-approval", consolidation["scope"])
            self.assertIn("modes/", consolidation["recommendation"])

    def test_render_portfolio_markdown_includes_new_card_types(self) -> None:
        report = {
            "source_review": {"sessions_scanned": 12, "sessions_analyzed": 7},
            "catalog_summary": {"skills_loaded": 3},
            "cards": [
                {
                    "issue_type": "skill-creation-opportunity",
                    "score": 28,
                    "scope": "attach-pdf-transaction",
                    "affected_runs": 2,
                    "total_runs": 7,
                    "prevalence": 0.286,
                    "hypothesis": "Repeated manual work is missing from the catalog.",
                    "recommendation": "Create a new skill.",
                    "target_files": ["attach-pdf-transaction/SKILL.md"],
                    "followup_brief": "Create the skill.",
                    "supporting_metrics": {"top_request_tokens": ["attach", "pdf"]},
                    "evidence": [
                        {
                            "timestamp": "2026-03-22T12:00:00+00:00",
                            "signal": "weak catalog overlap",
                            "user_request": "attach this pdf",
                        }
                    ],
                }
            ],
        }

        markdown = PORTFOLIO.render_portfolio_opportunity_markdown(report)

        self.assertIn("## Skill Portfolio Opportunity Funnel", markdown)
        self.assertIn("skill-creation-opportunity", markdown)
        self.assertIn("attach-pdf-transaction", markdown)


if __name__ == "__main__":
    unittest.main()
