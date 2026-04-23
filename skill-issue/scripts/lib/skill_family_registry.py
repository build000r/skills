"""
Shared failure-family metadata for skill review artifacts.
"""

from __future__ import annotations

FAMILY_REGISTRY = {
    "observability-gap": {
        "predicate": "missing_ack_after_skill_path",
        "severity": "low",
        "watch_metric": "ack_rate",
        "impact_weight": 1.5,
        "confidence_weight": 0.95,
        "allowed_fix_classes": ["add-stable-ack-marker"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "Invocation observability is too weak to trust the trend line.",
        "packet_why_now": (
            "Tracking depends on path heuristics instead of a stable acknowledgement, so "
            "usage history and trend reporting are noisier than they need to be."
        ),
        "packet_expected_contract": (
            "Emit a stable first progress marker such as `Using <skill>` whenever the "
            "skill becomes active."
        ),
        "opportunity_hypothesis": (
            "The skill does not require a stable first-use acknowledgement, so "
            "tracking usage depends on path-touch heuristics."
        ),
        "opportunity_recommendation": (
            "Require a stable first commentary marker so invocation detection and "
            "trend reporting are easier to trust."
        ),
        "legacy_opportunity_id": "ack-marker",
        "legacy_priority": "high",
        "legacy_summary": (
            "Some runs touched skill files without an explicit `Using <skill>` commentary marker. "
            "Make the first progress update mandatory and stable so last-use detection does not depend on path heuristics."
        ),
    },
    "verification-gap": {
        "predicate": "missing_validation",
        "severity": "high",
        "watch_metric": "validation_rate",
        "impact_weight": 5.0,
        "confidence_weight": 1.0,
        "allowed_fix_classes": ["tighten-skill-contract", "bundle-helper-script"],
        "target_files": ["SKILL.md", "scripts/"],
        "packet_failure_family": "The skill reaches closeout without enough verification evidence.",
        "packet_why_now": (
            "Unverified runs let the maintainer overestimate the reliability of a wording "
            "change or script addition."
        ),
        "packet_expected_contract": (
            "Run a concrete verification command or deterministic smoke path before handing "
            "the result back to the user."
        ),
        "opportunity_hypothesis": (
            "The skill contract does not force a concrete verification path, or the "
            "documented validation path is too manual to be used consistently."
        ),
        "opportunity_recommendation": (
            "Add or tighten a required verification block and bundle a helper script "
            "when the validation path is repetitive."
        ),
        "legacy_opportunity_id": "verification-gap",
        "legacy_priority": "high",
        "legacy_summary": (
            "Validation coverage is low relative to the number of detected invocations. "
            "Add a required verification block with concrete commands and a 'do not hand back untested changes' rule."
        ),
    },
    "checkpoint-defaults": {
        "predicate": "has_checkpoint",
        "severity": "medium",
        "watch_metric": "checkpoint_rate",
        "impact_weight": 3.0,
        "confidence_weight": 0.95,
        "allowed_fix_classes": ["move-preferences-into-defaults"],
        "target_files": ["SKILL.md", "modes/"],
        "packet_failure_family": "The skill still burns turns on avoidable human checkpoints.",
        "packet_why_now": (
            "Repeated preference questions slow the workflow and usually indicate that "
            "defaults or mode configuration are underspecified."
        ),
        "packet_expected_contract": (
            "Handle repeated preferences through defaults or mode files and only ask when "
            "information is missing or genuinely risky."
        ),
        "opportunity_hypothesis": (
            "The skill still relies on user checkpoints for choices that could be "
            "handled through defaults or mode configuration."
        ),
        "opportunity_recommendation": (
            "Move repeated preferences into mode files or explicit defaults so the "
            "skill only asks when information is missing or risky."
        ),
        "legacy_opportunity_id": "checkpoint-defaults",
        "legacy_priority": "medium",
        "legacy_summary": (
            "Checkpoint prompts are still common. Move repeated preferences into mode files or default decision rules so human checkpoints are reserved for missing information or high-risk operations."
        ),
    },
    "risk-gating-gap": {
        "predicate": "has_risk_gating",
        "severity": "high",
        "watch_metric": "risk_gating_rate",
        "impact_weight": 4.5,
        "confidence_weight": 0.8,
        "allowed_fix_classes": ["add-risk-gating-rules"],
        "target_files": ["SKILL.md", "references/", "modes/"],
        "packet_failure_family": "The skill crosses risky boundaries without the human gate the workflow expects.",
        "packet_why_now": (
            "When users have to say wait, ask first, or bring in an outside reviewer, "
            "the skill is treating risky branches as defaults instead of gated paths."
        ),
        "packet_expected_contract": (
            "Pause for confirmation, clarification, or designated outside review before "
            "irreversible or high-risk actions."
        ),
        "opportunity_hypothesis": (
            "The skill is treating an irreversible or externally reviewed step as a "
            "default path when it should pause for confirmation, clarification, or a "
            "designated human reviewer."
        ),
        "opportunity_recommendation": (
            "Add explicit risk gates for high-cost steps, including when to ask first, "
            "wait for clarification, or bring in a named reviewer before proceeding."
        ),
        "legacy_opportunity_id": "risk-gating-gap",
        "legacy_priority": "high",
        "legacy_summary": (
            "Users are explicitly flagging steps that should have paused for confirmation, clarification, or outside review before proceeding. Add risk-gating rules so irreversible or high-risk branches are not treated as defaults."
        ),
    },
    "contract-clarity": {
        "predicate": "has_correction",
        "severity": "high",
        "watch_metric": "correction_rate",
        "impact_weight": 5.0,
        "confidence_weight": 0.95,
        "allowed_fix_classes": ["tighten-trigger-language"],
        "target_files": ["SKILL.md", "references/"],
        "packet_failure_family": "The skill activates, but users still have to redirect it onto the right path.",
        "packet_why_now": (
            "Post-start corrections usually mean the trigger language, non-goals, or early "
            "branching rules are still underspecified."
        ),
        "packet_expected_contract": (
            "Choose the right path earlier by tightening trigger language, non-goals, and "
            "default branching rules."
        ),
        "opportunity_hypothesis": (
            "The skill contract is underspecified for at least one common task shape, "
            "so the user has to redirect the run after the skill is already active."
        ),
        "opportunity_recommendation": (
            "Tighten trigger language, defaults, non-goals, and early branching rules "
            "so the run picks the right path without redirection."
        ),
        "legacy_opportunity_id": "contract-clarity",
        "legacy_priority": "medium",
        "legacy_summary": (
            "Users are redirecting the run after it starts. Tighten trigger language, non-goals, and ask-cascade guidance so the skill picks the right path earlier."
        ),
    },
    "closeout-gap": {
        "predicate": "missing_completion",
        "severity": "medium",
        "watch_metric": "completion_rate",
        "impact_weight": 2.5,
        "confidence_weight": 0.75,
        "allowed_fix_classes": ["strengthen-closeout"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "Runs do work but do not consistently reach a visible done state.",
        "packet_why_now": (
            "A weak closeout contract hides whether the skill actually completed the job or "
            "just stopped producing output."
        ),
        "packet_expected_contract": (
            "End with explicit completion language tied to the verification evidence and any "
            "remaining risks."
        ),
        "opportunity_hypothesis": (
            "The skill does not consistently drive runs to a clear completion event "
            "or explicit final verification closeout."
        ),
        "opportunity_recommendation": (
            "Strengthen the completion block so the run ends with verification "
            "evidence and a clear done state."
        ),
    },
    "automation-gap": {
        "predicate": "raw_shell_stems",
        "severity": "medium",
        "watch_metric": "raw_shell_stem_frequency",
        "impact_weight": 3.0,
        "confidence_weight": 0.85,
        "allowed_fix_classes": ["bundle-helper-script"],
        "target_files": ["scripts/", "references/", "SKILL.md"],
        "packet_failure_family": "The workflow still depends on repeated freehand shell inspection.",
        "packet_why_now": (
            "If the same raw shell stems recur across runs, reliability is gated on manual "
            "operator dexterity rather than bundled reusable tooling."
        ),
        "packet_expected_contract": (
            "Bundle repeated shell-heavy inspection into helper scripts or concise references "
            "and point the skill at them."
        ),
        "opportunity_hypothesis": (
            "The workflow depends on repeated ad-hoc shell inspection instead of a "
            "stable helper script or reference."
        ),
        "opportunity_recommendation": (
            "Bundle the recurring analysis path into a helper script or concise "
            "reference and point the skill at it."
        ),
        "legacy_opportunity_id": "automation-gap",
        "legacy_priority": "medium",
        "legacy_summary": (
            "Repeated ad-hoc shell work appears across invocations. Bundle the recurring analysis path into helper scripts or references so reliability is not gated on freehand shell usage."
        ),
    },
    # --- Invocation-level failure modes (JIT-corpus MVP, #3 failure taxonomy) ---
    "invocation_miss": {
        "predicate": "has_invocation_miss",
        "severity": "high",
        "watch_metric": "invocation_miss_rate",
        "impact_weight": 4.0,
        "confidence_weight": 0.7,
        "allowed_fix_classes": ["sharpen-description-trigger", "surface-skill-in-discovery"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "The skill should have been invoked but was not.",
        "packet_why_now": (
            "A session's user_request looks skill-shaped but no trigger, ack, or "
            "path signal fired. Discoverability or description match is likely wrong."
        ),
        "packet_expected_contract": (
            "Sharpen the description field and trigger phrases so the activation "
            "surface catches the prompts this skill is meant to handle."
        ),
        "opportunity_hypothesis": (
            "The skill's description does not match the language the operator is "
            "actually using to request this kind of work."
        ),
        "opportunity_recommendation": (
            "Revise the description field and sample trigger phrases to cover the "
            "operator's real prompts; add a discovery hint if applicable."
        ),
        "legacy_opportunity_id": "invocation-miss",
        "legacy_priority": "high",
        "legacy_summary": (
            "Sessions that should have triggered this skill did not. Tighten the description "
            "and trigger phrases so activation is not left to chance."
        ),
    },
    "trigger_mismatch": {
        "predicate": "has_trigger_mismatch",
        "severity": "medium",
        "watch_metric": "trigger_mismatch_rate",
        "impact_weight": 3.0,
        "confidence_weight": 0.85,
        "allowed_fix_classes": ["sharpen-description-trigger"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "The user's phrasing looked like a trigger but the skill never acknowledged.",
        "packet_why_now": (
            "A user_trigger match fired without a matching assistant_ack, so the "
            "description is pulling in prompts the body is not actually servicing."
        ),
        "packet_expected_contract": (
            "Either broaden the skill to handle the trigger phrase, or narrow the "
            "description so it does not over-match."
        ),
        "opportunity_hypothesis": (
            "The description is broader than the skill's real coverage, producing "
            "trigger-without-ack events."
        ),
        "opportunity_recommendation": (
            "Narrow the description and add explicit non-goals, or expand the skill "
            "body to cover the missing shape."
        ),
        "legacy_opportunity_id": "trigger-mismatch",
        "legacy_priority": "medium",
        "legacy_summary": (
            "The trigger fires but the skill body does not acknowledge. Narrow description "
            "or expand coverage so trigger-without-ack stops occurring."
        ),
    },
    "output_rejected": {
        "predicate": "has_output_rejected",
        "severity": "high",
        "watch_metric": "output_rejected_rate",
        "impact_weight": 4.5,
        "confidence_weight": 0.85,
        "allowed_fix_classes": ["tighten-skill-contract", "tighten-trigger-language"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "The skill produced output the user rejected; the run did not complete.",
        "packet_why_now": (
            "A user correction appeared and task_complete was not reached, so the "
            "skill's output was discarded rather than edited in place."
        ),
        "packet_expected_contract": (
            "Tighten non-goals, default branching, and the expected output shape so "
            "the skill does not produce material the operator throws away."
        ),
        "opportunity_hypothesis": (
            "The skill produces output shapes the operator does not want, signaling a "
            "contract mismatch strong enough to abandon the run."
        ),
        "opportunity_recommendation": (
            "Tighten the skill contract, narrow defaults, and add explicit non-goals."
        ),
        "legacy_opportunity_id": "output-rejected",
        "legacy_priority": "high",
        "legacy_summary": (
            "Runs with corrections are not reaching completion. The output contract is "
            "losing the operator; tighten it."
        ),
    },
    "output_corrected": {
        "predicate": "has_output_corrected",
        "severity": "medium",
        "watch_metric": "output_corrected_rate",
        "impact_weight": 2.5,
        "confidence_weight": 0.8,
        "allowed_fix_classes": ["tighten-skill-contract"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "The skill's output was accepted but then corrected by the operator.",
        "packet_why_now": (
            "Runs with user corrections still reach task_complete, so the output is "
            "close enough to accept but off enough to need a fix."
        ),
        "packet_expected_contract": (
            "Close the gap between acceptable and right by sharpening the output "
            "contract or adding a post-hoc validation step."
        ),
        "opportunity_hypothesis": (
            "The skill's defaults land near-right but not right, leaking a consistent "
            "correction tax onto the operator."
        ),
        "opportunity_recommendation": (
            "Identify the recurring correction pattern and fold it into defaults, "
            "examples, or validation checks."
        ),
        "legacy_opportunity_id": "output-corrected",
        "legacy_priority": "medium",
        "legacy_summary": (
            "Completions still require the operator to correct output. Fold the recurring "
            "correction pattern into defaults or validation."
        ),
    },
    "wrong_skill_invoked": {
        "predicate": "has_wrong_skill_invoked",
        "severity": "medium",
        "watch_metric": "wrong_skill_invoked_rate",
        "impact_weight": 3.0,
        "confidence_weight": 0.7,
        "allowed_fix_classes": ["sharpen-description-trigger", "tighten-non-goals"],
        "target_files": ["SKILL.md"],
        "packet_failure_family": "The wrong skill activated; the operator redirected to a different one.",
        "packet_why_now": (
            "A user correction referenced a different slash-command or skill name, "
            "meaning this skill won an activation race it should have lost."
        ),
        "packet_expected_contract": (
            "Add non-goals and a clear boundary against the neighboring skill's "
            "territory; tighten trigger phrases so this skill stops over-matching."
        ),
        "opportunity_hypothesis": (
            "The skill's description overlaps with a sibling skill's territory, "
            "producing mis-activation."
        ),
        "opportunity_recommendation": (
            "Add explicit non-goals referencing the sibling skill and tighten the "
            "description to eliminate the overlap."
        ),
        "legacy_opportunity_id": "wrong-skill-invoked",
        "legacy_priority": "medium",
        "legacy_summary": (
            "This skill activated when the operator actually wanted a different one. Add "
            "non-goals referencing the sibling skill and tighten the description."
        ),
    },
    "provider-coverage": {
        "predicate": "missing_claude_provider",
        "severity": "low",
        "watch_metric": "provider_coverage",
        "impact_weight": 1.0,
        "confidence_weight": 0.95,
        "allowed_fix_classes": ["tighten-provider-detection"],
        "target_files": ["SKILL.md", "scripts/lib/skill_review.py"],
        "opportunity_hypothesis": (
            "The current review window lacks Claude Code matches, so some metrics are "
            "validated on Codex logs only."
        ),
        "opportunity_recommendation": (
            "Tighten provider-specific detection and marker guidance so review coverage "
            "does not silently collapse to a single source."
        ),
        "legacy_opportunity_id": "provider-coverage",
        "legacy_priority": "low",
        "legacy_summary": (
            "No Claude Code invocations were matched in the selected range. Detection and markers are currently validated on Codex logs only."
        ),
    },
}
