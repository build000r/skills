#!/usr/bin/env python3
"""Generate INDEX.mmdx — a directory of every .mmdx on the machine.

Renders a Gantt chart with one section per repo, one bar per file, positioned
by mtime. Each bar is `click`-able and opens that .mmdx in the buildooor
diagrams viewer (pako-encoded URL — the actual diagram, not a raw file dump).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mmd import (  # noqa: E402
    build_mmdx_document,
    build_source_metadata,
    build_state,
    build_url,
    encode_state,
    get_mmdx_entry_code,
)

HOME = Path.home()
SCAN_ROOTS = [HOME / "repos", HOME / ".claude"]
EXCLUDE_DIR_NAMES = {"node_modules", ".skillbox-state", ".cache", ".git"}
OUTPUT = HOME / "repos/opensource/skills/mmdx/INDEX.mmdx"


@dataclass
class Entry:
    abs_path: Path
    mtime: float
    repo: str
    rel_path: str
    pako_url: str


def find_mmdx(root: Path) -> Iterable[Path]:
    """Yield .mmdx files anywhere, plus .mmd files that are siblings of a
    plan.md (the domain-* slice convention: each slice dir contains plan.md
    plus a schema.mmd / flows.md / etc.). The domain slice .mmd files are
    treated as first-class diagrams in the index so the buildooor viewer
    shows them alongside everything else."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
        names = set(filenames)
        is_domain_slice_dir = "plan.md" in names
        for f in filenames:
            if f.endswith(".mmdx"):
                yield Path(dirpath) / f
            elif f.endswith(".mmd") and is_domain_slice_dir:
                yield Path(dirpath) / f


def encode_mmdx_url(path: Path) -> str | None:
    try:
        # Plain .mmd files (e.g. domain-* slice schema.mmd) are encoded as a
        # bare mermaid state. Only .mmdx files use build_mmdx_document.
        if path.suffix == ".mmd":
            code = path.read_text()
            state = build_state(code, source=build_source_metadata(str(path)))
            return build_url(encode_state(state))
        markdown = path.read_text()
        document = build_mmdx_document(markdown)
        entry_code = get_mmdx_entry_code(document)
        state = build_state(
            entry_code,
            source=build_source_metadata(str(path)),
            mmdx={
                "version": 1,
                "entry": document["entry"],
                "charts": document["charts"],
                "links": document["links"],
            },
        )
        return build_url(encode_state(state))
    except Exception as e:
        print(f"  skip {path}: {e}", file=sys.stderr)
        return None


def collect_entries() -> list[Entry]:
    entries: list[Entry] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in find_mmdx(root):
            if p.resolve() == OUTPUT.resolve():
                continue
            try:
                rel = p.relative_to(root)
            except ValueError:
                continue
            parts = rel.parts
            repo = parts[0] if parts else root.name
            rel_path = str(Path(*parts[1:])) if len(parts) > 1 else parts[0]
            url = encode_mmdx_url(p)
            if url is None:
                continue
            entries.append(Entry(
                abs_path=p,
                mtime=p.stat().st_mtime,
                repo=repo,
                rel_path=rel_path,
                pako_url=url,
            ))
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries


def safe_id(s: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")
    if not out or not out[0].isalpha():
        out = "n_" + out
    return out


def gantt_status(age_seconds: float) -> str:
    if age_seconds <= 24 * 3600:
        return "crit"
    if age_seconds <= 7 * 24 * 3600:
        return "active"
    return "done"


def short_label(rel_path: str, max_len: int = 38) -> str:
    p = Path(rel_path)
    name = p.name
    parent = p.parent.as_posix()
    if parent in ("", "."):
        s = name
    else:
        head = parent
        if len(head) > 18:
            head = "…" + head[-17:]
        s = f"{head}/{name}"
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s.replace(":", "·")


def group_by_repo(entries: list[Entry]) -> list[tuple[str, list[Entry]]]:
    groups: dict[str, list[Entry]] = {}
    for e in entries:
        groups.setdefault(e.repo, []).append(e)
    repo_order = sorted(
        groups.keys(),
        key=lambda r: max(e.mtime for e in groups[r]),
        reverse=True,
    )
    for r in repo_order:
        groups[r].sort(key=lambda e: e.mtime)
    return [(r, groups[r]) for r in repo_order]


def render_gantt(entries: list[Entry]) -> str:
    now = time.time()
    lines: list[str] = ["gantt"]
    lines.append(f"  title MMDX Directory — {len(entries)} files (refreshed {time.strftime('%Y-%m-%d %H:%M')})")
    lines.append("  dateFormat  YYYY-MM-DD HH:mm")
    lines.append("  axisFormat  %b %d")
    lines.append("")
    for repo, items in group_by_repo(entries):
        lines.append(f"  section {repo}")
        for i, e in enumerate(items):
            tid = f"{safe_id(repo)}_{i}"
            status = gantt_status(now - e.mtime)
            start = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.mtime))
            label = short_label(e.rel_path)
            lines.append(f"  {label}  :{status}, {tid}, {start}, 6h")
        lines.append("")
    lines.append("  %% click handlers")
    for repo, items in group_by_repo(entries):
        for i, e in enumerate(items):
            tid = f"{safe_id(repo)}_{i}"
            lines.append(f'  click {tid} href "{e.pako_url}"')
    return "\n".join(lines)


def render_overview_chart(entries: list[Entry]) -> str:
    groups = group_by_repo(entries)
    lines = ["flowchart LR", '  hub(["MMDX Directory"]):::hub']
    for repo, items in groups:
        nid = f"r_{safe_id(repo)}"
        lines.append(f'  {nid}["{repo}<br/>{len(items)} files"]')
        lines.append(f"  hub --> {nid}")
    lines.append("  classDef hub fill:#0f172a,stroke:#0f172a,color:#f8fafc,stroke-width:3px")
    return "\n".join(lines)


def render_mmdx(entries: list[Entry]) -> str:
    groups = group_by_repo(entries)
    links = [
        {
            "from": "main",
            "label": repo,
            "to": f"detail_{safe_id(repo)}",
            "title": f"Open {repo} ({len(items)} files)",
        }
        for repo, items in groups
    ]
    meta = {"entry": "main", "links": links}

    parts: list[str] = []
    parts.append("<!-- mmdx")
    parts.append(json.dumps(meta, indent=2))
    parts.append("-->")
    parts.append("")
    parts.append(f"## chart main MMDX Directory ({len(entries)} files)")
    parts.append("```mermaid")
    parts.append(render_gantt(entries))
    parts.append("```")
    for repo, items in groups:
        parts.append("")
        parts.append(f"## chart detail_{safe_id(repo)} {repo} drilldown")
        parts.append("```mermaid")
        parts.append(render_repo_detail(repo, items))
        parts.append("```")
    parts.append("")
    return "\n".join(parts)


def render_repo_detail(repo: str, items: list[Entry]) -> str:
    items_desc = sorted(items, key=lambda e: e.mtime, reverse=True)
    lines = ["gantt"]
    lines.append(f"  title {repo} — {len(items_desc)} files")
    lines.append("  dateFormat  YYYY-MM-DD HH:mm")
    lines.append("  axisFormat  %b %d")
    lines.append("")
    lines.append(f"  section {repo}")
    now = time.time()
    for i, e in enumerate(items_desc):
        tid = f"d_{safe_id(repo)}_{i}"
        status = gantt_status(now - e.mtime)
        start = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.mtime))
        label = short_label(e.rel_path, max_len=60)
        lines.append(f"  {label}  :{status}, {tid}, {start}, 6h")
    lines.append("")
    for i, e in enumerate(items_desc):
        tid = f"d_{safe_id(repo)}_{i}"
        lines.append(f'  click {tid} href "{e.pako_url}"')
    return "\n".join(lines)


def main() -> int:
    entries = collect_entries()
    if not entries:
        print("No .mmdx files found.", file=sys.stderr)
        return 1
    text = render_mmdx(entries)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text)
    print(f"Wrote {OUTPUT} with {len(entries)} entries.")
    print(f"Open: python3 {HOME}/.claude/skills/mmdx/scripts/mmd.py {OUTPUT} --open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
