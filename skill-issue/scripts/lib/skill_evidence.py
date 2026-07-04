"""
Operator-evidence packet generation for skill review reports.

This bridges aggregate transcript-review metrics to concrete skill edits and
historical reference slices before a team invests in a fuller eval harness.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _post_ship_window(affected_runs: int) -> dict[str, Any]:
    min_new_invocations = max(5, min(20, affected_runs * 2))
    return {
        "type": "real_invocation_window",
        "source_of_truth": "future real skill invocations",
        "synthetic_reruns": "avoid by default",
        "min_new_invocations": min_new_invocations,
        "max_days": 14,
    }


def _packet_brief(skill: str, issue_type: str, affected_runs: int, total_runs: int, expected_contract: str) -> str:
    return (
        f"Improve `{skill}` for `{issue_type}` using the attached operator evidence packet. "
        f"Affected runs: {affected_runs}/{total_runs}. Expected contract: {expected_contract}"
    )


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


def _ensure_family_candidates(review_report: dict[str, Any], fact_bundle: dict[str, Any]) -> dict[str, Any]:
    family_candidates = review_report.get("family_candidates")
    if family_candidates:
        return family_candidates
    return build_family_candidates(
        fact_bundle,
        source=review_report.get("source", "both"),
    )


def generate_evidence_report(
    review_report: dict[str, Any],
    min_occurrences: int = 2,
    max_packets: int = 5,
    max_examples: int = 3,
    max_controls: int = 2,
) -> dict[str, Any]:
    """Generate operator-evidence packets from a review report."""
    skill = review_report.get("skill")
    fact_bundle = _ensure_fact_bundle(review_report)
    family_candidates = _ensure_family_candidates(review_report, fact_bundle)

    packets: list[dict[str, Any]] = []
    for candidate in family_candidates.get("candidates", []):
        packet_meta = candidate.get("packet")
        if not packet_meta:
            continue
        if candidate.get("slice", {}).get("label") != "global":
            continue
        if candidate.get("affected_runs", 0) < min_occurrences:
            continue

        affected_runs = candidate["affected_runs"]
        total_runs = candidate["total_runs"]
        packet = {
            "packet_id": candidate["family_candidate_id"],
            "issue_type": candidate["family_id"],
            "failure_family": packet_meta["failure_family"],
            "why_now": packet_meta["why_now"],
            "expected_contract": packet_meta["expected_contract"],
            "suggested_fix_class": candidate["allowed_fix_classes"][0],
            "target_files": candidate["target_files"],
            "watch_metric": candidate["watch_metric"],
            "experiment_unit": "real_invocation_window",
            "affected_runs": affected_runs,
            "total_runs": total_runs,
            "prevalence": candidate["prevalence"],
            "representative_traces": list(candidate.get("representative_traces", []))[:max_examples],
            "historical_reference_slice": {
                "target_examples": list(candidate.get("representative_traces", []))[:max_examples],
                "holdout_examples": list(candidate.get("holdout_examples", []))[:max_controls],
            },
            "post_ship_window": _post_ship_window(affected_runs),
            "skill_issue_brief": _packet_brief(
                skill=skill,
                issue_type=candidate["family_id"],
                affected_runs=affected_runs,
                total_runs=total_runs,
                expected_contract=packet_meta["expected_contract"],
            ),
            "family_candidate_id": candidate["family_candidate_id"],
            "allowed_fix_classes": candidate["allowed_fix_classes"],
            "evidence_refs": candidate["evidence_refs"],
        }
        packet["replay_slice"] = packet["historical_reference_slice"]
        if candidate.get("supporting_metrics"):
            packet["supporting_metrics"] = candidate["supporting_metrics"]
        packets.append(packet)

    packets.sort(
        key=lambda packet: (
            packet["affected_runs"],
            packet["prevalence"],
            packet["packet_id"],
        ),
        reverse=True,
    )
    packets_generated = len(packets)
    packets = packets[:max_packets]

    return {
        "skill": skill,
        "generated_at": review_report.get("generated_at"),
        "source_review": {
            "generated_at": review_report.get("generated_at"),
            "source": review_report.get("source"),
            "since": review_report.get("since"),
            "until": review_report.get("until"),
            "sessions_scanned": review_report.get("sessions_scanned"),
            "invocations_found": review_report.get("invocations_found", fact_bundle.get("invocations_found", 0)),
        },
        "summary": {
            "packets_generated": packets_generated,
            "packets_returned": len(packets),
            "issue_types": {packet["issue_type"]: packet["affected_runs"] for packet in packets},
        },
        "llm_interpretation_packet": review_report.get("llm_interpretation_packet")
        or build_llm_interpretation_packet(fact_bundle, family_candidates),
        "packets": packets,
    }


def render_evidence_markdown(report: dict[str, Any]) -> str:
    """Render operator-evidence packets as markdown."""
    skill = report.get("skill", "unknown")
    source_review = report.get("source_review", {})
    packets = report.get("packets", [])

    lines = [f"## Operator Evidence Packets ({skill})", ""]
    lines.append(
        "Turns repeated transcript failures into packetized review artifacts that can "
        "drive a targeted skill patch and a post-ship live observation window."
    )
    lines.append("")
    lines.append(f"- Sessions scanned: {source_review.get('sessions_scanned', 0)}")
    lines.append(f"- Invocations analyzed: {source_review.get('invocations_found', 0)}")
    lines.append(f"- Packets returned: {len(packets)}")
    lines.append("")

    if not packets:
        lines.append("No evidence packets met the minimum occurrence threshold.")
        return "\n".join(lines) + "\n"

    lines.append("| Rank | Failure Family | Runs | Prev | Watch Metric | Fix Class |")
    lines.append("|------|----------------|------|------|--------------|-----------|")
    for idx, packet in enumerate(packets, start=1):
        lines.append(
            f"| {idx} | {packet['issue_type']} | {packet['affected_runs']}/{packet['total_runs']} | "
            f"{packet['prevalence']:.2f} | {packet['watch_metric']} | {packet['suggested_fix_class']} |"
        )

    for idx, packet in enumerate(packets, start=1):
        lines.append("")
        lines.append(f"### {idx}. {packet['issue_type']}")
        lines.append(f"Failure family: {packet['failure_family']}")
        lines.append(f"Why now: {packet['why_now']}")
        lines.append(f"Expected contract: {packet['expected_contract']}")
        lines.append(f"Target files: {', '.join(packet['target_files'])}")
        lines.append(f"Watch metric: {packet['watch_metric']}")
        if packet.get("experiment_unit"):
            lines.append(f"Experiment unit: {packet['experiment_unit']}")
        if packet.get("post_ship_window"):
            window = packet["post_ship_window"]
            lines.append(
                "Post-ship window: "
                f"next {window.get('min_new_invocations')} real invocations or "
                f"{window.get('max_days')} days"
            )
        lines.append(f"Skill-issue brief: {packet['skill_issue_brief']}")
        if packet.get("supporting_metrics"):
            stems = packet["supporting_metrics"].get("top_raw_shell_stems", [])
            if stems:
                pretty = ", ".join(
                    stem["stem"] if isinstance(stem, dict) else str(stem)
                    for stem in stems
                )
                lines.append(f"Supporting metrics: top raw shell stems = {pretty}")
        lines.append("Representative traces:")
        for trace in packet.get("representative_traces", []):
            session_id = trace.get("session_id") or trace.get("invocation_id") or "unknown-session"
            lines.append(
                f"- {trace.get('timestamp')} | {session_id} | {trace.get('signal')} | {trace.get('user_request') or 'n/a'}"
            )
        lines.append("Historical reference slice:")
        for trace in packet.get("historical_reference_slice", {}).get("holdout_examples", []):
            session_id = trace.get("session_id") or trace.get("invocation_id") or "unknown-session"
            lines.append(
                f"- holdout | {trace.get('timestamp')} | {session_id} | {trace.get('user_request') or 'n/a'}"
            )

    return "\n".join(lines) + "\n"
