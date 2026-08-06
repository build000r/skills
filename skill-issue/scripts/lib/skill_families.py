"""
Deterministic family candidate generation for skill review artifacts.
"""

from __future__ import annotations

import importlib.util
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAW_SHELL_STEMS = {"rg", "sed", "find", "git", "ls"}
SEVERITY_PRIORITY = {"high": "high", "medium": "medium", "low": "low"}
MIN_AUTOMATION_PREVALENCE = 0.3

try:
    from lib.skill_family_registry import FAMILY_REGISTRY
except ModuleNotFoundError:
    _registry_path = Path(__file__).resolve().with_name("skill_family_registry.py")
    _registry_spec = importlib.util.spec_from_file_location("skill_family_registry_local", _registry_path)
    _registry_module = importlib.util.module_from_spec(_registry_spec)
    assert _registry_spec and _registry_spec.loader
    _registry_spec.loader.exec_module(_registry_module)
    FAMILY_REGISTRY = _registry_module.FAMILY_REGISTRY


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _predicate_matches(family_id: str, invocation: dict[str, Any]) -> bool:
    flags = invocation.get("flags", {})
    matched_on = set(invocation.get("matched_on", []))
    if family_id == "observability-gap":
        return "skill_path" in matched_on and not (
            {"assistant_ack", "session_skill_context"} & matched_on
        )
    if family_id == "verification-gap":
        return not flags.get("has_validation")
    if family_id == "checkpoint-defaults":
        return flags.get("has_checkpoint", False)
    if family_id == "risk-gating-gap":
        return flags.get("has_risk_gate_gap", False)
    if family_id == "contract-clarity":
        return flags.get("has_user_correction", False)
    if family_id == "closeout-gap":
        return not flags.get("task_complete", False)
    if family_id == "automation-gap":
        stems = set(invocation.get("command_stems", {}))
        return bool(stems & RAW_SHELL_STEMS)
    if family_id == "invocation_miss":
        return flags.get("has_invocation_miss", False)
    if family_id == "trigger_mismatch":
        return flags.get("has_trigger_mismatch", False)
    if family_id == "output_rejected":
        return flags.get("has_output_rejected", False)
    if family_id == "output_corrected":
        return flags.get("has_output_corrected", False)
    if family_id == "wrong_skill_invoked":
        return flags.get("has_wrong_skill_invoked", False)
    raise KeyError(f"Unsupported family: {family_id}")


def _signal_for_family(family_id: str, invocation: dict[str, Any]) -> dict[str, Any]:
    base = {
        "invocation_id": invocation.get("invocation_id"),
        "session_id": invocation.get("session_id"),
        "timestamp": invocation.get("timestamp"),
        "project": invocation.get("project"),
        "task_type": invocation.get("task_type"),
        "file": invocation.get("file"),
        "user_request": invocation.get("user_request"),
    }
    refs = invocation.get("refs", {})
    if family_id == "observability-gap":
        return {**base, "signal": "skill path touched without explicit ack marker"}
    if family_id == "verification-gap":
        return {**base, "signal": "no validation command detected"}
    if family_id == "checkpoint-defaults":
        return {**base, "signal": (refs.get("checkpoint_messages") or ["checkpoint prompt detected"])[0]}
    if family_id == "risk-gating-gap":
        return {**base, "signal": (refs.get("risk_gating_messages") or ["risk gate should have existed"])[0]}
    if family_id == "contract-clarity":
        return {**base, "signal": (refs.get("user_corrections") or ["user redirect detected"])[0]}
    if family_id == "closeout-gap":
        return {**base, "signal": "no completion event detected"}
    if family_id == "automation-gap":
        stems = sorted(stem for stem in invocation.get("command_stems", {}) if stem in RAW_SHELL_STEMS)
        return {**base, "signal": f"raw shell stems: {', '.join(stems)}"}
    if family_id == "invocation_miss":
        return {**base, "signal": "user_request looks skill-shaped but scanner saw no trigger/ack/path signal"}
    if family_id == "trigger_mismatch":
        return {**base, "signal": "user_trigger matched without assistant_ack: description over-matches"}
    if family_id == "output_rejected":
        return {**base, "signal": (refs.get("user_corrections") or ["user correction without task_complete"])[0]}
    if family_id == "output_corrected":
        return {**base, "signal": (refs.get("user_corrections") or ["user correction after task_complete"])[0]}
    if family_id == "wrong_skill_invoked":
        return {**base, "signal": (refs.get("user_corrections") or ["user redirected to another slash-command"])[0]}
    raise KeyError(f"Unsupported family: {family_id}")


def _holdout_signal(family_id: str) -> str:
    mapping = {
        "observability-gap": "holdout control: explicit ack marker detected",
        "verification-gap": "holdout control: validation command detected",
        "checkpoint-defaults": "holdout control: no checkpoint prompt detected",
        "risk-gating-gap": "holdout control: no missing risk gate cue detected",
        "contract-clarity": "holdout control: no user redirect detected",
        "closeout-gap": "holdout control: completion event detected",
        "automation-gap": "holdout control: no raw shell stems detected",
        "invocation_miss": "holdout control: trigger/ack/path signal present",
        "trigger_mismatch": "holdout control: trigger and ack both present",
        "output_rejected": "holdout control: run completed without user correction",
        "output_corrected": "holdout control: run completed without user correction",
        "wrong_skill_invoked": "holdout control: no slash-command redirect in corrections",
    }
    return mapping[family_id]


