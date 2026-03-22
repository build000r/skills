"""
Operator-evidence packet generation for skill review reports.

This bridges aggregate transcript-review metrics to concrete skill edits and
historical reference slices before a team invests in a fuller eval harness.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

RAW_SHELL_STEMS = {"rg", "sed", "find", "git", "ls"}

TASK_TYPE_PATTERNS = (
    ("review", ("review", "audit", "lookback", "judge", "eval", "measure", "trend")),
    ("package", ("package", "publish", "bundle", ".skill")),
    ("create", ("create", "make", "new skill", "build", "template", "init")),
    ("update", ("update", "improve", "fix", "iterate", "refactor", "tighten")),
)

PACKET_RULES = {
    "observability-gap": {
        "failure_family": "Invocation observability is too weak to trust the trend line.",
        "why_now": (
            "Tracking depends on path heuristics instead of a stable acknowledgement, so "
            "usage history and trend reporting are noisier than they need to be."
        ),
        "expected_contract": (
            "Emit a stable first progress marker such as `Using <skill>` whenever the "
            "skill becomes active."
        ),
        "suggested_fix_class": "add-stable-ack-marker",
        "target_files": ["SKILL.md"],
        "watch_metric": "ack_rate",
    },
    "verification-gap": {
        "failure_family": "The skill reaches closeout without enough verification evidence.",
        "why_now": (
            "Unverified runs let the maintainer overestimate the reliability of a wording "
            "change or script addition."
        ),
        "expected_contract": (
            "Run a concrete verification command or deterministic smoke path before handing "
            "the result back to the user."
        ),
        "suggested_fix_class": "tighten-skill-contract",
        "target_files": ["SKILL.md", "scripts/"],
        "watch_metric": "validation_rate",
    },
    "checkpoint-defaults": {
        "failure_family": "The skill still burns turns on avoidable human checkpoints.",
        "why_now": (
            "Repeated preference questions slow the workflow and usually indicate that "
            "defaults or mode configuration are underspecified."
        ),
        "expected_contract": (
            "Handle repeated preferences through defaults or mode files and only ask when "
            "information is missing or genuinely risky."
        ),
        "suggested_fix_class": "move-preferences-into-defaults",
        "target_files": ["SKILL.md", "modes/"],
        "watch_metric": "checkpoint_rate",
    },
    "risk-gating-gap": {
        "failure_family": "The skill crosses risky boundaries without the human gate the workflow expects.",
        "why_now": (
            "When users have to say wait, ask first, or bring in an outside reviewer, "
            "the skill is treating risky branches as defaults instead of gated paths."
        ),
        "expected_contract": (
            "Pause for confirmation, clarification, or designated outside review before "
            "irreversible or high-risk actions."
        ),
        "suggested_fix_class": "add-risk-gating-rules",
        "target_files": ["SKILL.md", "references/", "modes/"],
        "watch_metric": "risk_gating_rate",
    },
    "contract-clarity": {
        "failure_family": "The skill activates, but users still have to redirect it onto the right path.",
        "why_now": (
            "Post-start corrections usually mean the trigger language, non-goals, or early "
            "branching rules are still underspecified."
        ),
        "expected_contract": (
            "Choose the right path earlier by tightening trigger language, non-goals, and "
            "default branching rules."
        ),
        "suggested_fix_class": "tighten-trigger-language",
        "target_files": ["SKILL.md", "references/"],
        "watch_metric": "correction_rate",
    },
    "closeout-gap": {
        "failure_family": "Runs do work but do not consistently reach a visible done state.",
        "why_now": (
            "A weak closeout contract hides whether the skill actually completed the job or "
            "just stopped producing output."
        ),
        "expected_contract": (
            "End with explicit completion language tied to the verification evidence and any "
            "remaining risks."
        ),
        "suggested_fix_class": "strengthen-closeout",
        "target_files": ["SKILL.md"],
        "watch_metric": "completion_rate",
    },
    "automation-gap": {
        "failure_family": "The workflow still depends on repeated freehand shell inspection.",
        "why_now": (
            "If the same raw shell stems recur across runs, reliability is gated on manual "
            "operator dexterity rather than bundled reusable tooling."
        ),
        "expected_contract": (
            "Bundle repeated shell-heavy inspection into helper scripts or concise references "
            "and point the skill at them."
        ),
        "suggested_fix_class": "bundle-helper-script",
        "target_files": ["scripts/", "references/", "SKILL.md"],
        "watch_metric": "raw_shell_stem_frequency",
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


def enrich_invocation(invocation: dict[str, Any]) -> dict[str, Any]:
    """Attach stable metadata used for historical reference slices."""
    enriched = dict(invocation)
    project = invocation.get("project")
    if isinstance(project, str) and project.startswith("/"):
        enriched["project"] = project.rstrip("/").rsplit("/", 1)[-1]
    enriched["task_type"] = infer_task_type(invocation.get("user_request"))
    return enriched


def _matches(issue_type: str, invocation: dict[str, Any]) -> bool:
    matched_on = set(invocation.get("matched_on", []))

    if issue_type == "observability-gap":
        return "skill_path" in matched_on and "assistant_ack" not in matched_on
    if issue_type == "verification-gap":
        return not invocation.get("validation_commands")
    if issue_type == "checkpoint-defaults":
        return bool(invocation.get("checkpoint_messages"))
    if issue_type == "risk-gating-gap":
        return bool(invocation.get("risk_gating_messages"))
    if issue_type == "contract-clarity":
        return bool(invocation.get("user_corrections"))
    if issue_type == "closeout-gap":
        return not invocation.get("task_complete")
    if issue_type == "automation-gap":
        stems = set(invocation.get("command_stems", {}))
        return bool(stems & RAW_SHELL_STEMS)
    raise KeyError(f"Unsupported issue type: {issue_type}")


def _signal(issue_type: str, invocation: dict[str, Any]) -> str:
    if issue_type == "observability-gap":
        return "skill path touched without explicit ack marker"
    if issue_type == "verification-gap":
        return "no validation command detected"
    if issue_type == "checkpoint-defaults":
        return (invocation.get("checkpoint_messages") or ["checkpoint prompt detected"])[0]
    if issue_type == "risk-gating-gap":
        return (invocation.get("risk_gating_messages") or ["risk gate should have existed"])[0]
    if issue_type == "contract-clarity":
        return (invocation.get("user_corrections") or ["user redirect detected"])[0]
    if issue_type == "closeout-gap":
        return "no completion event detected"
    if issue_type == "automation-gap":
        stems = sorted(stem for stem in invocation.get("command_stems", {}) if stem in RAW_SHELL_STEMS)
        return f"raw shell stems: {', '.join(stems)}"
    raise KeyError(f"Unsupported issue type: {issue_type}")


def _trace_row(issue_type: str, invocation: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": invocation.get("timestamp"),
        "project": invocation.get("project"),
        "task_type": invocation.get("task_type"),
        "file": invocation.get("file"),
        "user_request": invocation.get("user_request"),
        "signal": _signal(issue_type, invocation),
    }


def _holdout_signal(issue_type: str, invocation: dict[str, Any]) -> str:
    if issue_type == "observability-gap":
        return "holdout control: explicit ack marker detected"
    if issue_type == "verification-gap":
        return "holdout control: validation command detected"
    if issue_type == "checkpoint-defaults":
        return "holdout control: no checkpoint prompt detected"
    if issue_type == "risk-gating-gap":
        return "holdout control: no missing risk gate cue detected"
    if issue_type == "contract-clarity":
        return "holdout control: no user redirect detected"
    if issue_type == "closeout-gap":
        return "holdout control: completion event detected"
    if issue_type == "automation-gap":
        return "holdout control: no raw shell stems detected"
    raise KeyError(f"Unsupported issue type: {issue_type}")


def _holdout_examples(
    issue_type: str,
    focus_examples: list[dict[str, Any]],
    all_invocations: list[dict[str, Any]],
    max_controls: int,
) -> list[dict[str, Any]]:
    """Pick a few non-matching past runs as simple anti-regression controls."""
    if not focus_examples or max_controls <= 0:
        return []

    anchor = focus_examples[0]
    candidates = [
        invocation
        for invocation in all_invocations
        if not _matches(issue_type, invocation)
    ]
    candidates.sort(
        key=lambda invocation: (
            0 if invocation.get("task_type") == anchor.get("task_type") else 1,
            0 if invocation.get("project") == anchor.get("project") else 1,
            invocation.get("timestamp") or "",
        ),
        reverse=True,
    )
    rows = []
    for invocation in candidates[:max_controls]:
        row = _trace_row(issue_type, invocation)
        row["signal"] = _holdout_signal(issue_type, invocation)
        rows.append(row)
    return rows


def _automation_supporting_metrics(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    stem_counts: Counter[str] = Counter()
    for invocation in invocations:
        stems = set(invocation.get("command_stems", {}))
        stem_counts.update(stems & RAW_SHELL_STEMS)
    return {
        "top_raw_shell_stems": [stem for stem, _ in stem_counts.most_common(3)],
    }


def _post_ship_window(affected_runs: int) -> dict[str, Any]:
    """Recommend a lightweight live-traffic observation window after shipping."""
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


def generate_evidence_report(
    review_report: dict[str, Any],
    min_occurrences: int = 2,
    max_packets: int = 5,
    max_examples: int = 3,
    max_controls: int = 2,
) -> dict[str, Any]:
    """Generate operator-evidence packets from a review report."""
    skill = review_report.get("skill")
    raw_invocations = review_report.get("invocations", [])
    invocations = [enrich_invocation(invocation) for invocation in raw_invocations]
    total_runs = len(invocations)

    packets: list[dict[str, Any]] = []
    for issue_type, rule in PACKET_RULES.items():
        matches = [invocation for invocation in invocations if _matches(issue_type, invocation)]
        affected_runs = len(matches)
        if affected_runs < min_occurrences:
            continue

        traces = [_trace_row(issue_type, invocation) for invocation in matches[:max_examples]]
        prevalence = round(affected_runs / total_runs, 3) if total_runs else 0.0
        packet = {
            "packet_id": f"{issue_type}-global",
            "issue_type": issue_type,
            "failure_family": rule["failure_family"],
            "why_now": rule["why_now"],
            "expected_contract": rule["expected_contract"],
            "suggested_fix_class": rule["suggested_fix_class"],
            "target_files": rule["target_files"],
            "watch_metric": rule["watch_metric"],
            "experiment_unit": "real_invocation_window",
            "affected_runs": affected_runs,
            "total_runs": total_runs,
            "prevalence": prevalence,
            "representative_traces": traces,
            "historical_reference_slice": {
                "target_examples": traces,
                "holdout_examples": _holdout_examples(issue_type, matches, invocations, max_controls),
            },
            "post_ship_window": _post_ship_window(affected_runs),
            "skill_issue_brief": _packet_brief(
                skill=skill,
                issue_type=issue_type,
                affected_runs=affected_runs,
                total_runs=total_runs,
                expected_contract=rule["expected_contract"],
            ),
        }
        packet["replay_slice"] = packet["historical_reference_slice"]
        if issue_type == "automation-gap":
            packet["supporting_metrics"] = _automation_supporting_metrics(matches)
        packets.append(packet)

    packets.sort(
        key=lambda packet: (
            packet["affected_runs"],
            packet["prevalence"],
            packet["packet_id"],
        ),
        reverse=True,
    )

    return {
        "skill": skill,
        "generated_at": review_report.get("generated_at"),
        "source_review": {
            "generated_at": review_report.get("generated_at"),
            "source": review_report.get("source"),
            "since": review_report.get("since"),
            "until": review_report.get("until"),
            "sessions_scanned": review_report.get("sessions_scanned"),
            "invocations_found": review_report.get("invocations_found", total_runs),
        },
        "summary": {
            "packets_generated": len(packets),
            "packets_returned": min(len(packets), max_packets),
            "issue_types": {packet["issue_type"]: packet["affected_runs"] for packet in packets[:max_packets]},
        },
        "packets": packets[:max_packets],
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
                lines.append(f"Supporting metrics: top raw shell stems = {', '.join(stems)}")
        lines.append("Representative traces:")
        for trace in packet.get("representative_traces", []):
            lines.append(
                f"- {trace.get('timestamp')} | {trace.get('signal')} | {trace.get('user_request') or 'n/a'}"
            )
        lines.append("Historical reference slice:")
        for trace in packet.get("historical_reference_slice", {}).get("holdout_examples", []):
            lines.append(
                f"- holdout | {trace.get('timestamp')} | {trace.get('user_request') or 'n/a'}"
            )

    return "\n".join(lines) + "\n"
