#!/usr/bin/env python3
"""Validate and filter a canonical no-ragrets Beads plan frontier."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


PLAN_PREFIX = "plan:"
ROLE_PREFIX = "plan-role:"
STATE_PREFIX = "plan-state:"
ROOT_ROLE = "plan-role:root"
BRANCH_ROLE = "plan-role:branch"
GROUPING_ROLES = {ROOT_ROLE, BRANCH_ROLE}
DISPATCHABLE_ROLES = {
    "plan-role:execution-leaf",
    "plan-role:integration",
    "plan-role:review",
}
ALLOWED_ROLES = GROUPING_ROLES | DISPATCHABLE_ROLES
ALLOWED_ROOT_STATES = {
    "plan-state:draft",
    "plan-state:synthesized",
    "plan-state:handoff-ready",
}
HANDOFF_READY = "plan-state:handoff-ready"
CANONICAL_NOTE_FIELDS = (
    "planning_parent",
    "supports",
    "local_criteria",
    "produces",
)


def unwrap_issues(payload: object, source: str) -> list[dict[str, Any]]:
    """Accept both `br list` envelopes and `br ready` arrays."""
    if isinstance(payload, dict):
        payload = payload.get("issues")
    if not isinstance(payload, list):
        raise ValueError(f"{source} must be an issue array or an object with .issues")
    if not all(isinstance(issue, dict) for issue in payload):
        raise ValueError(f"{source} contains a non-object issue")
    return payload


def _labels(issue: dict[str, Any], defects: list[str]) -> list[str]:
    issue_id = issue.get("id", "<unknown>")
    labels = issue.get("labels")
    if not isinstance(labels, list) or not all(
        isinstance(label, str) for label in labels
    ):
        defects.append(f"{issue_id}: labels must be a string array")
        return []
    return labels


def _prefixed(labels: list[str], prefix: str) -> list[str]:
    return [label for label in labels if label.startswith(prefix)]


def _parse_notes(
    issue: dict[str, Any], defects: list[str]
) -> dict[str, str | None]:
    issue_id = issue.get("id", "<unknown>")
    notes = issue.get("notes")
    if not isinstance(notes, str):
        defects.append(f"{issue_id}: notes must be a string")
        notes = ""

    parsed: dict[str, str | None] = {}
    lines = notes.splitlines()
    for field in CANONICAL_NOTE_FIELDS:
        prefix = f"{field}:"
        values = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
        if not values:
            defects.append(f"{issue_id}: missing canonical notes field {field}")
            parsed[field] = None
        elif len(values) > 1:
            defects.append(f"{issue_id}: duplicate canonical notes field {field}")
            parsed[field] = None
        elif not values[0]:
            defects.append(f"{issue_id}: empty canonical notes field {field}")
            parsed[field] = None
        else:
            parsed[field] = values[0]
    return parsed


def _append_once(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _hierarchy_defects(
    issues_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, str | None],
    metadata_by_id: dict[str, dict[str, str | None]],
    root_id: str | None,
) -> list[str]:
    defects: list[str] = []
    parent_by_id = {
        issue_id: metadata.get("planning_parent")
        for issue_id, metadata in metadata_by_id.items()
    }

    if root_id is not None and parent_by_id.get(root_id) != "none":
        defects.append(f"{root_id}: root planning_parent must be none")

    for issue_id, parent_id in parent_by_id.items():
        if issue_id == root_id or parent_id is None:
            continue
        if parent_id == "none":
            defects.append(f"{issue_id}: non-root planning_parent must name an issue")
        elif parent_id == issue_id:
            defects.append(f"{issue_id}: planning_parent cannot reference itself")
        elif parent_id not in issues_by_id:
            defects.append(
                f"{issue_id}: planning_parent {parent_id} is outside the scoped plan"
            )

    cycle_signatures: set[tuple[str, ...]] = set()
    for start in parent_by_id:
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current in parent_by_id and current != "none":
            if current in positions:
                cycle = path[positions[current] :]
                signature = tuple(sorted(cycle))
                if signature not in cycle_signatures:
                    cycle_signatures.add(signature)
                    defects.append(
                        "planning_parent cycle: " + " -> ".join(cycle + [current])
                    )
                break
            positions[current] = len(path)
            path.append(current)
            current = parent_by_id.get(current)

    for issue_id, role in roles_by_id.items():
        if role in GROUPING_ROLES:
            issue_type = issues_by_id[issue_id].get("issue_type")
            if issue_type != "epic":
                defects.append(
                    f"{issue_id}: grouping role {role} requires issue_type epic"
                )
    return defects


def intake_plan(
    issues_payload: object,
    ready_payload: object,
    plan: str,
) -> dict[str, Any]:
    """Return a fail-closed intake receipt for one canonical plan."""
    plan_slug = plan.removeprefix(PLAN_PREFIX)
    plan_label = f"{PLAN_PREFIX}{plan_slug}"
    defects: list[str] = []

    issues = unwrap_issues(issues_payload, "issues payload")
    ready_issues = unwrap_issues(ready_payload, "ready payload")

    issue_ids = [issue.get("id") for issue in issues]
    invalid_ids = [
        issue_id
        for issue_id in issue_ids
        if not isinstance(issue_id, str) or not issue_id.strip()
    ]
    for issue_id in invalid_ids:
        defects.append(f"{issue_id!r}: invalid issue id")
    duplicate_ids = {
        issue_id
        for issue_id, count in Counter(issue_ids).items()
        if isinstance(issue_id, str) and count > 1
    }
    for issue_id in sorted(duplicate_ids):
        defects.append(f"{issue_id}: duplicate issue id")

    issues_by_id = {
        issue["id"]: issue
        for issue in issues
        if isinstance(issue.get("id"), str)
        and issue["id"].strip()
        and issue["id"] not in duplicate_ids
    }
    roles_by_id: dict[str, str | None] = {}
    metadata_by_id: dict[str, dict[str, str | None]] = {}
    root_states_by_id: dict[str, list[str]] = {}

    for issue_id, issue in issues_by_id.items():
        labels = _labels(issue, defects)
        plan_labels = _prefixed(labels, PLAN_PREFIX)
        if plan_labels != [plan_label]:
            defects.append(
                f"{issue_id}: expected exactly one {plan_label} label; "
                f"found {plan_labels}"
            )

        role_labels = _prefixed(labels, ROLE_PREFIX)
        if len(role_labels) != 1:
            defects.append(
                f"{issue_id}: expected exactly one canonical plan-role label; "
                f"found {role_labels}"
            )
            role = None
        elif role_labels[0] not in ALLOWED_ROLES:
            defects.append(f"{issue_id}: unknown canonical role {role_labels[0]}")
            role = None
        else:
            role = role_labels[0]
        roles_by_id[issue_id] = role

        state_labels = _prefixed(labels, STATE_PREFIX)
        if role == ROOT_ROLE:
            root_states_by_id[issue_id] = state_labels
        elif state_labels:
            defects.append(
                f"{issue_id}: plan-state labels are root-only; found {state_labels}"
            )

        metadata_by_id[issue_id] = _parse_notes(issue, defects)

    root_ids = sorted(
        issue_id for issue_id, role in roles_by_id.items() if role == ROOT_ROLE
    )
    root_id = root_ids[0] if len(root_ids) == 1 else None
    if len(root_ids) != 1:
        defects.append(
            f"{plan_label}: expected exactly one plan-role:root; found {root_ids}"
        )

    root_state: str | None = None
    if root_id is not None:
        root_states = root_states_by_id.get(root_id, [])
        if len(root_states) != 1:
            defects.append(
                f"{root_id}: expected exactly one canonical plan-state label; "
                f"found {root_states}"
            )
        elif root_states[0] not in ALLOWED_ROOT_STATES:
            defects.append(f"{root_id}: unknown canonical state {root_states[0]}")
        else:
            root_state = root_states[0]

    for defect in _hierarchy_defects(
        issues_by_id, roles_by_id, metadata_by_id, root_id
    ):
        _append_once(defects, defect)

    ready_ids: list[str] = []
    for ready_issue in ready_issues:
        ready_id = ready_issue.get("id")
        if not isinstance(ready_id, str) or not ready_id.strip():
            defects.append(f"{ready_id!r}: invalid ready issue id")
            continue
        if ready_id in ready_ids:
            defects.append(f"{ready_id}: duplicate ready issue id")
            continue
        ready_ids.append(ready_id)
        if ready_id not in issues_by_id:
            defects.append(f"{ready_id}: ready issue is outside the scoped plan")

    candidate_frontier: list[dict[str, str]] = []
    excluded_ready_grouping_ids: list[str] = []
    for ready_id in ready_ids:
        role = roles_by_id.get(ready_id)
        if role in DISPATCHABLE_ROLES:
            candidate_frontier.append({"id": ready_id, "role": role})
        elif role in GROUPING_ROLES:
            excluded_ready_grouping_ids.append(ready_id)

    gate_reasons: list[str] = []
    if defects:
        gate_reasons.append("canonical metadata or hierarchy defects")
    if root_state != HANDOFF_READY:
        gate_reasons.append(
            f"root state is {root_state or 'unknown'}; required {HANDOFF_READY}"
        )

    dispatchable = not gate_reasons
    admitted_frontier = candidate_frontier if dispatchable else []
    role_counts = Counter(
        role for role in roles_by_id.values() if isinstance(role, str)
    )
    recognized_count = sum(
        all(metadata.get(field) is not None for field in CANONICAL_NOTE_FIELDS)
        for metadata in metadata_by_id.values()
    )

    return {
        "plan": plan_slug,
        "plan_label": plan_label,
        "root": {
            "id": root_id,
            "state": root_state,
        },
        "node_count": len(issues),
        "role_counts": dict(sorted(role_counts.items())),
        "recognized_metadata": {
            "fields": list(CANONICAL_NOTE_FIELDS),
            "node_count": len(metadata_by_id),
            "complete_node_count": recognized_count,
        },
        "planning_hierarchy": [
            {
                "id": issue_id,
                "role": roles_by_id.get(issue_id),
                **metadata_by_id.get(issue_id, {}),
            }
            for issue_id in sorted(issues_by_id)
        ],
        "excluded_grouping_ids": sorted(
            issue_id
            for issue_id, role in roles_by_id.items()
            if role in GROUPING_ROLES
        ),
        "raw_ready_ids": ready_ids,
        "excluded_ready_grouping_ids": excluded_ready_grouping_ids,
        "candidate_frontier": candidate_frontier,
        "admitted_frontier": admitted_frontier,
        "dispatchable": dispatchable,
        "gate_reasons": gate_reasons,
        "defects": defects,
    }


def _read_json(path: str) -> object:
    return json.loads(Path(path).expanduser().read_text())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and filter a canonical no-ragrets Beads frontier"
    )
    parser.add_argument("--plan", required=True, help="Plan slug or plan:<slug>")
    parser.add_argument(
        "--issues-file",
        required=True,
        help="JSON from `br list --label plan:<slug> --json`",
    )
    parser.add_argument(
        "--ready-file",
        required=True,
        help="JSON from `br ready --label plan:<slug> --json`",
    )
    args = parser.parse_args()

    receipt = intake_plan(
        _read_json(args.issues_file),
        _read_json(args.ready_file),
        args.plan,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["dispatchable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
