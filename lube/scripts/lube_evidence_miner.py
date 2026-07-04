#!/usr/bin/env python3
"""Mine skill-review evidence and render it in lube's friction format."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL_ISSUE_ROOT = ROOT / "skill-issue"


def run(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout


def top_card(markdown: str) -> dict[str, str] | None:
    for line in markdown.splitlines():
        if not line.startswith("| 1 |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        return {
            "score": cells[1],
            "type": cells[2],
            "scope": cells[3],
            "runs": cells[4] if len(cells) > 4 else "n/a",
        }
    return None


def _short(text: object, max_chars: int = 160) -> str:
    value = " ".join(str(text or "n/a").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def top_card_from_json(output: str) -> dict[str, object] | None:
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        return None

    cards = report.get("cards")
    if not isinstance(cards, list) or not cards:
        return None

    card = cards[0]
    evidence = card.get("evidence") if isinstance(card, dict) else None
    evidence = evidence if isinstance(evidence, list) else []
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
            f"{session_id}: {_short(item.get('signal'))} | {_short(item.get('user_request'))}"
        )

    scope = card.get("scope")
    if not scope and isinstance(card.get("slice"), dict):
        scope = card["slice"].get("label")

    return {
        "score": str(card.get("score", "n/a")),
        "type": str(card.get("issue_type", "n/a")),
        "scope": str(scope or "n/a"),
        "runs": f"{card.get('affected_runs', 'n/a')}/{card.get('total_runs', 'n/a')}",
        "session_ids": session_ids,
        "excerpts": excerpts,
    }


def parse_top_card(output: str) -> dict[str, object] | None:
    return top_card_from_json(output) or top_card(output)


def card_observation(label: str, card: dict[str, object]) -> str:
    message = (
        f"{label}: top card {card['type']} in {card['scope']} "
        f"(score {card['score']}, runs {card['runs']})"
    )
    session_ids = card.get("session_ids") or []
    if session_ids:
        message += f"; session ids {', '.join(session_ids[:3])}"
    excerpts = card.get("excerpts") or []
    if excerpts:
        message += f"; excerpts {' / '.join(excerpts[:3])}"
    return message


def root_cause(card_type: str) -> str:
    return {
        "automation-gap": "missing automation",
        "contract-clarity": "unclear skill contract",
        "verification-gap": "missing verification path",
        "observability-gap": "weak invocation observability",
        "trigger_mismatch": "missing or overbroad skill trigger",
        "skill-discoverability-gap": "missing skill trigger",
        "skill-consolidation-opportunity": "overlapping skill contracts",
        "output_rejected": "unclear output contract",
    }.get(card_type, "weak defaults")


def durable_fix(card_type: str) -> str:
    return {
        "automation-gap": "bundle the repeated shell/review flow into a script",
        "contract-clarity": "tighten branch rules, defaults, and non-goals in SKILL.md",
        "verification-gap": "add a command-first verification block",
        "observability-gap": "require a stable first progress marker",
        "trigger_mismatch": "sharpen the description and trigger phrases",
        "skill-discoverability-gap": "add observed natural-language trigger phrases and examples",
        "skill-consolidation-opportunity": "choose one canonical skill and move edge cases into references",
        "output_rejected": "tighten the output shape and completion rules",
    }.get(card_type, "turn the repeated correction into a skill contract or helper")


def parse_skills(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[, ]+", value) if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run skill-issue evidence scans and emit lube friction output."
    )
    parser.add_argument(
        "--skills",
        default=os.environ.get("LUBE_SKILLS", "cass,skill-issue,lube"),
        help="Comma-separated skills to review after the portfolio scan.",
    )
    parser.add_argument("--since", default="month", help="Review window, e.g. week or month.")
    parser.add_argument("--source", default="both", choices=("claude", "codex", "both", "all"))
    parser.add_argument("--limit", type=int, default=50, help="Per-skill invocation limit.")
    parser.add_argument(
        "--skill-issue-root",
        type=Path,
        default=DEFAULT_SKILL_ISSUE_ROOT,
        help="Path to the skill-issue skill directory.",
    )
    args = parser.parse_args()

    skill_issue_root = args.skill_issue_root.expanduser().resolve()
    portfolio_script = skill_issue_root / "scripts" / "generate_skill_portfolio_opportunities.py"
    review_script = skill_issue_root / "scripts" / "review_skill_usage.py"
    opportunities_script = skill_issue_root / "scripts" / "generate_skill_opportunities.py"

    missing = [path for path in (portfolio_script, review_script, opportunities_script) if not path.exists()]
    if missing:
        print("Observed friction")
        for path in missing:
            print(f"- Missing required helper: {path}")
        print("\nRoot cause class")
        print("- missing environment setup")
        print("\nDurable unblocker")
        print("- Activate or install skill-issue so lube can run the evidence loop.")
        print("\nAction taken")
        print("- No scan ran because required helper scripts were unavailable.")
        print("\nRemaining ask")
        print("- Make skill-issue visible in this repo, then rerun this command.")
        return 2

    observations: list[str] = []
    causes: list[str] = []
    fixes: list[str] = []
    actions: list[str] = []
    asks: list[str] = []

    code, output = run(
        [
            sys.executable,
            str(portfolio_script),
            "--source",
            args.source,
            "--since",
            args.since,
            "--json",
        ],
        skill_issue_root,
    )
    card = parse_top_card(output)
    if code == 0 and card:
        observations.append(card_observation("portfolio", card))
        causes.append(f"portfolio: {root_cause(card['type'])}")
        fixes.append(f"portfolio: {durable_fix(card['type'])}")
    else:
        observations.append("portfolio: opportunity scan did not return a parsable top card")
        causes.append("portfolio: missing automation")
        fixes.append("portfolio: inspect the portfolio miner output and harden this wrapper")
        asks.append("Check the portfolio miner output if this persists.")
    actions.append("Ran portfolio opportunity scan through skill-issue.")

    with tempfile.TemporaryDirectory(prefix="lube-evidence-") as tmpdir:
        tmp = Path(tmpdir)
        for skill in parse_skills(args.skills):
            review_path = tmp / f"{skill}-review.json"
            code, review_output = run(
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
                ],
                skill_issue_root,
            )
            if code != 0:
                observations.append(f"{skill}: review scan failed")
                causes.append(f"{skill}: unavailable CLI/API/SDK")
                fixes.append(f"{skill}: repair review_skill_usage.py access or transcript source")
                asks.append(f"Review failure for {skill}: {review_output.splitlines()[-1:]}")
                continue
            review_path.write_text(review_output)
            code, opportunity_output = run(
                [sys.executable, str(opportunities_script), "--input", str(review_path), "--json"],
                skill_issue_root,
            )
            card = parse_top_card(opportunity_output)
            if code == 0 and card:
                observations.append(card_observation(skill, card))
                causes.append(f"{skill}: {root_cause(card['type'])}")
                fixes.append(f"{skill}: {durable_fix(card['type'])}")
            else:
                observations.append(f"{skill}: opportunity scan had no parsable top card")
                causes.append(f"{skill}: missing verification path")
                fixes.append(f"{skill}: add a focused review/validation command")
            actions.append(f"Ran usage review and opportunity scan for {skill}.")

    print("Observed friction")
    for item in observations:
        print(f"- {item}")
    print("\nRoot cause class")
    for item in causes:
        print(f"- {item}")
    print("\nDurable unblocker")
    for item in fixes:
        print(f"- {item}")
    print("\nAction taken")
    for item in actions:
        print(f"- {item}")
    print("\nRemaining ask")
    if asks:
        for item in asks:
            print(f"- {item}")
    else:
        print("- None for the evidence pass; execute the safest local fixes directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
