#!/usr/bin/env python3
"""Shared `br` (beads_rust) bridge for skills that declare `requires_beads: true`.

Wraps the small surface of `br` that skills actually need so each skill does not
re-implement the same shell-out logic. See:

  ../references/beads-contract.md

for the cross-skill contract this helper enforces.

CLI usage (every command emits JSON on stdout, non-zero exit on failure):

  br_helpers.py ensure                              # init .beads/ + AGENTS.md if missing
  br_helpers.py status                              # `br doctor` + `br where` summary
  br_helpers.py ready [--limit N] [--label …]       # `br ready --robot`
  br_helpers.py scheduler [--limit N]               # `br scheduler --robot`
  br_helpers.py mint-node exec-001-backend-api 'Backend API' \\
      --concern backend-api --repo backend \\
      --writes 'src/domain/**' --done-when '...' \\
      --validate 'npm test' --risk none \\
      --depends-on br-exec-000-... [--epic br-epic-...]
  br_helpers.py claim {id}                          # atomic in_progress
  br_helpers.py block {id} 'reason text'
  br_helpers.py done {id} 'summary'                 # close --suggest-next --robot
  br_helpers.py render-workgraph [--epic id] [--out WORKGRAPH.md]
  br_helpers.py flush                               # br sync --flush-only

Module usage:

  from br_helpers import ensure_initialized, ready_frontier, mint_node, claim, done

The helper does NOT auto-commit .beads/. Final integration waves commit
explicitly via the `commit` skill.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Optional


BR = shutil.which("br") or "/Users/b/.local/bin/br"


# ----------------------------- core shell-out -----------------------------


def _run(args: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Invoke `br` with attribution env vars threaded through."""
    env = os.environ.copy()
    env.setdefault("BR_AGENT_NAME", env.get("BR_AGENT_NAME", "skill-runtime"))
    env.setdefault("BR_HARNESS", env.get("BR_HARNESS", "claude-code"))
    return subprocess.run(
        [BR, *args],
        check=check,
        capture_output=capture,
        text=True,
        env=env,
    )


def _json(args: list[str]) -> Any:
    """Run a `br` subcommand with --json and parse the envelope.

    `--json` is the universal flag in `br`'s global options; `--robot` is a
    per-subcommand alias that only exists on `ready`, `scheduler`, `close`,
    `update`, and a few others. We always use `--json` for portability.
    """
    if "--json" not in args:
        args = [*args, "--json"]
    proc = _run(args)
    out = proc.stdout.strip()
    if not out:
        return None
    return json.loads(out)


# ----------------------------- bootstrap -----------------------------


def ensure_initialized(repo: Path | str = ".") -> dict:
    """Make sure `.beads/` exists and AGENTS.md has the workflow block."""
    repo = Path(repo).resolve()
    beads_dir = repo / ".beads"
    initialized = beads_dir.is_dir()
    if not initialized:
        _run(["init"], capture=False)
    # Idempotent: --force skips the prompt; --add upserts the block.
    _run(["agents", "--add", "--force"], check=False, capture=False)
    where = _run(["where"], check=False).stdout.strip()
    return {"initialized": initialized, "beads_dir": str(beads_dir), "where": where}


def status() -> dict:
    """Return a small dict summarizing whether beads is healthy in cwd."""
    where = _run(["where"], check=False)
    if where.returncode != 0:
        return {"healthy": False, "reason": "no_beads_dir", "where": where.stderr.strip()}
    doctor = _run(["doctor", "--robot"], check=False)
    return {
        "healthy": doctor.returncode == 0,
        "where": where.stdout.strip(),
        "doctor": doctor.stdout.strip() or doctor.stderr.strip(),
    }


# ----------------------------- read paths -----------------------------


def ready_frontier(*, limit: int = 20, labels: Iterable[str] = ()) -> list[dict]:
    """`br ready --json` — caller filters/sorts further if needed."""
    args = ["ready", "--limit", str(limit)]
    for label in labels:
        args += ["--label", label]
    data = _json(args)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("issues") or data.get("ready") or []
    return []


def scheduler_ranked(*, limit: int = 20) -> list[dict]:
    """`br scheduler --json` — ranked ready work with explainable evidence."""
    data = _json(["scheduler", "--limit", str(limit)])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("recommendations") or data.get("issues") or []
    return []


# ----------------------------- write paths -----------------------------


