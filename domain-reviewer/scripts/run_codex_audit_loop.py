#!/usr/bin/env python3
"""
Run the domain-reviewer audit -> fix -> re-review loop with Codex workers.

This orchestrator uses same-repository execution and optional parallel fix workers.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

import launch_codex_worker as launcher

# Orchestrator context budget rule:
# Workers use one temporary latest report for this helper's parser.
# Completed scratch is removed; interrupted runs retain recovery evidence.
#
# Workers run in background processes. A daemon thread per worker fires
# a callback when done — the orchestrator just waits on handles.


def _resolve_model_for_worker(
    worker: str,
    args: argparse.Namespace,
) -> tuple[str, str]:
    """Resolve model + effort for a worker, respecting override hierarchy.

    Priority: --model > --review-model/--fix-model > WORKER_DEFAULTS
    """
    # Model override hierarchy
    model_override = args.model  # global override wins
    if not model_override:
        if worker in ("audit", "re-review") and args.review_model:
            model_override = args.review_model
        elif worker in ("fix-backend", "fix-frontend") and args.fix_model:
            model_override = args.fix_model

    return launcher.resolve_model_config(worker, model_override, args.reasoning_effort)


def _expand(path_value: str) -> Path:
    return Path(path_value).expanduser()


def _report_path(plan_root: str, slice_name: str) -> Path:
    return _expand(plan_root) / slice_name / "AUDIT_REPORT.md"


def _read_report(plan_root: str, slice_name: str) -> str:
    path = _report_path(plan_root, slice_name)
    if not path.exists():
        raise FileNotFoundError(f"AUDIT_REPORT.md not found at {path}")
    return path.read_text(encoding="utf-8")


def _parse_score(report_text: str) -> int | None:
    overall_matches = re.findall(
        r"###\s*Overall Compliance Score:\s*\*\*(\d{1,3})/100\*\*",
        report_text,
        flags=re.IGNORECASE,
    )
    if overall_matches:
        return int(overall_matches[-1])

    updated_matches = re.findall(
        r"\*\*Updated Score:\s*\*\*(\d{1,3})/100\*\*",
        report_text,
        flags=re.IGNORECASE,
    )
    if updated_matches:
        return int(updated_matches[-1])

    return None


def _extract_handoff_block(report_text: str, label: str) -> str | None:
    pattern = rf"###\s*For {label} Issues.*?```(.*?)```"
    matches = re.findall(pattern, report_text, flags=re.IGNORECASE | re.DOTALL)
    if not matches:
        return None

    for candidate in reversed(matches):
        cleaned = candidate.strip()
        if not cleaned:
            continue
        if "{Only include" in cleaned:
            continue
        return cleaned

    return None


def _build_worker_args(
    *,
    slice_name: str,
    worker: str,
    repo: Path,
    mode_name: str,
    iteration: int,
    handoff_text: str | None,
    plan_root: str,
    plan_index: str,
    session_plan_index: str,
    report_path: str | None = None,
    score_threshold: int | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        slice=slice_name,
        worker=worker,
        repo=str(repo),
        mode=mode_name,
        iteration=iteration,
        handoff_file=None,
        handoff_text=handoff_text,
        output=None,
        execute=False,
        codex_bin="codex",
        plan_root=plan_root,
        plan_index=plan_index,
        session_plan_index=session_plan_index,
        report_path=report_path,
        score_threshold=score_threshold,
    )


def _worker_done_callback(handle: launcher.WorkerHandle) -> None:
    """Fires on a daemon thread when a background worker exits."""
    print(f"[orchestrator] {handle.label} finished (exit {handle.exit_code}). Log: {handle.log_file}")


def _build_worker_prompt(
    *,
    skill_root: Path,
    mode: launcher.ModeContext,
    slice_name: str,
    worker: str,
    iteration: int,
    handoff_text: str | None,
    repo: Path,
    plan_root: str,
    plan_index: str,
    session_plan_index: str,
    report_path: str | None = None,
    score_threshold: int | None = None,
) -> str:
    worker_args = _build_worker_args(
        slice_name=slice_name,
        worker=worker,
        repo=repo,
        mode_name=mode.name,
        iteration=iteration,
        handoff_text=handoff_text,
        plan_root=plan_root,
        plan_index=plan_index,
        session_plan_index=session_plan_index,
        report_path=report_path,
        score_threshold=score_threshold,
    )
    return launcher.build_prompt(worker_args, mode, skill_root)


def _launch_worker_bg(
    *,
    skill_root: Path,
    mode: launcher.ModeContext,
    repo: Path,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    slice_name: str,
    worker: str,
    iteration: int,
    handoff_text: str | None,
    plan_root: str,
    plan_index: str,
    session_plan_index: str,
    report_path: str | None = None,
    score_threshold: int | None = None,
    log_dir: Path | None = None,
) -> launcher.WorkerHandle:
    """Launch a worker in the background. Returns immediately."""
    prompt = _build_worker_prompt(
        skill_root=skill_root,
        mode=mode,
        slice_name=slice_name,
        worker=worker,
        iteration=iteration,
        handoff_text=handoff_text,
        repo=repo,
        plan_root=plan_root,
        plan_index=plan_index,
        session_plan_index=session_plan_index,
        report_path=report_path,
        score_threshold=score_threshold,
    )
    label = f"{slice_name}_{worker}"
    plan_root_resolved = str(Path(plan_root).expanduser())
    print(f"[orchestrator] Launching {label} in background... (model={model}, effort={reasoning_effort})")
    return launcher.run_codex_bg(
        prompt=prompt,
        repo=repo,
        codex_bin=codex_bin,
        model=model,
        reasoning_effort=reasoning_effort,
        log_dir=log_dir,
        worker_label=label,
        on_done=_worker_done_callback,
        extra_writable_dirs=[str(Path(report_path).parent)] if report_path else [plan_root_resolved],
    )


def _run_worker_sync(
    *,
    skill_root: Path,
    mode: launcher.ModeContext,
    repo: Path,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    slice_name: str,
    worker: str,
    iteration: int,
    handoff_text: str | None,
    plan_root: str,
    plan_index: str,
    session_plan_index: str,
    report_path: str | None = None,
    score_threshold: int | None = None,
    plan_only: bool,
    log_dir: Path | None = None,
) -> int:
    """Launch a worker and block until it finishes."""
    prompt = _build_worker_prompt(
        skill_root=skill_root,
        mode=mode,
        slice_name=slice_name,
        worker=worker,
        iteration=iteration,
        handoff_text=handoff_text,
        repo=repo,
        plan_root=plan_root,
        plan_index=plan_index,
        session_plan_index=session_plan_index,
        report_path=report_path,
        score_threshold=score_threshold,
    )

    if plan_only:
        print(f"\n=== Worker: {worker} (model={model}, effort={reasoning_effort}) ===")
        print(prompt)
        return 0

    plan_root_resolved = str(Path(plan_root).expanduser())
    print(f"[orchestrator] Starting {worker} worker... (model={model}, effort={reasoning_effort})")
    rc, log_file = launcher.run_codex(
        prompt=prompt,
        repo=repo,
        codex_bin=codex_bin,
        model=model,
        reasoning_effort=reasoning_effort,
        log_dir=log_dir,
        worker_label=f"{slice_name}_{worker}",
        extra_writable_dirs=[str(Path(report_path).parent)] if report_path else [plan_root_resolved],
    )
    print(f"[orchestrator] {worker} exited {rc}. Log: {log_file}")
    return rc


def _run_retire_worker(
    *,
    skill_root: Path,
    mode: launcher.ModeContext,
    repo: Path,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    slice_name: str,
    plan_root: str,
    plan_index: str,
    plan_only: bool,
    log_dir: Path | None = None,
) -> int:
    prompt = (
        f"Run retire mode for slice `{slice_name}`.\n\n"
        "Context:\n"
        f"- Plan files: {_expand(plan_root)}/{slice_name}/\n"
        f"- Plan index: {_expand(plan_index)}\n"
        f"- Mode file: {mode.mode_file}\n"
        f"- Retire workflow reference: {skill_root / 'references' / 'retire-workflow.md'}\n\n"
        "Guardrails:\n"
        "- Do not run destructive git commands (`git reset --hard`, `git checkout --`, mass reverts).\n"
        "- Do not revert teammate changes.\n\n"
        "- Before any git command, resolve the target repo and run `git -C \"$target_repo\" rev-parse --git-dir >/dev/null 2>&1`; if it fails, skip the git step with a clear message instead of running git from the current directory.\n\n"
        "Instructions:\n"
        "1. Follow `references/retire-workflow.md`.\n"
        "2. Generate/update COMPLETED.md for the slice.\n"
        "3. Ask for archival confirmation before moving files.\n"
        "4. Update INDEX.md story counts and date."
    )

    if plan_only:
        print(f"\n=== Worker: retire (model={model}, effort={reasoning_effort}) ===")
        print(prompt)
        return 0

    plan_root_resolved = str(Path(plan_root).expanduser())
    print(f"[orchestrator] Starting retire worker... (model={model}, effort={reasoning_effort})")
    rc, log_file = launcher.run_codex(
        prompt=prompt,
        repo=repo,
        codex_bin=codex_bin,
        model=model,
        reasoning_effort=reasoning_effort,
        log_dir=log_dir,
        worker_label=f"{slice_name}_retire",
        extra_writable_dirs=[plan_root_resolved],
    )
    print(f"[orchestrator] retire exited {rc}. Log: {log_file}")
    return rc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the domain-reviewer Codex audit/fix orchestration loop."
    )
    parser.add_argument("--slice", required=True, help="Slice name, e.g. agent_billing")
    parser.add_argument("--repo", default=".", help="Repository root for mode detection and codex --cd")
    parser.add_argument("--mode", help="Explicit mode name")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI binary name/path")
    parser.add_argument("--log-dir", default=None, help="Explicit retained log directory; default is private temporary scratch")
    parser.add_argument("--threshold", type=int, default=None, help="Explicit optional score threshold; default accepts required checks and material findings")
    parser.add_argument("--report-path", help="Explicit retained report output; default uses temporary scratch")
    parser.add_argument("--max-iterations", type=int, default=5, help="Maximum audit/re-review cycles")
    parser.add_argument(
        "--sequential-fixes",
        action="store_true",
        help="Run backend/frontend fix workers sequentially (default is parallel if both exist)",
    )
    parser.add_argument(
        "--retire-on-success",
        action="store_true",
        help="Run retire worker after convergence",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model for ALL workers (default: per-worker tier)",
    )
    parser.add_argument(
        "--review-model",
        default=None,
        help="Override model for audit/re-review workers only",
    )
    parser.add_argument(
        "--fix-model",
        default=None,
        help="Override model for fix-backend/fix-frontend workers only",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Override reasoning effort for ALL workers (default: per-worker tier)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print generated worker prompts without executing codex",
    )
    parser.add_argument("--plan-root", default=None, help="Override plan root (defaults to mode plan_root, then legacy default)")
    parser.add_argument("--plan-index", default=None, help="Override plan index (defaults to mode plan_index, then legacy default)")
    parser.add_argument(
        "--session-plan-index",
        default=None,
        help="Override session plan index (defaults to mode session_plan_index, then legacy default)",
    )
    return parser.parse_args(argv)


def _run(args: argparse.Namespace, scratch: Path) -> int:
    skill_root = Path(__file__).resolve().parents[1]
    repo = Path(args.repo).expanduser()

    try:
        modes = launcher.discover_modes(skill_root)
        mode = launcher.detect_mode(modes, repo, args.mode)

        args.plan_root = args.plan_root or mode.plan_root or launcher.DEFAULT_PLAN_ROOT
        args.plan_index = args.plan_index or mode.plan_index or launcher.DEFAULT_PLAN_INDEX
        args.session_plan_index = (
            args.session_plan_index or mode.session_plan_index or launcher.DEFAULT_SESSION_PLAN_INDEX
        )

        missing = []
        if not args.plan_root:
            missing.append("plan_root")
        if not args.plan_index:
            missing.append("plan_index")
        if not args.session_plan_index:
            missing.append("session_plan_index")
        if missing:
            raise ValueError(
                "Missing plan storage settings: "
                + ", ".join(missing)
                + ". Provide CLI overrides or define them in the active mode file."
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    log_dir = Path(args.log_dir) if args.log_dir else scratch / "logs"
    args.report_path = str(Path(args.report_path).expanduser().resolve()) if args.report_path else str(scratch / "AUDIT_REPORT.md")

    print(f"Mode: {mode.name}")
    print(f"Slice: {args.slice}")
    print(f"Threshold: {args.threshold}")
    print(f"Max iterations: {args.max_iterations}")
    print(f"Log dir: {log_dir or launcher._default_log_dir()}")

    common_kw = dict(
        skill_root=skill_root,
        mode=mode,
        repo=repo,
        plan_root=args.plan_root,
        plan_index=args.plan_index,
        session_plan_index=args.session_plan_index,
        report_path=args.report_path,
        score_threshold=args.threshold,
    )

    if args.plan_only:
        audit_model, audit_effort = _resolve_model_for_worker("audit", args)
        print(f"\nPlan-only mode: printing audit worker prompt.")
        return _run_worker_sync(
            **common_kw,
            codex_bin=args.codex_bin,
            model=audit_model,
            reasoning_effort=audit_effort,
            slice_name=args.slice,
            worker="audit",
            iteration=0,
            handoff_text=None,
            plan_only=True,
        )

    previous_handoffs = None
    for iteration in range(args.max_iterations):
        # --- AUDIT / RE-REVIEW (sequential, must finish before score parse) ---
        worker = "audit" if iteration == 0 else "re-review"
        review_number = iteration if worker == "re-review" else 0
        review_model, review_effort = _resolve_model_for_worker(worker, args)
        report_path = Path(args.report_path)
        previous_report_stat = report_path.stat() if report_path.exists() else None

        rc = _run_worker_sync(
            **common_kw,
            codex_bin=args.codex_bin,
            model=review_model,
            reasoning_effort=review_effort,
            slice_name=args.slice,
            worker=worker,
            iteration=review_number,
            handoff_text=None,
            plan_only=False,
            log_dir=log_dir,
        )
        if rc != 0:
            print(f"{worker} worker failed with exit code {rc}", file=sys.stderr)
            return rc

        # --- SCORE PARSE (orchestrator reads artifact, not worker stream) ---
        try:
            current_report_stat = report_path.stat()
            if previous_report_stat is not None and all(
                getattr(current_report_stat, key) == getattr(previous_report_stat, key)
                for key in ("st_ino", "st_mtime_ns", "st_ctime_ns", "st_size")
            ):
                raise ValueError("Review worker did not replace the current report")
            report_text = report_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"Failed to read audit report: {exc}", file=sys.stderr)
            return 1

        try:
            accepted = _acceptance_passed(report_text, args.threshold)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if accepted:
            print("[orchestrator] Acceptance criteria and required checks passed.")
            print(report_text[:6000].strip())
            if args.retire_on_success:
                retire_model, retire_effort = _resolve_model_for_worker("retire", args)
                retire_rc = _run_retire_worker(
                    skill_root=skill_root,
                    mode=mode,
                    repo=repo,
                    codex_bin=args.codex_bin,
                    model=retire_model,
                    reasoning_effort=retire_effort,
                    slice_name=args.slice,
                    plan_root=args.plan_root,
                    plan_index=args.plan_index,
                    plan_only=False,
                    log_dir=log_dir,
                )
                return retire_rc
            return 0

        # --- FIX PHASE (background workers, ping on done) ---
        backend_handoff = _extract_handoff_block(report_text, "Backend")
        frontend_handoff = _extract_handoff_block(report_text, "Frontend")

        if not backend_handoff and not frontend_handoff:
            print(
                "Acceptance remains unresolved but no actionable backend/frontend handoff was provided.",
                file=sys.stderr,
            )
            return 1

        handoffs = (backend_handoff, frontend_handoff)
        if handoffs == previous_handoffs:
            print("Repair made no material progress; diagnose the unchanged findings before retrying.", file=sys.stderr)
            return 2
        if iteration + 1 >= args.max_iterations:
            print("Review budget exhausted; remaining fixes require a review opportunity.", file=sys.stderr)
            return 2
        previous_handoffs = handoffs

        fix_jobs: list[tuple[str, str]] = []
        if backend_handoff:
            fix_jobs.append(("fix-backend", backend_handoff))
        if frontend_handoff:
            fix_jobs.append(("fix-frontend", frontend_handoff))

        if len(fix_jobs) >= 2 and not args.sequential_fixes:
            # Launch both in background, wait for both to ping back
            print("[orchestrator] Launching fix workers in background...")
            handles = []
            for worker_name, handoff in fix_jobs:
                fix_model, fix_effort = _resolve_model_for_worker(worker_name, args)
                handles.append(
                    _launch_worker_bg(
                        **common_kw,
                        codex_bin=args.codex_bin,
                        model=fix_model,
                        reasoning_effort=fix_effort,
                        slice_name=args.slice,
                        worker=worker_name,
                        iteration=0,
                        handoff_text=handoff,
                        log_dir=log_dir,
                    )
                )
            # Wait for all to finish (on_done callback prints status as each completes)
            for h in handles:
                h.wait()
            for h in handles:
                if h.exit_code != 0:
                    print(f"Fix worker {h.label} failed with exit code {h.exit_code}", file=sys.stderr)
                    return h.exit_code
        else:
            if len(fix_jobs) == 2:
                print("[orchestrator] Running fix workers sequentially.")
            for worker_name, handoff in fix_jobs:
                fix_model, fix_effort = _resolve_model_for_worker(worker_name, args)
                rc = _run_worker_sync(
                    **common_kw,
                    codex_bin=args.codex_bin,
                    model=fix_model,
                    reasoning_effort=fix_effort,
                    slice_name=args.slice,
                    worker=worker_name,
                    iteration=0,
                    handoff_text=handoff,
                    plan_only=False,
                    log_dir=log_dir,
                )
                if rc != 0:
                    print(f"{worker_name} worker failed with exit code {rc}", file=sys.stderr)
                    return rc

    print(
        f"Reached max iterations ({args.max_iterations}) with unresolved acceptance findings.",
        file=sys.stderr,
    )
    return 2


def _acceptance_passed(report: str, threshold: int | None = None) -> bool:
    values = {}
    for field in ("Acceptance", "Required checks"):
        matches = re.findall(rf"^{field}: (PASS|FAIL)$", report, flags=re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"Review requires one current {field}: PASS|FAIL line")
        values[field] = matches[0]
    if threshold is not None:
        score = _parse_score(report)
        if score is None or not 0 <= score <= 100:
            raise ValueError("Explicit threshold requires a score from 0 to 100")
        if score < threshold:
            return False
    return (all(value == "PASS" for value in values.values())
            and not any(_extract_handoff_block(report, label) for label in ("Backend", "Frontend")))


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.max_iterations < 1 or (args.threshold is not None and not 0 <= args.threshold <= 100):
        raise ValueError("iterations must be positive and explicit threshold must be 0..100")
    scratch = Path(tempfile.mkdtemp(prefix="domain-review-"))
    try:
        result = _run(args, scratch)
    except BaseException:
        print(f"Interrupted review scratch retained at {scratch}", file=sys.stderr)
        raise
    else:
        if result == 0:
            shutil.rmtree(scratch)
        else:
            print(f"Unresolved review scratch retained at {scratch}; collect evidence then remove it.", file=sys.stderr)
        return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
