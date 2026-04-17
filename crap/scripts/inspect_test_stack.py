#!/usr/bin/env python3
"""
Inspect a repository scope for test and coverage prerequisites needed by /crap.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


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


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Repository path or narrowed package path to inspect (defaults to current directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the default text report.",
    )
    return parser.parse_args()


def iter_files(root: Path, pattern: str) -> list[Path]:
    matches: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d))
        root_path = Path(current_root)
        for name in sorted(files):
            if Path(name).match(pattern):
                matches.append((root_path / name).resolve())
    return matches


def has_descendant_match(root: Path, patterns: list[str]) -> bool:
    for pattern in patterns:
        if iter_files(root, pattern):
            return True
    return False


def discover_nested_manifests(root: Path) -> list[str]:
    manifest_names = {"pyproject.toml", "package.json", "Cargo.toml"}
    parents: set[Path] = set()

    for current_root, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d))
        root_path = Path(current_root)
        for name in files:
            if name in manifest_names:
                manifest_dir = (root_path / name).parent.resolve()
                if manifest_dir != root.resolve():
                    parents.add(manifest_dir)

    return sorted(path.relative_to(root.resolve()).as_posix() for path in parents)


def parse_make_targets(makefile_path: Path | None) -> set[str]:
    if makefile_path is None or not makefile_path.exists():
        return set()

    targets: set[str] = set()
    for line in read_text(makefile_path).splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?![=])", line)
        if match:
            targets.add(match.group(1))
    return targets


def detect_artifacts(root: Path) -> set[str]:
    artifacts: set[str] = set()
    wanted = {"coverage.xml", "cobertura.xml", "lcov.info"}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d, allow_coverage_dir=True))
        for name in files:
            if name in wanted:
                artifacts.add(name)
    return artifacts


@dataclass
class LaneReport:
    ecosystem: str
    manifest: str | None
    tests_present: bool
    runner_present: bool
    coverage_support_present: bool
    machine_artifact_present: bool
    preferred_wrapper: str
    recommended_mode: str
    suggested_targets: list[str]
    actions: list[str]


@dataclass
class RepoReport:
    scope: str
    makefile_present: bool
    make_targets: list[str]
    coverage_artifacts: list[str]
    nested_manifests: list[str]
    lanes: list[LaneReport]


def inspect_python(root: Path, make_targets: set[str], artifacts: set[str], makefile_present: bool) -> LaneReport | None:
    manifest = root / "pyproject.toml"
    python_files = iter_files(root, "*.py")
    if not manifest.exists() and not python_files:
        return None

    manifest_text = read_text(manifest).lower() if manifest.exists() else ""
    tests_present = (root / "tests").exists() or bool(iter_files(root, "test_*.py")) or bool(iter_files(root, "*_test.py"))
    runner_present = "pytest" in manifest_text or "[tool.pytest.ini_options]" in manifest_text or tests_present
    coverage_target_present = "pytest-cov-xml" in make_targets
    coverage_support_present = (
        "pytest-cov" in manifest_text
        or "coverage.xml" in artifacts
        or "cobertura.xml" in artifacts
        or coverage_target_present
    )
    machine_artifact_present = "coverage.xml" in artifacts or "cobertura.xml" in artifacts or coverage_target_present
    preferred_wrapper = "make" if makefile_present else "manifest"

    if machine_artifact_present:
        recommended_mode = "ready"
        actions = [
            "Reuse the existing pytest baseline and coverage lane for /crap reruns.",
            "Keep scope labels exact when narrowing to a package or path.",
        ]
    elif not tests_present or not runner_present:
        recommended_mode = "bootstrap-tests"
        actions = [
            "Add pytest and pytest-cov to the test dependency set.",
            "Create a narrow characterization test under tests/ around the hottest module or service path.",
            "Add a stable baseline entrypoint before CRAP remediation so the loop can rerun tests after each slice.",
            "Add an additive XML coverage target and rerun /crap once the baseline test path is green.",
        ]
    else:
        recommended_mode = "add-coverage-target"
        actions = [
            "Keep the fast-path pytest target intact.",
            "Add an additive XML coverage export target and write coverage.xml.",
            "Rerun the baseline test path, then the coverage target, then analyze_crap.py on the same scope.",
        ]

    suggested_targets = ["pytest", "pytest-cov", "pytest-cov-xml"] if preferred_wrapper == "make" else ["pytest", "coverage.xml"]

    return LaneReport(
        ecosystem="python",
        manifest="pyproject.toml" if manifest.exists() else None,
        tests_present=tests_present,
        runner_present=runner_present,
        coverage_support_present=coverage_support_present,
        machine_artifact_present=machine_artifact_present,
        preferred_wrapper=preferred_wrapper,
        recommended_mode=recommended_mode,
        suggested_targets=suggested_targets,
        actions=actions,
    )


def inspect_typescript(root: Path, make_targets: set[str], artifacts: set[str], makefile_present: bool) -> LaneReport | None:
    manifest = root / "package.json"
    ts_files = iter_files(root, "*.ts") + iter_files(root, "*.tsx")
    if not manifest.exists() and not ts_files:
        return None

    package_data: dict[str, object] = {}
    if manifest.exists():
        try:
            package_data = json.loads(read_text(manifest))
        except json.JSONDecodeError:
            package_data = {}

    scripts = package_data.get("scripts") or {}
    dependencies = package_data.get("dependencies") or {}
    dev_dependencies = package_data.get("devDependencies") or {}
    all_package_text = json.dumps([scripts, dependencies, dev_dependencies]).lower()

    tests_present = (
        (root / "tests").exists()
        or (root / "__tests__").exists()
        or has_descendant_match(root, ["*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx"])
    )
    runner_present = "vitest" in all_package_text or "jest" in all_package_text or tests_present
    coverage_target_present = "vitest-cov-lcov" in make_targets
    coverage_support_present = (
        "@vitest/coverage-v8" in all_package_text
        or "@vitest/coverage-istanbul" in all_package_text
        or "--coverage" in all_package_text
        or "lcov.info" in artifacts
        or coverage_target_present
    )
    machine_artifact_present = "lcov.info" in artifacts or coverage_target_present
    preferred_wrapper = "make" if makefile_present else "manifest"

    if machine_artifact_present:
        recommended_mode = "ready"
        actions = [
            "Reuse the existing test baseline and lcov lane for /crap reruns.",
            "Keep scope labels exact when narrowing to a package or path.",
        ]
    elif not tests_present or not runner_present:
        recommended_mode = "bootstrap-tests"
        actions = [
            "Add Vitest plus one coverage provider package.",
            "Create a narrow .test.ts or .spec.ts file around the hottest module.",
            "Add a stable test entrypoint before CRAP remediation so the loop can rerun tests after each slice.",
            "Add an additive lcov target and rerun /crap once the baseline test path is green.",
        ]
    else:
        recommended_mode = "add-coverage-target"
        actions = [
            "Keep the fast-path test script intact.",
            "Add an additive coverage run that writes lcov.info.",
            "Rerun the baseline test path, then the coverage target, then analyze_crap.py on the same scope.",
        ]

    suggested_targets = ["vitest", "vitest-cov-lcov"] if preferred_wrapper == "make" else ["test", "test:cov"]

    return LaneReport(
        ecosystem="typescript",
        manifest="package.json" if manifest.exists() else None,
        tests_present=tests_present,
        runner_present=runner_present,
        coverage_support_present=coverage_support_present,
        machine_artifact_present=machine_artifact_present,
        preferred_wrapper=preferred_wrapper,
        recommended_mode=recommended_mode,
        suggested_targets=suggested_targets,
        actions=actions,
    )


def _has_xcresult_bundle(root: Path) -> bool:
    for current_root, dirs, _files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d, allow_coverage_dir=True))
        for name in dirs:
            if name.endswith(".xcresult"):
                return True
    return False


def inspect_swift(root: Path, make_targets: set[str], artifacts: set[str], makefile_present: bool) -> LaneReport | None:
    swift_files = iter_files(root, "*.swift")
    package_swift = root / "Package.swift"
    xcodeproj = sorted(list(root.glob("*.xcodeproj")) + list(root.glob("*.xcworkspace")))
    if not swift_files and not package_swift.exists() and not xcodeproj:
        return None

    if package_swift.exists():
        manifest_label: str | None = "Package.swift"
    elif xcodeproj:
        manifest_label = xcodeproj[0].name
    else:
        manifest_label = None

    xcresult_present = _has_xcresult_bundle(root)
    xcresultparser_present = shutil.which("xcresultparser") is not None

    tests_present = any(
        "Tests" in p.parts or p.name.endswith("Tests.swift") for p in swift_files
    )
    runner_present = bool(xcodeproj) or package_swift.exists() or tests_present
    coverage_target_present = "crap-swift-cobertura" in make_targets
    machine_artifact_present = (
        "coverage.xml" in artifacts
        or "cobertura.xml" in artifacts
        or coverage_target_present
    )
    coverage_support_present = machine_artifact_present or xcresult_present

    preferred_wrapper = "make" if makefile_present else "manifest"

    if machine_artifact_present:
        recommended_mode = "ready"
        actions = [
            "Reuse the existing Swift baseline and coverage lane for /crap reruns.",
            "Keep scope labels exact when narrowing to a scheme or target.",
        ]
    elif not tests_present or not runner_present:
        recommended_mode = "bootstrap-tests"
        actions = [
            "Add an XCTest target around the hottest Swift module.",
            "Use xcodebuild test as the stable baseline before CRAP remediation slices.",
            "Install xcresultparser (brew install xcresultparser) before adding the coverage target.",
            "Add the crap-swift-cobertura target once the baseline test path is green.",
        ]
    else:
        recommended_mode = "add-coverage-target"
        actions = [
            "Keep the fast-path xcodebuild test entrypoint intact.",
            "Add an additive crap-swift-cobertura target that writes coverage.xml from the .xcresult bundle.",
            "Install lizard (pip install lizard) so the Swift analyzer lane is active.",
        ]
        if not xcresultparser_present:
            actions.append("xcresultparser not on PATH — install with: brew install xcresultparser.")

    suggested_targets = (
        ["test", "crap-swift-cobertura"]
        if preferred_wrapper == "make"
        else ["xcodebuild test", "xcresultparser -o cobertura"]
    )

    return LaneReport(
        ecosystem="swift",
        manifest=manifest_label,
        tests_present=tests_present,
        runner_present=runner_present,
        coverage_support_present=coverage_support_present,
        machine_artifact_present=machine_artifact_present,
        preferred_wrapper=preferred_wrapper,
        recommended_mode=recommended_mode,
        suggested_targets=suggested_targets,
        actions=actions,
    )


def inspect_rust(root: Path, make_targets: set[str], artifacts: set[str], makefile_present: bool) -> LaneReport | None:
    manifest = root / "Cargo.toml"
    rust_files = iter_files(root, "*.rs")
    if not manifest.exists() and not rust_files:
        return None

    tests_present = (root / "tests").exists() or any("#[cfg(test)]" in read_text(path) for path in rust_files)
    runner_present = manifest.exists() or tests_present
    coverage_target_present = "cargo-cov-lcov" in make_targets
    coverage_support_present = "lcov.info" in artifacts or coverage_target_present
    machine_artifact_present = "lcov.info" in artifacts or coverage_target_present
    preferred_wrapper = "make" if makefile_present else "manifest"

    if machine_artifact_present:
        recommended_mode = "ready"
        actions = [
            "Reuse the existing cargo test baseline and lcov lane for /crap reruns.",
            "Keep scope labels exact when narrowing to a crate or path.",
        ]
    elif not tests_present:
        recommended_mode = "bootstrap-tests"
        actions = [
            "Add a narrow unit or integration test around the hottest function or module path.",
            "Use cargo test as the stable baseline before CRAP remediation slices.",
            "Add a cargo llvm-cov lcov target once the baseline test path is green.",
        ]
    else:
        recommended_mode = "add-coverage-target"
        actions = [
            "Keep the fast-path cargo test entrypoint intact.",
            "Add an additive cargo llvm-cov target that writes lcov.info.",
            "If cargo llvm-cov is missing, install it before rerunning /crap.",
        ]

    suggested_targets = ["test", "cargo-cov-lcov"] if preferred_wrapper == "make" else ["cargo test", "cargo llvm-cov --lcov --output-path lcov.info"]

    return LaneReport(
        ecosystem="rust",
        manifest="Cargo.toml" if manifest.exists() else None,
        tests_present=tests_present,
        runner_present=runner_present,
        coverage_support_present=coverage_support_present,
        machine_artifact_present=machine_artifact_present,
        preferred_wrapper=preferred_wrapper,
        recommended_mode=recommended_mode,
        suggested_targets=suggested_targets,
        actions=actions,
    )


def inspect_repo(root: Path) -> RepoReport:
    root = root.resolve()
    makefile = root / "Makefile"
    make_targets = parse_make_targets(makefile if makefile.exists() else None)
    artifacts = detect_artifacts(root)

    lanes = [
        lane
        for lane in (
            inspect_python(root, make_targets, artifacts, makefile.exists()),
            inspect_typescript(root, make_targets, artifacts, makefile.exists()),
            inspect_rust(root, make_targets, artifacts, makefile.exists()),
            inspect_swift(root, make_targets, artifacts, makefile.exists()),
        )
        if lane is not None
    ]

    return RepoReport(
        scope=str(root),
        makefile_present=makefile.exists(),
        make_targets=sorted(make_targets),
        coverage_artifacts=sorted(artifacts),
        nested_manifests=discover_nested_manifests(root),
        lanes=lanes,
    )


def render_text(report: RepoReport) -> str:
    lines = [
        f"Scope: {report.scope}",
        f"Makefile: {'present' if report.makefile_present else 'absent'}",
        "Coverage artifacts: " + (", ".join(report.coverage_artifacts) if report.coverage_artifacts else "none"),
    ]

    if report.nested_manifests:
        lines.append("Nested manifests: " + ", ".join(report.nested_manifests))
        lines.append(
            "Scope note: narrow to one manifest-owning package when root automation is too thin for a trustworthy baseline."
        )

    if not report.lanes:
        lines.append("Supported ecosystems: none detected")
        return "\n".join(lines)

    for lane in report.lanes:
        lines.extend(
            [
                "",
                f"Lane: {lane.ecosystem}",
                f"  Manifest: {lane.manifest or 'not found at scope root'}",
                f"  Tests present: {'yes' if lane.tests_present else 'no'}",
                f"  Runner present: {'yes' if lane.runner_present else 'no'}",
                f"  Machine coverage artifact: {'yes' if lane.machine_artifact_present else 'no'}",
                f"  Preferred wrapper: {lane.preferred_wrapper}",
                f"  Recommendation: {lane.recommended_mode}",
                "  Suggested targets: " + ", ".join(lane.suggested_targets),
                "  Next actions:",
            ]
        )
        for action in lane.actions:
            lines.append(f"  - {action}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = inspect_repo(Path(args.target))
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
