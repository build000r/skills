#!/usr/bin/env python3
"""Mine skill-review evidence and render it in lube's friction format."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL_ISSUE_ROOT = ROOT / "skill-issue"
DEFAULT_CASS_COMMAND = "sbp cass search"

# Curated friction signals mined repeatedly from past sessions. Each pattern
# groups the search terms that surface it and the lube root-cause class the
# resulting bead should target.
FRICTION_PATTERNS: list[dict[str, object]] = [
    {
        "pattern": "permission-prompt-friction",
        "terms": ["permission denied", "requires approval", "permission prompt"],
        "lube_target": "weak defaults",
    },
    {
        "pattern": "retry-loop",
        "terms": ["retrying", "retry loop"],
        "lube_target": "missing automation",
    },
    {
        "pattern": "timeout",
        "terms": ["timed out", "timeout exceeded"],
        "lube_target": "weak defaults",
    },
    {
        "pattern": "skill-visibility-miss",
        "terms": [
            "doesn't see the skill",
            "can't find the skill",
            "skill not found",
            "skill appears inactive",
            "not in the available skills",
        ],
        "lube_target": "missing skill trigger",
    },
    {
        "pattern": "rate-limit",
        "terms": ["rate limit", "rate limited"],
        "lube_target": "missing runbook",
    },
    {
        "pattern": "context-compression",
        "terms": ["context compression", "context compaction", "context low"],
        "lube_target": "missing automation",
    },
    {
        "pattern": "tui-blocked",
        "terms": ["TUI blocked", "interactive prompt", "cannot interact"],
        "lube_target": "brittle manual step",
    },
    {
        "pattern": "missing-command",
        "terms": ["command not found"],
        "lube_target": "missing environment setup",
    },
    {
        "pattern": "missing-credentials",
        "terms": ["missing API key", "unauthorized", "credentials not found"],
        "lube_target": "absent API key",
    },
    {
        "pattern": "stale-lock",
        "terms": ["stale lock", "lock held"],
        "lube_target": "missing runbook",
    },
]


def run(
    command: list[str],
    cwd: Path,
    timeout_seconds: int | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return 124, f"process timed out after {timeout_seconds}s: {' '.join(command[:4])}"
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


def classify_lube_target(text: str) -> str:
    lowered = text.lower()
    rules = (
        (("permission", "approval", "allowlist"), "weak defaults"),
        (("api key", "credential", "unauthorized", "token"), "absent API key"),
        (("doesn't see", "can't find", "not visible", "skill"), "missing skill trigger"),
        (("command not found", "no such file", "not installed"), "missing environment setup"),
        (("interactive", "tui", "prompt", "cannot interact"), "brittle manual step"),
        (("rate limit", "lock"), "missing runbook"),
        (("timeout", "timed out"), "weak defaults"),
    )
    for needles, target in rules:
        if any(needle in lowered for needle in needles):
            return target
    return "missing automation"


def cass_search(
    term: str,
    limit: int,
    timeout_seconds: int,
    command: str = DEFAULT_CASS_COMMAND,
) -> dict[str, object]:
    """Run one query through the sbp cass search backend and parse its JSON."""
    argv = shlex.split(command) + [
        term,
        "--json",
        "--limit",
        str(limit),
        "--fields",
        "all",
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    # Backend honors --timeout-seconds only when healthy; a hung front door
    # (remote host, rebuild lock) needs a process-level kill as well.
    code, output = run(argv, Path.cwd(), timeout_seconds=timeout_seconds + 15)
    if code != 0:
        return {"error": f"exit {code}: {_short(output)}"}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"error": f"unparsable backend output: {_short(output)}"}
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return {"error": f"backend returned no result object: {_short(output)}"}
    hits = result.get("hits")
    return {
        "hits": hits if isinstance(hits, list) else [],
        "total_matches": int(result.get("total_matches") or 0),
    }


def session_id_from_hit(hit: dict[str, object]) -> str:
    source_path = str(hit.get("source_path") or "")
    return Path(source_path).stem if source_path else "unknown-session"


# Injected harness/catalog text echoes friction vocabulary without any friction
# having occurred ("cass grep contamination"). Hits matching these signatures
# are counted separately and never contribute to score or sample snippets.
DOC_ECHO_SIGNATURES = (
    "<system-reminder>",
    "<command-message>",
    "<command-name>",
    "base directory for this skill",
    "# claudemd",
    "the following skills are available",
    "use the skill tool",
)


def is_doc_echo(text: str) -> bool:
    lowered = text.lower()
    return any(signature in lowered for signature in DOC_ECHO_SIGNATURES)


def aggregate_pattern(
    pattern: dict[str, object],
    searches: list[dict[str, object]],
) -> dict[str, object]:
    """Fold per-term search results into one ranked friction-pattern row."""
    session_ids: list[str] = []
    seen_hits: set[tuple[str, object]] = set()
    approx_tokens = 0
    total_matches = 0
    doc_echo_hits = 0
    sample_snippet = ""
    errors: list[str] = []
    for search in searches:
        error = search.get("error")
        if error:
            errors.append(str(error))
            continue
        total_matches += int(search.get("total_matches") or 0)
        for hit in search.get("hits") or []:
            if not isinstance(hit, dict):
                continue
            key = (str(hit.get("source_path") or ""), hit.get("line_number"))
            if key in seen_hits:
                continue
            seen_hits.add(key)
            text = str(hit.get("content") or hit.get("title") or "")
            if is_doc_echo(text):
                doc_echo_hits += 1
                continue
            approx_tokens += max(len(text) // 4, 1)
            if not sample_snippet and text:
                sample_snippet = _short(text)
            session_id = session_id_from_hit(hit)
            if session_id not in session_ids:
                session_ids.append(session_id)
    session_count = len(session_ids)
    return {
        "pattern": pattern["pattern"],
        "lube_target": pattern["lube_target"],
        "terms": list(pattern["terms"]),
        "score": session_count * max(approx_tokens, 1),
        "session_count": session_count,
        "total_matches": total_matches,
        "approx_match_tokens": approx_tokens,
        "doc_echo_hits": doc_echo_hits,
        "session_ids": session_ids[:10],
        "sample_snippet": sample_snippet,
        "errors": errors,
    }


def frequency_patterns(extra_terms: list[str]) -> list[dict[str, object]]:
    patterns = [dict(pattern) for pattern in FRICTION_PATTERNS]
    for term in extra_terms:
        patterns.append(
            {
                "pattern": re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-") or "custom",
                "terms": [term],
                "lube_target": classify_lube_target(term),
            }
        )
    return patterns


def parse_terms(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def run_frequency_mode(args: argparse.Namespace) -> int:
    patterns = frequency_patterns(parse_terms(args.terms))
    rows: list[dict[str, object]] = []
    consecutive_process_timeouts = 0
    backend_circuit_open = False
    for index, pattern in enumerate(patterns, start=1):
        print(
            f"[lube-miner] {index}/{len(patterns)} searching: {pattern['pattern']}",
            file=sys.stderr,
            flush=True,
        )
        searches: list[dict[str, object]] = []
        for term in pattern["terms"]:
            if backend_circuit_open:
                searches.append(
                    {"error": "skipped: backend circuit open after repeated process timeouts"}
                )
                continue
            result = cass_search(
                term, args.per_term_limit, args.timeout_seconds, args.cass_command
            )
            if "process timed out" in str(result.get("error") or ""):
                consecutive_process_timeouts += 1
                if consecutive_process_timeouts >= 2:
                    backend_circuit_open = True
                    print(
                        "[lube-miner] backend unresponsive after "
                        f"{consecutive_process_timeouts} consecutive process timeouts; "
                        "skipping remaining searches (partial results below)",
                        file=sys.stderr,
                        flush=True,
                    )
            else:
                consecutive_process_timeouts = 0
            searches.append(result)
        rows.append(aggregate_pattern(pattern, searches))
    rows.sort(key=lambda row: (-int(row["score"]), -int(row["total_matches"])))
    report = {
        "mode": "frequency",
        "backend": args.cass_command,
        "per_term_limit": args.per_term_limit,
        "patterns": rows[: args.top],
    }
    print(json.dumps(report, indent=2))
    if all(row["errors"] and not row["session_count"] for row in rows):
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run skill-issue evidence scans and emit lube friction output."
    )
    parser.add_argument(
        "--mode",
        default="evidence",
        choices=("evidence", "frequency"),
        help="evidence: skill-issue scans (default). frequency: batch cass friction mining.",
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
    parser.add_argument(
        "--terms",
        default="",
        help="Frequency mode: comma-separated extra friction terms to mine.",
    )
    parser.add_argument(
        "--per-term-limit",
        type=int,
        default=20,
        help="Frequency mode: hits fetched per search term.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Frequency mode: ranked patterns to emit.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Frequency mode: per-search backend timeout.",
    )
    parser.add_argument(
        "--cass-command",
        default=os.environ.get("LUBE_CASS_COMMAND", DEFAULT_CASS_COMMAND),
        help="Frequency mode: cass search front door (env LUBE_CASS_COMMAND).",
    )
    args = parser.parse_args()

    if args.mode == "frequency":
        return run_frequency_mode(args)

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
