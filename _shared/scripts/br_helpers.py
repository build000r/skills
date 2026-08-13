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
  br_helpers.py ready --plan {slug} --require-handoff-ready
                                                    # accepted no-ragrets intake
  br_helpers.py scheduler [--limit N]               # `br scheduler --json`
  br_helpers.py mint-node exec-001-backend-api 'Backend API' \\
      --concern backend-api --repo backend \\
      --writes 'src/domain/**' --done-when '...' \\
      --validate 'npm test' --risk none \\
      --depends-on br-exec-000-... [--epic br-epic-...]
  br_helpers.py mint-subgoal auth-hardening 'Subgoal: auth hardening' \\
      --slice {slice-slug} --writes 'backend/auth/**' \\
      --shared-file 'backend/migrations/**' --max-workers 3
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
import fnmatch
import json
import os
import re
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

# ---- accepted no-ragrets plan vocabulary (see ../references/beads-contract.md) ----
# `no-ragrets` owns the planning graph and stamps these labels; this helper is the
# consumer side. Only the dispatchable roles may ever enter an execution frontier.
PLAN_LABEL_PREFIX = "plan"
PLAN_ROLE_PREFIX = "plan-role"
PLAN_STATE_PREFIX = "plan-state"
PLAN_EVIDENCE_PREFIX = "plan-evidence"
PLAN_ROOT_ROLE = "root"
PLAN_HANDOFF_STATE = "handoff-ready"
PLAN_DISPATCHABLE_ROLES = ("execution-leaf", "integration", "review")
PLAN_GROUPING_ROLES = ("root", "branch")
PLAN_HISTORICAL_ROLES = ("historical-evidence",)
PLAN_HISTORICAL_EVIDENCE = "historical-only"
PLAN_NOTE_SCALARS = ("planning_parent", "supports", "local_criteria", "produces")
PLAN_ROOT_NOTE_SCALARS = ("synthesis_receipt", "plan_score", "hard_gate_result")

# Values that look filled in but carry no invocation-specific meaning. An accepted
# plan is written before a swarm exists, so `run_dir`/`expected_assignee` are the
# two fields that must be hydrated at admission time rather than trusted as-is.
_PLACEHOLDER_TOKENS = frozenset({
    "tbd", "tba", "todo", "none", "null", "nil", "n/a", "na", "unknown",
    "unassigned", "placeholder", "pending", "fixme", "xxx", "example",
    "worker", "worker-id", "agent", "someone", "?", "-",
})
_PLACEHOLDER_SHAPE = re.compile(r"<[^>]*>|\{[^}]*\}|\$\{?[A-Z_][A-Z0-9_]*\}?|\.\.\.")


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


def _label_values(labels: Iterable[str], prefix: str) -> list[str]:
    """Every value carried under one label prefix (roles can be duplicated)."""
    marker = f"{prefix}:"
    return [label[len(marker):] for label in labels if label.startswith(marker)]


