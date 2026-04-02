#!/usr/bin/env python3
"""
Delta Integrity Audit for /crap remediation loops.

Detects whether CRAP score improvements came from legitimate work (real coverage
gains, genuine simplification) or from gaming (function splits that preserve net
complexity, code moved out of scope, hollow tests without assertions, silent
scope narrowing).

Two modes:
  --snapshot   Capture the current function inventory as a baseline JSON file.
  --audit      Compare a baseline snapshot to the current state and emit a
               machine-readable DELTA_INTEGRITY verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from importlib.machinery import SourceFileLoader
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
_analyze = SourceFileLoader(
    "analyze_crap",
    str(SKILL_ROOT / "scripts" / "analyze_crap.py"),
).load_module()

ASSERTION_PATTERNS = re.compile(
    r"\b(?:assert|expect|should|must|verify|check)\b"
    r"|\.to(?:Equal|Be|Have|Match|Throw|Contain)\b"
    r"|\.toBe(?:Truthy|Falsy|Defined|Null|Undefined|NaN|GreaterThan|LessThan)\b"
    r"|\.toStrictEqual\b"
    r"|assert_eq!|assert_ne!|assert!\b"
    r"|#\[should_panic\]",
    re.IGNORECASE,
)

TEST_FILE_PATTERNS = re.compile(
    r"(?:^|/)test[_s]?[/.]"
    r"|[_.]test\."
    r"|[_.]spec\."
    r"|(?:^|/)tests/"
    r"|(?:^|/)__tests__/",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    snap = sub.add_parser("snapshot", help="Capture baseline function inventory.")
    snap.add_argument("target", nargs="?", default=".", help="Repo or path to snapshot.")
    snap.add_argument("--languages", default="", help="Comma-separated language filter.")
    snap.add_argument("-o", "--output", required=True, help="Output JSON path.")

    audit = sub.add_parser("audit", help="Compare baseline to current state.")
    audit.add_argument("baseline", help="Baseline snapshot JSON from a prior --snapshot run.")
    audit.add_argument("target", nargs="?", default=".", help="Repo or path to audit.")
    audit.add_argument("--languages", default="", help="Comma-separated language filter.")
    audit.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Inventory collection
# ---------------------------------------------------------------------------

@dataclass
class FunctionRecord:
    file: str
    symbol: str
    language: str
    start_line: int
    end_line: int
    cc: int
    line_count: int


@dataclass
class Snapshot:
    target: str
    scope_path: str
    functions: list[FunctionRecord]
    file_hashes: dict[str, str]
    test_file_assertion_counts: dict[str, int]


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def count_assertions_in_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return len(ASSERTION_PATTERNS.findall(text))


def collect_inventory(target: Path, languages: list[str]) -> Snapshot:
    target = target.resolve()
    selection_root = target if target.is_dir() else target.parent
    repo_root = _analyze.resolve_project_root(selection_root)
    supported_files = _analyze.iter_supported_files(target, languages)

    functions: list[FunctionRecord] = []
    hashes: dict[str, str] = {}
    test_assertions: dict[str, int] = {}

    for file_path in supported_files:
        rel = file_path.relative_to(repo_root).as_posix()
        hashes[rel] = file_hash(file_path)
        lang = _analyze.detect_language(file_path)

        if TEST_FILE_PATTERNS.search(rel):
            test_assertions[rel] = count_assertions_in_file(file_path)

        for symbol, start_line, end_line, cc in _analyze.analyze_file(file_path):
            functions.append(FunctionRecord(
                file=rel,
                symbol=symbol,
                language=lang,
                start_line=start_line,
                end_line=end_line,
                cc=cc,
                line_count=end_line - start_line + 1,
            ))

    return Snapshot(
        target=str(target),
        scope_path=str(repo_root),
        functions=functions,
        file_hashes=hashes,
        test_file_assertion_counts=test_assertions,
    )


def snapshot_to_dict(snap: Snapshot) -> dict:
    return {
        "target": snap.target,
        "scope_path": snap.scope_path,
        "functions": [asdict(f) for f in snap.functions],
        "file_hashes": snap.file_hashes,
        "test_file_assertion_counts": snap.test_file_assertion_counts,
    }


def snapshot_from_dict(data: dict) -> Snapshot:
    return Snapshot(
        target=data["target"],
        scope_path=data["scope_path"],
        functions=[FunctionRecord(**f) for f in data["functions"]],
        file_hashes=data.get("file_hashes", {}),
        test_file_assertion_counts=data.get("test_file_assertion_counts", {}),
    )


# ---------------------------------------------------------------------------
# Delta analysis
# ---------------------------------------------------------------------------

@dataclass
class Flag:
    category: str  # split-without-reduction, scope-escape, hollow-coverage, scope-narrowing
    severity: str  # suspicious, warning
    detail: str
    functions: list[str] = field(default_factory=list)


@dataclass
class AuditResult:
    verdict: str  # clean, suspicious, warning
    flag_count: int
    flags: list[Flag]
    summary: str
    stats: dict


def _func_key(rec: FunctionRecord) -> str:
    return f"{rec.file}::{rec.symbol}"


def _git_deleted_files(repo_root: str) -> set[str]:
    """Ask git for files actually deleted (not just moved) since HEAD."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=D", "HEAD"],
            capture_output=True, text=True, cwd=repo_root, timeout=10,
        )
        deleted = set()
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                deleted.add(parts[1])
        return deleted
    except (subprocess.SubprocessError, FileNotFoundError):
        return set()


