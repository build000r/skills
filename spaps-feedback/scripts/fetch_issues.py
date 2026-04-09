#!/usr/bin/env python3
"""Fetch SPAPS issue_reports rows via SSH+docker+psql, read-only.

Reads connection details from the resolved skillbox client overlay's
`spaps_feedback.db` block (with fallback to `deploy.droplet_ssh`).

Usage:
  fetch_issues.py [--cwd PATH] [--since 7d|24h|2025-04-01] [--limit N]
                  [--id UUID] [--application UUID] [--json]

No arguments prints usage and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ALLOWED_COLUMNS = [
    "id",
    "application_id",
    "reporter_user_id",
    "reporter_role_hint",
    "component_key",
    "component_label",
    "page_url",
    "surface_ref",
    "target_metadata",
    "note",
    "source_app",
    "source_record_id",
    "support_case_id",
    "created_at",
    "updated_at",
]


def die(msg: str, code: int = 2) -> None:
    print(f"spaps-feedback fetch_issues: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_since(value: str) -> str:
    """Return an ISO-8601 timestamp suitable for psql comparison."""
    m = re.fullmatch(r"(\d+)([hd])", value)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(hours=n) if unit == "h" else timedelta(days=n)
        return (datetime.now(timezone.utc) - delta).isoformat()
    # Allow plain ISO date or datetime; psql will validate
    return value


def load_overlay(cwd: Path, client: str | None = None) -> dict[str, Any]:
    """Resolve the active client overlay for cwd via skill-issue's manager."""
    manage = Path.home() / ".claude/skills/skill-issue/scripts/manage_overlays.py"
    if not manage.exists():
        die(f"skill-issue manage_overlays.py not found at {manage}")
    try:
        out = subprocess.check_output(
            ["python3", str(manage), "match", "--cwd", str(cwd), "--json"],
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        die(
            "no client overlay matches "
            f"{cwd}. Create one with: "
            f"python3 {manage} create --client-id <id> --cwd {cwd} --json\n"
            f"underlying error: {e.stderr.strip()}"
        )
    payload = json.loads(out)
    matches = payload.get("matches") or []
    if client:
        picked = next((m for m in matches if m.get("client_id") == client), None)
        if not picked:
            ids = ", ".join(m.get("client_id") or "?" for m in matches) or "<none>"
            die(f"--client {client} did not match. Available: {ids}")
        overlay_path = picked.get("path")
    elif not matches:
        overlay_path = payload.get("overlay_path") or payload.get("path")
    elif len(matches) == 1:
        overlay_path = matches[0].get("path")
    else:
        ranked = sorted(
            matches,
            key=lambda m: (-len(m.get("matched_pattern") or ""), m.get("client_id") or ""),
        )
        top_len = len(ranked[0].get("matched_pattern") or "")
        tied = [m for m in ranked if len(m.get("matched_pattern") or "") == top_len]
        if len(tied) > 1:
            ids = ", ".join(m.get("client_id") or "?" for m in tied)
            die(
                f"multiple client overlays match {cwd}: {ids}. "
                f"Pass --client <id> to pick one."
            )
        overlay_path = ranked[0].get("path")
    if not overlay_path:
        die(f"overlay match returned no path: {payload}")
    try:
        import yaml  # type: ignore
    except ImportError:
        die("PyYAML required: pip install pyyaml")
    with open(os.path.expanduser(overlay_path)) as fh:
        return yaml.safe_load(fh) or {}


def get_db_config(overlay: dict[str, Any]) -> dict[str, Any]:
    ctx = (overlay.get("client") or {}).get("context") or {}
    sf = ctx.get("spaps_feedback") or {}
    db = dict(sf.get("db") or {})
    deploy = ctx.get("deploy") or {}
    db.setdefault("droplet_ssh", deploy.get("droplet_ssh"))
    db.setdefault("ssh_key", deploy.get("ssh_key"))
    db.setdefault("table", "issue_reports")
    missing = [k for k in ("droplet_ssh", "container", "user", "database") if not db.get(k)]
    if missing:
        die(
            "spaps_feedback.db config incomplete: missing "
            + ", ".join(missing)
            + ". Add a spaps_feedback block to the client overlay; see "
            "spaps-feedback/references/overlay-schema.md"
        )
    return db


def build_sql(args: argparse.Namespace, db: dict[str, Any]) -> str:
    table = db["table"]
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table):
        die(f"refusing unsafe table name: {table}")
    cols = ", ".join(ALLOWED_COLUMNS)
    where = []
    if args.id:
        if not re.fullmatch(r"[0-9a-fA-F\-]{36}", args.id):
            die("--id must be a UUID")
        where.append(f"id = '{args.id}'")
    if args.application:
        if not re.fullmatch(r"[0-9a-fA-F\-]{36}", args.application):
            die("--application must be a UUID")
        where.append(f"application_id = '{args.application}'")
    elif db.get("application_filter"):
        af = db["application_filter"]
        if not re.fullmatch(r"[0-9a-fA-F\-]{36}", af):
            die("overlay application_filter must be a UUID")
        where.append(f"application_id = '{af}'")
    if args.since:
        ts = parse_since(args.since)
        # Quote ISO timestamp safely (no single quotes possible from parse_since)
        if "'" in ts:
            die("invalid --since value")
        where.append(f"created_at >= '{ts}'")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit = max(1, min(args.limit, 500))
    return (
        f"SELECT {cols} FROM {table} {where_sql} "
        f"ORDER BY created_at DESC LIMIT {limit};"
    )


