#!/usr/bin/env python3
"""
Generate and optionally run prefilled Codex worker prompts for domain-reviewer.

This script supports same-repository orchestration without extra worktrees.
It resolves mode context, builds a worker-specific prompt, and can launch:

    codex exec --cd <repo> "<prompt>"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from textwrap import dedent


DEFAULT_PLAN_ROOT = None  # Set via --plan-root or mode config (plan_root)
DEFAULT_PLAN_INDEX = None  # Set via --plan-index or mode config (plan_index)
DEFAULT_SESSION_PLAN_INDEX = None  # Set via --session-plan-index or mode config (session_plan_index)

# Default model + reasoning effort per worker type.
# Override with --model and/or --reasoning-effort on the CLI.
DEFAULT_MODEL = "gpt-5.3-codex"
WORKER_DEFAULTS: dict[str, dict[str, str]] = {
    "audit":        {"model": DEFAULT_MODEL, "reasoning_effort": "xhigh"},
    "re-review":    {"model": DEFAULT_MODEL, "reasoning_effort": "xhigh"},
    "fix-backend":  {"model": DEFAULT_MODEL, "reasoning_effort": "medium"},
    "fix-frontend": {"model": DEFAULT_MODEL, "reasoning_effort": "medium"},
    "retire":       {"model": DEFAULT_MODEL, "reasoning_effort": "medium"},
}


@dataclass
class ModeContext:
    name: str
    mode_file: Path
    cwd_matches: list[str]
    backend_path_pattern: str | None
    backend_standards: str | None
    frontend_path_pattern: str | None
    frontend_standards: str | None
    plan_root: str | None
    plan_index: str | None
    session_plan_index: str | None


def _expand(path_value: str) -> str:
    return str(Path(path_value).expanduser())


def _parse_table_rows(mode_text: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for raw_line in mode_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        parts = [cell.strip() for cell in line.strip("|").split("|")]
        if len(parts) < 3:
            continue
        if parts[0].lower() == "layer":
            continue
        if set(parts[0]) == {"-"}:
            continue
        rows.append((parts[0], parts[1], parts[2]))
    return rows


def _extract_mode_setting(mode_text: str, key: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", mode_text, flags=re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def parse_mode_file(path: Path) -> ModeContext:
    text = path.read_text(encoding="utf-8")
    cwd_matches = re.findall(r"^\s*cwd_match:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    rows = _parse_table_rows(text)

    backend_path_pattern = None
    backend_standards = None
    frontend_path_pattern = None
    frontend_standards = None

    for layer, pattern, standards in rows:
        lowered = layer.strip().lower()
        if lowered == "backend":
            backend_path_pattern = pattern
            backend_standards = standards
        if lowered == "frontend":
            frontend_path_pattern = pattern
            frontend_standards = standards

    return ModeContext(
        name=path.stem,
        mode_file=path,
        cwd_matches=[item.strip() for item in cwd_matches],
        backend_path_pattern=backend_path_pattern,
        backend_standards=backend_standards,
        frontend_path_pattern=frontend_path_pattern,
        frontend_standards=frontend_standards,
        plan_root=_extract_mode_setting(text, "plan_root"),
        plan_index=_extract_mode_setting(text, "plan_index"),
        session_plan_index=_extract_mode_setting(text, "session_plan_index"),
    )


def discover_modes(skill_root: Path) -> list[ModeContext]:
    modes_dir = skill_root / "modes"
    if not modes_dir.exists():
        return []
    mode_files = sorted(modes_dir.glob("*.md"))
    return [parse_mode_file(mode_file) for mode_file in mode_files]


def _is_under(repo: Path, maybe_parent: str) -> bool:
    repo_resolved = repo.expanduser().resolve()
    parent_resolved = Path(maybe_parent).expanduser().resolve()
    return repo_resolved == parent_resolved or repo_resolved.is_relative_to(parent_resolved)


def detect_mode(modes: list[ModeContext], repo: Path, explicit_mode: str | None) -> ModeContext:
    if not modes:
        raise ValueError("No mode files found under domain-reviewer/modes/")

    if explicit_mode:
        for mode in modes:
            if mode.name == explicit_mode:
                return mode
        available = ", ".join(sorted(mode.name for mode in modes))
        raise ValueError(f"Unknown mode '{explicit_mode}'. Available: {available}")

    matched: list[ModeContext] = []
    for mode in modes:
        for cwd_match in mode.cwd_matches:
            if _is_under(repo, cwd_match):
                matched.append(mode)
                break

    if len(matched) == 1:
        return matched[0]

    available = ", ".join(sorted(mode.name for mode in modes))
    if not matched:
        raise ValueError(
            f"No mode matched repo '{repo}'. Use --mode. Available modes: {available}"
        )
    raise ValueError(
        f"Multiple modes matched repo '{repo}': {', '.join(mode.name for mode in matched)}. "
        f"Use --mode explicitly."
    )


def _resolve_slice_path(pattern: str | None, slice_name: str) -> str | None:
    if pattern is None:
        return None
    return pattern.replace("{slice}", slice_name)


def _load_handoff(args: argparse.Namespace) -> str:
    if args.handoff_text:
        return args.handoff_text.strip()
    if args.handoff_file:
        return Path(args.handoff_file).read_text(encoding="utf-8").strip()
    raise ValueError("Fix workers require --handoff-file or --handoff-text")


def _core_context_block(args: argparse.Namespace, mode: ModeContext, skill_root: Path) -> str:
    backend_path = _resolve_slice_path(mode.backend_path_pattern, args.slice)
    frontend_path = _resolve_slice_path(mode.frontend_path_pattern, args.slice)
    lines = [
        f"- Plan files: {_expand(args.plan_root)}/{args.slice}/",
        f"- Plan index: {_expand(args.plan_index)}",
        f"- Session plan index: {_expand(args.session_plan_index)}",
        f"- Mode file: {mode.mode_file}",
        f"- Audit workflow reference: {skill_root / 'references' / 'audit-workflow.md'}",
        f"- Audit template reference: {skill_root / 'references' / 'audit-template.md'}",
    ]
    if backend_path:
        lines.append(f"- Backend code: {backend_path}")
    if mode.backend_standards:
        lines.append(f"- Backend standards: {mode.backend_standards}")
    if frontend_path:
        lines.append(f"- Frontend code: {frontend_path}")
    if mode.frontend_standards:
        lines.append(f"- Frontend standards: {mode.frontend_standards}")
    return "\n".join(lines)


def build_prompt(args: argparse.Namespace, mode: ModeContext, skill_root: Path) -> str:
    context_block = _core_context_block(args, mode, skill_root)

    common_guardrails = dedent(
        """
        Guardrails:
        - Stay inside owned scope for this worker.
        - Do not run destructive git commands (`git reset --hard`, `git checkout --`, mass reverts).
        - Do not revert teammate changes.
        - If scope crossing is required, stop and request handoff.
        """
    ).strip()

    if args.worker == "audit":
        return (
            f"Audit the `{args.slice}` slice implementation against its plan.\n"
            "You are the AUDIT worker phase in domain-reviewer.\n\n"
            "Context:\n"
            f"{context_block}\n\n"
            f"{common_guardrails}\n\n"
            "Instructions:\n"
            "1. Follow `references/audit-workflow.md` end-to-end.\n"
            f"2. Write/update `{_expand(args.plan_root)}/{args.slice}/AUDIT_REPORT.md`.\n"
            f"3. Update `{_expand(args.plan_index)}` status based on verdict.\n"
            "4. Include parseable score line: `### Overall Compliance Score: **XX/100**`.\n"
            "5. Include `## Agent Handoffs` blocks for remaining issues.\n"
            f"6. Commit with: `audit({args.slice}): {{verdict}} - score {{XX}}/100`."
        )

    if args.worker == "re-review":
        return (
            f"Re-review the `{args.slice}` slice after fixes were applied (re-review #{args.iteration}).\n"
            "You are the RE-REVIEW worker phase in domain-reviewer.\n\n"
            "Context:\n"
            f"{context_block}\n\n"
            f"{common_guardrails}\n\n"
            "Instructions:\n"
            "1. Read plan files and current `AUDIT_REPORT.md`.\n"
            "2. Compare changes since baseline using `git diff`.\n"
            "3. Mark each previous issue as FIXED / PARTIALLY FIXED / NOT ADDRESSED.\n"
            "4. Add new issues introduced by fixes.\n"
            f"5. Append `Re-Review #{args.iteration}` section to `AUDIT_REPORT.md`.\n"
            "6. Recalculate score and keep parseable score format.\n"
            f"7. Update `{_expand(args.plan_index)}` if verdict/status changed.\n"
            f"8. Commit with: `audit({args.slice}): re-review #{args.iteration} - score {{XX}}/100`."
        )

    if args.worker == "fix-backend":
        handoff_block = _load_handoff(args)
        backend_path = _resolve_slice_path(mode.backend_path_pattern, args.slice) or "(not defined in mode)"
        backend_standards = mode.backend_standards or "(not defined in mode)"
        return (
            f"Apply backend fixes for slice `{args.slice}` from this handoff block:\n\n"
            f"{handoff_block}\n\n"
            "Context:\n"
            f"- Backend code location: {backend_path}\n"
            f"- Backend standards: {backend_standards}\n"
            f"- Plan files: {_expand(args.plan_root)}/{args.slice}/\n"
            f"- Mode file: {mode.mode_file}\n\n"
            f"{common_guardrails}\n\n"
            "Instructions:\n"
            "1. Write/fix tests first, then implementation.\n"
            "2. Implement only backend-owned scope for this handoff.\n"
            f"3. Commit with: `fix({args.slice}): {{brief description of fixes}}`."
        )

    if args.worker == "fix-frontend":
        handoff_block = _load_handoff(args)
        frontend_path = _resolve_slice_path(mode.frontend_path_pattern, args.slice) or "(not defined in mode)"
        frontend_standards = mode.frontend_standards or "(not defined in mode)"
        return (
            f"Apply frontend fixes for slice `{args.slice}` from this handoff block:\n\n"
            f"{handoff_block}\n\n"
            "Context:\n"
            f"- Frontend code location: {frontend_path}\n"
            f"- Frontend standards: {frontend_standards}\n"
            f"- Plan files: {_expand(args.plan_root)}/{args.slice}/\n"
            f"- Mode file: {mode.mode_file}\n\n"
            f"{common_guardrails}\n\n"
            "Instructions:\n"
            "1. Implement only frontend-owned scope for this handoff.\n"
            "2. Align with mode frontend patterns/conventions.\n"
            f"3. Commit with: `fix({args.slice}): {{brief description of fixes}}`."
        )

    raise ValueError(f"Unsupported worker: {args.worker}")


def resolve_model_config(
    worker: str,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> tuple[str, str]:
    """Return (model, reasoning_effort) for a worker type."""
    defaults = WORKER_DEFAULTS.get(worker, {"model": DEFAULT_MODEL, "reasoning_effort": "medium"})
    model = model_override or defaults["model"]
    effort = effort_override or defaults["reasoning_effort"]
    return model, effort


def _build_codex_command(
    codex_bin: str,
    repo: Path,
    prompt: str,
    model: str,
    reasoning_effort: str,
    extra_writable_dirs: list[str] | None = None,
) -> list[str]:
    """Build the full codex exec command with model and reasoning effort."""
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
    return Path("/tmp/domain-reviewer-logs")


def _prepare_log_file(log_dir: Path | None, worker_label: str) -> Path:
    if log_dir is None:
        log_dir = _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{worker_label}_{ts}.log"


def _status_dir(log_dir: Path | None = None) -> Path:
    base = log_dir if log_dir else _default_log_dir()
    d = base / "status"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_status(status_dir: Path, label: str, data: dict) -> Path:
    """Write a JSON status file for a worker. Atomic via rename."""
    path = status_dir / f"{label}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.rename(path)
    return path


def read_all_statuses(log_dir: Path | None = None) -> list[dict]:
    """Read all worker status files. Used by check_workers.py."""
    sd = _status_dir(log_dir)
    results = []
    for p in sorted(sd.glob("*.json")):
        try:
            results.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _scan_artifacts(
    worker_label: str,
    plan_root: str | None,
    slice_name: str | None,
) -> list[str]:
    """After a worker finishes, find artifacts it produced.

    Checks known locations — the orchestrator reads these,
    never the raw log file.
    """
    found: list[str] = []
    if not slice_name:
        return found

    # Convention: AUDIT_REPORT.md in plan dir or /tmp fallback
    candidates = []
    if plan_root:
        candidates.append(Path(plan_root).expanduser() / slice_name / "AUDIT_REPORT.md")
    candidates.append(Path(f"/tmp/{slice_name}_AUDIT_REPORT.md"))

    for c in candidates:
        if c.exists():
            found.append(str(c))

    return found


def launch_detached(
    prompt: str,
    repo: Path,
    codex_bin: str,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = "medium",
    log_dir: Path | None = None,
    worker_label: str = "worker",
    plan_root: str | None = None,
    slice_name: str | None = None,
    extra_writable_dirs: list[str] | None = None,
) -> dict:
    """Fork a Codex worker into a fully detached background process.

    Returns immediately with worker metadata. The agent's tool call
    does NOT block. The child process writes a .json status marker
    when it finishes — check with check_workers.py.

    Artifacts (not logs) are recorded in the status file so the
    orchestrator knows what to read.
    """
    log_file = _prepare_log_file(log_dir, worker_label)
    sd = _status_dir(log_dir)

    started_at = datetime.now().isoformat()
    status_data = {
        "label": worker_label,
        "status": "RUNNING",
        "pid": None,
        "started_at": started_at,
        "finished_at": None,
        "exit_code": None,
        "artifacts": [],
        "model": model,
        "reasoning_effort": reasoning_effort,
        # Log path stored for debugging only — not surfaced to agent by default
        "_log_file": str(log_file),
    }

    pid = os.fork()
    if pid > 0:
        # Parent: record PID and return immediately
        status_data["pid"] = pid
        _write_status(sd, worker_label, status_data)
        return status_data

    # Child: detach from parent session, run codex, write completion marker
    try:
        os.setsid()
        command = _build_codex_command(codex_bin, repo, prompt, model, reasoning_effort, extra_writable_dirs)
        with open(log_file, "w", encoding="utf-8") as fh:
            result = subprocess.run(command, stdout=fh, stderr=fh, check=False)

        artifacts = _scan_artifacts(worker_label, plan_root, slice_name)

        status_data["pid"] = os.getpid()
        status_data["status"] = "DONE"
        status_data["exit_code"] = result.returncode
        status_data["finished_at"] = datetime.now().isoformat()
        status_data["artifacts"] = artifacts
        _write_status(sd, worker_label, status_data)
    except Exception as exc:
        status_data["pid"] = os.getpid()
        status_data["status"] = "FAILED"
        status_data["exit_code"] = -1
        status_data["error"] = str(exc)
        status_data["finished_at"] = datetime.now().isoformat()
        _write_status(sd, worker_label, status_data)
    finally:
        os._exit(0)


@dataclass
class WorkerHandle:
    """Non-blocking handle to a running Codex worker process.

    The worker's stdout/stderr go to a log file on disk.
    A daemon thread watches the process and fires on_done when it exits.
    """

    label: str
    log_file: Path
    _process: subprocess.Popen = field(repr=False)
    _done_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _exit_code: int | None = field(default=None, repr=False)

    @property
    def done(self) -> bool:
        return self._done_event.is_set()

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    def poll(self) -> int | None:
        """Check if done without blocking. Returns exit code or None."""
        if self._done_event.is_set():
            return self._exit_code
        rc = self._process.poll()
        if rc is not None:
            self._exit_code = rc
            self._done_event.set()
        return rc

    def wait(self, timeout: float | None = None) -> int:
        """Block until worker finishes. Returns exit code."""
        self._done_event.wait(timeout=timeout)
        if self._exit_code is None:
            raise TimeoutError(f"Worker {self.label} did not finish in time")
        return self._exit_code


def run_codex_bg(
    prompt: str,
    repo: Path,
    codex_bin: str,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = "medium",
    log_dir: Path | None = None,
    worker_label: str = "worker",
    on_done: callable | None = None,
    extra_writable_dirs: list[str] | None = None,
) -> WorkerHandle:
    """Launch codex exec in the background. Returns immediately.

    Worker output goes to a log file. When the process exits, the
    optional on_done(handle) callback fires on a daemon thread —
    use this to "ping" the orchestrator.
    """
    command = _build_codex_command(codex_bin, repo, prompt, model, reasoning_effort, extra_writable_dirs)
    log_file = _prepare_log_file(log_dir, worker_label)
    fh = open(log_file, "w", encoding="utf-8")
    proc = subprocess.Popen(command, stdout=fh, stderr=fh)

    handle = WorkerHandle(
        label=worker_label,
        log_file=log_file,
        _process=proc,
    )

    def _watcher():
        proc.wait()
        fh.close()
        handle._exit_code = proc.returncode
        handle._done_event.set()
        if on_done is not None:
            on_done(handle)

    t = threading.Thread(target=_watcher, daemon=True)
    t.start()

    return handle


def run_codex(
    prompt: str,
    repo: Path,
    codex_bin: str,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = "medium",
    log_dir: Path | None = None,
    worker_label: str = "worker",
    extra_writable_dirs: list[str] | None = None,
) -> tuple[int, Path]:
    """Run codex exec synchronously. Blocks until done.

    Returns (exit_code, log_file_path). Worker output goes to log file,
    never to the caller's stdout.
    """
    handle = run_codex_bg(
        prompt=prompt,
        repo=repo,
        codex_bin=codex_bin,
        model=model,
        reasoning_effort=reasoning_effort,
        log_dir=log_dir,
        worker_label=worker_label,
        extra_writable_dirs=extra_writable_dirs,
    )
    rc = handle.wait()
    return rc, handle.log_file


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and optionally run prefilled Codex worker prompts for domain-reviewer."
    )
    parser.add_argument("--slice", required=True, help="Slice name, e.g. agent_billing")
    parser.add_argument(
        "--worker",
        required=True,
        choices=["audit", "re-review", "fix-backend", "fix-frontend"],
        help="Worker phase prompt to generate",
    )
    parser.add_argument("--repo", default=".", help="Repository root (used for mode detection and codex --cd)")
    parser.add_argument("--mode", help="Explicit mode name")
    parser.add_argument("--iteration", type=int, default=1, help="Re-review iteration number")
    parser.add_argument("--handoff-file", help="Path to handoff block markdown file (fix workers)")
    parser.add_argument("--handoff-text", help="Inline handoff block text (fix workers)")
    parser.add_argument("--output", help="Write prompt to file")
    parser.add_argument("--execute", action="store_true", help="Run prompt via `codex exec` (blocks until done)")
    parser.add_argument("--bg", action="store_true", help="Launch worker in background and return immediately")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI binary name/path")
    parser.add_argument(
        "--model",
        default=None,
        help="Override model for this worker (default: per-worker tier, see WORKER_DEFAULTS)",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Override reasoning effort (default: per-worker tier, see WORKER_DEFAULTS)",
    )
    parser.add_argument("--log-dir", default=None, help="Directory for worker log files (default: /tmp/domain-reviewer-logs)")
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
        modes = discover_modes(skill_root)
        mode = detect_mode(modes, repo, args.mode)

        args.plan_root = args.plan_root or mode.plan_root or DEFAULT_PLAN_ROOT
        args.plan_index = args.plan_index or mode.plan_index or DEFAULT_PLAN_INDEX
        args.session_plan_index = (
            args.session_plan_index or mode.session_plan_index or DEFAULT_SESSION_PLAN_INDEX
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

        prompt = build_prompt(args, mode, skill_root)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(prompt + "\n", encoding="utf-8")
        print(f"Wrote prompt to {out_path}")

    model, effort = resolve_model_config(args.worker, args.model, args.reasoning_effort)
    log_dir = Path(args.log_dir) if args.log_dir else None

    # Plan root is often outside the --cd repo — make it writable
    extra_dirs = []
    if args.plan_root:
        extra_dirs.append(str(Path(args.plan_root).expanduser()))

    if not args.execute and not args.bg:
        print("\n--- Prefilled Worker Prompt ---\n")
        print(prompt)
        print(f"\nModel: {model} | Reasoning effort: {effort}")
        print("\nRun with --execute (blocking) or --bg (background) to launch Codex.")
        return 0

    if args.bg:
        # Fire-and-forget: forks a detached process and returns immediately.
        # The agent gets back one line. Check with check_workers.py.
        status = launch_detached(
            prompt=prompt,
            repo=repo,
            codex_bin=args.codex_bin,
            model=model,
            reasoning_effort=effort,
            log_dir=log_dir,
            worker_label=f"{args.slice}_{args.worker}",
            plan_root=args.plan_root,
            slice_name=args.slice,
            extra_writable_dirs=extra_dirs,
        )
        print(f"Launched {status['label']} in background (pid {status['pid']}). Model: {model} | Effort: {effort}")
        print(f"Check status: python3 {Path(__file__).parent}/check_workers.py")
        return 0

    # --execute: blocking mode, one-line status when done.
    print(f"Model: {model} | Reasoning effort: {effort}")
    rc, log_file = run_codex(
        prompt=prompt,
        repo=repo,
        codex_bin=args.codex_bin,
        model=model,
        reasoning_effort=effort,
        log_dir=log_dir,
        worker_label=f"{args.slice}_{args.worker}",
        extra_writable_dirs=extra_dirs,
    )
    print(f"Worker {args.worker} exited {rc}. Log: {log_file}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