def _build_holdout_examples(
    family_id: str,
    group_invocations: list[dict[str, Any]],
    max_controls: int,
) -> list[dict[str, Any]]:
    if max_controls <= 0:
        return []

    candidates = [
        invocation
        for invocation in group_invocations
        if not _predicate_matches(family_id, invocation)
    ]
    candidates.sort(
        key=lambda invocation: (
            _parse_timestamp(invocation.get("timestamp")),
            invocation.get("invocation_id") or "",
        ),
        reverse=True,
    )
    rows = []
    for invocation in candidates[:max_controls]:
        row = _signal_for_family(family_id, invocation)
        row["signal"] = _holdout_signal(family_id)
        rows.append(row)
    return rows


def _coverage_weight(total_runs: int, overall_runs: int) -> float:
    if overall_runs <= 0:
        return 1.0
    fraction = total_runs / overall_runs
    return 0.6 + 0.4 * min(fraction / 0.5, 1.0)


def _recency_weight(invocations: list[dict[str, Any]], now: datetime) -> float:
    if not invocations:
        return 1.0

    latest = max(_parse_timestamp(invocation.get("timestamp")) for invocation in invocations)
    age_days = max(0, (now - latest).days)
    if age_days <= 7:
        return 1.25
    if age_days <= 30:
        return 1.1
    return 1.0


def _score_candidate(
    *,
    prevalence: float,
    total_runs: int,
    overall_runs: int,
    affected_invocations: list[dict[str, Any]],
    impact_weight: float,
    confidence_weight: float,
    now: datetime,
) -> tuple[int, float, float]:
    coverage_weight = _coverage_weight(total_runs, overall_runs)
    recency_weight = _recency_weight(affected_invocations, now)
    score = round(prevalence * impact_weight * confidence_weight * coverage_weight * recency_weight * 20)
    return score, coverage_weight, recency_weight


def _group_invocations(invocations: list[dict[str, Any]], min_slice_runs: int) -> list[dict[str, Any]]:
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
            if len(items) < min_slice_runs:
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