def mint_node(
    slug: str,
    title: str,
    *,
    concern: Optional[str] = None,
    repo: Optional[str] = None,
    writes: Iterable[str] = (),
    done_when: Optional[str] = None,
    validate: Iterable[str] = (),
    risk: str = "none",
    depends_on: Iterable[str] = (),
    epic: Optional[str] = None,
    priority: int = 2,
    issue_type: str = "task",
    labels: Iterable[str] = (),
) -> str:
    """Create an executable `br` child issue and return its ID."""
    label_list = [f"risk:{risk}"]
    if concern:
        label_list.append(f"concern:{concern}")
    if repo:
        label_list.append(f"repo:{repo}")
    label_list.extend(labels)
    design_lines = []
    if writes:
        design_lines.append("writes:")
        design_lines.extend(f"  - {w}" for w in writes)
    notes_lines = []
    if validate:
        notes_lines.append("validate:")
        notes_lines.extend(f"  - {v}" for v in validate)

    # `br create` only accepts a small set of flags; rich fields like
    # --design, --notes, --acceptance-criteria are update-only. We create
    # first with the small set, then flow the rich fields via update.
    create_args = [
        "create",
        title,
        "--slug", slug,
        "--type", issue_type,
        "--priority", str(priority),
        "--labels", ",".join(label_list),
        "--json",
    ]
    if epic:
        create_args += ["--parent", epic]

    proc = _run(create_args)
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"br create returned non-JSON: {proc.stdout!r}") from exc
    issue_id = envelope.get("id") or envelope.get("issue", {}).get("id")
    if not issue_id:
        raise RuntimeError(f"br create envelope missing id: {envelope!r}")

    # Apply rich fields via update if any were provided.
    update_args: list[str] = []
    if design_lines:
        update_args += ["--design", "\n".join(design_lines)]
    if notes_lines:
        update_args += ["--notes", "\n".join(notes_lines)]
    if done_when:
        update_args += ["--acceptance-criteria", done_when]
    if update_args:
        _run(["update", issue_id, *update_args, "--json"], capture=True)

    for parent in depends_on:
        # capture=True so `br dep add` chatter does not pollute our stdout
        # JSON envelope when this helper is invoked from a shell pipeline.
        _run(["dep", "add", issue_id, parent], capture=True)
    return issue_id


def claim(issue_id: str) -> dict:
    """Atomic claim: assignee=actor + status=in_progress."""
    proc = _run(["update", issue_id, "--claim", "--json"])
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {"id": issue_id}
    except json.JSONDecodeError:
        return {"id": issue_id, "raw": proc.stdout}


def block(issue_id: str, reason: str) -> dict:
    proc = _run(["update", issue_id, "-s", "blocked", "--notes", reason, "--json"])
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {"id": issue_id}
    except json.JSONDecodeError:
        return {"id": issue_id, "raw": proc.stdout}


def done(issue_id: str, reason: str) -> dict:
    """Close + return newly-unblocked issues in one call."""
    proc = _run(["close", issue_id, "--reason", reason, "--suggest-next", "--json"])
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {"id": issue_id}
    except json.JSONDecodeError:
        return {"id": issue_id, "raw": proc.stdout}


def flush() -> dict:
    """Force JSONL export so the next git commit picks up the latest state."""
    proc = _run(["sync", "--flush-only", "--json"], check=False)
    return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}


# ----------------------------- view rendering -----------------------------


def render_workgraph(*, epic: Optional[str] = None, include_closed: bool = True) -> str:
    """Produce a human-readable WORKGRAPH.md view from current br state.

    The view is generated, not authoritative. Skills regenerate it from
    `br list --json` on demand and never edit it in place.
    """
    args = ["list"]
    if epic:
        args += ["--parent", epic]
    if include_closed:
        # `br list` defaults to open-only; -a/--all includes closed.
        args += ["--all"]
    data = _json(args)
    issues = data if isinstance(data, list) else data.get("issues", [])

    lines = [
        "# WORKGRAPH (generated view)",
        "",
        "*This file is rendered from `br list --json`. Do not edit by hand —*",
        "*update via `br update`/`br close` and regenerate with `br_helpers.py render-workgraph`.*",
        "",
    ]
    for issue in issues:
        iid = issue.get("id", "?")
        title = issue.get("title", "")
        status = issue.get("status", "?")
        labels = issue.get("labels", []) or []
        deps = issue.get("dependencies", []) or issue.get("depends_on", [])
        lines.append(f"- **{iid}** `{status}` — {title}")
        if labels:
            lines.append(f"  labels: {', '.join(labels)}")
        if deps:
            dep_ids = [d.get("id", d) if isinstance(d, dict) else d for d in deps]
            lines.append(f"  depends_on: {', '.join(dep_ids)}")
    return "\n".join(lines) + "\n"