def _is_placeholder(value: Optional[str]) -> bool:
    """True when a field is blank or a template stand-in rather than a real value."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    if _PLACEHOLDER_SHAPE.search(text):
        return True
    return text.strip("`'\"").lower() in _PLACEHOLDER_TOKENS


def _normalize_scope(scope: str) -> str:
    text = str(scope).strip().strip("'\"")
    if text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def _scopes_overlap(left: str, right: str) -> bool:
    """Conservative write-scope collision test over exact paths and globs.

    Fails loud rather than silent: `fnmatch` treats `*` as matching `/` too, so a
    glob such as `skill/**` is reported as overlapping `skill/SKILL.md`. Directory
    containment is checked separately because plain prefixes carry no wildcard.
    """
    a = _normalize_scope(left)
    b = _normalize_scope(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    return a.startswith(f"{b}/") or b.startswith(f"{a}/")


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


# ------------------- accepted no-ragrets plan intake (read) -------------------


def _rejection(issue_id: Optional[str], reason: str, detail: str, repair: str) -> dict:
    """One machine-readable admission failure that says how to repair itself."""
    return {"id": issue_id, "reason": reason, "detail": detail, "repair": repair}


def _split_ids(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,\s]+", str(value)) if part.strip()]


def _plan_node_view(issue: dict) -> dict:
    """Project one Beads issue onto the canonical plan vocabulary."""
    labels = _labels(issue)
    notes = issue.get("notes")
    view = {
        "id": issue.get("id"),
        "title": issue.get("title"),
        "status": issue.get("status"),
        "labels": labels,
        "plan": _label_value(labels, PLAN_LABEL_PREFIX),
        "roles": _label_values(labels, PLAN_ROLE_PREFIX),
        "plan_state": _label_value(labels, PLAN_STATE_PREFIX),
        "plan_evidence": _label_value(labels, PLAN_EVIDENCE_PREFIX),
    }
    for key in (*PLAN_NOTE_SCALARS, *PLAN_ROOT_NOTE_SCALARS):
        view[key] = _parse_scalar(notes, key)
    return view


def _is_historical(view: dict) -> bool:
    """Historical-evidence nodes are read-only provenance, never executable work."""
    if view.get("plan_evidence") == PLAN_HISTORICAL_EVIDENCE:
        return True
    return any(role in PLAN_HISTORICAL_ROLES for role in view.get("roles") or [])


def _hydrate_plan_node(issue: dict) -> dict:
    """Merge `br show` rich fields into a thin `br list`/`br ready` row.

    `br ready --json` rows carry neither `labels` nor `notes` on some versions,
    so a label check against the raw row would silently drop every node.
    """
    issue_id = str(issue.get("id") or "")
    if not issue_id or ("labels" in issue and "notes" in issue):
        return issue
    try:
        return {**issue, **show_issue(issue_id)}
    except (subprocess.CalledProcessError, RuntimeError, json.JSONDecodeError):
        return issue


def _admit_plan_node(view: dict) -> tuple[Optional[dict], Optional[dict]]:
    """Return (admitted_contract, rejection) for one ready plan node.

    Role filtering uses OR semantics here in helper code rather than repeated
    `br ready --label` flags, because `br`'s multi-label behavior is not proven
    to be AND across versions and the allowed roles are alternatives, not a
    conjunction.
    """
    issue_id = view["id"]
    roles = [role for role in view.get("roles") or []]
    if not roles:
        return None, _rejection(
            issue_id,
            "plan_role_missing",
            "ready plan node carries no plan-role:* label",
            f"br update {issue_id} --labels plan-role:execution-leaf "
            "(or plan-role:branch to keep it non-dispatchable)",
        )
    if len(set(roles)) > 1:
        return None, _rejection(
            issue_id,
            "plan_role_ambiguous",
            f"multiple plan-role labels: {', '.join(sorted(set(roles)))}",
            f"remove the extra plan-role:* labels from {issue_id} so exactly one remains",
        )
    role = roles[0]
    if role in PLAN_GROUPING_ROLES:
        return None, _rejection(
            issue_id,
            "plan_role_not_dispatchable",
            f"plan-role:{role} is a grouping node but is in the ready frontier",
            f"make {issue_id} non-dispatchable (epic/grouping shape or a blocking "
            "dependency on its children); grouping nodes never dispatch",
        )
    if role not in PLAN_DISPATCHABLE_ROLES:
        return None, _rejection(
            issue_id,
            "plan_role_unknown",
            f"plan-role:{role} is not a canonical role",
            f"relabel {issue_id} with one of "
            + ", ".join(f"plan-role:{allowed}" for allowed in PLAN_DISPATCHABLE_ROLES),
        )

    try:
        contract = hydrate_node_contract(issue_id, include_comments=False)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        return None, _rejection(
            issue_id,
            "hydration_failed",
            f"br show could not hydrate the node: {exc}",
            f"verify {issue_id} exists and `br show {issue_id} --json` returns an issue",
        )
    if not contract.get("concern"):
        return None, _rejection(
            issue_id,
            "concern_label_missing",
            "admitted nodes must carry at least one concern:* label",
            f"br update {issue_id} --labels concern:<slug>",
        )
    if not contract["dispatch_ready"]:
        missing = ", ".join(contract["missing_dispatch_fields"])
        return None, _rejection(
            issue_id,
            "hydration_incomplete",
            f"missing dispatch fields: {missing}",
            f"python3 br_helpers.py update-node {issue_id} "
            "--run-dir <absolute-run-dir> --expected-assignee <worker-id> "
            "--repo-path <repo> --branch <branch> --model-route <route> "
            "--validate <cmd> --done-when <check> --global-constraint <rule>",
        )
    if _is_placeholder(contract.get("run_dir")) or not str(contract["run_dir"]).startswith("/"):
        return None, _rejection(
            issue_id,
            "run_dir_placeholder",
            f"run_dir is not an invocation-specific absolute path: {contract.get('run_dir')!r}",
            f"python3 br_helpers.py update-node {issue_id} --run-dir "
            "{invocation_root}/{repo_slug}/divide-and-conquer/{run_id}",
        )
    if _is_placeholder(contract.get("expected_assignee")):
        return None, _rejection(
            issue_id,
            "expected_assignee_placeholder",
            f"expected_assignee is not a concrete worker: {contract.get('expected_assignee')!r}",
            f"python3 br_helpers.py update-node {issue_id} --expected-assignee <worker-id>",
        )

    admitted = dict(contract)
    admitted["plan_role"] = role
    for key in PLAN_NOTE_SCALARS:
        admitted[key] = view.get(key)
    return admitted, None


def _serialize_write_scopes(
    admitted: list[dict],
    *,
    materialize: bool = False,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split an admitted frontier into a concurrently-safe set plus deferrals.

    Ready siblings cannot already be ordered by `br` (an open dependency would
    keep them out of the frontier), so any declared write-scope collision between
    two ready nodes is unsafe concurrency. We materialize the ordering edge and
    defer the later node instead of dispatching both.
    """
    concurrent: list[dict] = []
    deferred: list[dict] = []
    edges: list[dict] = []
    for candidate in admitted:
        conflict = None
        for accepted in concurrent:
            overlap = [
                [left, right]
                for left in candidate.get("writes") or []
                for right in accepted.get("writes") or []
                if _scopes_overlap(left, right)
            ]
            if overlap:
                conflict = (accepted, overlap)
                break
        if conflict is None:
            concurrent.append(candidate)
            continue
        accepted, overlap = conflict
        edge = {
            "blocked": candidate["id"],
            "blocked_by": accepted["id"],
            "overlapping_writes": overlap,
            "repair": f"br dep add {candidate['id']} {accepted['id']}",
            "materialized": False,
        }
        if materialize:
            try:
                _run(["dep", "add", candidate["id"], accepted["id"]], capture=True)
                edge["materialized"] = True
            except subprocess.CalledProcessError as exc:
                edge["error"] = f"br dep add failed (exit {exc.returncode})"
        edges.append(edge)
        deferred.append({
            "id": candidate["id"],
            "plan_role": candidate.get("plan_role"),
            "reason": "write_scope_overlap",
            "detail": f"declared writes collide with {accepted['id']}: {overlap}",
            "repair": edge["repair"],
        })
    return concurrent, deferred, edges


