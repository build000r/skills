#!/usr/bin/env python3
"""
Critical review of a domain plan before sign-off.

Launches a Codex worker (gpt-5.3-codex, xhigh reasoning) to review all 6 plan
files against the plan quality rubric, sibling slices, and mode context.
Produces a REVIEW.md with per-dimension scores, concerns, and suggested upgrades.

Usage:
    # Dry run — print the prompt
    python3 scripts/review_plan.py --slice agent_billing

    # Execute — launch Codex worker, block until done
    python3 scripts/review_plan.py --slice agent_billing --execute

    # Override model/effort
    python3 scripts/review_plan.py --slice agent_billing --execute --model gpt-5.2-codex --reasoning-effort high
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent

DEFAULT_PLAN_ROOT = None  # Set via --plan-root or mode config (plan_root)
DEFAULT_PLAN_INDEX = None  # Set via --plan-index or mode config (plan_index)
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_REASONING_EFFORT = "xhigh"

PLAN_FILES = ["plan.md", "shared.md", "backend.md", "frontend.md", "flows.md", "schema.mmd"]


def _expand(path_value: str) -> str:
    return str(Path(path_value).expanduser())


def _plan_dir(plan_root: str, slice_name: str) -> Path:
    return Path(plan_root).expanduser() / slice_name


def _check_plan_exists(plan_root: str, slice_name: str) -> list[str]:
    """Return list of missing plan files."""
    plan_path = _plan_dir(plan_root, slice_name)
    missing = []
    for f in PLAN_FILES:
        if not (plan_path / f).exists():
            missing.append(f)
    return missing


def _discover_mode(skill_root: Path, repo: Path, explicit_mode: str | None) -> Path | None:
    """Find the matching mode file, or None."""
    modes_dir = skill_root / "modes"
    if not modes_dir.exists():
        return None

    if explicit_mode:
        candidate = modes_dir / f"{explicit_mode}.md"
        return candidate if candidate.exists() else None

    # Auto-detect from cwd_match
    for mode_file in sorted(modes_dir.glob("*.md")):
        text = mode_file.read_text(encoding="utf-8")
        cwd_matches = re.findall(r"^\s*cwd_match:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        for pattern in cwd_matches:
            pattern_resolved = Path(pattern.strip()).expanduser().resolve()
            repo_resolved = repo.resolve()
            if repo_resolved == pattern_resolved or repo_resolved.is_relative_to(pattern_resolved):
                return mode_file
    return None


def _mode_setting(mode_file: Path | None, key: str) -> str | None:
    if mode_file is None:
        return None
    text = mode_file.read_text(encoding="utf-8")
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def build_prompt(
    slice_name: str,
    plan_root: str,
    plan_index: str,
    skill_root: Path,
    mode_file: Path | None,
) -> str:
    plan_path = _expand(plan_root) + f"/{slice_name}"
    review_output = f"{plan_path}/REVIEW.md"

    context_lines = [
        f"- Plan directory: {plan_path}",
        f"- Plan index: {_expand(plan_index)}",
        f"- Planning skill reference: {skill_root / 'SKILL.md'}",
        f"- Plan quality rubric: {skill_root / 'references' / 'plan-quality-rubric.md'}",
        f"- Phase questions reference: {skill_root / 'references' / 'phase-questions.md'}",
        f"- Standard stories: {skill_root / 'references' / 'standard-stories/'}",
    ]
    if mode_file:
        context_lines.append(f"- Mode file: {mode_file}")

    context_block = "\n".join(context_lines)

    return dedent(f"""\
        Review the `{slice_name}` domain plan before sign-off.
        You are the PLAN REVIEWER — a thorough but fair quality gate before implementation begins.

        Context:
        {context_block}

        Plan files to review:
        {', '.join(PLAN_FILES)}

        ## How to Review

        1. Read the plan quality rubric. It defines exactly 10 dimensions, each worth 10 points.
        2. Read ALL 6 plan files carefully.
        3. Read INDEX.md to identify 2-3 closest sibling slices. Skim their shared.md files.
        4. Score each of the 10 rubric dimensions. Start at 10/10 and deduct per the rubric's scale.
        5. Write the review output.

        ## Scoring Calibration

        Apply the rubric's deduction scale strictly:
        - **-1** — Minor: easily fixable, low implementation impact
        - **-2** — Moderate: could cause scaffolder confusion
        - **-5** — Major: would cause WRONG implementation (not just missing detail)

        Critical calibration rules:
        - Only deduct for issues that affect THIS plan's implementability. Do NOT deduct for:
          - Sibling slice contracts that need updating (report these as informational, not as deductions)
          - Missing operational bounds (rate limits, pagination maxes) unless the plan explicitly claims to define them
          - Missing rate limits or payload size limits for v1 plans — these are acceptable to defer
        - Dimension 4 (Test Payload Completeness): Test scenarios need expected status + error code + outcome description. Full JSON request/response bodies are ideal but outcome-level scenarios (e.g., "Happy: user books → 201, booking confirmed, capacity decremented") are acceptable and should score 7-8/10, not 3-4/10.
        - Dimension 6 (Spec/Implementation Boundary): Component names with behavioral descriptions (states, interactions, layout) ARE spec — they communicate design intent. Deduct only for actual implementation code (TypeScript/Python/JSX, import statements, hook implementations, file path trees). A component described as "CallStatusBadge — shows booked time or Book call prompt, with onBook/onReschedule actions" is spec. A component with `export function CallStatusBadge({{ props }}: Props) {{...}}` is implementation.
        - Dimension 9 (Scope Discipline): Explicitly grade highest-best-use / 80-20 slicing. Deduct when the plan is not anchored to the Phase 0.5 Core Value Gate, when admin/config/reporting/abstraction work is specified ahead of the primary actor's visible win, or when the slice bundles multiple adjacent wins that should be split.
        - Sibling conflicts are informational context, NOT automatic score deductions. Report them in the Sibling Conflicts section. Only deduct if the conflict would cause THIS plan's implementation to fail (e.g., this plan references an endpoint that doesn't exist in the sibling).
        - A plan that clearly communicates all business rules, user stories, API contracts, flows, and component behavior should score 85-95 on a first pass even if some operational details (rate limits, pagination bounds, per-endpoint error matrices) are deferred. The final sign-off target is still 100/100.

        ## Output

        Write `{review_output}` with this exact structure:

        ```markdown
        # Plan Review: {{slice_name}}
        **Reviewed:** {{date}}
        **Verdict:** COMPLIANT / NEEDS REVISION / MAJOR CONCERNS

        ## Summary
        One paragraph overall assessment.

        ## Score: **XX/100**

        ### Dimension Breakdown
        | # | Dimension | Score | Notes |
        |---|-----------|-------|-------|
        | 1 | File completeness | X/10 | {{brief note or "Clean"}} |
        | 2 | Type consistency | X/10 | ... |
        | 3 | Slug/constant consistency | X/10 | ... |
        | 4 | Test payload completeness | X/10 | ... |
        | 5 | User story quality | X/10 | ... |
        | 6 | Spec/implementation boundary | X/10 | ... |
        | 7 | Schema accuracy | X/10 | ... |
        | 8 | Cross-file reference integrity | X/10 | ... |
        | 9 | Scope discipline | X/10 | ... |
        | 10 | Single source of truth | X/10 | ... |

        ## Questions for the Planner
        Numbered list of specific questions. Each should be "should X be Y or Z?" — not "is this right?"

        ## Concerns
        Issues that need fixing. Each with:
        - **File:** which plan file + line/section
        - **Issue:** what's wrong
        - **Suggestion:** how to fix it

        ## Suggested Upgrades
        Optional improvements that would make the plan stronger but aren't blockers.
        These do NOT affect the score.

        ## Sibling Conflicts
        Any conflicts with existing slices (informational — these don't affect score unless
        they would cause THIS plan's implementation to fail).

        ## Verdict Rationale
        Why COMPLIANT (100) / NEEDS REVISION (85-99) / MAJOR CONCERNS (<85).
        ```

        Verdict thresholds:
        - **COMPLIANT** (100): Ready for implementation. No blocking ambiguity remains.
        - **NEEDS REVISION** (85-99): Good foundation but still has gaps that must be fixed before sign-off.
        - **MAJOR CONCERNS** (<85): Significant issues that would cause wrong or unstable implementations.

        Guardrails:
        - Do NOT modify any plan files. This is read-only review.
        - Do NOT create implementation code.
        - Be specific — cite file names and line-level details.
        - Every point deducted MUST correspond to a concern in the Concerns section.
        - Do NOT deduct for "nice to haves" or stylistic preferences.
        - Commit with: `review({slice_name}): {{verdict}} - score {{XX}}/100`."""
    ).strip()


def _build_codex_command(
    codex_bin: str,
    repo: Path,
    prompt: str,
    model: str,
    reasoning_effort: str,
    extra_writable_dirs: list[str] | None = None,
) -> list[str]:
    cmd = [
        codex_bin, "exec",
        "-m", model,
        "-c", f'model_reasoning_effort="{reasoning_effort}"',
        "--cd", str(repo),
    ]
    for d in (extra_writable_dirs or []):
        cmd.extend(["--add-dir", d])
    cmd.append(prompt)
    return cmd


def _default_log_dir() -> Path:
    return Path("/tmp/domain-planner-logs")


def _prepare_log_file(log_dir: Path | None, label: str) -> Path:
    if log_dir is None:
        log_dir = _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{label}_{ts}.log"


def run_review(
    prompt: str,
    repo: Path,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    log_dir: Path | None = None,
    worker_label: str = "plan-review",
    extra_writable_dirs: list[str] | None = None,
) -> tuple[int, Path]:
    """Run plan review synchronously. Blocks until done."""
    command = _build_codex_command(codex_bin, repo, prompt, model, reasoning_effort, extra_writable_dirs)
    log_file = _prepare_log_file(log_dir, worker_label)
    with open(log_file, "w", encoding="utf-8") as fh:
        result = subprocess.run(command, stdout=fh, stderr=fh, check=False)
    return result.returncode, log_file


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Critical review of a domain plan before sign-off."
    )
    parser.add_argument("--slice", required=True, help="Slice name, e.g. agent_billing")
    parser.add_argument("--repo", default=".", help="Repository root (for mode detection and codex --cd)")
    parser.add_argument("--mode", help="Explicit mode name")
    parser.add_argument("--execute", action="store_true", help="Run via codex exec (blocks until done)")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI binary name/path")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help=f"Reasoning effort (default: {DEFAULT_REASONING_EFFORT})",
    )
    parser.add_argument("--log-dir", default=None, help="Directory for log files")
    parser.add_argument("--plan-root", default=None, help="Override plan root (defaults to mode plan_root, then legacy default)")
    parser.add_argument("--plan-index", default=None, help="Override plan index (defaults to mode plan_index, then legacy default)")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    skill_root = Path(__file__).resolve().parents[1]
    repo = Path(args.repo).expanduser()

    # Detect mode first so plan paths can be resolved from mode config.
    mode_file = _discover_mode(skill_root, repo, args.mode)

    plan_root = args.plan_root or _mode_setting(mode_file, "plan_root") or DEFAULT_PLAN_ROOT
    plan_index = args.plan_index or _mode_setting(mode_file, "plan_index") or DEFAULT_PLAN_INDEX

    if not plan_root or not plan_index:
        print(
            "Missing plan storage configuration. Provide --plan-root and --plan-index "
            "or use a mode file with plan_root/plan_index.",
            file=sys.stderr,
        )
        return 1

    # Check plan files exist
    missing = _check_plan_exists(plan_root, args.slice)
    if missing:
        print(f"Warning: missing plan files for '{args.slice}': {', '.join(missing)}", file=sys.stderr)
        if len(missing) == len(PLAN_FILES):
            print(f"No plan files found at {_plan_dir(plan_root, args.slice)}", file=sys.stderr)
            return 1

    # Build prompt
    prompt = build_prompt(
        slice_name=args.slice,
        plan_root=plan_root,
        plan_index=plan_index,
        skill_root=skill_root,
        mode_file=mode_file,
    )

    if not args.execute:
        print("\n--- Plan Review Prompt ---\n")
        print(prompt)
        print(f"\nModel: {args.model} | Reasoning effort: {args.reasoning_effort}")
        print("\nRun with --execute to launch Codex.")
        return 0

    print(f"Reviewing plan: {args.slice}")
    print(f"Model: {args.model} | Reasoning effort: {args.reasoning_effort}")

    log_dir = Path(args.log_dir) if args.log_dir else None
    plan_dir_resolved = str(_plan_dir(plan_root, args.slice))
    rc, log_file = run_review(
        prompt=prompt,
        repo=repo,
        codex_bin=args.codex_bin,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        log_dir=log_dir,
        worker_label=f"{args.slice}_plan-review",
        extra_writable_dirs=[plan_dir_resolved],
    )

    review_path = _plan_dir(plan_root, args.slice) / "REVIEW.md"
    if review_path.exists():
        print(f"Review written: {review_path}")
    else:
        print(f"Warning: REVIEW.md not found at {review_path}", file=sys.stderr)

    print(f"Plan review exited {rc}. Log: {log_file}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
