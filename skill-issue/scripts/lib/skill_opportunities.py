"""
Deterministic-ish opportunity mining for skill review reports.

Turns post-invocation skill review data into ranked improvement cards that can
be handed back into skill-issue for focused iteration.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIN_CARD_SCORE = 10

try:
    from lib.skill_facts import build_skill_fact_bundle
    from lib.skill_families import build_family_candidates, build_llm_interpretation_packet
except ModuleNotFoundError:
    def _load_local_module(filename: str, module_name: str) -> Any:
        module_path = Path(__file__).resolve().with_name(filename)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    _skill_facts = _load_local_module("skill_facts.py", "skill_facts_local")
    _skill_families = _load_local_module("skill_families.py", "skill_families_local")
    build_skill_fact_bundle = _skill_facts.build_skill_fact_bundle
    build_family_candidates = _skill_families.build_family_candidates
    build_llm_interpretation_packet = _skill_families.build_llm_interpretation_packet


def _ensure_fact_bundle(review_report: dict[str, Any]) -> dict[str, Any]:
    fact_bundle = review_report.get("fact_bundle")
    if fact_bundle:
        return fact_bundle

    generated_at = review_report.get("generated_at") or datetime.now(timezone.utc).isoformat()
    return build_skill_fact_bundle(
        skill=review_report.get("skill", "unknown"),
        source=review_report.get("source", "both"),
        since=review_report.get("since", ""),
        until=review_report.get("until", ""),
        generated_at=generated_at,
        sessions_scanned=review_report.get("sessions_scanned", 0),
        invocations=review_report.get("invocations", []),
        summary=review_report.get("summary", {}),
        tool_counts=review_report.get("tool_counts", []),
    )


def _ensure_family_candidates(review_report: dict[str, Any], fact_bundle: dict[str, Any], min_runs: int) -> dict[str, Any]:
    family_candidates = review_report.get("family_candidates")
    if family_candidates:
        return family_candidates
    return build_family_candidates(
        fact_bundle,
        source=review_report.get("source", "both"),
        min_slice_runs=min_runs,
    )


def _candidate_to_card(skill: str, candidate: dict[str, Any]) -> dict[str, Any] | None:
    opportunity = candidate.get("opportunity")
    if not opportunity:
        return None
    if candidate["rank"]["score"] < MIN_CARD_SCORE:
        return None

    card = {
        "skill": skill,
        "issue_type": candidate["family_id"],
        "score": candidate["rank"]["score"],
        "severity": candidate["severity"],
        "affected_runs": candidate["affected_runs"],
        "total_runs": candidate["total_runs"],
        "prevalence": candidate["prevalence"],
        "slice": candidate["slice"],
        "hypothesis": opportunity["hypothesis"],
        "recommendation": opportunity["recommendation"],
        "suggested_fix_class": candidate["allowed_fix_classes"][0],
        "allowed_fix_classes": candidate["allowed_fix_classes"],
        "target_files": candidate["target_files"],
        "evidence": list(candidate.get("representative_traces", [])),
        "evidence_refs": list(candidate.get("evidence_refs", [])),
        "family_candidate_id": candidate["family_candidate_id"],
        "skill_issue_brief": (
            f"Improve `{skill}` for `{candidate['family_id']}` in the slice `{candidate['slice']['label']}`. "
            f"Affected runs: {candidate['affected_runs']}/{candidate['total_runs']}. "
            f"{opportunity['recommendation']}"
        ),
    }
    if candidate.get("supporting_metrics"):
        card["supporting_metrics"] = candidate["supporting_metrics"]
    return card


def _filter_redundant_slices(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep global cards and only slice cards that materially differ."""
    globals_by_issue = {
        card["issue_type"]: card
        for card in cards
        if card["slice"]["label"] == "global"
    }

    filtered: list[dict[str, Any]] = []
    per_issue_counts: dict[str, int] = {}

    for card in cards:
        issue_type = card["issue_type"]
        is_global = card["slice"]["label"] == "global"
        global_card = globals_by_issue.get(issue_type)

        if is_global:
            filtered.append(card)
            per_issue_counts[issue_type] = per_issue_counts.get(issue_type, 0) + 1
            continue

        if not global_card:
            filtered.append(card)
            per_issue_counts[issue_type] = per_issue_counts.get(issue_type, 0) + 1
            continue

        prevalence_gap = card["prevalence"] - global_card["prevalence"]
        score_gap = card["score"] - global_card["score"]
        if prevalence_gap < 0.15 and score_gap < 5:
            continue

        if per_issue_counts.get(issue_type, 0) >= 3:
            continue

        filtered.append(card)
        per_issue_counts[issue_type] = per_issue_counts.get(issue_type, 0) + 1

    return filtered


