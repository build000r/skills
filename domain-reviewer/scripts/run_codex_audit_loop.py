#!/usr/bin/env python3
"""
Run the domain-reviewer audit -> fix -> re-review loop with Codex workers.

This orchestrator uses same-repository execution and optional parallel fix workers.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import launch_codex_worker as launcher

# Orchestrator context budget rule:
# Worker output NEVER flows into stdout. Workers write artifacts to disk
# (AUDIT_REPORT.md, INDEX.md). The orchestrator reads only those artifacts
# and prints one-line status summaries.
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
        extra_writable_dirs=[plan_root_resolved],
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
        extra_writable_dirs=[plan_root_resolved],
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
    parser.add_argument("--log-dir", default=None, help="Directory for worker log files (default: /tmp/domain-reviewer-logs)")
    parser.add_argument("--threshold", type=int, default=94, help="Score threshold for convergence")
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


def main(argv: list[str]) -> int:
    args = parse_args(argv)
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

    log_dir = Path(args.log_dir) if args.log_dir else None

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

    for iteration in range(args.max_iterations):
        # --- AUDIT / RE-REVIEW (sequential, must finish before score parse) ---
        worker = "audit" if iteration == 0 else "re-review"
        review_number = iteration if worker == "re-review" else 0
        review_model, review_effort = _resolve_model_for_worker(worker, args)

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
            report_text = _read_report(args.plan_root, args.slice)
        except Exception as exc:
            print(f"Failed to read audit report: {exc}", file=sys.stderr)
            return 1

        score = _parse_score(report_text)
        if score is None:
            print("Could not parse compliance score from AUDIT_REPORT.md", file=sys.stderr)
            return 1

        print(f"[orchestrator] Parsed score: {score}/100")
        if score >= args.threshold:
            print("[orchestrator] Converged.")
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
                "Score is below threshold but no backend/frontend handoff blocks were found.",
                file=sys.stderr,
            )
            return 1

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
        f"Reached max iterations ({args.max_iterations}) without reaching {args.threshold}/100.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