def run_psql(db: dict[str, Any], sql: str) -> list[dict[str, Any]]:
    psql_cmd = (
        f"psql -U {shlex.quote(db['user'])} -d {shlex.quote(db['database'])} "
        f"-At -F $'\\x1f' -c {shlex.quote(sql)}"
    )
    docker_cmd = f"docker exec {shlex.quote(db['container'])} sh -c {shlex.quote(psql_cmd)}"
    ssh_cmd = ["ssh", db["droplet_ssh"], docker_cmd]
    try:
        out = subprocess.check_output(ssh_cmd, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        die(f"ssh/psql failed: {e.stderr.strip()}", code=3)
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != len(ALLOWED_COLUMNS):
            continue
        row = dict(zip(ALLOWED_COLUMNS, parts))
        # target_metadata comes back as JSON text; try to parse
        if row.get("target_metadata"):
            try:
                row["target_metadata"] = json.loads(row["target_metadata"])
            except json.JSONDecodeError:
                pass
        rows.append(row)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(
        description="Read SPAPS issue reports via overlay-driven SSH+psql.",
    )
    p.add_argument("--cwd", default=os.getcwd(), help="cwd to resolve client overlay against")
    p.add_argument("--client", help="force a specific client overlay id when multiple match")
    p.add_argument("--since", help="time window e.g. 24h, 7d, or ISO date")
    p.add_argument("--limit", type=int, default=25, help="max rows (1-500)")
    p.add_argument("--id", help="single issue UUID")
    p.add_argument("--application", help="application UUID filter")
    p.add_argument("--json", action="store_true", help="emit JSON (default: pretty)")
    if len(sys.argv) == 1:
        p.print_help(sys.stderr)
        print("\nRun with --since 7d or --id <uuid> to fetch issues.", file=sys.stderr)
        return 2
    args = p.parse_args()

    overlay = load_overlay(Path(args.cwd), client=args.client)
    db = get_db_config(overlay)
    sql = build_sql(args, db)
    if not sql.lstrip().upper().startswith("SELECT"):
        die("internal: refusing non-SELECT query")
    rows = run_psql(db, sql)

    if args.json:
        json.dump(rows, sys.stdout, default=str, indent=2)
        sys.stdout.write("\n")
    else:
        for r in rows:
            note = (r.get("note") or "").replace("\n", " ")
            if len(note) > 80:
                note = note[:77] + "..."
            print(f"{r['created_at']}  {r['id'][:8]}  {r['component_label']}  {note}")
        print(f"\n{len(rows)} issue(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