def plan_admission(
    plan_slug: str,
    *,
    limit: int = 20,
    require_handoff_ready: bool = True,
    materialize_serialization: bool = False,
) -> dict:
    """Intake an accepted `no-ragrets` graph without reminting or flattening it.

    Consumes the producer contract documented in
    `../references/beads-contract.md`: exactly one `plan:{slug}` root labeled
    `plan-role:root` and `plan-state:handoff-ready`, then dispatches only ready
    `plan-role:execution-leaf`, `plan-role:integration`, and `plan-role:review`
    nodes. Everything else becomes a machine-readable rejection carrying its own
    repair instruction. This helper never creates, closes, or relabels plan
    nodes; the existing epic and its children are reused as-is.
    """
    plan_label = f"{PLAN_LABEL_PREFIX}:{plan_slug}"
    result: dict[str, Any] = {
        "plan": plan_slug,
        "plan_label": plan_label,
        "require_handoff_ready": require_handoff_ready,
        "root": None,
        "plan_state": None,
        "handoff_ready": False,
        "admitted": [],
        "deferred": [],
        "serialization_edges": [],
        "excluded_historical": [],
        "rejected": [],
        "coverage": {"declared": [], "covered": [], "uncovered": [], "by_criterion": {}},
        "ok": False,
    }
    try:
        raw_nodes = list_issues(labels=[plan_label])
    except subprocess.CalledProcessError as exc:
        result["rejected"].append(_rejection(
            None,
            "plan_query_failed",
            f"br list --label {plan_label} failed (exit {exc.returncode})",
            f"verify the plan label exists: br list --label {plan_label} --json",
        ))
        return result

    # Defensive helper-side filter: some `br` versions OR label filters.
    views = [
        _plan_node_view(_hydrate_plan_node(issue))
        for issue in raw_nodes
        if plan_label in _labels(issue)
    ]
    by_id = {view["id"]: view for view in views}

    roots = [view for view in views if PLAN_ROOT_ROLE in (view.get("roles") or [])]
    if not roots:
        result["rejected"].append(_rejection(
            None,
            "plan_root_missing",
            f"no issue labeled {plan_label} carries plan-role:root",
            f"label the accepted epic with {plan_label} and plan-role:root, "
            "or re-run no-ragrets synthesis before handoff",
        ))
    elif len(roots) > 1:
        result["rejected"].append(_rejection(
            None,
            "plan_root_duplicate",
            "multiple accepted roots: " + ", ".join(sorted(str(r["id"]) for r in roots)),
            "keep exactly one plan-role:root for this plan and demote the rest to "
            "plan-role:branch",
        ))
    else:
        root = roots[0]
        result["root"] = root
        result["plan_state"] = root.get("plan_state")
        result["handoff_ready"] = root.get("plan_state") == PLAN_HANDOFF_STATE
        if require_handoff_ready and not result["handoff_ready"]:
            result["rejected"].append(_rejection(
                root["id"],
                "plan_state_not_handoff_ready",
                "root plan-state is "
                f"{root.get('plan_state') or 'unset'}, expected {PLAN_HANDOFF_STATE}",
                "finish no-ragrets synthesis, prove grouping nodes cannot dispatch, "
                f"then set plan-state:{PLAN_HANDOFF_STATE} on {root['id']}",
            ))

    try:
        frontier = ready_frontier(limit=limit, labels=[plan_label])
    except subprocess.CalledProcessError as exc:
        result["rejected"].append(_rejection(
            None,
            "plan_frontier_query_failed",
            f"br ready --label {plan_label} failed (exit {exc.returncode})",
            f"verify readiness directly: br ready --label {plan_label} --json",
        ))
        frontier = []

    admitted: list[dict] = []
    for issue in frontier:
        # `br ready` already applied dependency readiness; only role/hydration
        # filtering happens here so we never widen the frontier. Resolve the
        # label-bearing view first: ready rows can be thin, so filtering on the
        # raw row would drop the whole frontier.
        view = by_id.get(issue.get("id")) or _plan_node_view(_hydrate_plan_node(issue))
        if plan_label not in (view.get("labels") or []):
            continue
        if _is_historical(view):
            result["excluded_historical"].append({
                "id": view["id"],
                "reason": "historical_evidence_never_dispatches",
                "roles": view.get("roles"),
                "plan_evidence": view.get("plan_evidence"),
            })
            continue
        node, rejection = _admit_plan_node(view)
        if rejection is not None:
            result["rejected"].append(rejection)
            continue
        admitted.append(node)

    # A strict handoff request is an execution gate, not merely a diagnostic.
    # Never expose dispatchable work when the accepted root is absent, duplicate,
    # or not handoff-ready; callers that intentionally inspect drafts must opt in
    # through require_handoff_ready=False / --allow-draft-plan.
    if require_handoff_ready and not result["handoff_ready"]:
        admitted = []
    concurrent, deferred, edges = _serialize_write_scopes(
        admitted, materialize=materialize_serialization
    )
    result["admitted"] = concurrent
    result["deferred"] = deferred
    result["serialization_edges"] = edges

    # Criterion coverage deliberately ignores historical-evidence nodes so a
    # criterion "covered" only by past proof still reads as uncovered.
    live = [view for view in views if not _is_historical(view)]
    root_view = result["root"]
    declared: list[str] = []
    if root_view and root_view.get("local_criteria"):
        declared = _split_ids(root_view["local_criteria"])
    else:
        seen: list[str] = []
        for view in views:
            for criterion in _split_ids(view.get("supports")):
                if criterion not in seen:
                    seen.append(criterion)
        declared = seen
    by_criterion: dict[str, list[str]] = {criterion: [] for criterion in declared}
    for view in live:
        if root_view and view["id"] == root_view["id"]:
            continue
        for criterion in _split_ids(view.get("supports")):
            by_criterion.setdefault(criterion, [])
            if view["id"] not in by_criterion[criterion]:
                by_criterion[criterion].append(view["id"])
    covered = [criterion for criterion in declared if by_criterion.get(criterion)]
    uncovered = [criterion for criterion in declared if not by_criterion.get(criterion)]
    result["coverage"] = {
        "declared": declared,
        "covered": covered,
        "uncovered": uncovered,
        "by_criterion": by_criterion,
    }

    result["ok"] = not result["rejected"]
    return result


