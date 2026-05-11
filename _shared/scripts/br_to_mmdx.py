#!/usr/bin/env python3
"""Render `br` (beads_rust) chain state as an MMDX chart stack.

The beads contract treats `chain:smart` issues (and any other labelled chain)
as the durable, machine-readable spine of an iterative loop. Markdown chain
files are merely views. This script adds a *visual* view: a Gantt of every
chain link grouped by loop, with one drilldown flowchart per loop showing the
ordered links, their loop-status, and their resume_condition.

Output is an `.mmdx` file consumable by:

    python3 ~/.claude/skills/mmdx/scripts/mmd.py <output.mmdx> --open

Discovery modes:

  --repo PATH           Render chains from a single repo's .beads/.
  --scan ROOT [...]     Walk one or more roots looking for .beads/ dirs.
  (default)             Walk ~/repos.

Filtering:

  --label chain:smart   The label (or comma-separated labels) to filter on.
                        Defaults to chain:smart.

Output:

  --out PATH            Where to write the .mmdx. Defaults to a dated file
                        under ~/.claude/skills/smart/chains/.
  --open                Pass the result through mmd.py --open.

This is invoked from `br_helpers.py render-mmdx` and may also be run directly.
It does not mutate any beads state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

HOME = Path.home()
DEFAULT_SCAN_ROOTS = [HOME / "repos"]
DEFAULT_OUT_DIR = HOME / ".claude" / "skills" / "smart" / "chains"
BR = shutil.which("br") or "/Users/b/.local/bin/br"


# --------------------------- repo discovery ---------------------------


def find_beads_repos(roots: Iterable[Path]) -> list[Path]:
    """Walk roots, return repo dirs (parents of .beads/)."""
    found: list[Path] = []
    seen: set[Path] = set()
    skip_dirs = {"node_modules", ".cache", ".git"}
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            if ".beads" in dirnames:
                p = Path(dirpath).resolve()
                if p not in seen:
                    seen.add(p)
                    found.append(p)
                # don't descend into nested .beads; one chain per repo root
                dirnames[:] = [d for d in dirnames if d != ".beads"]
    return found


# --------------------------- br query ---------------------------


def br_list(repo: Path, labels: list[str]) -> list[dict]:
    """Return all issues (open + closed) in `repo` matching every label."""
    args = [BR, "list", "--all", "--json"]
    for label in labels:
        args += ["--label", label]
    try:
        proc = subprocess.run(
            args,
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "BR_AGENT_NAME": "br_to_mmdx"},
        )
    except FileNotFoundError:
        print(f"  br not found at {BR}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        return []
    out = proc.stdout.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    return data.get("issues") or []


# --------------------------- modeling ---------------------------


@dataclass
class Link:
    issue_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    labels: list[str]
    resume_condition: str = ""
    loop_status: str = ""

    @property
    def is_open(self) -> bool:
        return self.status not in {"closed", "resolved", "done"}


@dataclass
class Loop:
    loop_id: str
    repo: str
    links: list[Link] = field(default_factory=list)

    @property
    def latest(self) -> Link:
        return sorted(self.links, key=lambda l: l.created_at)[-1]

    @property
    def open(self) -> bool:
        return any(l.is_open for l in self.links)


# Resume condition lives in `notes`/`design` as `resume_condition:` lines.
RESUME_RE = re.compile(r"^resume_condition:\s*(.+)$", re.MULTILINE)
LOOP_LABEL_RE = re.compile(r"^loop:(.+)$")
LOOP_STATUS_LABEL_RE = re.compile(r"^loop-status:(.+)$")


def parse_link(issue: dict) -> Link:
    labels = issue.get("labels") or []
    notes = (issue.get("notes") or "") + "\n" + (issue.get("design") or "")
    resume_match = RESUME_RE.search(notes)
    loop_status = ""
    for label in labels:
        m = LOOP_STATUS_LABEL_RE.match(label)
        if m:
            loop_status = m.group(1)
            break
    return Link(
        issue_id=issue.get("id", "?"),
        title=issue.get("title", ""),
        status=issue.get("status", "open"),
        created_at=issue.get("created_at", ""),
        updated_at=issue.get("updated_at", ""),
        labels=labels,
        resume_condition=resume_match.group(1).strip() if resume_match else "",
        loop_status=loop_status,
    )


def group_into_loops(issues_by_repo: dict[str, list[dict]]) -> list[Loop]:
    """Each loop:<id> label across repos becomes its own Loop. Links missing a
    loop label are bucketed into a synthetic 'unscoped:<repo>' loop."""
    loops: dict[str, Loop] = {}
    for repo, issues in issues_by_repo.items():
        for issue in issues:
            link = parse_link(issue)
            loop_id: str | None = None
            for label in link.labels:
                m = LOOP_LABEL_RE.match(label)
                if m:
                    loop_id = m.group(1)
                    break
            key = f"{repo}::{loop_id or '_unscoped'}"
            loops.setdefault(key, Loop(loop_id=loop_id or "(no loop label)", repo=repo)).links.append(link)
    # Sort each loop's links chronologically.
    for loop in loops.values():
        loop.links.sort(key=lambda l: l.created_at)
    # Order loops by latest activity, descending.
    return sorted(loops.values(), key=lambda lp: lp.latest.updated_at, reverse=True)


# --------------------------- rendering ---------------------------


def safe_id(s: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")
    if not out or not out[0].isalpha():
        out = "n_" + out
    return out


def gantt_status(link: Link) -> str:
    if link.status == "blocked":
        return "crit"
    if link.is_open:
        return "active"
    return "done"


def short(s: str, n: int = 38) -> str:
    s = s.replace(":", "·").replace("`", "'")
    return s if len(s) <= n else s[: n - 1] + "…"


def parse_iso(ts: str) -> float | None:
    if not ts:
        return None
    # Trim Z and fractional seconds for portability with strptime.
    ts = ts.replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return time.mktime(time.strptime(ts, fmt))
        except ValueError:
            continue
    return None


def fmt_date(ts: str) -> str:
    epoch = parse_iso(ts) or time.time()
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


def link_duration_h(link: Link) -> int:
    start = parse_iso(link.created_at) or time.time()
    end = parse_iso(link.updated_at) if not link.is_open else time.time()
    if end is None:
        end = time.time()
    hours = max(1, int((end - start) / 3600))
    return min(hours, 24 * 30)  # cap at 30 days for chart legibility


def render_main_gantt(loops: list[Loop]) -> str:
    lines = [
        "gantt",
        f"  title BR Chain — {sum(len(l.links) for l in loops)} links across {len(loops)} loops",
        "  dateFormat  YYYY-MM-DD HH:mm",
        "  axisFormat  %b %d",
        "",
    ]
    click_lines: list[str] = ["  %% click handlers route to per-loop drilldown"]
    for loop in loops:
        section = f"{loop.repo} · {loop.loop_id}"
        lines.append(f"  section {short(section, 60)}")
        for i, link in enumerate(loop.links):
            tid = f"{safe_id(loop.repo)}_{safe_id(loop.loop_id)}_{i}"
            label = short(link.title, 38)
            lines.append(
                f"  {label}  :{gantt_status(link)}, {tid}, {fmt_date(link.created_at)}, {link_duration_h(link)}h"
            )
        lines.append("")
    return "\n".join(lines)


def render_loop_drilldown(loop: Loop) -> str:
    """A flowchart showing each link as a node, status pill, and the resume
    condition on the latest open link if any."""
    lines = ["flowchart TD"]
    prev: str | None = None
    for i, link in enumerate(loop.links):
        nid = f"l{i}"
        status_pill = link.loop_status or link.status
        body = f"{short(link.title, 60)}<br/><b>{status_pill}</b><br/><i>{fmt_date(link.created_at)}</i>"
        shape = f'{nid}["{body}"]'
        cls = "open" if link.is_open else "done"
        if link.status == "blocked":
            cls = "blocked"
        lines.append(f"  {shape}:::{cls}")
        if prev:
            lines.append(f"  {prev} --> {nid}")
        prev = nid
    # Resume node hangs off the latest open link if there is one.
    open_links = [l for l in loop.links if l.is_open]
    if open_links and open_links[-1].resume_condition:
        last = loop.links.index(open_links[-1])
        lines.append(
            f'  resume["resume when:<br/>{short(open_links[-1].resume_condition, 70)}"]:::resume'
        )
        lines.append(f"  l{last} -.-> resume")
    lines.append("  classDef open fill:#fde68a,stroke:#b45309,color:#1c1917")
    lines.append("  classDef blocked fill:#fecaca,stroke:#991b1b,color:#1c1917")
    lines.append("  classDef done fill:#bbf7d0,stroke:#166534,color:#1c1917")
    lines.append("  classDef resume fill:#dbeafe,stroke:#1e40af,color:#1e3a8a,stroke-dasharray: 4 2")
    return "\n".join(lines)


def render_mmdx(loops: list[Loop]) -> str:
    if not loops:
        return ""
    links = [
        {
            "from": "main",
            "label": short(f"{loop.repo} · {loop.loop_id}", 60),
            "to": f"loop_{safe_id(loop.repo)}_{safe_id(loop.loop_id)}",
            "title": f"Open {loop.repo} {loop.loop_id} ({len(loop.links)} links, {'open' if loop.open else 'closed'})",
        }
        for loop in loops
    ]
    meta = {"entry": "main", "links": links}

    parts = ["<!-- mmdx", json.dumps(meta, indent=2), "-->", ""]
    parts.append(f"## chart main BR Chain ({len(loops)} loops)")
    parts.append("```mermaid")
    parts.append(render_main_gantt(loops))
    parts.append("```")
    for loop in loops:
        chart_id = f"loop_{safe_id(loop.repo)}_{safe_id(loop.loop_id)}"
        parts.append("")
        parts.append(f"## chart {chart_id} {short(loop.repo + ' · ' + loop.loop_id, 70)}")
        parts.append("```mermaid")
        parts.append(render_loop_drilldown(loop))
        parts.append("```")
    parts.append("")
    return "\n".join(parts)


# --------------------------- entrypoint ---------------------------


def collect(repos: list[Path], labels: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for repo in repos:
        issues = br_list(repo, labels)
        if issues:
            out[repo.name] = issues
    return out


def open_with_mmd(path: Path) -> int:
    mmd = HOME / ".claude" / "skills" / "mmdx" / "scripts" / "mmd.py"
    if not mmd.is_file():
        print(f"  mmd.py not found at {mmd}; cannot --open", file=sys.stderr)
        return 1
    return subprocess.call(["python3", str(mmd), str(path), "--open"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", type=Path, help="Render a single repo (must contain .beads/).")
    p.add_argument("--scan", type=Path, action="append", default=[], help="Root(s) to walk for .beads/ dirs.")
    p.add_argument("--label", default="chain:smart", help="Comma-separated labels to filter on.")
    p.add_argument("--out", type=Path, help="Write .mmdx to this path.")
    p.add_argument("--open", action="store_true", help="Pipe through mmd.py --open after writing.")
    p.add_argument("--print", action="store_true", help="Print rendered .mmdx to stdout instead of writing.")
    args = p.parse_args(argv)

    labels = [l.strip() for l in args.label.split(",") if l.strip()]

    if args.repo:
        repos = [args.repo.expanduser().resolve()]
    elif args.scan:
        repos = find_beads_repos(args.scan)
    else:
        repos = find_beads_repos(DEFAULT_SCAN_ROOTS)

    if not repos:
        print("No repos with .beads/ found.", file=sys.stderr)
        return 1

    issues_by_repo = collect(repos, labels)
    loops = group_into_loops(issues_by_repo)
    if not loops:
        print(f"No issues found matching labels: {', '.join(labels)}", file=sys.stderr)
        return 1

    text = render_mmdx(loops)

    if args.print:
        sys.stdout.write(text)
        return 0

    out_path = args.out
    if out_path is None:
        DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = "-".join(labels).replace(":", "_")
        out_path = DEFAULT_OUT_DIR / f"{stamp}-{slug}.mmdx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"Wrote {out_path}")
    print(f"  loops: {len(loops)}  links: {sum(len(l.links) for l in loops)}  repos: {len(issues_by_repo)}")
    print(f"Open: python3 {HOME}/.claude/skills/mmdx/scripts/mmd.py {out_path} --open")

    if args.open:
        return open_with_mmd(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
