#!/usr/bin/env python3
"""Shared `br` (beads_rust) bridge for skills that declare `requires_beads: true`.

Wraps the small surface of `br` that skills actually need so each skill does not
re-implement the same shell-out logic. See:

  ../references/beads-contract.md

for the cross-skill contract this helper enforces.

CLI usage (every command emits JSON on stdout, non-zero exit on failure):

  br_helpers.py ensure                              # init .beads/ + AGENTS.md if missing
  br_helpers.py status                              # `br doctor` + `br where` summary
  br_helpers.py ready [--limit N] [--label …]       # `br ready --json`
  br_helpers.py scheduler [--limit N]               # `br scheduler --json`
  br_helpers.py mint-node exec-001-backend-api 'Backend API' \\
      --concern backend-api --repo backend \\
      --writes 'src/domain/**' --done-when '...' \\
      --validate 'npm test' --risk none \\
      --depends-on br-exec-000-... [--epic br-epic-...]
  br_helpers.py update-node {id} --writes 'src/domain/**' --validate 'npm test'
  br_helpers.py hydrate-node {id}                    # Beads-backed dispatch contract
  br_helpers.py render-node-brief {id}               # Worker prompt from Beads
  br_helpers.py claim {id}                          # atomic in_progress
  br_helpers.py block {id} 'reason text'
  br_helpers.py done {id} 'summary'                 # close --suggest-next --json
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


BR = shutil.which("br") or "br"
BR_AGENTS_MARKER = "<!-- br-agent-instructions-v1 -->"
CURATED_AGENTS_MARKERS = (
    "<!-- bv-agent-instructions-v2 -->",
)


# ----------------------------- core shell-out -----------------------------


def _run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess:
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
        cwd=str(cwd) if cwd is not None else None,
    )


def _json(args: list[str], *, cwd: Path | str | None = None) -> Any:
    """Run a `br` subcommand with --json and parse the envelope.

    `--json` is the universal flag in `br`'s global options; `--robot` is a
    per-subcommand alias that only exists on `ready`, `scheduler`, `close`,
    `update`, and a few others. We always use `--json` for portability.
    """
    if "--json" not in args:
        args = [*args, "--json"]
    proc = _run(args, cwd=cwd)
    out = proc.stdout.strip()
    if not out:
        return None
    return json.loads(out)


def _first_issue(envelope: Any) -> dict:
    """Normalize `br show`/`br update` envelopes to one issue-like dict."""
    if isinstance(envelope, list):
        return envelope[0] if envelope else {}
    if isinstance(envelope, dict):
        if isinstance(envelope.get("issue"), dict):
            return envelope["issue"]
        if isinstance(envelope.get("issues"), list):
            return envelope["issues"][0] if envelope["issues"] else {}
        return envelope
    return {}


def _append_block(lines: list[str], key: str, values: Iterable[str]) -> None:
    materialized = [str(value) for value in values if str(value).strip()]
    if not materialized:
        return
    lines.append(f"{key}:")
    lines.extend(f"  - {value}" for value in materialized)


def _parse_list_block(text: Optional[str], key: str) -> list[str]:
    """Parse the simple YAML-ish list blocks this helper writes."""
    if not text:
        return []
    target = f"{key}:"
    result: list[str] = []
    in_block = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped == target:
            in_block = True
            continue
        if in_block:
            if not stripped:
                continue
            if stripped.endswith(":") and not stripped.startswith("- "):
                break
            if stripped.startswith("- "):
                result.append(stripped[2:].strip())
                continue
            if raw.startswith("  - "):
                result.append(raw[4:].strip())
                continue
            break
    return result


def _parse_scalar(text: Optional[str], key: str) -> Optional[str]:
    if not text:
        return None
    prefix = f"{key}:"
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            return value or None
    return None


def _first_nonempty(values: Iterable[str], fallback: Iterable[str]) -> list[str]:
    materialized = [str(value) for value in values if str(value).strip()]
    return materialized if materialized else list(fallback)


def _scalar_or_existing(value: Optional[str], existing: Optional[str]) -> Optional[str]:
    return value if value is not None and str(value).strip() else existing


def _labels(issue: dict) -> list[str]:
    return [str(label) for label in (issue.get("labels") or [])]


def _label_value(labels: Iterable[str], prefix: str) -> Optional[str]:
    marker = f"{prefix}:"
    for label in labels:
        if label.startswith(marker):
            return label[len(marker):]
    return None


def _lines_from_text(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return [line.strip("- ").strip() for line in text.splitlines() if line.strip()]


# ----------------------------- bootstrap -----------------------------


def _agents_update_policy(repo: Path) -> tuple[bool, Optional[str]]:
    """Return whether `br agents --add --force` can safely rewrite AGENTS.md."""
    agents_path = repo / "AGENTS.md"
    if not agents_path.exists():
        return True, None
    text = agents_path.read_text(encoding="utf-8", errors="replace")
    if BR_AGENTS_MARKER in text:
        return True, None
    for marker in CURATED_AGENTS_MARKERS:
        if marker in text:
            return False, f"existing_curated_agents_block:{marker}"
    if "agent-instructions" in text:
        return False, "existing_non_br_agent_instructions"
    return True, None


def ensure_initialized(repo: Path | str = ".") -> dict:
    """Make sure `.beads/` exists and AGENTS.md has the workflow block."""
    repo = Path(repo).resolve()
    beads_dir = repo / ".beads"
    initialized = beads_dir.is_dir()
    if not initialized:
        _run(["init"], capture=False, cwd=repo)
    should_update_agents, agents_skip_reason = _agents_update_policy(repo)
    agents_updated = False
    if should_update_agents:
        # Idempotent: --force skips the prompt; --add upserts the br-owned block.
        _run(["agents", "--add", "--force"], check=False, capture=False, cwd=repo)
        agents_updated = True
    where = _run(["where"], check=False, cwd=repo).stdout.strip()
    return {
        "initialized": initialized,
        "beads_dir": str(beads_dir),
        "where": where,
        "agents_updated": agents_updated,
        "agents_skip_reason": agents_skip_reason,
    }


def status() -> dict:
    """Return a small dict summarizing whether beads is healthy in cwd."""
    where = _run(["where"], check=False)
    if where.returncode != 0:
        return {"healthy": False, "reason": "no_beads_dir", "where": where.stderr.strip()}
    doctor = _run(["doctor", "--json"], check=False)
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


def list_issues(
    *,
    labels: Iterable[str] = (),
    include_closed: bool = False,
    parent: str | None = None,
    cwd: Path | str | None = None,
) -> list[dict]:
    """Return `br list --json` issues with shared envelope normalization."""
    args = ["list"]
    if parent:
        args += ["--parent", parent]
    if include_closed:
        args += ["--all"]
    for label in labels:
        args += ["--label", label]
    data = _json(args, cwd=cwd)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("issues") or []
    return []


# ----------------------------- write paths -----------------------------


def mint_node(
    slug: str,
    title: str,
    *,
    description: Optional[str] = None,
    concern: Optional[str] = None,
    repo: Optional[str] = None,
    writes: Iterable[str] = (),
    done_when: Optional[str] = None,
    validate: Iterable[str] = (),
    risk: str = "none",
    model_route: Optional[str] = None,
    repo_path: Optional[str] = None,
    branch: Optional[str] = None,
    run_dir: Optional[str] = None,
    stop_rules: Iterable[str] = (),
    non_goals: Iterable[str] = (),
    global_constraints: Iterable[str] = (),
    expected_assignee: Optional[str] = None,
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
    design_lines: list[str] = []
    _append_block(design_lines, "writes", writes)
    _append_block(design_lines, "stop_rules", stop_rules)
    _append_block(design_lines, "non_goals", non_goals)
    _append_block(design_lines, "global_constraints", global_constraints)
    notes_lines: list[str] = []
    _append_block(notes_lines, "validate", validate)
    if model_route:
        notes_lines.append(f"model_route: {model_route}")
    if repo_path:
        notes_lines.append(f"repo_path: {repo_path}")
    if branch:
        notes_lines.append(f"branch: {branch}")
    if run_dir:
        notes_lines.append(f"run_dir: {run_dir}")
    if expected_assignee:
        notes_lines.append(f"expected_assignee: {expected_assignee}")

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
    if description:
        update_args += ["--description", description]
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


def update_node_contract(
    issue_id: str,
    *,
    description: Optional[str] = None,
    writes: Iterable[str] = (),
    done_when: Optional[str] = None,
    validate: Iterable[str] = (),
    model_route: Optional[str] = None,
    repo_path: Optional[str] = None,
    branch: Optional[str] = None,
    run_dir: Optional[str] = None,
    stop_rules: Iterable[str] = (),
    non_goals: Iterable[str] = (),
    global_constraints: Iterable[str] = (),
    expected_assignee: Optional[str] = None,
) -> dict:
    """Write the Beads-backed execution-pack fields onto an existing issue."""
    existing = show_issue(issue_id)
    existing_design = existing.get("design")
    existing_notes = existing.get("notes")
    should_update_design = bool(writes or stop_rules or non_goals or global_constraints)
    should_update_notes = bool(
        validate
        or model_route is not None
        or repo_path is not None
        or branch is not None
        or run_dir is not None
        or expected_assignee is not None
    )

    design_lines: list[str] = []
    if should_update_design:
        _append_block(design_lines, "writes", _first_nonempty(writes, _parse_list_block(existing_design, "writes")))
        _append_block(design_lines, "stop_rules", _first_nonempty(stop_rules, _parse_list_block(existing_design, "stop_rules")))
        _append_block(design_lines, "non_goals", _first_nonempty(non_goals, _parse_list_block(existing_design, "non_goals")))
        _append_block(
            design_lines,
            "global_constraints",
            _first_nonempty(global_constraints, _parse_list_block(existing_design, "global_constraints")),
        )
    notes_lines: list[str] = []
    if should_update_notes:
        _append_block(notes_lines, "validate", _first_nonempty(validate, _parse_list_block(existing_notes, "validate")))
        scalar_fields = {
            "model_route": _scalar_or_existing(model_route, _parse_scalar(existing_notes, "model_route")),
            "repo_path": _scalar_or_existing(repo_path, _parse_scalar(existing_notes, "repo_path")),
            "branch": _scalar_or_existing(branch, _parse_scalar(existing_notes, "branch")),
            "run_dir": _scalar_or_existing(run_dir, _parse_scalar(existing_notes, "run_dir")),
            "expected_assignee": _scalar_or_existing(
                expected_assignee,
                _parse_scalar(existing_notes, "expected_assignee"),
            ),
        }
        for key, scalar in scalar_fields.items():
            if scalar:
                notes_lines.append(f"{key}: {scalar}")

    update_args: list[str] = []
    if description is not None:
        update_args += ["--description", description]
    if design_lines:
        update_args += ["--design", "\n".join(design_lines)]
    if notes_lines:
        update_args += ["--notes", "\n".join(notes_lines)]
    if done_when is not None:
        update_args += ["--acceptance-criteria", done_when]
    if not update_args:
        return show_issue(issue_id)
    return _first_issue(_json(["update", issue_id, *update_args]))


def show_issue(issue_id: str) -> dict:
    """Return the rich `br show` issue payload for one issue."""
    return _first_issue(_json(["show", issue_id]))


def issue_comments(issue_id: str) -> list[dict]:
    """Return comments when the installed `br` supports them."""
    try:
        data = _json(["comments", "list", issue_id])
    except subprocess.CalledProcessError:
        return []
    return data if isinstance(data, list) else []


def hydrate_node_contract(issue_id: str, *, include_comments: bool = True) -> dict:
    """Hydrate one Beads issue into the divide-and-conquer dispatch contract."""
    issue = show_issue(issue_id)
    if not issue:
        raise RuntimeError(f"br show returned no issue for {issue_id}")
    labels = _labels(issue)
    dependencies = issue.get("dependencies") or []
    depends_on = [
        dep.get("id") or dep.get("depends_on_id") or dep
        for dep in dependencies
        if dep
    ]
    contract = {
        "id": issue.get("id"),
        "title": issue.get("title"),
        "status": issue.get("status"),
        "assignee": issue.get("assignee"),
        "description": issue.get("description"),
        "depends_on": depends_on,
        "labels": labels,
        "concern": _label_value(labels, "concern"),
        "repo": _label_value(labels, "repo"),
        "risk_gate": _label_value(labels, "risk") or "none",
        "model_route": _parse_scalar(issue.get("notes"), "model_route"),
        "repo_path": _parse_scalar(issue.get("notes"), "repo_path"),
        "branch": _parse_scalar(issue.get("notes"), "branch"),
        "run_dir": _parse_scalar(issue.get("notes"), "run_dir"),
        "expected_assignee": _parse_scalar(issue.get("notes"), "expected_assignee"),
        "writes": _parse_list_block(issue.get("design"), "writes"),
        "stop_rules": _parse_list_block(issue.get("design"), "stop_rules"),
        "non_goals": _parse_list_block(issue.get("design"), "non_goals"),
        "global_constraints": _parse_list_block(issue.get("design"), "global_constraints"),
        "done_when": _lines_from_text(issue.get("acceptance_criteria")),
        "validate_cmds": _parse_list_block(issue.get("notes"), "validate"),
    }
    if include_comments:
        contract["comments"] = issue_comments(issue_id)
    missing = []
    if not contract["concern"]:
        missing.append("concern")
    for field in ("done_when", "validate_cmds"):
        if not contract[field]:
            missing.append(field)
    if not contract["model_route"]:
        missing.append("model_route")
    if not contract["repo_path"]:
        missing.append("repo_path")
    if not contract["branch"]:
        missing.append("branch")
    if not contract["run_dir"]:
        missing.append("run_dir")
    if not contract["expected_assignee"]:
        missing.append("expected_assignee")
    if not contract["global_constraints"]:
        missing.append("global_constraints")
    contract["dispatch_ready"] = not missing
    contract["missing_dispatch_fields"] = missing
    return contract


def render_node_brief(issue_id: str) -> str:
    """Render the worker prompt from Beads state, not from hand-written markdown."""
    contract = hydrate_node_contract(issue_id, include_comments=False)
    if not contract["dispatch_ready"]:
        missing = ", ".join(contract["missing_dispatch_fields"])
        raise RuntimeError(f"{issue_id} is not dispatch-ready; missing {missing}")

    def bullets(values: Iterable[str], *, fallback: str = "None") -> str:
        items = [str(value) for value in values if str(value).strip()]
        return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"

    return "\n".join([
        "You own one divide-and-conquer node inside an execution swarm.",
        "",
        "Source of truth: br (this brief was rendered from `br show`)",
        f"Issue ID: {contract['id']}",
        f"Repo path: {contract.get('repo_path')}",
        f"Branch/HEAD: {contract.get('branch')}",
        f"Run directory: {contract.get('run_dir') or 'n/a'}",
        f"Concern: {contract.get('concern') or 'unspecified'}",
        "Depends on:",
        bullets(contract.get("depends_on") or []),
        "Writes:",
        bullets(contract.get("writes") or []),
        "",
        "Underlying ask:",
        contract.get("description") or contract.get("title") or "",
        "",
        "Done when:",
        bullets(contract.get("done_when") or []),
        "",
        "Validate:",
        bullets(contract.get("validate_cmds") or []),
        "",
        f"Risk gate: {contract.get('risk_gate') or 'none'}",
        f"Model route: {contract.get('model_route')}",
        f"Expected Beads assignee: {contract.get('expected_assignee') or '<worker-id>'}",
        "",
        "Non-goals:",
        bullets(contract.get("non_goals") or []),
        "",
        "Stop rules:",
        bullets(contract.get("stop_rules") or []),
        "",
        "Global constraints:",
        bullets(contract.get("global_constraints") or []),
        "",
        "Rules:",
        "- export BR_AGENT_NAME=<role> BR_HARNESS=<harness> BR_MODEL=<model> before any br call",
        "- On entry: verify the lead's claim with `br show <id> --json`; do not edit until it shows `status=in_progress` and your expected assignee",
        "- Work only inside the repo and inside your declared write scope",
        "- Do not commit; the integration wave commits everything together",
        "- If you need edits outside `writes`, do NOT close the issue; report the smallest graph change needed",
        "- Run your validate commands before declaring success",
        "- On done: `br close <id> --reason \"<summary>\" --suggest-next --json`",
        "- On blocked: `br update <id> -s blocked --notes \"<reason>\"`",
        "",
    ])


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
    try:
        issues = list_issues(parent=epic, include_closed=include_closed)
    except subprocess.CalledProcessError:
        if not epic:
            raise
        # br 0.2.x does not support `br list --parent`. Fall back to
        # `br show <epic>` plus its dependent issue ids, then hydrate each
        # child with `br show` so older br versions can still render a view.
        root_data = _json(["show", epic])
        if isinstance(root_data, list):
            root = root_data[0] if root_data else {}
        else:
            root = root_data.get("issue", root_data) if isinstance(root_data, dict) else {}
        issues = [root] if root else []
        for ref in root.get("dependents", []) or []:
            child_id = ref.get("id") if isinstance(ref, dict) else ref
            if not child_id:
                continue
            child_data = _json(["show", str(child_id)])
            if isinstance(child_data, list):
                issues.extend(child_data)
            elif isinstance(child_data, dict):
                issues.append(child_data.get("issue", child_data))

    rich_issues = []
    seen: set[str] = set()
    for issue in issues:
        iid = str(issue.get("id", ""))
        if iid and iid not in seen:
            try:
                issue = {**issue, **show_issue(iid)}
            except (subprocess.CalledProcessError, RuntimeError):
                pass
            seen.add(iid)
        rich_issues.append(issue)

    lines = [
        "# WORKGRAPH (generated view)",
        "",
        "*This file is rendered from `br list --json`. Do not edit by hand —*",
        "*update via `br update`/`br close` and regenerate with `br_helpers.py render-workgraph`.*",
        "",
    ]
    for issue in rich_issues:
        iid = issue.get("id", "?")
        title = issue.get("title", "")
        status = issue.get("status", "?")
        labels = issue.get("labels", []) or []
        deps = issue.get("dependencies", []) or issue.get("depends_on", [])
        lines.append(f"- **{iid}** `{status}` — {title}")
        if issue.get("assignee"):
            lines.append(f"  assignee: {issue['assignee']}")
        if labels:
            lines.append(f"  labels: {', '.join(labels)}")
        if deps:
            dep_ids = [
                str(d.get("id") or d.get("depends_on_id") or d)
                if isinstance(d, dict)
                else str(d)
                for d in deps
            ]
            lines.append(f"  depends_on: {', '.join(dep_ids)}")
        writes = _parse_list_block(issue.get("design"), "writes")
        done_when = _lines_from_text(issue.get("acceptance_criteria"))
        validate = _parse_list_block(issue.get("notes"), "validate")
        model_route = _parse_scalar(issue.get("notes"), "model_route")
        repo_path = _parse_scalar(issue.get("notes"), "repo_path")
        branch = _parse_scalar(issue.get("notes"), "branch")
        global_constraints = _parse_list_block(issue.get("design"), "global_constraints")
        if repo_path:
            lines.append(f"  repo_path: {repo_path}")
        if branch:
            lines.append(f"  branch: {branch}")
        if writes:
            lines.append(f"  writes: {', '.join(writes)}")
        if done_when:
            lines.append(f"  done_when: {'; '.join(done_when)}")
        if validate:
            lines.append(f"  validate: {'; '.join(validate)}")
        if model_route:
            lines.append(f"  model_route: {model_route}")
        if global_constraints:
            lines.append(f"  global_constraints: {'; '.join(global_constraints)}")
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
    sp.add_argument("--description")
    sp.add_argument("--concern")
    sp.add_argument("--repo")
    sp.add_argument("--writes", action="append", default=[])
    sp.add_argument("--done-when")
    sp.add_argument("--validate", action="append", default=[])
    sp.add_argument("--risk", default="none")
    sp.add_argument("--model-route")
    sp.add_argument("--repo-path")
    sp.add_argument("--branch")
    sp.add_argument("--run-dir")
    sp.add_argument("--stop-rule", action="append", default=[], dest="stop_rules")
    sp.add_argument("--non-goal", action="append", default=[], dest="non_goals")
    sp.add_argument("--global-constraint", action="append", default=[], dest="global_constraints")
    sp.add_argument("--expected-assignee")
    sp.add_argument("--depends-on", action="append", default=[])
    sp.add_argument("--epic")
    sp.add_argument("--priority", type=int, default=2)
    sp.add_argument("--type", default="task", dest="issue_type")
    sp.add_argument("--label", action="append", default=[], dest="labels")

    sp = sub.add_parser("update-node")
    sp.add_argument("id")
    sp.add_argument("--description")
    sp.add_argument("--writes", action="append", default=[])
    sp.add_argument("--done-when")
    sp.add_argument("--validate", action="append", default=[])
    sp.add_argument("--model-route")
    sp.add_argument("--repo-path")
    sp.add_argument("--branch")
    sp.add_argument("--run-dir")
    sp.add_argument("--stop-rule", action="append", default=[], dest="stop_rules")
    sp.add_argument("--non-goal", action="append", default=[], dest="non_goals")
    sp.add_argument("--global-constraint", action="append", default=[], dest="global_constraints")
    sp.add_argument("--expected-assignee")

    sp = sub.add_parser("hydrate-node")
    sp.add_argument("id")
    sp.add_argument("--no-comments", action="store_true")

    sp = sub.add_parser("render-node-brief")
    sp.add_argument("id")
    sp.add_argument("--out", default="-")

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
            description=args.description,
            concern=args.concern,
            repo=args.repo,
            writes=args.writes,
            done_when=args.done_when,
            validate=args.validate,
            risk=args.risk,
            model_route=args.model_route,
            repo_path=args.repo_path,
            branch=args.branch,
            run_dir=args.run_dir,
            stop_rules=args.stop_rules,
            non_goals=args.non_goals,
            global_constraints=args.global_constraints,
            expected_assignee=args.expected_assignee,
            depends_on=args.depends_on,
            epic=args.epic,
            priority=args.priority,
            issue_type=args.issue_type,
            labels=args.labels,
        )})
    elif args.cmd == "update-node":
        _emit(update_node_contract(
            args.id,
            description=args.description,
            writes=args.writes,
            done_when=args.done_when,
            validate=args.validate,
            model_route=args.model_route,
            repo_path=args.repo_path,
            branch=args.branch,
            run_dir=args.run_dir,
            stop_rules=args.stop_rules,
            non_goals=args.non_goals,
            global_constraints=args.global_constraints,
            expected_assignee=args.expected_assignee,
        ))
    elif args.cmd == "hydrate-node":
        _emit(hydrate_node_contract(args.id, include_comments=not args.no_comments))
    elif args.cmd == "render-node-brief":
        rendered = render_node_brief(args.id)
        if args.out == "-":
            sys.stdout.write(rendered)
        else:
            Path(args.out).write_text(rendered)
            _emit({"wrote": args.out, "bytes": len(rendered)})
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
