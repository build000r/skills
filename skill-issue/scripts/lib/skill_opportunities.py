"""
Deterministic-ish opportunity mining for skill review reports.

Turns post-invocation skill review data into ranked improvement cards that can
be handed back into skill-issue for focused iteration.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from lib.skill_review import parse_timestamp

RAW_SHELL_STEMS = {"rg", "sed", "find", "git", "ls"}
MIN_CARD_SCORE = 10

TASK_TYPE_PATTERNS = (
    ("review", ("review", "audit", "lookback", "judge", "eval", "measure", "trend")),
    ("package", ("package", "publish", "bundle", ".skill")),
    ("create", ("create", "make", "new skill", "build", "template", "init")),
    ("update", ("update", "improve", "fix", "iterate", "refactor", "tighten")),
)

ISSUE_RULES = {
    "verification-gap": {
        "impact_weight": 5.0,
        "confidence_weight": 1.0,
        "severity": "high",
        "suggested_fix_class": "tighten-skill-contract",
        "target_files": ["SKILL.md", "scripts/"],
        "hypothesis": (
            "The skill contract does not force a concrete verification path, or the "
            "documented validation path is too manual to be used consistently."
        ),
        "recommendation": (
            "Add or tighten a required verification block and bundle a helper script "
            "when the validation path is repetitive."
        ),
    },
    "contract-clarity": {
        "impact_weight": 5.0,
        "confidence_weight": 0.95,
        "severity": "high",
        "suggested_fix_class": "tighten-trigger-language",
        "target_files": ["SKILL.md", "references/"],
        "hypothesis": (
            "The skill contract is underspecified for at least one common task shape, "
            "so the user has to redirect the run after the skill is already active."
        ),
        "recommendation": (
            "Tighten trigger language, defaults, non-goals, and early branching rules "
            "so the run picks the right path without redirection."
        ),
    },
    "checkpoint-defaults": {
        "impact_weight": 3.0,
        "confidence_weight": 0.95,
        "severity": "medium",
        "suggested_fix_class": "move-preferences-into-defaults",
        "target_files": ["SKILL.md", "modes/"],
        "hypothesis": (
            "The skill still relies on user checkpoints for choices that could be "
            "handled through defaults or mode configuration."
        ),
        "recommendation": (
            "Move repeated preferences into mode files or explicit defaults so the "
            "skill only asks when information is missing or risky."
        ),
    },
    "risk-gating-gap": {
        "impact_weight": 4.5,
        "confidence_weight": 0.8,
        "severity": "high",
        "suggested_fix_class": "add-risk-gating-rules",
        "target_files": ["SKILL.md", "references/", "modes/"],
        "hypothesis": (
            "The skill is treating an irreversible or externally reviewed step as a "
            "default path when it should pause for confirmation, clarification, or a "
            "designated human reviewer."
        ),
        "recommendation": (
            "Add explicit risk gates for high-cost steps, including when to ask first, "
            "wait for clarification, or bring in a named reviewer before proceeding."
        ),
    },
    "automation-gap": {
        "impact_weight": 3.0,
        "confidence_weight": 0.85,
        "severity": "medium",
        "suggested_fix_class": "bundle-helper-script",
        "target_files": ["scripts/", "references/", "SKILL.md"],
        "hypothesis": (
            "The workflow depends on repeated ad-hoc shell inspection instead of a "
            "stable helper script or reference."
        ),
        "recommendation": (
            "Bundle the recurring analysis path into a helper script or concise "
            "reference and point the skill at it."
        ),
    },
    "closeout-gap": {
        "impact_weight": 2.5,
        "confidence_weight": 0.75,
        "severity": "medium",
        "suggested_fix_class": "strengthen-closeout",
        "target_files": ["SKILL.md"],
        "hypothesis": (
            "The skill does not consistently drive runs to a clear completion event "
            "or explicit final verification closeout."
        ),
        "recommendation": (
            "Strengthen the completion block so the run ends with verification "
            "evidence and a clear done state."
        ),
    },
    "observability-gap": {
        "impact_weight": 1.5,
        "confidence_weight": 0.95,
        "severity": "low",
        "suggested_fix_class": "add-stable-ack-marker",
        "target_files": ["SKILL.md"],
        "hypothesis": (
            "The skill does not require a stable first-use acknowledgement, so "
            "tracking usage depends on path-touch heuristics."
        ),
        "recommendation": (
            "Require a stable first commentary marker so invocation detection and "
            "trend reporting are easier to trust."
        ),
    },
}


def infer_task_type(user_request: str | None) -> str:
    """Infer a coarse task type from the first user request."""
    if not user_request:
        return "general"

    text = user_request.lower()
    for label, patterns in TASK_TYPE_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return label
    return "general"


def infer_invocation_mode(invocation: dict[str, Any]) -> str:
    """Infer how the invocation was detected."""
    matched_on = set(invocation.get("matched_on", []))
    if "assistant_ack" in matched_on:
        return "explicit-ack"
    if "skill_path" in matched_on:
        return "path-inferred"
    if "user_trigger" in matched_on:
        return "trigger-inferred"
    return "unknown"


def enrich_invocation(invocation: dict[str, Any]) -> dict[str, Any]:
    """Attach stable metadata used for slicing."""
    enriched = dict(invocation)
    project = invocation.get("project")
    if isinstance(project, str) and project.startswith("/"):
        enriched["project"] = project.rstrip("/").rsplit("/", 1)[-1]
    enriched["task_type"] = infer_task_type(invocation.get("user_request"))
    enriched["invocation_mode"] = infer_invocation_mode(invocation)
    return enriched


def group_invocations(invocations: list[dict[str, Any]], min_runs: int) -> list[dict[str, Any]]:
    """Create global and single-dimension slices for opportunity mining."""
    groups = [
        {
            "label": "global",
            "dimension": "global",
            "value": "all",
            "invocations": invocations,
        }
    ]

    for dimension in ("provider", "project", "task_type", "invocation_mode"):
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for invocation in invocations:
            value = invocation.get(dimension) or "unknown"
            buckets[str(value)].append(invocation)

        for value, items in sorted(buckets.items()):
            if len(items) < min_runs:
                continue
            groups.append(
                {
                    "label": f"{dimension}={value}",
                    "dimension": dimension,
                    "value": value,
                    "invocations": items,
                }
            )

    return groups


def _coverage_weight(total_runs: int, overall_runs: int) -> float:
    """Favor signals that affect meaningful portions of the sample."""
    if overall_runs <= 0:
        return 1.0
    fraction = total_runs / overall_runs
    return 0.6 + 0.4 * min(fraction / 0.5, 1.0)


def _recency_weight(invocations: list[dict[str, Any]], now: datetime) -> float:
    """Favor issues that are still happening recently."""
    if not invocations:
        return 1.0

    latest = max(
        parse_timestamp(invocation.get("timestamp"), now)
        for invocation in invocations
    )
    age_days = max(0, (now - latest).days)
    if age_days <= 7:
        return 1.25
    if age_days <= 30:
        return 1.1
    return 1.0


def _score_card(
    prevalence: float,
    total_runs: int,
    overall_runs: int,
    affected_invocations: list[dict[str, Any]],
    impact_weight: float,
    confidence_weight: float,
    now: datetime,
) -> int:
    """Compute a ranked score for an opportunity card."""
    coverage_weight = _coverage_weight(total_runs, overall_runs)
    recency_weight = _recency_weight(affected_invocations, now)
    return round(prevalence * impact_weight * confidence_weight * coverage_weight * recency_weight * 20)


def _evidence_for_rule(issue_type: str, invocation: dict[str, Any]) -> dict[str, Any]:
    """Build a compact evidence snippet for one invocation."""
    evidence = {
        "timestamp": invocation.get("timestamp"),
        "file": invocation.get("file"),
        "user_request": invocation.get("user_request"),
    }

    if issue_type == "verification-gap":
        evidence["signal"] = "no validation command detected"
    elif issue_type == "contract-clarity":
        evidence["signal"] = (invocation.get("user_corrections") or ["user redirect detected"])[0]
    elif issue_type == "checkpoint-defaults":
        evidence["signal"] = (invocation.get("checkpoint_messages") or ["checkpoint prompt detected"])[0]
    elif issue_type == "risk-gating-gap":
        evidence["signal"] = (invocation.get("risk_gating_messages") or ["risk gate should have existed"])[0]
    elif issue_type == "closeout-gap":
        evidence["signal"] = "no completion event detected"
    elif issue_type == "observability-gap":
        evidence["signal"] = "skill path touched without explicit ack marker"

    return evidence


def _predicate_matches(issue_type: str, invocation: dict[str, Any]) -> bool:
    """Return whether an invocation matches a rule."""
    matched_on = set(invocation.get("matched_on", []))

    if issue_type == "verification-gap":
        return not invocation.get("validation_commands")
    if issue_type == "contract-clarity":
        return bool(invocation.get("user_corrections"))
    if issue_type == "checkpoint-defaults":
        return bool(invocation.get("checkpoint_messages"))
    if issue_type == "risk-gating-gap":
        return bool(invocation.get("risk_gating_messages"))
    if issue_type == "closeout-gap":
        return not invocation.get("task_complete")
    if issue_type == "observability-gap":
        return "skill_path" in matched_on and "assistant_ack" not in matched_on
    raise KeyError(f"Unsupported issue type: {issue_type}")


def _automation_card(
    skill: str,
    group: dict[str, Any],
    overall_runs: int,
    max_evidence: int,
    now: datetime,
) -> dict[str, Any] | None:
    """Generate an automation-gap card from repeated raw shell stems."""
    stem_counts: Counter[str] = Counter()
    affected_invocations: list[dict[str, Any]] = []

    for invocation in group["invocations"]:
        invocation_stems = set(invocation.get("command_stems", {}))
        raw_hits = sorted(stem for stem in invocation_stems if stem in RAW_SHELL_STEMS)
        if not raw_hits:
            continue
        stem_counts.update(raw_hits)
        affected_invocations.append(invocation)

    total_runs = len(group["invocations"])
    affected_runs = len(affected_invocations)
    if total_runs == 0 or affected_runs < 2:
        return None

    prevalence = affected_runs / total_runs
    if prevalence < 0.3:
        return None

    score = _score_card(
        prevalence=prevalence,
        total_runs=total_runs,
        overall_runs=overall_runs,
        affected_invocations=affected_invocations,
        impact_weight=ISSUE_RULES["automation-gap"]["impact_weight"],
        confidence_weight=ISSUE_RULES["automation-gap"]["confidence_weight"],
        now=now,
    )
    if score < MIN_CARD_SCORE:
        return None

    top_stems = [stem for stem, _ in stem_counts.most_common(3)]
    rule = ISSUE_RULES["automation-gap"]
    evidence = []
    for invocation in affected_invocations[:max_evidence]:
        invocation_stems = sorted(stem for stem in invocation.get("command_stems", {}) if stem in RAW_SHELL_STEMS)
        evidence.append(
            {
                "timestamp": invocation.get("timestamp"),
                "file": invocation.get("file"),
                "user_request": invocation.get("user_request"),
                "signal": f"raw shell stems: {', '.join(invocation_stems)}",
            }
        )

    return {
        "skill": skill,
        "issue_type": "automation-gap",
        "score": score,
        "severity": rule["severity"],
        "affected_runs": affected_runs,
        "total_runs": total_runs,
        "prevalence": round(prevalence, 3),
        "slice": {
            "label": group["label"],
            "dimension": group["dimension"],
            "value": group["value"],
        },
        "supporting_metrics": {
            "top_raw_shell_stems": top_stems,
        },
        "hypothesis": rule["hypothesis"],
        "recommendation": rule["recommendation"],
        "suggested_fix_class": rule["suggested_fix_class"],
        "target_files": rule["target_files"],
        "evidence": evidence,
        "skill_issue_brief": _skill_issue_brief(
            skill=skill,
            issue_type="automation-gap",
            group=group,
            affected_runs=affected_runs,
            total_runs=total_runs,
            recommendation=rule["recommendation"],
        ),
    }


def _rule_cards(
    skill: str,
    group: dict[str, Any],
    overall_runs: int,
    max_evidence: int,
    now: datetime,
) -> list[dict[str, Any]]:
    """Generate cards for simple per-invocation predicates."""
    cards: list[dict[str, Any]] = []
    total_runs = len(group["invocations"])
    if total_runs == 0:
        return cards

    for issue_type, rule in ISSUE_RULES.items():
        if issue_type == "automation-gap":
            continue

        affected_invocations = [
            invocation
            for invocation in group["invocations"]
            if _predicate_matches(issue_type, invocation)
        ]
        affected_runs = len(affected_invocations)
        if affected_runs == 0:
            continue

        prevalence = affected_runs / total_runs
        score = _score_card(
            prevalence=prevalence,
            total_runs=total_runs,
            overall_runs=overall_runs,
            affected_invocations=affected_invocations,
            impact_weight=rule["impact_weight"],
            confidence_weight=rule["confidence_weight"],
            now=now,
        )
        if score < MIN_CARD_SCORE:
            continue

        evidence = [
            _evidence_for_rule(issue_type, invocation)
            for invocation in affected_invocations[:max_evidence]
        ]
        cards.append(
            {
                "skill": skill,
                "issue_type": issue_type,
                "score": score,
                "severity": rule["severity"],
                "affected_runs": affected_runs,
                "total_runs": total_runs,
                "prevalence": round(prevalence, 3),
                "slice": {
                    "label": group["label"],
                    "dimension": group["dimension"],
                    "value": group["value"],
                },
                "hypothesis": rule["hypothesis"],
                "recommendation": rule["recommendation"],
                "suggested_fix_class": rule["suggested_fix_class"],
                "target_files": rule["target_files"],
                "evidence": evidence,
                "skill_issue_brief": _skill_issue_brief(
                    skill=skill,
                    issue_type=issue_type,
                    group=group,
                    affected_runs=affected_runs,
                    total_runs=total_runs,
                    recommendation=rule["recommendation"],
                ),
            }
        )

    automation = _automation_card(
        skill=skill,
        group=group,
        overall_runs=overall_runs,
        max_evidence=max_evidence,
        now=now,
    )
    if automation:
        cards.append(automation)

    return cards


def _skill_issue_brief(
    skill: str,
    issue_type: str,
    group: dict[str, Any],
    affected_runs: int,
    total_runs: int,
    recommendation: str,
) -> str:
    """Create a concise handoff line for a follow-up skill-issue run."""
    if group["label"] == "global":
        scope = "across all detected runs"
    else:
        scope = f"in the slice `{group['label']}`"

    return (
        f"Improve `{skill}` for `{issue_type}` {scope}. "
        f"Affected runs: {affected_runs}/{total_runs}. {recommendation}"
    )


def generate_opportunity_report(
    review_report: dict[str, Any],
    min_runs: int = 3,
    max_cards: int = 10,
    max_evidence: int = 3,
) -> dict[str, Any]:
    """Generate ranked improvement cards from a review report."""
    skill = review_report.get("skill")
    raw_invocations = review_report.get("invocations", [])
    invocations = [enrich_invocation(invocation) for invocation in raw_invocations]
    overall_runs = len(invocations)
    now = datetime.now(timezone.utc)

    groups = group_invocations(invocations, min_runs=min_runs)
    cards: list[dict[str, Any]] = []
    for group in groups:
        cards.extend(
            _rule_cards(
                skill=skill,
                group=group,
                overall_runs=overall_runs,
                max_evidence=max_evidence,
                now=now,
            )
        )

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

    issue_counts = Counter(card["issue_type"] for card in cards)
    slice_counts = Counter(card["slice"]["label"] for card in cards)

    return {
        "skill": skill,
        "generated_at": now.isoformat(),
        "source_review": {
            "generated_at": review_report.get("generated_at"),
            "source": review_report.get("source"),
            "since": review_report.get("since"),
            "until": review_report.get("until"),
            "sessions_scanned": review_report.get("sessions_scanned"),
            "invocations_found": review_report.get("invocations_found", overall_runs),
        },
        "summary": {
            "cards_generated": len(cards),
            "cards_returned": min(len(cards), max_cards),
            "issue_types": dict(issue_counts),
            "slices": dict(slice_counts),
        },
        "cards": cards[:max_cards],
    }


def _filter_redundant_slices(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep global cards and only slice cards that are materially worse than global."""
    globals_by_issue = {
        card["issue_type"]: card
        for card in cards
        if card["slice"]["label"] == "global"
    }

    filtered: list[dict[str, Any]] = []
    per_issue_counts: Counter[str] = Counter()

    for card in cards:
        issue_type = card["issue_type"]
        is_global = card["slice"]["label"] == "global"
        global_card = globals_by_issue.get(issue_type)

        if is_global:
            filtered.append(card)
            per_issue_counts[issue_type] += 1
            continue

        if not global_card:
            filtered.append(card)
            per_issue_counts[issue_type] += 1
            continue

        prevalence_gap = card["prevalence"] - global_card["prevalence"]
        score_gap = card["score"] - global_card["score"]
        if prevalence_gap < 0.15 and score_gap < 5:
            continue

        if per_issue_counts[issue_type] >= 3:
            continue

        filtered.append(card)
        per_issue_counts[issue_type] += 1

    return filtered


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
                lines.append(f"Supporting metrics: top raw shell stems = {', '.join(stems)}")
        lines.append("Evidence:")
        for evidence in card.get("evidence", []):
            signal = evidence.get("signal", "")
            request = evidence.get("user_request") or "n/a"
            lines.append(
                f"- {evidence.get('timestamp')} | {signal} | {request}"
            )

    return "\n".join(lines) + "\n"
