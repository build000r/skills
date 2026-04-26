#!/usr/bin/env python3
"""
Analyze a repository for CRAP-style hotspots across Rust, Python, TypeScript, and Swift.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import os
import re
import signal
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SUPPORTED_LANGUAGES = ("rust", "python", "typescript", "swift")
LANGUAGE_EXTENSIONS = {
    "rust": {".rs"},
    "python": {".py"},
    "typescript": {".ts", ".tsx"},
    "swift": {".swift"},
}
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    ".build",
    "coverage",
    "dist",
    "build",
    "node_modules",
    "target",
    "vendor",
    "DerivedData",
    "Pods",
    "Carthage",
}


def should_ignore_dir(name: str, *, allow_coverage_dir: bool = False) -> bool:
    if allow_coverage_dir and name == "coverage":
        return False
    if name in IGNORED_DIRS:
        return True
    if name.startswith(".venv."):
        return True
    if name.startswith("DerivedData"):
        return True
    return False


@dataclass
class CoverageRecord:
    instrumented: set[int] = field(default_factory=set)
    covered: set[int] = field(default_factory=set)

    def add_line(self, number: int, hits: int) -> None:
        self.instrumented.add(number)
        if hits > 0:
            self.covered.add(number)

    def ratio_for_range(self, start_line: int, end_line: int) -> float | None:
        instrumented_count = 0
        covered_count = 0
        for line in range(start_line, end_line + 1):
            if line not in self.instrumented:
                continue
            instrumented_count += 1
            if line in self.covered:
                covered_count += 1

        if instrumented_count == 0:
            return None
        return covered_count / instrumented_count


@dataclass
class Finding:
    language: str
    path: Path
    symbol: str
    start_line: int
    end_line: int
    cc: int
    coverage: float | None
    crap: float | None


class CoverageIndex:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.records: dict[str, CoverageRecord] = {}
        self._key_cache: dict[tuple[str, str], list[str]] = {}

    def add_hit(self, raw_path: str, base_dir: Path, line_number: int, hits: int) -> None:
        keys = self._keys_for(raw_path, base_dir)
        if not keys:
            return

        primary = next(iter(keys))
        record = self.records.get(primary)
        if record is None:
            record = CoverageRecord()
            for key in keys:
                self.records[key] = record
        record.add_line(line_number, hits)

    def coverage_for(self, file_path: Path, start_line: int, end_line: int) -> float | None:
        keys = self._keys_for(file_path, file_path.parent)
        for key in keys:
            record = self.records.get(key)
            if record is None:
                continue
            ratio = record.ratio_for_range(start_line, end_line)
            if ratio is not None:
                return ratio
        return None

    def _keys_for(self, raw_path: str | Path, base_dir: Path) -> list[str]:
        cache_key = (str(raw_path), str(base_dir))
        cached = self._key_cache.get(cache_key)
        if cached is not None:
            return cached

        raw = Path(raw_path)
        candidates: list[Path] = []

        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.append((self.repo_root / raw).resolve())
            candidates.append((base_dir / raw).resolve())
            stripped = str(raw).lstrip("./")
            if stripped:
                candidates.append((self.repo_root / stripped).resolve())

        keys: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            if value not in seen:
                seen.add(value)
                keys.append(value)

        add(raw.as_posix())
        add(raw.name)

        for candidate in candidates:
            add(str(candidate))
            add(candidate.as_posix())
            if candidate.exists():
                resolved = candidate.resolve()
                add(str(resolved))
                add(resolved.as_posix())
            try:
                rel = candidate.relative_to(self.repo_root)
            except ValueError:
                continue
            add(rel.as_posix())

        self._key_cache[cache_key] = keys
        return keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Repository path or subdirectory to analyze (defaults to current directory).",
    )
    parser.add_argument(
        "--languages",
        default="",
        help="Comma-separated list from: rust, python, typescript, swift.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only display the top N ranked findings. FINAL_SCORE still uses all findings.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Optional target FINAL_SCORE threshold to echo in the report. The /crap skill defaults to 30 when omitted.",
    )
    return parser.parse_args()


def requested_languages(raw: str) -> tuple[list[str], list[str]]:
    if not raw.strip():
        return list(SUPPORTED_LANGUAGES), []

    requested = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unsupported = [language for language in requested if language not in SUPPORTED_LANGUAGES]
    supported = [language for language in requested if language in SUPPORTED_LANGUAGES]
    return supported, unsupported


def iter_supported_files(target: Path, languages: Iterable[str]) -> list[Path]:
    wanted_exts = set().union(*(LANGUAGE_EXTENSIONS[language] for language in languages))

    if target.is_file():
        return [target.resolve()] if target.suffix in wanted_exts else []

    found: list[Path] = []
    for current_root, dirs, files in os.walk(target):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d))
        root_path = Path(current_root)
        for name in sorted(files):
            path = root_path / name
            if path.suffix in wanted_exts:
                found.append(path.resolve())
    return found


def find_coverage_files(repo_root: Path) -> list[Path]:
    matches: list[Path] = []
    for current_root, dirs, files in os.walk(repo_root):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d, allow_coverage_dir=True))
        root_path = Path(current_root)
        for name in files:
            if name in {"lcov.info", "coverage.xml", "cobertura.xml"}:
                matches.append((root_path / name).resolve())
    return sorted(matches)


def resolve_project_root(selection_root: Path) -> Path:
    markers = {"lcov.info", "coverage.xml", "cobertura.xml", ".git", "Cargo.toml", "pyproject.toml", "package.json"}
    for candidate in [selection_root, *selection_root.parents]:
        if any((candidate / marker).exists() for marker in markers):
            return candidate.resolve()
    return selection_root.resolve()


def parse_lcov(path: Path, coverage: CoverageIndex) -> None:
    current_source: str | None = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("SF:"):
            current_source = line[3:].strip()
            continue
        if not current_source or not line.startswith("DA:"):
            continue

        payload = line[3:].split(",")
        if len(payload) < 2:
            continue

        try:
            line_number = int(payload[0])
            hits = int(payload[1])
        except ValueError:
            continue

        coverage.add_hit(current_source, path.parent, line_number, hits)


def parse_xml_coverage(path: Path, coverage: CoverageIndex) -> None:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return

    tag = root.tag.split("}")[-1].lower()
    if tag not in {"coverage", "report"}:
        return

    candidates: list[tuple[str, list[ET.Element]]] = []
    for element in root.iter():
        filename = element.attrib.get("filename") or element.attrib.get("name")
        if not filename:
            continue
        lines = [child for child in element.iter() if child.tag.split("}")[-1] == "line"]
        if lines:
            candidates.append((filename, lines))

    for filename, lines in candidates:
        for line in lines:
            number = line.attrib.get("number") or line.attrib.get("nr")
            hits = line.attrib.get("hits") or line.attrib.get("ci")
            if number is None or hits is None:
                continue
            try:
                line_number = int(number)
                hit_count = int(float(hits))
            except ValueError:
                continue
            coverage.add_hit(filename, path.parent, line_number, hit_count)


def load_coverage(repo_root: Path) -> CoverageIndex:
    coverage = CoverageIndex(repo_root)
    for coverage_file in find_coverage_files(repo_root):
        if coverage_file.name == "lcov.info":
            parse_lcov(coverage_file, coverage)
        else:
            parse_xml_coverage(coverage_file, coverage)
    return coverage


class PythonFunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_stack: list[str] = []
        self.functions: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prefix = ".".join(self.class_stack)
        name = f"{prefix}.{node.name}" if prefix else node.name
        self.functions.append((name, node))
        # Do not recurse into nested functions while collecting siblings.

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        prefix = ".".join(self.class_stack)
        name = f"{prefix}.{node.name}" if prefix else node.name
        self.functions.append((name, node))


class PythonComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.score = 1

    def visit_If(self, node: ast.If) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.score += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.score += len(node.handlers)
        if node.orelse:
            self.score += 1
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.score += max(0, len(node.cases) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.score += 1 + len(node.ifs)
        self.generic_visit(node)


def analyze_python(path: Path) -> list[tuple[str, int, int, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    collector = PythonFunctionCollector()
    collector.visit(tree)

    findings: list[tuple[str, int, int, int]] = []
    for symbol, node in collector.functions:
        visitor = PythonComplexityVisitor()
        for statement in node.body:
            visitor.visit(statement)
        findings.append((symbol, node.lineno, getattr(node, "end_lineno", node.lineno), visitor.score))
    return findings


def strip_code_like_text(text: str) -> str:
    result: list[str] = []
    i = 0
    length = len(text)
    state = "code"
    quote_char = ""

    def single_quote_closes_before_newline(start_index: int) -> bool:
        cursor = start_index + 1
        while cursor < length:
            current = text[cursor]
            if current == "\n":
                return False
            if current == "\\":
                cursor += 2
                continue
            if current == "'":
                return True
            cursor += 1
        return False

    while i < length:
        current = text[i]
        nxt = text[i + 1] if i + 1 < length else ""

        if state == "code":
            if current == "/" and nxt == "/":
                state = "line_comment"
                result.extend("  ")
                i += 2
                continue
            if current == "/" and nxt == "*":
                state = "block_comment"
                result.extend("  ")
                i += 2
                continue
            if current in {'"', "`"} or (
                current == "'" and single_quote_closes_before_newline(i)
            ):
                state = "string"
                quote_char = current
                result.append(" ")
                i += 1
                continue
            result.append(current)
            i += 1
            continue

        if state == "line_comment":
            result.append("\n" if current == "\n" else " ")
            if current == "\n":
                state = "code"
            i += 1
            continue

        if state == "block_comment":
            if current == "*" and nxt == "/":
                result.extend("  ")
                i += 2
                state = "code"
                continue
            result.append("\n" if current == "\n" else " ")
            i += 1
            continue

        if state == "string":
            if current == "\\":
                result.extend("  ")
                i += 2
                continue
            result.append("\n" if current == "\n" else " ")
            if current == quote_char:
                state = "code"
            i += 1
            continue

    return "".join(result)


def find_matching_brace(text: str, open_index: int, stripped: str | None = None) -> int | None:
    if stripped is None:
        stripped = strip_code_like_text(text)
    depth = 0
    for index in range(open_index, len(stripped)):
        if stripped[index] == "{":
            depth += 1
        elif stripped[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def extract_code_functions(text: str, patterns: Iterable[re.Pattern[str]]) -> list[tuple[str, int, int, int, str]]:
    functions: list[tuple[str, int, int, int, str]] = []
    seen_ranges: set[tuple[int, int]] = set()
    stripped = strip_code_like_text(text)
    line_starts = [0]
    line_starts.extend(match.end() for match in re.finditer(r"\n", text))

    def line_for(index: int) -> int:
        return bisect.bisect_right(line_starts, index)

    for pattern in patterns:
        for match in pattern.finditer(text):
            symbol = match.group("name")
            brace_index = text.find("{", match.end() - 1)
            if brace_index == -1:
                continue
            end_index = find_matching_brace(text, brace_index, stripped)
            if end_index is None:
                continue
            if (match.start(), end_index) in seen_ranges:
                continue
            seen_ranges.add((match.start(), end_index))
            start_line = line_for(match.start())
            end_line = line_for(end_index)
            body = text[brace_index + 1 : end_index]
            functions.append((symbol, start_line, end_line, brace_index, body))

    return sorted(functions, key=lambda item: (item[1], item[0]))


def decision_count(body: str, keywords: Iterable[str], include_question_mark: bool = False) -> int:
    stripped = strip_code_like_text(body)
    score = 1
    for keyword in keywords:
        score += len(re.findall(keyword, stripped))
    score += len(re.findall(r"&&|\|\|", stripped))
    if include_question_mark:
        score += len(re.findall(r"\?(?!\.)", stripped))
    return score


def analyze_rust(path: Path) -> list[tuple[str, int, int, int]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    patterns = [
        re.compile(r"\b(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b[^{;]*\{", re.MULTILINE),
    ]
    functions = extract_code_functions(text, patterns)
    return [
        (symbol, start_line, end_line, decision_count(body, [r"\bif\b", r"\bfor\b", r"\bwhile\b", r"\bloop\b", r"\bmatch\b"]))
        for symbol, start_line, end_line, _brace_index, body in functions
    ]


def analyze_typescript(path: Path) -> list[tuple[str, int, int, int]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    patterns = [
        re.compile(r"\bfunction\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*(?::[^{=]+)?\{", re.MULTILINE),
        re.compile(
            r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?=>\s*\{",
            re.MULTILINE,
        ),
    ]
    functions = extract_code_functions(text, patterns)
    return [
        (symbol, start_line, end_line, decision_count(body, [r"\bif\b", r"\bfor\b", r"\bwhile\b", r"\bcatch\b", r"\bcase\b"]))
        for symbol, start_line, end_line, _brace_index, body in functions
    ]


_LIZARD_WARNED = False


def analyze_swift(path: Path) -> list[tuple[str, int, int, int]]:
    try:
        import lizard  # type: ignore import-not-found
    except ImportError:
        global _LIZARD_WARNED
        if not _LIZARD_WARNED:
            print(
                "warning: lizard is required to analyze .swift files; skipping. "
                "Install with: pip install lizard",
                file=sys.stderr,
            )
            _LIZARD_WARNED = True
        return []

    try:
        info = lizard.analyze_file(str(path))
    except Exception:
        return []

    findings: list[tuple[str, int, int, int]] = []
    for func in info.function_list:
        findings.append(
            (func.name, func.start_line, func.end_line, func.cyclomatic_complexity)
        )
    return findings


def analyze_file(path: Path) -> list[tuple[str, int, int, int]]:
    suffix = path.suffix
    if suffix == ".py":
        return analyze_python(path)
    if suffix == ".rs":
        return analyze_rust(path)
    if suffix in {".ts", ".tsx"}:
        return analyze_typescript(path)
    if suffix == ".swift":
        return analyze_swift(path)
    return []


def detect_language(path: Path) -> str:
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        if path.suffix in extensions:
            return language
    raise ValueError(f"Unsupported file extension: {path}")


def crap_score(cc: int, coverage: float | None) -> float | None:
    if coverage is None:
        return None
    return cc * cc * ((1.0 - coverage) ** 3) + cc


def format_coverage(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def format_crap(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def sort_key(finding: Finding) -> tuple[int, float, str, str]:
    if finding.crap is None:
        return (1, 0.0, finding.path.as_posix(), finding.symbol)
    return (0, -finding.crap, finding.path.as_posix(), finding.symbol)


def derive_group(repo_root: Path, path: Path, language: str) -> str:
    rel_parts = path.relative_to(repo_root).parts
    if len(rel_parts) >= 2 and rel_parts[0] in {"crates", "services", "apps", "packages", "libs"}:
        area = rel_parts[1]
    elif "src" in rel_parts:
        src_index = rel_parts.index("src")
        area = rel_parts[src_index - 1] if src_index > 0 else path.stem
    else:
        area = path.parent.name or path.stem
    return f"{language}-{area.replace('_', '-')}"


def render_report(
    repo_root: Path,
    findings: list[Finding],
    top: int | None = None,
    threshold: float | None = None,
) -> str:
    displayed_findings = findings if top is None else findings[:top]
    if top is not None and top < len(findings):
        lines = [f"CRAP Report (top {len(displayed_findings)} of {len(findings)} findings)"]
    else:
        lines = ["CRAP Report"]

    for index, finding in enumerate(displayed_findings, start=1):
        rel_path = finding.path.relative_to(repo_root).as_posix()
        lines.append(
            f"{index}. CRAP {format_crap(finding.crap)} | coverage {format_coverage(finding.coverage)} | "
            f"CC {finding.cc} | {finding.language} | {rel_path}::{finding.symbol}"
        )

    numeric_scores = [finding.crap for finding in findings if finding.crap is not None]
    final_score = max(numeric_scores) if numeric_scores else 0.0
    if threshold is not None:
        status = "met" if final_score < threshold else "not met"
        lines.append(f"Threshold target: < {threshold:.2f} ({status})")
    lines.append(f"FINAL_SCORE: {final_score:.2f}")

    numeric_findings = [finding for finding in displayed_findings if finding.crap is not None]
    if not numeric_findings:
        return "\n".join(lines)

    group_to_findings: dict[str, list[Finding]] = {}
    for finding in numeric_findings:
        group = derive_group(repo_root, finding.path, finding.language)
        group_to_findings.setdefault(group, []).append(finding)

    ordered_groups = sorted(
        group_to_findings.items(),
        key=lambda item: (
            -max(finding.crap or 0.0 for finding in item[1]),
            item[0],
        ),
    )

    lines.append("")
    lines.append("Suggested /describe follow-on")
    for group, group_findings in ordered_groups:
        lead = max(group_findings, key=lambda finding: finding.crap or 0.0)
        rel_path = lead.path.relative_to(repo_root).as_posix()
        lines.append(
            f"- {group}: /describe remediation spec for {rel_path} hotspots "
            f"(top CRAP {lead.crap:.2f}, {len(group_findings)} finding{'s' if len(group_findings) != 1 else ''})"
        )

    group_names = ", ".join(group for group, _findings in ordered_groups)
    lines.append(
        f"- cross-language: /describe thresholds, coverage gaps, and launch recommendation across {group_names}"
    )
    if final_score < 30:
        lines.append(
            "- mutation-hardening: /mutate the top hotspot groups once the baseline test path is green; use survivors to drive stronger tests, then rerun CRAP toward < 8"
        )
    else:
        lines.append(
            "- mutation-hardening: defer /mutate until the scoped FINAL_SCORE is below 30 or the hotspot is otherwise stable enough to mutate economically"
        )
    lines.append(
        "Do we need to adjust any of these findings/next actions, or does this look good to launch?"
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    if args.threshold is not None and args.threshold <= 0:
        print(f"Threshold must be positive: {args.threshold}", file=sys.stderr)
        return 2

    languages, unsupported = requested_languages(args.languages)
    if unsupported:
        unsupported_list = ", ".join(sorted(unsupported))
        print(
            "Unsupported language selection: "
            f"{unsupported_list}. Supported languages: rust, python, typescript, swift."
        )
        return 2

    selection_root = target if target.is_dir() else target.parent
    repo_root = resolve_project_root(selection_root)
    supported_files = iter_supported_files(target, languages)
    if not supported_files:
        print("No supported files to analyze.")
        print("FINAL_SCORE: 0.00")
        return 0

    coverage = load_coverage(repo_root)
    findings: list[Finding] = []
    for file_path in supported_files:
        language = detect_language(file_path)
        for symbol, start_line, end_line, cc in analyze_file(file_path):
            finding_coverage = coverage.coverage_for(file_path, start_line, end_line)
            findings.append(
                Finding(
                    language=language,
                    path=file_path,
                    symbol=symbol,
                    start_line=start_line,
                    end_line=end_line,
                    cc=cc,
                    coverage=finding_coverage,
                    crap=crap_score(cc, finding_coverage),
                )
            )

    if not findings:
        print("No analyzable functions found in supported files.")
        print("FINAL_SCORE: 0.00")
        return 0

    findings.sort(key=sort_key)
    print(render_report(repo_root, findings, top=args.top, threshold=args.threshold))
    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(141)