def _supporting_metrics_for_group(group_invocations: list[dict[str, Any]]) -> dict[str, Any]:
    stem_counts: Counter[str] = Counter()
    for invocation in group_invocations:
        stem_counts.update(stem for stem in invocation.get("command_stems", {}) if stem in RAW_SHELL_STEMS)
    return {
        "top_raw_shell_stems": [
            {"stem": stem, "count": count}
            for stem, count in sorted(stem_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
    }


def build_family_candidates(
    fact_bundle: dict[str, Any],
    *,
    source: str,
    max_evidence: int = 3,
    max_controls: int = 2,
    min_slice_runs: int = 3,
) -> dict[str, Any]:
    """Build deterministic family candidates from a fact bundle."""
    now = _parse_timestamp(fact_bundle.get("generated_at"))
    invocations = list(fact_bundle.get("invocations", []))
    overall_runs = len(invocations)
    candidates: list[dict[str, Any]] = []

    for group in _group_invocations(invocations, min_slice_runs=min_slice_runs):
        group_invocations = group["invocations"]
        total_runs = len(group_invocations)

        for family_id, rule in FAMILY_REGISTRY.items():
            if family_id == "provider-coverage":
                if group["label"] != "global":
                    continue
                providers = fact_bundle.get("summary", {}).get("providers", {})
                if source not in {"claude", "both", "all"} or providers.get("claude", 0) > 0:
                    continue
                affected_invocations: list[dict[str, Any]] = []
                affected_runs = 0
                prevalence = 0.0
                score, coverage_weight, recency_weight = _score_candidate(
                    prevalence=1.0,
                    total_runs=max(total_runs, 1),
                    overall_runs=max(overall_runs, 1),
                    affected_invocations=group_invocations,
                    impact_weight=rule["impact_weight"],
                    confidence_weight=rule["confidence_weight"],
                    now=now,
                )
                representative_traces: list[dict[str, Any]] = []
                evidence_refs: list[str] = []
                holdout_examples: list[dict[str, Any]] = []
            else:
                affected_invocations = [
                    invocation for invocation in group_invocations if _predicate_matches(family_id, invocation)
                ]
                affected_runs = len(affected_invocations)
                if affected_runs == 0:
                    continue
                prevalence = round(affected_runs / total_runs, 3) if total_runs else 0.0
                if family_id == "automation-gap" and prevalence < MIN_AUTOMATION_PREVALENCE:
                    continue

                score, coverage_weight, recency_weight = _score_candidate(
                    prevalence=prevalence,
                    total_runs=total_runs,
                    overall_runs=max(overall_runs, 1),
                    affected_invocations=affected_invocations,
                    impact_weight=rule["impact_weight"],
                    confidence_weight=rule["confidence_weight"],
                    now=now,
                )
                representative_traces = [
                    _signal_for_family(family_id, invocation) for invocation in affected_invocations[:max_evidence]
                ]
                evidence_refs = [invocation.get("invocation_id") for invocation in affected_invocations[:max_evidence]]
                holdout_examples = _build_holdout_examples(
                    family_id,
                    group_invocations,
                    max_controls=max_controls,
                )

            candidate = {
                "family_candidate_id": f"{family_id}__{group['label']}",
                "family_id": family_id,
                "slice": {
                    "label": group["label"],
                    "dimension": group["dimension"],
                    "value": group["value"],
                },
                "affected_runs": affected_runs,
                "total_runs": total_runs,
                "prevalence": prevalence,
                "watch_metric": rule["watch_metric"],
                "severity": rule["severity"],
                "allowed_fix_classes": list(rule["allowed_fix_classes"]),
                "target_files": list(rule["target_files"]),
                "evidence_refs": evidence_refs,
                "representative_traces": representative_traces,
                "holdout_examples": holdout_examples,
                "rank": {
                    "score": score,
                    "impact_weight": rule["impact_weight"],
                    "confidence_weight": rule["confidence_weight"],
                    "coverage_weight": coverage_weight,
                    "recency_weight": recency_weight,
                },
                "legacy": {
                    "opportunity_id": rule.get("legacy_opportunity_id"),
                    "priority": rule.get("legacy_priority", SEVERITY_PRIORITY[rule["severity"]]),
                    "summary": rule.get("legacy_summary"),
                },
            }
            if rule.get("packet_failure_family"):
                candidate["packet"] = {
                    "failure_family": rule["packet_failure_family"],
                    "why_now": rule["packet_why_now"],
                    "expected_contract": rule["packet_expected_contract"],
                }
            if rule.get("opportunity_hypothesis"):
                candidate["opportunity"] = {
                    "hypothesis": rule["opportunity_hypothesis"],
                    "recommendation": rule["opportunity_recommendation"],
                }
            if family_id == "automation-gap":
                candidate["supporting_metrics"] = _supporting_metrics_for_group(group_invocations)
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -item["rank"]["score"],
            -item["prevalence"],
            -item["affected_runs"],
            0 if item["slice"]["label"] == "global" else 1,
            item["family_id"],
            item["slice"]["label"],
        )
    )

    return {
        "schema": "family_candidates.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_schema": fact_bundle.get("schema"),
        "skill": fact_bundle.get("skill"),
        "candidates": candidates,
    }


def build_llm_interpretation_packet(
    fact_bundle: dict[str, Any],
    family_candidates: dict[str, Any],
    *,
    max_candidates: int = 3,
) -> dict[str, Any]:
    """Build a bounded deterministic packet for the interpretation layer."""
    candidates = sorted(
        family_candidates.get("candidates", []),
        key=lambda item: (
            0 if item["slice"]["label"] == "global" else 1,
            -item["rank"]["score"],
            item["family_candidate_id"],
        ),
    )
    selected = candidates[:max_candidates]
    return {
        "schema": "llm_interpretation_packet.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skill": fact_bundle.get("skill"),
        "bundle_hash": fact_bundle.get("bundle_hash"),
        "candidate_count": len(selected),
        "top_candidates": [
            {
                "family_candidate_id": candidate["family_candidate_id"],
                "family_id": candidate["family_id"],
                "slice": candidate["slice"],
                "watch_metric": candidate["watch_metric"],
                "allowed_fix_classes": candidate["allowed_fix_classes"],
                "target_files": candidate["target_files"],
                "evidence_refs": candidate["evidence_refs"],
            }
            for candidate in selected
        ],
        "constraints": {
            "must_cite_candidate_ids": True,
            "must_choose_from_allowed_fix_classes": True,
            "max_candidates": max_candidates,
        },
    }


def build_opportunities_from_candidates(
    family_candidates: dict[str, Any],
    *,
    global_only: bool = True,
) -> list[dict[str, Any]]:
    """Render legacy opportunity rows from shared family candidates."""
    opportunities: list[dict[str, Any]] = []
    skill = family_candidates.get("skill", "skill")
    for candidate in family_candidates.get("candidates", []):
        if global_only and candidate.get("slice", {}).get("label") != "global":
            continue

        legacy = candidate.get("legacy", {})
        opportunity_id = legacy.get("opportunity_id")
        summary = legacy.get("summary")
        if not opportunity_id or not summary:
            continue

        evidence = list(candidate.get("representative_traces", []))
        if candidate["family_id"] == "automation-gap":
            evidence = list(candidate.get("supporting_metrics", {}).get("top_raw_shell_stems", []))

        opportunities.append(
            {
                "id": opportunity_id,
                "priority": legacy.get("priority", "medium"),
                "summary": summary.replace("<skill>", skill),
                "evidence": evidence,
            }
        )
    return opportunities