# ----------------------------- CLI -----------------------------


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Cross-skill br/beads_rust bridge")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ensure", help="Initialize .beads/ + AGENTS.md if missing")
    sub.add_parser("status", help="Health summary of br in cwd")

    sp = sub.add_parser("ready")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--label", action="append", default=[])

    sp = sub.add_parser("scheduler")
    sp.add_argument("--limit", type=int, default=20)

    sp = sub.add_parser("mint-node")
    sp.add_argument("slug")
    sp.add_argument("title")
    sp.add_argument("--concern")
    sp.add_argument("--repo")
    sp.add_argument("--writes", action="append", default=[])
    sp.add_argument("--done-when")
    sp.add_argument("--validate", action="append", default=[])
    sp.add_argument("--risk", default="none")
    sp.add_argument("--depends-on", action="append", default=[])
    sp.add_argument("--epic")
    sp.add_argument("--priority", type=int, default=2)
    sp.add_argument("--type", default="task", dest="issue_type")
    sp.add_argument("--label", action="append", default=[], dest="labels")

    sp = sub.add_parser("claim")
    sp.add_argument("id")

    sp = sub.add_parser("block")
    sp.add_argument("id")
    sp.add_argument("reason")

    sp = sub.add_parser("done")
    sp.add_argument("id")
    sp.add_argument("reason")

    sp = sub.add_parser("render-workgraph")
    sp.add_argument("--epic")
    sp.add_argument("--out", default="-")

    sp = sub.add_parser(
        "render-mmdx",
        help="Render br chain state (e.g. chain:smart) as an .mmdx stack via br_to_mmdx.py",
    )
    sp.add_argument("--repo", help="Single repo dir containing .beads/. Defaults to scanning ~/repos.")
    sp.add_argument("--scan", action="append", default=[], help="Root(s) to walk for .beads/. Repeatable.")
    sp.add_argument("--label", default="chain:smart", help="Comma-separated label filter. Default chain:smart.")
    sp.add_argument("--out", help="Write to this path. Defaults to ~/.claude/skills/smart/chains/<stamp>.mmdx.")
    sp.add_argument("--open", action="store_true", help="Pipe through mmd.py --open after writing.")
    sp.add_argument("--print", action="store_true", help="Print to stdout instead of writing a file.")

    sub.add_parser("flush")

    args = p.parse_args(argv)

    if args.cmd == "ensure":
        _emit(ensure_initialized())
    elif args.cmd == "status":
        _emit(status())
    elif args.cmd == "ready":
        _emit(ready_frontier(limit=args.limit, labels=args.label))
    elif args.cmd == "scheduler":
        _emit(scheduler_ranked(limit=args.limit))
    elif args.cmd == "mint-node":
        _emit({"id": mint_node(
            slug=args.slug,
            title=args.title,
            concern=args.concern,
            repo=args.repo,
            writes=args.writes,
            done_when=args.done_when,
            validate=args.validate,
            risk=args.risk,
            depends_on=args.depends_on,
            epic=args.epic,
            priority=args.priority,
            issue_type=args.issue_type,
            labels=args.labels,
        )})
    elif args.cmd == "claim":
        _emit(claim(args.id))
    elif args.cmd == "block":
        _emit(block(args.id, args.reason))
    elif args.cmd == "done":
        _emit(done(args.id, args.reason))
    elif args.cmd == "flush":
        _emit(flush())
    elif args.cmd == "render-workgraph":
        rendered = render_workgraph(epic=args.epic)
        if args.out == "-":
            sys.stdout.write(rendered)
        else:
            Path(args.out).write_text(rendered)
            _emit({"wrote": args.out, "bytes": len(rendered)})
    elif args.cmd == "render-mmdx":
        # Delegate to the sibling script so render logic stays in one place.
        bridge = Path(__file__).resolve().parent / "br_to_mmdx.py"
        forwarded = []
        if args.repo:
            forwarded += ["--repo", args.repo]
        for root in args.scan:
            forwarded += ["--scan", root]
        forwarded += ["--label", args.label]
        if args.out:
            forwarded += ["--out", args.out]
        if args.open:
            forwarded.append("--open")
        if args.print:
            forwarded.append("--print")
        return subprocess.call([sys.executable, str(bridge), *forwarded])
    return 0


if __name__ == "__main__":
    sys.exit(main())