# ----------------------------- write paths -----------------------------


def _create_issue(
    *,
    slug: str,
    title: str,
    issue_type: str,
    priority: int,
    labels: Iterable[str],
    epic: Optional[str] = None,
) -> str:
    """`br create` with the small flag set it accepts, returning the new ID.

    Rich fields like --design, --notes, and --acceptance-criteria are
    update-only, so callers create first and flow the rest through `br update`.
    """
    create_args = [
        "create",
        title,
        "--slug", slug,
        "--type", issue_type,
        "--priority", str(priority),
        "--labels", ",".join(labels),
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
    return issue_id


def _add_dependencies(issue_id: str, depends_on: Iterable[str]) -> None:
    """Add each dependency edge; a failed edge must not lose the minted issue.

    Accepts both repeated flags and comma-joined lists because `br dep add`
    takes exactly one dependency per call.
    """
    dep_ids = [d.strip() for entry in depends_on for d in str(entry).split(",") if d.strip()]
    for parent in dep_ids:
        try:
            # capture=True so `br dep add` chatter does not pollute our stdout
            # JSON envelope when this helper is invoked from a shell pipeline.
            _run(["dep", "add", issue_id, parent], capture=True)
        except subprocess.CalledProcessError as exc:
            print(
                f"warning: {issue_id} minted but dep edge on {parent!r} failed "
                f"(exit {exc.returncode}); repair with: br dep add {issue_id} {parent}",
                file=sys.stderr,
            )


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
        # br labels allow only [A-Za-z0-9_:-]. Paths passed as --repo would
        # fail validation mid-mint, so slugify: keep the basename and map
        # any remaining invalid characters to '-'.
        repo_slug = re.sub(r"[^A-Za-z0-9_:-]", "-", repo.rstrip("/").rsplit("/", 1)[-1])
        label_list.append(f"repo:{repo_slug}")
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

    issue_id = _create_issue(
        slug=slug,
        title=title,
        issue_type=issue_type,
        priority=priority,
        labels=label_list,
        epic=epic,
    )

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

    _add_dependencies(issue_id, depends_on)
    if not (branch and expected_assignee and global_constraints):
        print(
            f"note: {issue_id} is not dispatch-ready yet; render-node-brief requires "
            "branch, expected_assignee, and global_constraints (backfill via update-node)",
            file=sys.stderr,
        )
    return issue_id


def mint_subgoal(
    slug: str,
    title: str,
    *,
    slice_slug: str,
    description: Optional[str] = None,
    writes: Iterable[str] = (),
    shared_files: Iterable[str] = (),
    stop_rules: Iterable[str] = (),
    escalation: Iterable[str] = (),
    parent_run_dir: Optional[str] = None,
    subgoal_run_dir: Optional[str] = None,
    frontier_filter: Optional[str] = None,
    child_orchestrator: Optional[str] = None,
    ntm_project: Optional[str] = None,
    max_workers: Optional[int] = None,
    max_subgoal_depth: Optional[int] = None,
    isolation: str = "checkout",
    status_artifact: Optional[str] = None,
    done_when: Optional[str] = None,
    depends_on: Iterable[str] = (),
    epic: Optional[str] = None,
    priority: int = 1,
    labels: Iterable[str] = (),
) -> str:
    """Create a durable subgoal **controller** issue and return its ID.

    Controllers are delegation boundaries, not executable leaves: they carry the
    subgoal's outer write scope, root-owned shared files, frontier filter, and
    run directories. Leaves inside the subgoal are ordinary `mint_node` calls
    plus `subgoal:{slug}` / `subgoal-role:leaf` labels. Field mapping lives in
    `../references/beads-contract.md` under "Subgoal Controller Field Mapping".
    """
    label_list = [
        f"slice:{slice_slug}",
        f"subgoal:{slug}",
        "subgoal-role:controller",
        *labels,
    ]
    design_lines: list[str] = []
    _append_block(design_lines, "writes", writes)
    _append_block(design_lines, "shared_files", shared_files)
    _append_block(design_lines, "stop_rules", stop_rules)
    _append_block(design_lines, "escalation", escalation)
    notes_lines: list[str] = [f"subgoal_id: {slug}", f"parent_slice: {slice_slug}"]
    scalars = {
        "parent_run_dir": parent_run_dir,
        "subgoal_run_dir": subgoal_run_dir,
        "frontier_filter": frontier_filter or f"slice:{slice_slug},subgoal:{slug}",
        "child_orchestrator": child_orchestrator,
        "ntm_project": ntm_project,
        "max_workers": max_workers,
        "max_subgoal_depth": max_subgoal_depth,
        "isolation": isolation,
        "status_artifact": status_artifact,
    }
    for key, value in scalars.items():
        if value is not None and str(value).strip():
            notes_lines.append(f"{key}: {value}")

    issue_id = _create_issue(
        slug=f"subgoal-{slug}",
        title=title,
        issue_type="task",
        priority=priority,
        labels=label_list,
        epic=epic,
    )

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

    _add_dependencies(issue_id, depends_on)
    if not writes:
        print(
            f"note: {issue_id} has no declared subgoal writes; the root cannot prove "
            "cohort write isolation until `writes:` is set (backfill via br update --design)",
            file=sys.stderr,
        )
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
        "completion_protocol": _parse_list_block(issue.get("design"), "completion_protocol"),
        "worker_write_authority": _parse_list_block(issue.get("design"), "worker_write_authority"),
        "apply_step_json": _parse_list_block(issue.get("design"), "apply_step_json"),
        "close_step_json": _parse_list_block(issue.get("design"), "close_step_json"),
        "transaction_driver": _parse_scalar(issue.get("design"), "transaction_driver"),
        "patch_artifact": _parse_scalar(issue.get("design"), "patch_artifact"),
        "result_artifact": _parse_scalar(issue.get("design"), "result_artifact"),
        "apply_receipt": _parse_scalar(issue.get("design"), "apply_receipt"),
        "apply_log": _parse_scalar(issue.get("design"), "apply_log"),
        "close_receipt": _parse_scalar(issue.get("design"), "close_receipt"),
        "close_log": _parse_scalar(issue.get("design"), "close_log"),
        "policy_home": _parse_scalar(issue.get("design"), "policy_home"),
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

    protected_completion = bool(contract.get("transaction_driver") and contract.get("close_step_json"))
    completion_rules = (
        [
            "- Do not call `br close` or `br update` directly; follow the protected completion contract above through its transaction driver",
            *(
                [
                    "- Pass validation only through the rendered apply step JSON to the transaction driver; never execute apply step JSON or close step JSON directly",
                    "- Invoke the transaction driver in apply mode with the rendered repo, patch, policy home, apply receipt/log, close receipt/log, declared write targets, current base OID, and every rendered step JSON",
                ]
                if contract.get("apply_step_json")
                else [
                    "- Invoke the transaction driver with `--close-only` and the rendered close step/receipt/log; never execute close step JSON directly",
                ]
            ),
            "- On any apply, validation, receipt, release, recovery, or close failure: stop without retrying mutation or closing the node and report the exact artifact",
        ]
        if protected_completion
        else [
            "- On done: `br close <id> --reason \"<summary>\" --suggest-next --json`",
            "- On blocked: `br update <id> -s blocked --notes \"<reason>\"`",
        ]
    )
    protected_lines = []
    if protected_completion:
        protected_lines = [
            "",
            "Protected completion contract:",
            f"Transaction driver: {contract.get('transaction_driver') or 'None'}",
            f"Patch artifact: {contract.get('patch_artifact') or 'None'}",
            f"Result artifact: {contract.get('result_artifact') or 'None'}",
            f"Policy home: {contract.get('policy_home') or 'None'}",
            f"Apply receipt: {contract.get('apply_receipt') or 'None'}",
            f"Apply log: {contract.get('apply_log') or 'None'}",
            f"Close receipt: {contract.get('close_receipt') or 'None'}",
            f"Close log: {contract.get('close_log') or 'None'}",
            "Worker write authority:",
            bullets(contract.get("worker_write_authority") or []),
            "Apply step JSON:",
            bullets(contract.get("apply_step_json") or []),
            "Close step JSON:",
            bullets(contract.get("close_step_json") or []),
            "Completion protocol:",
            bullets(contract.get("completion_protocol") or []),
        ]

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
        *protected_lines,
        "",
        "Rules:",
        "- export BR_AGENT_NAME=<role> BR_HARNESS=<harness> BR_MODEL=<model> before any br call",
        "- On entry: verify the lead's claim with `br show <id> --json`; do not edit until it shows `status=in_progress` and your expected assignee",
        "- Work only inside the repo and inside your declared write scope",
        "- Do not commit; the integration wave commits everything together",
        "- If you need edits outside `writes`, do NOT close the issue; report the smallest graph change needed",
        *( [] if protected_completion else ["- Run your validate commands before declaring success"] ),
        *completion_rules,
        "",
    ])


