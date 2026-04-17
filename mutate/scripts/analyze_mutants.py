#!/usr/bin/env python3
"""
Analyze mutation-testing artifacts and normalize them into a deterministic backlog.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_ADAPTERS = ("cargo-mutants", "mutmut", "stryker", "muter")
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    "coverage",
    "dist",
    "build",
    "node_modules",
    "target",
    "vendor",
}
ACTIVE_STATUSES = {
    "survived",
    "no_coverage",
    "no_tests",
    "timeout",
    "suspicious",
    "not_checked",
    "compile_error",
    "segfault",
    "type_check",
    "deferred",
}
CLOSED_STATUSES = {"killed", "skipped", "ignored", "equivalent", "resolved"}
REVIEW_STATUSES = {"deferred", "equivalent", "ignored", "resolved"}
STATUS_ORDER = {
    "survived": 0,
    "no_coverage": 1,
    "no_tests": 2,
    "timeout": 3,
    "suspicious": 4,
    "type_check": 5,
    "compile_error": 6,
    "segfault": 7,
    "not_checked": 8,
    "deferred": 9,
    "ignored": 90,
    "equivalent": 91,
    "resolved": 92,
    "skipped": 93,
    "killed": 94,
}
MUTMUT_STATUS_BY_EXIT_CODE = defaultdict(
    lambda: "suspicious",
    {
        0: "survived",
        1: "killed",
        3: "killed",
        5: "no_tests",
        33: "no_tests",
        34: "skipped",
        35: "suspicious",
        36: "timeout",
        37: "type_check",
        None: "not_checked",
        -24: "timeout",
        24: "timeout",
        152: "timeout",
        255: "timeout",
        -11: "segfault",
        -9: "segfault",
    },
)
CARGO_TEXT_STATUS_FILES = {
    "missed.txt": "survived",
    "caught.txt": "killed",
    "timeout.txt": "timeout",
    "unviable.txt": "ignored",
    "ignored.txt": "ignored",
    "skipped.txt": "skipped",
}
STRYKER_REPORT_NAMES = {
    "mutation.json",
    "mutations.json",
    "mutation-report.json",
    "stryker-incremental.json",
}
MUTER_REPORT_NAMES = {
    "muterReport.json",
    "muter-report.json",
}
SOURCE_EXTENSIONS = (".rs", ".py", ".js", ".jsx", ".ts", ".tsx", ".swift")
SOURCE_PATH_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./\\-]+\.(?:rs|py|js|jsx|ts|tsx|swift))(?:[:#](?:L)?(?P<line>\d+))?"
)


@dataclass
class Finding:
    adapter: str
    key: str
    status: str
    source: Path
    path: Path | None = None
    symbol: str | None = None
    line: int | None = None
    raw_id: str | None = None
    detail: str | None = None
    review_status: str | None = None
    note: str | None = None
    first_seen: str | None = None

    @property
    def effective_status(self) -> str:
        if self.review_status in REVIEW_STATUSES:
            return self.review_status
        return self.status

    @property
    def todo(self) -> bool:
        return self.effective_status in ACTIVE_STATUSES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Repository path or subdirectory to analyze (defaults to current directory).",
    )
    parser.add_argument(
        "--adapters",
        default="",
        help="Comma-separated list from: cargo-mutants, mutmut, stryker, muter.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only display the top N ranked findings. FINAL_TODO still uses all findings.",
    )
    parser.add_argument(
        "--ledger",
        default=".mutate/ledger.json",
        help="Ledger path relative to repo root or absolute path.",
    )
    parser.add_argument(
        "--write-ledger",
        action="store_true",
        help="Write the normalized backlog to the ledger path after analysis.",
    )
    return parser.parse_args()


def requested_adapters(raw: str) -> tuple[list[str], list[str]]:
    if not raw.strip():
        return list(SUPPORTED_ADAPTERS), []
    requested = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unsupported = [adapter for adapter in requested if adapter not in SUPPORTED_ADAPTERS]
    supported = [adapter for adapter in requested if adapter in SUPPORTED_ADAPTERS]
    return supported, unsupported


def should_ignore_dir(name: str) -> bool:
    return name in IGNORED_DIRS or name.startswith(".venv.")


def resolve_project_root(selection_root: Path) -> Path:
    markers = {
        ".git",
        "Cargo.toml",
        "pyproject.toml",
        "package.json",
        "mutants.out",
        "mutants",
        ".mutate",
    }
    for candidate in [selection_root, *selection_root.parents]:
        if any((candidate / marker).exists() for marker in markers):
            return candidate.resolve()
    return selection_root.resolve()


def ledger_path_for(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def load_existing_reviews(ledger_path: Path) -> dict[str, dict[str, str]]:
    if not ledger_path.exists():
        return {}
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    reviews: dict[str, dict[str, str]] = {}
    for mutant in payload.get("mutants", []):
        key = mutant.get("key")
        if not key:
            continue
        preserved = {}
        for field in ("review_status", "note", "first_seen"):
            value = mutant.get(field)
            if isinstance(value, str) and value:
                preserved[field] = value
        if preserved:
            reviews[key] = preserved
    return reviews


def discover_files(repo_root: Path) -> list[Path]:
    matches: list[Path] = []
    for current_root, dirs, files in os.walk(repo_root):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d))
        root_path = Path(current_root)
        for name in sorted(files):
            path = root_path / name
            rel_parts = path.relative_to(repo_root).parts
            if name.endswith(".meta") and "mutants" in rel_parts:
                matches.append(path.resolve())
                continue
            if "mutants.out" in rel_parts and (name == "outcomes.json" or name in CARGO_TEXT_STATUS_FILES):
                matches.append(path.resolve())
                continue
            if name in STRYKER_REPORT_NAMES and any(part in {"reports", "stryker"} for part in rel_parts):
                matches.append(path.resolve())
                continue
            if name in MUTER_REPORT_NAMES:
                matches.append(path.resolve())
    return matches


def normalize_path(raw: str | None, repo_root: Path) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(repo_root)
        except ValueError:
            return path.resolve()
    return Path(path.as_posix())


def relative_text(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def extract_path_line(text: str, repo_root: Path) -> tuple[Path | None, int | None]:
    match = SOURCE_PATH_RE.search(text)
    if not match:
        return None, None
    line = match.group("line")
    return normalize_path(match.group("path"), repo_root), int(line) if line else None


def detect_language(path: Path | None) -> str:
    if path is None:
        return "unknown"
    suffix = path.suffix.lower()
    if suffix == ".rs":
        return "rust"
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix in {".js", ".jsx"}:
        return "javascript"
    if suffix == ".swift":
        return "swift"
    return "unknown"


def symbol_from_mutmut_key(raw: str) -> str | None:
    prefix = raw.partition("__mutmut_")[0]
    tail = prefix.rpartition(".")[2]
    if tail.startswith("x_"):
        return tail[2:]
    if tail.startswith("xǁ") and "ǁ" in tail[2:]:
        return tail.rpartition("ǁ")[2]
    return tail or None


def canonicalize_cargo_status(raw: str | None) -> str:
    value = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if value in {"caught", "caught_mutant", "caughtmutant", "killed"}:
        return "killed"
    if value in {"missed", "survived"}:
        return "survived"
    if value in {"timeout", "timed_out"}:
        return "timeout"
    if value == "unviable":
        return "ignored"
    if value in {"compile_error", "build_error"}:
        return "compile_error"
    if value == "success":
        return "resolved"
    if value in {"skipped", "ignored"}:
        return value
    if value in ACTIVE_STATUSES or value in CLOSED_STATUSES:
        return value
    return "suspicious"


def canonicalize_muter_status(raw: str | None) -> str:
    value = (raw or "").strip()
    mapping = {
        "passed": "survived",
        "failed": "killed",
        "buildError": "compile_error",
        "runtimeError": "killed",
        "noCoverage": "no_coverage",
        "timeout": "timeout",
    }
    if value in mapping:
        return mapping[value]
    # Defensive: some muter versions/outputs may already use the human-readable form.
    lowered = value.lower().replace(" ", "_")
    if lowered in {"mutant_survived", "survived"}:
        return "survived"
    if lowered.startswith("mutant_killed") or lowered == "killed":
        return "killed"
    if lowered in {"build_error", "compile_error"}:
        return "compile_error"
    if lowered in {"skipped_(no_coverage)", "no_coverage", "nocoverage"}:
        return "no_coverage"
    if lowered in {"time_out", "timeout", "timed_out"}:
        return "timeout"
    return "suspicious"


def canonicalize_stryker_status(raw: str | None) -> str:
    value = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "survived": "survived",
        "killed": "killed",
        "nocoverage": "no_coverage",
        "no_coverage": "no_coverage",
        "timeout": "timeout",
        "compileerror": "compile_error",
        "compile_error": "compile_error",
        "runtimeerror": "suspicious",
        "ignored": "ignored",
        "pending": "not_checked",
    }
    return mapping.get(value, "suspicious")


def make_key(*parts: str | int | None) -> str:
    return ":".join("" if part is None else str(part) for part in parts)


def parse_mutmut_meta(repo_root: Path, meta_path: Path) -> list[Finding]:
    repo_root = repo_root.resolve()
    meta_path = meta_path.resolve()
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    rel_meta = meta_path.relative_to(repo_root)
    rel_source = Path(rel_meta.as_posix()[len("mutants/") : -len(".meta")])
    findings: list[Finding] = []
    type_errors = payload.get("type_check_error_by_key", {})
    for raw_id, exit_code in payload.get("exit_code_by_key", {}).items():
        findings.append(
            Finding(
                adapter="mutmut",
                key=make_key("mutmut", rel_source.as_posix(), raw_id),
                status=MUTMUT_STATUS_BY_EXIT_CODE[exit_code],
                source=meta_path,
                path=rel_source,
                symbol=symbol_from_mutmut_key(raw_id),
                raw_id=raw_id,
                detail=type_errors.get(raw_id),
            )
        )
    return findings


def _json_candidates(node: Any) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        if any(key in node for key in ("status", "result", "outcome", "summary")):
            yield node
        for value in node.values():
            yield from _json_candidates(value)
    elif isinstance(node, list):
        for item in node:
            yield from _json_candidates(item)


def _first(node: dict[str, Any], paths: Iterable[tuple[str, ...]]) -> Any:
    for path in paths:
        current: Any = node
        for part in path:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def parse_cargo_outcomes(repo_root: Path, outcomes_path: Path) -> list[Finding]:
    repo_root = repo_root.resolve()
    outcomes_path = outcomes_path.resolve()
    try:
        payload = json.loads(outcomes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    raw_outcomes = payload.get("outcomes") if isinstance(payload, dict) else None
    if isinstance(raw_outcomes, list):
        findings: list[Finding] = []
        for entry in raw_outcomes:
            if not isinstance(entry, dict):
                continue

            raw_status = _first(entry, (("summary",), ("status",), ("result",), ("outcome",)))
            if raw_status is None:
                continue
            status = canonicalize_cargo_status(str(raw_status))

            scenario = entry.get("scenario")
            if isinstance(scenario, str) and scenario.strip().lower() == "baseline":
                continue

            mutant = None
            if isinstance(scenario, dict):
                mutant = scenario.get("Mutant") or scenario.get("mutant")

            candidate = mutant if isinstance(mutant, dict) else entry
            raw_path = _first(
                candidate,
                (
                    ("file",),
                    ("path",),
                    ("source_path",),
                    ("sourceFile",),
                    ("mutation", "file"),
                    ("span", "file"),
                ),
            )
            raw_line = _first(
                candidate,
                (
                    ("line",),
                    ("line_number",),
                    ("span", "line"),
                    ("span", "start", "line"),
                    ("location", "start", "line"),
                    ("function", "span", "start", "line"),
                ),
            )
            raw_id = _first(candidate, (("name",), ("id",),))
            if raw_id is None:
                raw_id = _first(entry, (("scenario",), ("log_path",), ("diff_path",)))

            detail = _first(
                candidate,
                (("replacement",), ("message",), ("description",), ("diff",), ("snippet",)),
            )
            if detail is None:
                detail = _first(entry, (("log_path",), ("diff_path",)))

            symbol = _first(candidate, (("function", "function_name"),))
            path = normalize_path(str(raw_path), repo_root) if raw_path is not None else None
            try:
                line = int(raw_line) if raw_line is not None else None
            except (TypeError, ValueError):
                line = None

            findings.append(
                Finding(
                    adapter="cargo-mutants",
                    key=make_key(
                        "cargo-mutants",
                        path.as_posix() if path else None,
                        line,
                        raw_id,
                        status,
                    ),
                    status=status,
                    source=outcomes_path,
                    path=path,
                    symbol=str(symbol) if symbol is not None else None,
                    line=line,
                    raw_id=str(raw_id) if raw_id is not None else None,
                    detail=str(detail) if detail is not None else None,
                )
            )
        return findings

    findings = []
    for candidate in _json_candidates(payload):
        raw_status = _first(candidate, (("status",), ("result",), ("outcome",), ("summary",)))
        if raw_status is None:
            continue
        status = canonicalize_cargo_status(str(raw_status))
        raw_path = _first(
            candidate,
            (
                ("file",),
                ("path",),
                ("source_path",),
                ("sourceFile",),
                ("mutation", "file"),
                ("span", "file"),
            ),
        )
        raw_line = _first(
            candidate,
            (
                ("line",),
                ("line_number",),
                ("span", "line"),
                ("span", "start", "line"),
                ("location", "start", "line"),
            ),
        )
        raw_id = _first(candidate, (("id",), ("name",), ("scenario",), ("mutant",)))
        detail = _first(candidate, (("message",), ("description",), ("diff",), ("snippet",)))
        path = normalize_path(str(raw_path), repo_root) if raw_path is not None else None
        try:
            line = int(raw_line) if raw_line is not None else None
        except (TypeError, ValueError):
            line = None
        findings.append(
            Finding(
                adapter="cargo-mutants",
                key=make_key(
                    "cargo-mutants",
                    path.as_posix() if path else None,
                    line,
                    raw_id,
                    status,
                ),
                status=status,
                source=outcomes_path,
                path=path,
                line=line,
                raw_id=str(raw_id) if raw_id is not None else None,
                detail=str(detail) if detail is not None else None,
            )
        )
    return findings


def parse_cargo_text(repo_root: Path, status_path: Path) -> list[Finding]:
    repo_root = repo_root.resolve()
    status_path = status_path.resolve()
    status = CARGO_TEXT_STATUS_FILES[status_path.name]
    findings: list[Finding] = []
    for raw_line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line_text = raw_line.strip()
        if not line_text:
            continue
        path, line = extract_path_line(line_text, repo_root)
        findings.append(
            Finding(
                adapter="cargo-mutants",
                key=make_key(
                    "cargo-mutants",
                    status,
                    path.as_posix() if path else None,
                    line,
                    line_text,
                ),
                status=status,
                source=status_path,
                path=path,
                line=line,
                detail=line_text,
            )
        )
    return findings


def _stryker_entries(payload: Any) -> Iterable[tuple[str | None, dict[str, Any]]]:
    if isinstance(payload, dict):
        files = payload.get("files")
        if isinstance(files, dict):
            for raw_path, file_entry in files.items():
                mutants = file_entry.get("mutants") if isinstance(file_entry, dict) else None
                if isinstance(mutants, list):
                    for mutant in mutants:
                        if isinstance(mutant, dict):
                            yield raw_path, mutant
        mutants = payload.get("mutants")
        if isinstance(mutants, list):
            for mutant in mutants:
                if isinstance(mutant, dict):
                    yield None, mutant


def parse_stryker_report(repo_root: Path, report_path: Path) -> list[Finding]:
    repo_root = repo_root.resolve()
    report_path = report_path.resolve()
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    findings: list[Finding] = []
    for inherited_path, mutant in _stryker_entries(payload):
        raw_status = mutant.get("status")
        if raw_status is None:
            continue
        raw_path = (
            inherited_path
            or mutant.get("sourceFilePath")
            or mutant.get("sourcePath")
            or _first(mutant, (("location", "file"),))
        )
        raw_line = _first(mutant, (("location", "start", "line"), ("line",)))
        try:
            line = int(raw_line) if raw_line is not None else None
        except (TypeError, ValueError):
            line = None

        path = normalize_path(str(raw_path), repo_root) if raw_path is not None else None
        mutator = mutant.get("mutatorName") or mutant.get("mutator")
        replacement = mutant.get("replacement") or mutant.get("replacementText")
        raw_id = mutant.get("id")
        findings.append(
            Finding(
                adapter="stryker",
                key=make_key(
                    "stryker",
                    path.as_posix() if path else None,
                    line,
                    mutator,
                    replacement,
                    raw_id,
                ),
                status=canonicalize_stryker_status(str(raw_status)),
                source=report_path,
                path=path,
                line=line,
                raw_id=str(raw_id) if raw_id is not None else None,
                detail=str(mutator) if mutator is not None else None,
            )
        )
    return findings


def parse_muter_report(repo_root: Path, report_path: Path) -> list[Finding]:
    repo_root = repo_root.resolve()
    report_path = report_path.resolve()
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    file_reports = payload.get("fileReports") if isinstance(payload, dict) else None
    if not isinstance(file_reports, list):
        return []

    findings: list[Finding] = []
    for file_entry in file_reports:
        if not isinstance(file_entry, dict):
            continue
        fallback_name = file_entry.get("fileName") or file_entry.get("path")
        operators = file_entry.get("appliedOperators")
        if not isinstance(operators, list):
            continue
        for mutant in operators:
            if not isinstance(mutant, dict):
                continue
            raw_status = mutant.get("testSuiteOutcome")
            if raw_status is None:
                continue
            status = canonicalize_muter_status(str(raw_status))

            point = mutant.get("mutationPoint") if isinstance(mutant.get("mutationPoint"), dict) else {}
            raw_path = point.get("filePath") or point.get("path") or fallback_name
            operator = point.get("mutationOperatorId") or point.get("mutationOperator")
            position = point.get("position") if isinstance(point.get("position"), dict) else {}
            raw_line = position.get("line") or point.get("line")

            path = normalize_path(str(raw_path), repo_root) if raw_path is not None else None
            try:
                line = int(raw_line) if raw_line is not None else None
            except (TypeError, ValueError):
                line = None

            snapshot = mutant.get("mutationSnapshot") if isinstance(mutant.get("mutationSnapshot"), dict) else None
            detail = str(operator) if operator is not None else None
            if snapshot:
                before = snapshot.get("before")
                after = snapshot.get("after")
                if before is not None and after is not None:
                    delta = f"{before!r} -> {after!r}"
                    detail = f"{detail}: {delta}" if detail else delta

            findings.append(
                Finding(
                    adapter="muter",
                    key=make_key(
                        "muter",
                        path.as_posix() if path else None,
                        line,
                        operator,
                        raw_status,
                    ),
                    status=status,
                    source=report_path,
                    path=path,
                    line=line,
                    raw_id=str(operator) if operator is not None else None,
                    detail=detail,
                )
            )
    return findings


def collect_findings(repo_root: Path, adapters: Iterable[str]) -> tuple[list[Finding], list[Path]]:
    repo_root = repo_root.resolve()
    findings: list[Finding] = []
    sources: list[Path] = []
    files = discover_files(repo_root)
    cargo_dirs: set[Path] = set()
    for path in files:
        rel_parts = path.relative_to(repo_root).parts
        if "mutants.out" in rel_parts:
            cargo_dir = repo_root / Path(*rel_parts[: rel_parts.index("mutants.out") + 1])
            cargo_dirs.add(cargo_dir)

    if "mutmut" in adapters:
        for path in files:
            if path.name.endswith(".meta") and "mutants" in path.relative_to(repo_root).parts:
                sources.append(path)
                findings.extend(parse_mutmut_meta(repo_root, path))

    if "cargo-mutants" in adapters:
        for cargo_dir in sorted(cargo_dirs):
            outcomes_path = cargo_dir / "outcomes.json"
            if outcomes_path.exists():
                sources.append(outcomes_path.resolve())
                parsed = parse_cargo_outcomes(repo_root, outcomes_path.resolve())
                if parsed:
                    findings.extend(parsed)
                    continue
            for name in sorted(CARGO_TEXT_STATUS_FILES):
                text_path = cargo_dir / name
                if text_path.exists():
                    sources.append(text_path.resolve())
                    findings.extend(parse_cargo_text(repo_root, text_path.resolve()))

    if "stryker" in adapters:
        for path in files:
            if path.name in STRYKER_REPORT_NAMES:
                sources.append(path)
                findings.extend(parse_stryker_report(repo_root, path))

    if "muter" in adapters:
        for path in files:
            if path.name in MUTER_REPORT_NAMES:
                sources.append(path)
                findings.extend(parse_muter_report(repo_root, path))

    deduped: dict[str, Finding] = {}
    for finding in findings:
        current = deduped.get(finding.key)
        if current is None:
            deduped[finding.key] = finding
            continue
        current_has_location = current.path is not None or current.line is not None
        new_has_location = finding.path is not None or finding.line is not None
        if new_has_location and not current_has_location:
            deduped[finding.key] = finding
    return sorted(deduped.values(), key=sort_key), sorted(set(sources))


def apply_reviews(findings: list[Finding], reviews: dict[str, dict[str, str]]) -> None:
    for finding in findings:
        preserved = reviews.get(finding.key, {})
        finding.review_status = preserved.get("review_status")
        finding.note = preserved.get("note")
        finding.first_seen = preserved.get("first_seen")


def sort_key(finding: Finding) -> tuple[int, int, str, int, str, str]:
    path_text = finding.path.as_posix() if finding.path else ""
    return (
        0 if finding.todo else 1,
        STATUS_ORDER.get(finding.effective_status, 99),
        path_text,
        finding.line or 0,
        finding.symbol or "",
        finding.key,
    )


def summarize(findings: list[Finding]) -> tuple[Counter[str], int]:
    counts = Counter(finding.effective_status for finding in findings)
    todo_count = sum(1 for finding in findings if finding.todo)
    return counts, todo_count


def format_location(repo_root: Path, finding: Finding) -> str:
    if finding.path is None:
        return finding.raw_id or finding.key
    path_text = finding.path.as_posix()
    if finding.line is not None:
        path_text += f":{finding.line}"
    if finding.symbol:
        path_text += f"::{finding.symbol}"
    return path_text


def render_report(
    repo_root: Path,
    findings: list[Finding],
    *,
    top: int | None = None,
    ledger_path: Path,
    sources: list[Path],
) -> str:
    repo_root = repo_root.resolve()
    displayed = findings if top is None else findings[:top]
    if top is not None and top < len(findings):
        lines = [f"Mutation Backlog Report (top {len(displayed)} of {len(findings)} findings)"]
    else:
        lines = ["Mutation Backlog Report"]

    if not findings:
        lines.append("No supported mutation artifacts found.")
        lines.append(f"Ledger path: {ledger_path}")
        lines.append("FINAL_TODO: 0")
        return "\n".join(lines)

    for index, finding in enumerate(displayed, start=1):
        review_suffix = f" | review {finding.review_status}" if finding.review_status else ""
        lines.append(
            f"{index}. {'TODO' if finding.todo else 'done'} {finding.effective_status} | "
            f"{finding.adapter} | {detect_language(finding.path)} | {format_location(repo_root, finding)}{review_suffix}"
        )

    counts, todo_count = summarize(findings)
    lines.append(f"Ledger path: {ledger_path}")
    lines.append(
        "Status counts: "
        + ", ".join(f"{status} {counts[status]}" for status in sorted(counts, key=lambda status: (STATUS_ORDER.get(status, 99), status)))
    )
    lines.append(
        "Artifact sources: "
        + ", ".join(sorted(relative_text(source, repo_root) for source in sources))
    )
    lines.append(f"FINAL_TODO: {todo_count}")

    todo_findings = [finding for finding in findings if finding.todo]
    if not todo_findings:
        return "\n".join(lines)

    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in todo_findings:
        grouped[finding.path.as_posix() if finding.path else "<unknown>"].append(finding)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (
            -len(item[1]),
            STATUS_ORDER.get(min(item[1], key=sort_key).effective_status, 99),
            item[0],
        ),
    )

    lines.append("")
    lines.append("Suggested next slice")
    for path_text, group in ordered_groups[:5]:
        statuses = Counter(finding.effective_status for finding in group)
        status_summary = ", ".join(
            f"{status} {count}"
            for status, count in sorted(statuses.items(), key=lambda item: (STATUS_ORDER.get(item[0], 99), item[0]))
        )
        lines.append(
            f"- {path_text}: /describe mutation hardening for {len(group)} active findings ({status_summary})"
        )
    lines.append(
        "Do we need to adjust any of these mutant backlog findings/next actions, or does this look good to launch?"
    )
    return "\n".join(lines)


def write_ledger(
    ledger_path: Path,
    repo_root: Path,
    findings: list[Finding],
    sources: list[Path],
) -> None:
    repo_root = repo_root.resolve()
    counts, todo_count = summarize(findings)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": now,
        "repo_root": repo_root.as_posix(),
        "summary": {
            "total": len(findings),
            "todo": todo_count,
            "status_counts": dict(sorted(counts.items())),
        },
        "sources": [relative_text(source, repo_root) for source in sources],
        "mutants": [
            {
                "key": finding.key,
                "adapter": finding.adapter,
                "status": finding.status,
                "effective_status": finding.effective_status,
                "todo": finding.todo,
                "path": finding.path.as_posix() if finding.path else None,
                "symbol": finding.symbol,
                "line": finding.line,
                "raw_id": finding.raw_id,
                "detail": finding.detail,
                "source": relative_text(finding.source, repo_root),
                "review_status": finding.review_status,
                "note": finding.note,
                "first_seen": finding.first_seen or now,
                "last_seen": now,
            }
            for finding in findings
        ],
    }
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    adapters, unsupported = requested_adapters(args.adapters)
    if unsupported:
        unsupported_list = ", ".join(sorted(unsupported))
        print(
            "Unsupported adapter selection: "
            f"{unsupported_list}. Supported adapters: cargo-mutants, mutmut, stryker, muter."
        )
        return 2

    selection_root = target if target.is_dir() else target.parent
    repo_root = resolve_project_root(selection_root)
    ledger_path = ledger_path_for(repo_root, args.ledger)
    findings, sources = collect_findings(repo_root, adapters)
    apply_reviews(findings, load_existing_reviews(ledger_path))
    findings.sort(key=sort_key)

    if args.write_ledger:
        write_ledger(ledger_path, repo_root, findings, sources)

    print(render_report(repo_root, findings, top=args.top, ledger_path=ledger_path, sources=sources))
    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(141)
