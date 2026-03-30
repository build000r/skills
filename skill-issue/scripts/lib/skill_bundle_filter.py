from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path


DEFAULT_EXCLUDE_PATTERNS = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    "*.pyc",
    "*.pyo",
    "*.skill",
    "*.zip",
    ".DS_Store",
)


def iter_included_skill_files(skill_path: Path):
    """Yield packageable skill files, excluding Git-ignored and junk artifacts."""
    skill_path = Path(skill_path).resolve()
    files = sorted((path.resolve() for path in skill_path.rglob("*") if path.is_file()), key=_sort_key)
    ignored = _resolve_gitignored_files(skill_path, files)
    fallback_patterns = _load_skill_local_ignore_patterns(skill_path)

    for file_path in files:
        rel_path = file_path.relative_to(skill_path).as_posix()
        if _matches_patterns(rel_path, DEFAULT_EXCLUDE_PATTERNS):
            continue
        if file_path in ignored:
            continue
        if not ignored and _matches_patterns(rel_path, fallback_patterns):
            continue
        yield file_path


def _resolve_gitignored_files(skill_path: Path, files: list[Path]) -> set[Path]:
    git_root = _find_git_root(skill_path)
    if git_root is None or not files:
        return set()

    repo_rel_paths = []
    path_by_repo_rel: dict[str, Path] = {}
    for file_path in files:
        try:
            repo_rel = file_path.relative_to(git_root).as_posix()
        except ValueError:
            continue
        repo_rel_paths.append(repo_rel)
        path_by_repo_rel[repo_rel] = file_path

    if not repo_rel_paths:
        return set()

    payload = "\0".join(repo_rel_paths) + "\0"
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        cwd=git_root,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return set()
    return {
        path_by_repo_rel[repo_rel]
        for repo_rel in result.stdout.split("\0")
        if repo_rel and repo_rel in path_by_repo_rel
    }


def _find_git_root(start_path: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _load_skill_local_ignore_patterns(skill_path: Path) -> set[str]:
    gitignore_path = skill_path / ".gitignore"
    if not gitignore_path.exists():
        return set()

    patterns = set()
    for line in gitignore_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.add(line.rstrip("/"))
    return patterns


def _matches_patterns(rel_path: str, patterns) -> bool:
    parts = Path(rel_path).parts
    name = Path(rel_path).name
    normalized_rel_path = rel_path.replace("\\", "/")
    for pattern in patterns:
        normalized_pattern = pattern.strip().rstrip("/")
        if not normalized_pattern:
            continue
        if normalized_pattern in parts or normalized_rel_path.startswith(f"{normalized_pattern}/"):
            return True
        if fnmatch(normalized_rel_path, normalized_pattern) or fnmatch(name, normalized_pattern):
            return True
    return False


def _sort_key(path: Path) -> str:
    return path.as_posix()