def _git_renamed_files(repo_root: str) -> dict[str, str]:
    """Ask git for renames: old_path -> new_path."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=R", "-M", "HEAD"],
            capture_output=True, text=True, cwd=repo_root, timeout=10,
        )
        renames: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                renames[parts[1]] = parts[2]
        return renames
    except (subprocess.SubprocessError, FileNotFoundError):
        return {}


def audit_delta(baseline: Snapshot, current: Snapshot) -> AuditResult:
    flags: list[Flag] = []

    # Index functions by key
    base_by_key = {_func_key(f): f for f in baseline.functions}
    curr_by_key = {_func_key(f): f for f in current.functions}

    # Index functions by file
    base_by_file: dict[str, list[FunctionRecord]] = {}
    for f in baseline.functions:
        base_by_file.setdefault(f.file, []).append(f)
    curr_by_file: dict[str, list[FunctionRecord]] = {}
    for f in current.functions:
        curr_by_file.setdefault(f.file, []).append(f)

    git_deleted = _git_deleted_files(baseline.scope_path)
    git_renames = _git_renamed_files(baseline.scope_path)

    # --- Check 1: Scope narrowing ---
    base_target = Path(baseline.target).resolve()
    curr_target = Path(current.target).resolve()
    if curr_target != base_target:
        try:
            curr_target.relative_to(base_target)
            flags.append(Flag(
                category="scope-narrowing",
                severity="suspicious",
                detail=f"Target narrowed from {baseline.target} to {current.target} between runs. "
                       f"Score comparison across different scopes is misleading.",
            ))
        except ValueError:
            flags.append(Flag(
                category="scope-narrowing",
                severity="warning",
                detail=f"Target changed from {baseline.target} to {current.target}. "
                       f"These are different scopes entirely.",
            ))

    # --- Check 2: Split without net reduction ---
    for file_path, base_funcs in base_by_file.items():
        curr_funcs = curr_by_file.get(file_path, [])
        if not curr_funcs:
            continue

        disappeared = [f for f in base_funcs if _func_key(f) not in curr_by_key]
        appeared = [f for f in curr_funcs if _func_key(f) not in base_by_key]

        if not disappeared or not appeared:
            continue

        for gone in disappeared:
            # Find new functions that overlap the old function's line range or
            # appeared nearby in the same file
            candidates = [
                a for a in appeared
                if a.file == gone.file
            ]
            if len(candidates) < 2:
                continue

            sum_cc = sum(c.cc for c in candidates)
            if sum_cc >= gone.cc:
                flags.append(Flag(
                    category="split-without-reduction",
                    severity="suspicious",
                    detail=f"{gone.file}::{gone.symbol} (CC={gone.cc}) disappeared and "
                           f"{len(candidates)} new functions appeared in the same file "
                           f"with sum(CC)={sum_cc} >= original. Net complexity not reduced.",
                    functions=[_func_key(gone)] + [_func_key(c) for c in candidates],
                ))

    # --- Check 3: Scope escape ---
    disappeared_files = set(base_by_file.keys()) - set(curr_by_file.keys())
    for file_path in disappeared_files:
        rel = file_path
        if rel in git_deleted:
            continue  # Genuine deletion, not a move
        renamed_to = git_renames.get(rel)
        if renamed_to and renamed_to in curr_by_file:
            continue  # Renamed but still in scope
        if renamed_to:
            flags.append(Flag(
                category="scope-escape",
                severity="suspicious",
                detail=f"{rel} was renamed to {renamed_to} which is outside the current scope. "
                       f"{len(base_by_file[file_path])} function(s) escaped scoring.",
                functions=[_func_key(f) for f in base_by_file[file_path]],
            ))
        else:
            # File disappeared without git recording a deletion — likely moved
            funcs = base_by_file[file_path]
            total_cc = sum(f.cc for f in funcs)
            if total_cc > 1:  # Ignore trivial single-CC disappearances
                flags.append(Flag(
                    category="scope-escape",
                    severity="suspicious",
                    detail=f"{rel} disappeared from scope (sum CC={total_cc}, "
                           f"{len(funcs)} function(s)) without a recorded git deletion. "
                           f"Code may have moved out of the analyzed target.",
                    functions=[_func_key(f) for f in funcs],
                ))

    # --- Check 4: Hollow coverage ---
    new_test_files = set(current.test_file_assertion_counts.keys()) - set(
        baseline.test_file_assertion_counts.keys()
    )
    hollow_tests = []
    for test_file in sorted(new_test_files):
        assertion_count = current.test_file_assertion_counts[test_file]
        if assertion_count == 0:
            hollow_tests.append(test_file)

    if hollow_tests:
        flags.append(Flag(
            category="hollow-coverage",
            severity="suspicious",
            detail=f"{len(hollow_tests)} new test file(s) contain zero assertions. "
                   f"These inflate coverage without verifying behavior: "
                   f"{', '.join(hollow_tests)}",
        ))

    # Also flag existing test files where assertions decreased
    for test_file in sorted(set(baseline.test_file_assertion_counts.keys()) &
                            set(current.test_file_assertion_counts.keys())):
        base_count = baseline.test_file_assertion_counts[test_file]
        curr_count = current.test_file_assertion_counts[test_file]
        if base_count > 0 and curr_count == 0:
            flags.append(Flag(
                category="hollow-coverage",
                severity="warning",
                detail=f"{test_file} had {base_count} assertion(s) at baseline but now has 0. "
                       f"Test may have been gutted to avoid failures.",
            ))

    # --- Compute stats ---
    base_total_cc = sum(f.cc for f in baseline.functions)
    curr_total_cc = sum(f.cc for f in current.functions)
    base_func_count = len(baseline.functions)
    curr_func_count = len(current.functions)
    base_file_count = len(base_by_file)
    curr_file_count = len(curr_by_file)

    stats = {
        "baseline_functions": base_func_count,
        "current_functions": curr_func_count,
        "baseline_total_cc": base_total_cc,
        "current_total_cc": curr_total_cc,
        "baseline_files": base_file_count,
        "current_files": curr_file_count,
        "functions_disappeared": len(set(base_by_key.keys()) - set(curr_by_key.keys())),
        "functions_appeared": len(set(curr_by_key.keys()) - set(base_by_key.keys())),
        "new_test_files": len(new_test_files),
        "hollow_test_files": len(hollow_tests),
    }

    # --- Verdict ---
    suspicious_count = sum(1 for f in flags if f.severity == "suspicious")
    warning_count = sum(1 for f in flags if f.severity == "warning")

    if suspicious_count > 0:
        verdict = "suspicious"
    elif warning_count > 0:
        verdict = "warning"
    else:
        verdict = "clean"

    summary_parts = []
    if verdict == "clean":
        summary_parts.append("No gaming signals detected. Score changes appear legitimate.")
    else:
        summary_parts.append(f"{suspicious_count} suspicious and {warning_count} warning flag(s) detected.")
        categories = sorted(set(f.category for f in flags))
        summary_parts.append(f"Categories: {', '.join(categories)}.")
        summary_parts.append("Review flagged items before committing.")

    return AuditResult(
        verdict=verdict,
        flag_count=len(flags),
        flags=flags,
        summary=" ".join(summary_parts),
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_text(result: AuditResult) -> str:
    lines = ["Delta Integrity Audit", ""]

    lines.append(f"Functions: {result.stats['baseline_functions']} -> {result.stats['current_functions']} "
                 f"({result.stats['functions_appeared']} appeared, {result.stats['functions_disappeared']} disappeared)")
    lines.append(f"Total CC: {result.stats['baseline_total_cc']} -> {result.stats['current_total_cc']}")
    lines.append(f"Files: {result.stats['baseline_files']} -> {result.stats['current_files']}")
    lines.append(f"New test files: {result.stats['new_test_files']} "
                 f"(hollow: {result.stats['hollow_test_files']})")
    lines.append("")

    if result.flags:
        for i, flag in enumerate(result.flags, 1):
            marker = "!!" if flag.severity == "suspicious" else "  "
            lines.append(f"{marker} {i}. [{flag.category}] {flag.detail}")
            if flag.functions:
                for func in flag.functions[:5]:
                    lines.append(f"       - {func}")
                if len(flag.functions) > 5:
                    lines.append(f"       ... and {len(flag.functions) - 5} more")
            lines.append("")

    lines.append(f"DELTA_INTEGRITY: {result.verdict} ({result.flag_count} flag(s))")
    return "\n".join(lines)


def render_json(result: AuditResult) -> str:
    return json.dumps({
        "verdict": result.verdict,
        "flag_count": result.flag_count,
        "flags": [asdict(f) for f in result.flags],
        "summary": result.summary,
        "stats": result.stats,
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def cmd_snapshot(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    languages, unsupported = _analyze.requested_languages(args.languages)
    if unsupported:
        print(f"Unsupported languages: {', '.join(unsupported)}", file=sys.stderr)
        return 2

    snap = collect_inventory(target, languages)
    output = Path(args.output)
    output.write_text(json.dumps(snapshot_to_dict(snap), indent=2) + "\n", encoding="utf-8")
    print(f"Snapshot: {len(snap.functions)} functions across {len(snap.file_hashes)} files -> {output}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"Baseline snapshot not found: {baseline_path}", file=sys.stderr)
        return 1

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    baseline = snapshot_from_dict(json.loads(baseline_path.read_text(encoding="utf-8")))

    languages, unsupported = _analyze.requested_languages(args.languages)
    if unsupported:
        print(f"Unsupported languages: {', '.join(unsupported)}", file=sys.stderr)
        return 2

    current = collect_inventory(target, languages)
    result = audit_delta(baseline, current)

    if args.json:
        print(render_json(result))
    else:
        print(render_text(result))

    return 0


def main() -> int:
    args = parse_args()
    if args.command == "snapshot":
        return cmd_snapshot(args)
    elif args.command == "audit":
        return cmd_audit(args)
    else:
        print("Usage: delta_audit.py {snapshot|audit} ...", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(141)
