#!/usr/bin/env python3
"""Run portfolio and per-skill opportunity scans as one ranked backlog pass."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(command: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout


def split_skills(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[, ]+", value) if item.strip()]


def top_table_rows(markdown: str, limit: int) -> list[str]:
    rows: list[str] = []
    for line in markdown.splitlines():
        if re.match(r"^\| [0-9]+ \|", line):
            rows.append(line)
            if len(rows) >= limit:
                break
    return rows


def _short(text: object, max_chars: int = 150) -> str:
    value = " ".join(str(text or "n/a").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _card_scope(card: dict) -> str:
    if card.get("scope"):
        return str(card["scope"])
    if isinstance(card.get("slice"), dict):
        return str(card["slice"].get("label") or "n/a")
    return "n/a"


def _card_fix_class(card: dict) -> str:
    return str(card.get("suggested_fix_class") or card.get("severity") or "n/a")


def card_summaries_from_json(output: str, limit: int) -> str | None:
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        return None

    cards = report.get("cards")
    if not isinstance(cards, list) or not cards:
        return None

    lines = ["| Rank | Score | Type | Scope | Runs | Prev | Fix Class |"]
    lines.append("|------|-------|------|-------|------|------|-----------|")
    details: list[str] = []
    for idx, card in enumerate(cards[:limit], start=1):
        if not isinstance(card, dict):
            continue
        runs = f"{card.get('affected_runs', 'n/a')}/{card.get('total_runs', 'n/a')}"
        prevalence = card.get("prevalence")
        prevalence_text = f"{prevalence:.2f}" if isinstance(prevalence, (float, int)) else "n/a"
        lines.append(
            f"| {idx} | {card.get('score', 'n/a')} | {card.get('issue_type', 'n/a')} | "
            f"{_card_scope(card)} | {runs} | {prevalence_text} | {_card_fix_class(card)} |"
        )

        evidence = card.get("evidence") if isinstance(card.get("evidence"), list) else []
        session_ids: list[str] = []
        excerpts: list[str] = []
        for item in evidence[:3]:
            if not isinstance(item, dict):
                continue
            session_id = item.get("session_id") or item.get("invocation_id") or "unknown-session"
            session_id = str(session_id)
            if session_id not in session_ids:
                session_ids.append(session_id)
            excerpts.append(
                f"- {session_id}: {_short(item.get('signal'))} | {_short(item.get('user_request'))}"
            )
        if session_ids or excerpts:
            details.append("")
            details.append(f"### {idx}. {card.get('issue_type', 'n/a')} evidence")
            if session_ids:
                details.append(f"Session IDs: {', '.join(session_ids)}")
            if excerpts:
                details.append("Representative excerpts:")
                details.extend(excerpts)

    return "\n".join(lines + details)


def section(title: str, body: str) -> None:
    print(f"\n## {title}")
    print(body.rstrip() if body.strip() else "_No output._")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank portfolio and selected skill-improvement opportunities in one pass."
    )
    parser.add_argument(
        "--skills",
        default="cass,skill-issue,lube",
        help="Comma-separated skills to review after the portfolio scan.",
    )
    parser.add_argument("--since", default="month", help="Review window, e.g. week or month.")
    parser.add_argument("--source", default="both", choices=("claude", "codex", "both", "all"))
    parser.add_argument("--limit", type=int, default=50, help="Per-skill invocation limit.")
    parser.add_argument("--portfolio-limit", type=int, default=200, help="Portfolio session limit.")
    parser.add_argument("--top", type=int, default=5, help="Rows to include from each ranked table.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print complete underlying reports instead of only top rows.",
    )
    args = parser.parse_args()

    portfolio_script = SCRIPTS / "generate_skill_portfolio_opportunities.py"
    review_script = SCRIPTS / "review_skill_usage.py"
    opportunity_script = SCRIPTS / "generate_skill_opportunities.py"

    for path in (portfolio_script, review_script, opportunity_script):
        if not path.exists():
            print(f"missing helper: {path}", file=sys.stderr)
            return 2

    print("# Skill Improvement Backlog")
    print()
    print(f"- source: {args.source}")
    print(f"- since: {args.since}")
    print(f"- skills: {', '.join(split_skills(args.skills))}")

    portfolio_command = [
        sys.executable,
        str(portfolio_script),
        "--source",
        args.source,
        "--since",
        args.since,
        "--limit",
        str(args.portfolio_limit),
    ]
    if not args.full:
        portfolio_command.append("--json")
    code, portfolio = run(portfolio_command)
    if code != 0:
        section("Portfolio Opportunities", f"Portfolio scan failed:\n\n{portfolio}")
    elif args.full:
        section("Portfolio Opportunities", portfolio)
    else:
        body = card_summaries_from_json(portfolio, args.top)
        rows = top_table_rows(portfolio, args.top) if body is None else []
        section(
            "Portfolio Opportunities",
            body or ("\n".join(rows) if rows else "No ranked portfolio rows found."),
        )

    with tempfile.TemporaryDirectory(prefix="skill-rank-") as tmpdir:
        tmp = Path(tmpdir)
        for skill in split_skills(args.skills):
            review_path = tmp / f"{skill}-review.json"
            code, review = run(
                [
                    sys.executable,
                    str(review_script),
                    "--skill",
                    skill,
                    "--source",
                    args.source,
                    "--limit",
                    str(args.limit),
                    "--no-marker",
                ]
            )
            if code != 0:
                section(f"{skill} Opportunities", f"Review scan failed:\n\n{review}")
                continue
            review_path.write_text(review)
            opportunity_command = [sys.executable, str(opportunity_script), "--input", str(review_path)]
            if not args.full:
                opportunity_command.append("--json")
            code, opportunities = run(opportunity_command)
            if code != 0:
                section(f"{skill} Opportunities", f"Opportunity scan failed:\n\n{opportunities}")
                continue
            if args.full:
                section(f"{skill} Opportunities", opportunities)
            else:
                body = card_summaries_from_json(opportunities, args.top)
                rows = top_table_rows(opportunities, args.top) if body is None else []
                section(
                    f"{skill} Opportunities",
                    body or ("\n".join(rows) if rows else "No ranked skill rows found."),
                )

    print("\n## Next Step")
    print(
        "Turn the highest repeated friction into a Bead, then patch the owning skill "
        "with the smallest durable unblocker and run quick_validate.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