def claim(issue_id: str) -> dict:
    """Atomic claim: assignee=actor + status=in_progress.

    Some br versions resolve `--claim` to the system user instead of
    BR_AGENT_NAME, so enforce the intended assignee explicitly afterwards.
    """
    proc = _run(["update", issue_id, "--claim", "--json"])
    agent = os.environ.get("BR_AGENT_NAME")
    if agent:
        _run(["update", issue_id, "--assignee", agent, "--json"], check=False)
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

    # A no-ragrets plan can intentionally consume an issue whose ownership
    # parent remains another epic.  Intake scopes those nodes by the canonical
    # plan label, so the generated workgraph must use the same union rather than
    # silently omitting an external consumer from the handoff view.
    if epic:
        root = next((item for item in issues if str(item.get("id")) == epic), None)
        if root is None:
            try:
                root = show_issue(epic)
            except (subprocess.CalledProcessError, RuntimeError):
                root = None
        plan_labels = [
            label for label in ((root or {}).get("labels") or [])
            if str(label).startswith(f"{PLAN_LABEL_PREFIX}:")
        ]
        if len(plan_labels) == 1:
            try:
                issues.extend(list_issues(labels=(plan_labels[0],), include_closed=include_closed))
            except subprocess.CalledProcessError:
                pass

    rich_issues = []
    seen: set[str] = set()
    for issue in issues:
        iid = str(issue.get("id", ""))
        if iid and iid in seen:
            continue
        if iid:
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
    sp.add_argument(
        "--plan",
        help="Accepted no-ragrets plan slug; switches ready into plan-intake mode",
    )
    sp.add_argument(
        "--require-handoff-ready",
        action="store_true",
        help="Reassert the default plan-state:handoff-ready gate (fails closed anyway)",
    )
    sp.add_argument(
        "--allow-draft-plan",
        action="store_true",
        help="Inspect a draft/synthesized plan without enforcing the handoff gate",
    )
    sp.add_argument(
        "--materialize-serialization",
        action="store_true",
        help="Run `br dep add` for write-scope collisions instead of only proposing them",
    )

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

    sp = sub.add_parser(
        "mint-subgoal",
        help="Create a durable subgoal controller issue (delegation boundary, not a leaf)",
    )
    sp.add_argument("slug")
    sp.add_argument("title")
    sp.add_argument("--slice", required=True, dest="slice_slug")
    sp.add_argument("--description")
    sp.add_argument("--writes", action="append", default=[])
    sp.add_argument("--shared-file", action="append", default=[], dest="shared_files")
    sp.add_argument("--stop-rule", action="append", default=[], dest="stop_rules")
    sp.add_argument("--escalation", action="append", default=[])
    sp.add_argument("--parent-run-dir")
    sp.add_argument("--subgoal-run-dir")
    sp.add_argument("--frontier-filter")
    sp.add_argument("--child-orchestrator")
    sp.add_argument("--ntm-project")
    sp.add_argument("--max-workers", type=int)
    sp.add_argument("--max-subgoal-depth", type=int)
    sp.add_argument("--isolation", default="checkout", choices=["checkout", "worktree"])
    sp.add_argument("--status-artifact")
    sp.add_argument("--done-when")
    sp.add_argument("--depends-on", action="append", default=[])
    sp.add_argument("--epic")
    sp.add_argument("--priority", type=int, default=1)
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
        if args.plan:
            if args.require_handoff_ready and args.allow_draft_plan:
                p.error("--require-handoff-ready and --allow-draft-plan are mutually exclusive")
            admission = plan_admission(
                args.plan,
                limit=args.limit,
                require_handoff_ready=not args.allow_draft_plan,
                materialize_serialization=args.materialize_serialization,
            )
            _emit(admission)
            # Non-zero so a shell gate cannot mistake a rejected plan for a
            # dispatchable frontier. Generic (non-plan) `ready` still exits 0.
            return 0 if admission["ok"] else 2
        if args.require_handoff_ready or args.allow_draft_plan or args.materialize_serialization:
            p.error("--require-handoff-ready/--allow-draft-plan/--materialize-serialization require --plan")
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
    elif args.cmd == "mint-subgoal":
        _emit({"id": mint_subgoal(
            slug=args.slug,
            title=args.title,
            slice_slug=args.slice_slug,
            description=args.description,
            writes=args.writes,
            shared_files=args.shared_files,
            stop_rules=args.stop_rules,
            escalation=args.escalation,
            parent_run_dir=args.parent_run_dir,
            subgoal_run_dir=args.subgoal_run_dir,
            frontier_filter=args.frontier_filter,
            child_orchestrator=args.child_orchestrator,
            ntm_project=args.ntm_project,
            max_workers=args.max_workers,
            max_subgoal_depth=args.max_subgoal_depth,
            isolation=args.isolation,
            status_artifact=args.status_artifact,
            done_when=args.done_when,
            depends_on=args.depends_on,
            epic=args.epic,
            priority=args.priority,
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