def generate_opportunity_report(
    review_report: dict[str, Any],
    min_runs: int = 3,
    max_cards: int = 10,
    max_evidence: int = 3,
) -> dict[str, Any]:
    """Generate ranked improvement cards from a review report."""
    del max_evidence  # family candidates already bound evidence selection
    skill = review_report.get("skill")
    fact_bundle = _ensure_fact_bundle(review_report)
    family_candidates = _ensure_family_candidates(review_report, fact_bundle, min_runs=min_runs)

    cards = []
    for candidate in family_candidates.get("candidates", []):
        card = _candidate_to_card(skill, candidate)
        if card:
            cards.append(card)

    cards = _filter_redundant_slices(cards)
    cards.sort(
        key=lambda card: (
            card["score"],
            card["prevalence"],
            card["affected_runs"],
            1 if card["slice"]["label"] == "global" else 0,
        ),
        reverse=True,
    )
    cards_generated = len(cards)
    cards = cards[:max_cards]

    issue_types = {}
    slices = {}
    for card in cards:
        issue_types[card["issue_type"]] = issue_types.get(card["issue_type"], 0) + 1
        label = card["slice"]["label"]
        slices[label] = slices.get(label, 0) + 1

    return {
        "skill": skill,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_review": {
            "generated_at": review_report.get("generated_at"),
            "source": review_report.get("source"),
            "since": review_report.get("since"),
            "until": review_report.get("until"),
            "sessions_scanned": review_report.get("sessions_scanned"),
            "invocations_found": review_report.get("invocations_found", fact_bundle.get("invocations_found", 0)),
        },
        "summary": {
            "cards_generated": cards_generated,
            "cards_returned": len(cards),
            "issue_types": issue_types,
            "slices": slices,
        },
        "llm_interpretation_packet": review_report.get("llm_interpretation_packet")
        or build_llm_interpretation_packet(fact_bundle, family_candidates),
        "cards": cards,
    }


def render_opportunity_markdown(report: dict[str, Any]) -> str:
    """Render the opportunity report as markdown."""
    skill = report.get("skill", "unknown")
    source_review = report.get("source_review", {})
    cards = report.get("cards", [])

    lines = [f"## Skill Opportunity Funnel ({skill})", ""]
    lines.append(
        "Uses post-invocation transcript facts to rank the highest-leverage ways "
        "to improve the skill."
    )
    lines.append("")
    lines.append(f"- Sessions scanned: {source_review.get('sessions_scanned', 0)}")
    lines.append(f"- Invocations analyzed: {source_review.get('invocations_found', 0)}")
    lines.append(f"- Cards returned: {len(cards)}")
    lines.append("")

    if not cards:
        lines.append("No opportunity cards met the scoring threshold.")
        return "\n".join(lines) + "\n"

    lines.append("| Rank | Score | Type | Scope | Runs | Prev | Fix Class |")
    lines.append("|------|-------|------|-------|------|------|-----------|")
    for idx, card in enumerate(cards, start=1):
        lines.append(
            f"| {idx} | {card['score']} | {card['issue_type']} | {card['slice']['label']} | "
            f"{card['affected_runs']}/{card['total_runs']} | {card['prevalence']:.2f} | "
            f"{card['suggested_fix_class']} |"
        )

    for idx, card in enumerate(cards, start=1):
        lines.append("")
        lines.append(f"### {idx}. {card['issue_type']} ({card['score']})")
        lines.append(f"Scope: `{card['slice']['label']}`")
        lines.append(f"Why it matters: {card['hypothesis']}")
        lines.append(f"Suggested change: {card['recommendation']}")
        lines.append(f"Target files: {', '.join(card['target_files'])}")
        lines.append(f"Skill-issue brief: {card['skill_issue_brief']}")
        if card.get("supporting_metrics"):
            metrics = card["supporting_metrics"]
            stems = metrics.get("top_raw_shell_stems")
            if stems:
                pretty = ", ".join(
                    stem["stem"] if isinstance(stem, dict) else str(stem)
                    for stem in stems
                )
                lines.append(f"Supporting metrics: top raw shell stems = {pretty}")
        lines.append("Evidence:")
        for evidence in card.get("evidence", []):
            signal = evidence.get("signal", "")
            request = evidence.get("user_request") or "n/a"
            lines.append(
                f"- {evidence.get('timestamp')} | {signal} | {request}"
            )

    return "\n".join(lines) + "\n"
