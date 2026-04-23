"""
Shared deterministic fact normalization for skill review artifacts.
"""

from __future__ import annotations

import json
from hashlib import sha1, sha256
from pathlib import Path
from typing import Any

TASK_TYPE_PATTERNS = (
    ("review", ("review", "audit", "lookback", "judge", "eval", "measure", "trend")),
    ("package", ("package", "publish", "bundle", ".skill")),
    ("create", ("create", "make", "new skill", "build", "template", "init")),
    ("update", ("update", "improve", "fix", "iterate", "refactor", "tighten")),
)


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


def build_invocation_id(invocation: dict[str, Any]) -> str:
    """Build a stable invocation id from transcript metadata."""
    key = "|".join(
        [
            str(invocation.get("provider", "")),
            str(invocation.get("file", "")),
            str(invocation.get("timestamp", "")),
            str(invocation.get("user_request", "")),
        ]
    )
    return f"inv_{sha1(key.encode('utf-8')).hexdigest()[:12]}"


def enrich_invocation(invocation: dict[str, Any]) -> dict[str, Any]:
    """Attach shared deterministic fields used across review outputs."""
    enriched = dict(invocation)
    project = invocation.get("project")
    if isinstance(project, str) and project.startswith("/"):
        enriched["project"] = Path(project.rstrip("/")).name

    validation_commands = list(invocation.get("validation_commands", []))
    checkpoint_messages = list(invocation.get("checkpoint_messages", []))
    user_corrections = list(invocation.get("user_corrections", []))
    risk_gating_messages = list(invocation.get("risk_gating_messages", []))
    matched_on = set(invocation.get("matched_on", []))
    task_complete = bool(invocation.get("task_complete"))
    has_correction = bool(user_corrections)
    # Invocation-level failure modes (v1, heuristic — refine as data accumulates):
    #   invocation_miss: scanner saw no trigger/ack/path signal on a real session
    #   trigger_mismatch: user phrasing triggered, but the skill never acknowledged
    #   output_rejected: user corrected and the run did not complete
    #   output_corrected: user corrected but the run still reached completion
    #   wrong_skill_invoked: correction references another slash-command/skill name
    import re as _re
    slash_in_correction = any(
        _re.search(r"(?:try|use|should (?:be|have used))\s*/[\w-]+", text, _re.IGNORECASE)
        or _re.search(r"/(?:skill-|cass|wiki|deploy|review|ultrareview)[\w-]*", text)
        for text in user_corrections
    )

    enriched["invocation_id"] = build_invocation_id(invocation)
    enriched["task_type"] = infer_task_type(invocation.get("user_request"))
    enriched["invocation_mode"] = infer_invocation_mode(invocation)
    enriched["flags"] = {
        "has_ack": "assistant_ack" in matched_on,
        "has_validation": bool(validation_commands),
        "has_checkpoint": bool(checkpoint_messages),
        "has_risk_gate_gap": bool(risk_gating_messages),
        "has_user_correction": has_correction,
        "task_complete": task_complete,
        "has_invocation_miss": not matched_on and bool(invocation.get("user_request")),
        "has_trigger_mismatch": "user_trigger" in matched_on and "assistant_ack" not in matched_on,
        "has_output_rejected": has_correction and not task_complete,
        "has_output_corrected": has_correction and task_complete,
        "has_wrong_skill_invoked": slash_in_correction,
    }
    enriched["counts"] = {
        "validation_commands": len(validation_commands),
        "checkpoint_messages": len(checkpoint_messages),
        "risk_gating_messages": len(risk_gating_messages),
        "user_corrections": len(user_corrections),
        "tool_calls": int(invocation.get("tool_calls", 0)),
    }
    enriched["refs"] = {
        "assistant_ack": invocation.get("assistant_ack"),
        "validation_commands": validation_commands,
        "checkpoint_messages": checkpoint_messages,
        "user_corrections": user_corrections,
        "risk_gating_messages": risk_gating_messages,
        "touched_paths": list(invocation.get("touched_paths", [])),
    }
    return enriched


def build_skill_fact_bundle(
    *,
    skill: str,
    source: str,
    since: str,
    until: str,
    generated_at: str,
    sessions_scanned: int,
    invocations: list[dict[str, Any]],
    summary: dict[str, Any],
    tool_counts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical fact bundle for a review window."""
    enriched_invocations = [enrich_invocation(invocation) for invocation in invocations]
    bundle = {
        "schema": "skill_fact_bundle.v1",
        "generated_at": generated_at,
        "skill": skill,
        "source": source,
        "window": {
            "since": since,
            "until": until,
        },
        "sessions_scanned": sessions_scanned,
        "invocations_found": len(enriched_invocations),
        "summary": summary,
        "tool_counts": tool_counts,
        "invocations": enriched_invocations,
    }
    digest = sha256(json.dumps(bundle, sort_keys=True).encode("utf-8")).hexdigest()
    bundle["bundle_hash"] = digest
    return bundle
