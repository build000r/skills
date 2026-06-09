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
                    f"description: {json.dumps(description)}",
                    "---",
                    "",
                    body.strip(),
                    "",
                ]
            ),
            encoding="utf-8",
        )

    @contextmanager
    def patch_default_roots(self, *roots: Path):
        original = PORTFOLIO.DEFAULT_SKILLS_ROOT_CANDIDATES
        PORTFOLIO.DEFAULT_SKILLS_ROOT_CANDIDATES = tuple(roots)
        try:
            yield
        finally:
            PORTFOLIO.DEFAULT_SKILLS_ROOT_CANDIDATES = original

    def test_generate_portfolio_report_surfaces_creation_discoverability_and_consolidation(self) -> None:
        now = datetime.now(timezone.utc)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            public_skills_root = root / "skills-public"
            private_skills_root = root / "skills-private"
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
                public_skills_root,
                "deploy",
                "Deploy and debug Docker infrastructure with health checks, container logs, rollbacks, and environment sync.",
                shared_body,
            )
            self.write_skill(
                private_skills_root,
                "deploy-approval",
                'Deploy and debug the approval api infrastructure. Use when handling "approval api", "api.example.com", "app.example.com", container logs, rollbacks, or health checks.',
                shared_body,
            )
            self.write_skill(
                public_skills_root,
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
                    ["ssh", "root@example-host", "docker logs approval-api-1 --since 30m"],
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
                    skills_root=[public_skills_root, private_skills_root],
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
            self.assertEqual(portfolio["skills_root"], str(public_skills_root.resolve()))
            self.assertEqual(
                portfolio["catalog_roots"],
                [str(public_skills_root.resolve()), str(private_skills_root.resolve())],
            )
            self.assertEqual(report["catalog_summary"]["roots_loaded"], 2)
            self.assertEqual(len(report["catalog_summary"]["root_details"]), 2)
            self.assertEqual(report["catalog_summary"]["invalid_skills_skipped"], [])

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

    def test_request_token_filter_drops_ids_and_worker_instruction_noise(self) -> None:
        tokens = PORTFOLIO._tokenize_request(
            "Stand by. Do not claim or edit any Bead 0003 0bfb 37r3 while processing invoice pdf OCR."
        )

        self.assertNotIn("stand", tokens)
        self.assertNotIn("claim", tokens)
        self.assertNotIn("edit", tokens)
        self.assertNotIn("bead", tokens)
        self.assertNotIn("0003", tokens)
        self.assertNotIn("0bfb", tokens)
        self.assertNotIn("37r3", tokens)
        self.assertIn("invoice", tokens)
        self.assertIn("pdf", tokens)
        self.assertIn("ocr", tokens)

    def test_discoverability_cards_ignore_repeated_worker_instruction_noise(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_root = root / "skills"
            codex_dir = root / "codex"
            claude_dir = root / "claude"

            self.write_skill(
                skills_root,
                "visual-inspiration-demo",
                "Use when visual inspiration work mentions stand claim edit bead source concepts.",
                """
# Visual Inspiration Demo

Stand claim edit bead source concept registry visual design inspiration.
""",
            )

            for index in range(3):
                timestamp = now - timedelta(minutes=index)
                self.write_jsonl(
                    codex_dir / "2026" / "06" / f"noise-{index}.jsonl",
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
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": "Stand by. Do not claim or edit any Bead 0003 0004 0005.",
                                    }
                                ],
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

        discoverability_scopes = [
            card["scope"] for card in report["cards"] if card["issue_type"] == "skill-discoverability-gap"
        ]
        self.assertNotIn("visual-inspiration-demo", discoverability_scopes)

    def test_render_portfolio_markdown_includes_new_card_types(self) -> None:
        report = {
            "source_review": {"sessions_scanned": 12, "sessions_analyzed": 7},
            "catalog_summary": {
                "skills_loaded": 3,
                "roots_loaded": 2,
                "root_details": [
                    {
                        "root": "/tmp/public-skills",
                        "skills_loaded": 2,
                        "duplicates_skipped": 0,
                        "invalid_skills_skipped": 0,
                    },
                    {
                        "root": "/tmp/private-skills",
                        "skills_loaded": 1,
                        "duplicates_skipped": 1,
                        "invalid_skills_skipped": 1,
                    },
                ],
                "invalid_skills_skipped": [
                    {
                        "path": "/tmp/private-skills/bad-skill/SKILL.md",
                        "catalog_root": "/tmp/private-skills",
                        "reason": "missing or empty description",
                    }
                ],
            },
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
        self.assertIn("Catalog roots: 2", markdown)
        self.assertIn("/tmp/private-skills", markdown)
        self.assertIn("duplicates skipped=1", markdown)
        self.assertIn("invalid skipped=1", markdown)
        self.assertIn("Invalid skills skipped: 1", markdown)
        self.assertIn("/tmp/private-skills/bad-skill/SKILL.md (missing or empty description)", markdown)

    def test_default_catalog_roots_federate_multiple_existing_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            public_skills_root = root / "skills-public"
            private_skills_root = root / "skills-private"
            missing_root = root / "missing-root"

            self.write_skill(
                public_skills_root,
                "describe",
                "Turn work into pass/fail test cases before patching.",
                "# Describe",
            )
            self.write_skill(
                private_skills_root,
                "smart",
                "Ask the single highest-leverage next question.",
                "# Smart",
            )

            with self.patch_default_roots(public_skills_root, missing_root, private_skills_root):
                bundle = PORTFOLIO.load_skill_catalog_bundle()

        self.assertEqual(
            bundle["catalog_roots"],
            [str(public_skills_root.resolve()), str(private_skills_root.resolve())],
        )
        self.assertEqual(
            sorted(skill["name"] for skill in bundle["catalog"]),
            ["describe", "smart"],
        )

    def test_scan_skill_portfolio_carries_invalid_skill_summary(self) -> None:
        now = datetime.now(timezone.utc)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_root = root / "skills"
            codex_dir = root / "codex"
            claude_dir = root / "claude"
            self.write_skill(
                skills_root,
                "describe",
                "Turn work into pass/fail test cases before patching.",
                "# Describe",
            )
            invalid_dir = skills_root / "bad-skill"
            invalid_dir.mkdir(parents=True, exist_ok=True)
            (invalid_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: bad-skill",
                        'description: ""',
                        "---",
                        "",
                        "# Bad Skill",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with self.patch_session_dirs(codex_dir, claude_dir):
                portfolio = PORTFOLIO.scan_skill_portfolio(
                    source="both",
                    since=now - timedelta(days=1),
                    until=now + timedelta(days=1),
                    limit=20,
                    skills_root=skills_root,
                )
                report = PORTFOLIO.generate_portfolio_opportunity_report(portfolio)

        self.assertEqual(len(portfolio["catalog_summary"]["invalid_skills_skipped"]), 1)
        self.assertEqual(portfolio["catalog_summary"]["root_details"][0]["invalid_skills_skipped"], 1)
        self.assertEqual(
            report["catalog_summary"]["invalid_skills_skipped"][0]["reason"],
            "missing or empty description",
        )


if __name__ == "__main__":
    unittest.main()
