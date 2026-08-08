#!/usr/bin/env python3
"""Run a mutation transaction behind provider-neutral writer-session fences."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence
import uuid


SCHEMA = "commit-writer-session/v1"
CAPABILITIES_SCHEMA = "commit-writer-session-runner-capabilities/v1"
RUNNER_CAPABILITIES = (
    "acquisition-sealing-v1",
    "policy-home-v1",
    "receipt-bound-single-pinned-recovery-v1",
)
SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
DEFAULT_PROVIDER = "commit-writer-session-provider"
PROVIDERS_ENV = "COMMIT_WRITER_SESSION_PROVIDERS"
REQUIRED_ENV = "COMMIT_WRITER_SESSION_REQUIRE_PROVIDER"
POLICY_HOME_ENV = "COMMIT_WRITER_SESSION_POLICY_HOME"
POLICY_FILE = ".commit-writer-session.json"
POLICY_SCHEMA = "commit-writer-session-policy/v1"
VERDICT_WEIGHT = {"allow": 0, "indeterminate": 1, "blocked": 2}
MAX_PROVIDER_SOURCE_BYTES = 8 * 1024 * 1024
MAX_PROVIDER_REQUEST_BYTES = 64 * 1024
SAFE_MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
SAFE_RESOURCE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESOURCE_PLACEHOLDER_RE = re.compile(r"^\{resource:([A-Za-z_][A-Za-z0-9_]*)\}$")
SEALED_PYTHON_SOURCE_BOOTSTRAP = r'''import hashlib, importlib.util, os, sys, types
def read_source(fd):
    chunks = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(fd)
    return b"".join(chunks)

entry_fd = int(sys.argv[1])
repo_root = os.path.realpath(sys.argv[2])
module_count = int(sys.argv[3])
offset = 4
modules = []
for _ in range(module_count):
    name, fd = sys.argv[offset:offset + 2]
    modules.append((name, int(fd)))
    offset += 2
program_argv = sys.argv[offset:]
def inside_repo(path):
    resolved = os.path.realpath(path or os.getcwd())
    return resolved == repo_root or resolved.startswith(repo_root + os.sep)
sys.path[:] = [
    item for item in sys.path
    if item and not inside_repo(item)
]
pythonpath = os.environ.get("PYTHONPATH")
if pythonpath is not None:
    safe_pythonpath = [
        item for item in pythonpath.split(os.pathsep)
        if item and not inside_repo(item)
    ]
    if safe_pythonpath:
        os.environ["PYTHONPATH"] = os.pathsep.join(safe_pythonpath)
    else:
        os.environ.pop("PYTHONPATH", None)
for name, fd in modules:
    source_path = "<sealed-module:" + name + ">"
    source = read_source(fd)
    module = types.ModuleType(name)
    module.__file__ = source_path
    module.__package__ = name.rpartition(".")[0]
    module.__loader__ = None
    module.__spec__ = importlib.util.spec_from_loader(name, loader=None, origin=source_path)
    module._HELD_SOURCE_SHA256 = hashlib.sha256(source).hexdigest()
    sys.modules[name] = module
    exec(compile(source, source_path, "exec"), module.__dict__, module.__dict__)
entry_source = read_source(entry_fd)
entry_path = "<sealed-provider-entry>"
sys.argv = [entry_path, *program_argv]
globals_dict = {
    "__name__": "__main__",
    "__file__": entry_path,
    "__package__": None,
    "__cached__": None,
    "_HELD_SOURCE_SHA256": hashlib.sha256(entry_source).hexdigest(),
}
exec(compile(entry_source, entry_path, "exec"), globals_dict)
'''

EXIT_USAGE = 64
EXIT_PROVIDER_REQUIRED = 69
EXIT_BLOCKED = 70
EXIT_INDETERMINATE = 71
EXIT_RELEASE_FAILED = 72


class ConfigurationError(ValueError):
    """The local runner configuration is invalid."""


class SchemaError(ValueError):
    """A provider response does not satisfy commit-writer-session/v1."""


@dataclass(frozen=True)
class ProviderModule:
    name: str
    source_path: Path
    source_sha256: str


@dataclass(frozen=True)
class ProviderResource:
    name: str
    source_path: Path
    source_sha256: str


@dataclass(frozen=True)
class Provider:
    argv: tuple[str, ...]
    label: str
    source_path: Path | None = None
    source_sha256: str | None = None
    modules: tuple[ProviderModule, ...] = ()
    resources: tuple[ProviderResource, ...] = ()
    repository_root: Path | None = None


@dataclass(frozen=True)
class HeldSource:
    """Provider bytes verified once, at acquisition, and never re-read from disk."""

    label: str
    name: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class HeldProviderSources:
    entry: HeldSource
    modules: tuple[HeldSource, ...] = ()
    resources: tuple[HeldSource, ...] = ()

    def digests(self) -> dict[str, str]:
        return {
            held.label: held.sha256
            for held in (self.entry, *self.modules, *self.resources)
        }


@dataclass
class ProviderState:
    provider: Provider
    request_id: str
    begin: dict[str, Any] | None = None
    session: dict[str, str] | None = None
    held: HeldProviderSources | None = None


def provider_identity_sha256(provider: Provider) -> str:
    """Stable provider topology identity; source contents may upgrade."""

    payload = {
        "argv": list(provider.argv),
        "entry": str(provider.source_path) if provider.source_path is not None else None,
        "modules": [
            {"name": module.name, "source": str(module.source_path)}
            for module in provider.modules
        ],
        "resources": [
            {"name": resource.name, "source": str(resource.source_path)}
            for resource in provider.resources
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_from_argv(value: Any, *, source: str, position: int) -> Provider:
    if isinstance(value, str):
        argv = (value,)
    elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        argv = tuple(value)
    else:
        raise ConfigurationError(
            f"{source} entry {position} must be an executable string or a non-empty JSON argv array"
        )
    if not argv[0] or any(not item for item in argv):
        raise ConfigurationError(f"{source} entry {position} contains an empty argv item")
    return Provider(argv=argv, label=f"{Path(argv[0]).name}#{position}")


def _repo_relative_path(repo: Path, raw: Any, *, field: str) -> Path:
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or Path(raw).is_absolute()
        or any(part in {"", ".", ".."} for part in Path(raw).parts)
    ):
        raise ConfigurationError(f"repository policy {field} must be a safe repo-relative path")
    resolved = (repo / raw).resolve(strict=False)
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise ConfigurationError(f"repository policy {field} escapes the repository") from exc
    return resolved


def _expand_policy_argv(repo: Path, values: Any, *, position: int) -> tuple[str, ...]:
    if not isinstance(values, list) or not values or not all(
        isinstance(value, str) and value for value in values
    ):
        raise ConfigurationError(
            f"repository policy provider {position} argv must be a non-empty string array"
        )
    expanded: list[str] = []
    for value in values:
        if value == "{python}":
            expanded.append(sys.executable)
        elif value == "{repo}":
            expanded.append(str(repo))
        elif value.startswith("{repo}/"):
            expanded.append(
                str(_repo_relative_path(repo, value[len("{repo}/") :], field="argv path"))
            )
        elif RESOURCE_PLACEHOLDER_RE.fullmatch(value):
            expanded.append(value)
        elif "{" in value or "}" in value:
            raise ConfigurationError(
                f"repository policy provider {position} uses an unsupported argv placeholder"
            )
        else:
            expanded.append(value)
    return tuple(expanded)


def _verify_provider_source(provider: Provider) -> None:
    if provider.source_path is None:
        return
    assert provider.source_sha256 is not None
    sources = [
        ("entry", provider.source_path, provider.source_sha256),
        *[(f"module {module.name}", module.source_path, module.source_sha256) for module in provider.modules],
        *[(f"resource {resource.name}", resource.source_path, resource.source_sha256) for resource in provider.resources],
    ]
    for label, source_path, source_sha256 in sources:
        try:
            metadata = source_path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise ConfigurationError(f"provider {label} source is not a regular non-symlink file: {source_path}")
            content = source_path.read_bytes()
        except OSError as exc:
            raise ConfigurationError(f"provider {label} source is unavailable: {source_path}: {exc}") from exc
        if len(content) > MAX_PROVIDER_SOURCE_BYTES:
            raise ConfigurationError(f"provider {label} source is oversized: {source_path}")
        if hashlib.sha256(content).hexdigest() != source_sha256:
            raise ConfigurationError(f"provider {label} source digest does not match repository policy: {source_path}")


def _git_bytes(repo: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            shell=False,
        )
    except OSError as exc:
        raise ConfigurationError(f"repository policy Git read failed: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ConfigurationError(detail or "repository policy Git read failed")
    return completed.stdout


def _head_policy(repo: Path) -> bytes | None:
    head_oid = _git(repo, "rev-parse", "--verify", "HEAD", allow_failure=True)
    if head_oid is None:
        return None
    listing = _git_bytes(repo, "ls-tree", "-z", head_oid, "--", POLICY_FILE)
    records = [record for record in listing.split(b"\0") if record]
    if not records:
        return None
    if len(records) != 1:
        raise ConfigurationError("committed repository policy identity is ambiguous")
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, object_type, object_id = metadata.split(b" ", 2)
    except ValueError as exc:
        raise ConfigurationError("committed repository policy identity is malformed") from exc
    if raw_path != POLICY_FILE.encode() or mode != b"100644" or object_type != b"blob":
        raise ConfigurationError("committed repository policy is not one regular non-executable blob")
    return _git_bytes(repo, "cat-file", "blob", object_id.decode("ascii"))


def _index_policy(repo: Path) -> bytes | None:
    listing = _git_bytes(repo, "ls-files", "--stage", "-z", "--", POLICY_FILE)
    records = [record for record in listing.split(b"\0") if record]
    if not records:
        return None
    if len(records) != 1:
        raise ConfigurationError("index repository policy identity is ambiguous")
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, object_id, stage = metadata.split(b" ", 2)
    except ValueError as exc:
        raise ConfigurationError("index repository policy identity is malformed") from exc
    if raw_path != POLICY_FILE.encode() or mode != b"100644" or stage != b"0":
        raise ConfigurationError("index repository policy is conflicted or not one regular blob")
    return _git_bytes(repo, "cat-file", "blob", object_id.decode("ascii"))


def _worktree_policy(repo: Path) -> bytes | None:
    policy_path = repo / POLICY_FILE
    try:
        metadata = policy_path.lstat()
    except FileNotFoundError:
        return None
    try:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ConfigurationError("repository writer-session policy must be a regular non-symlink file")
        raw = policy_path.read_bytes()
    except OSError as exc:
        raise ConfigurationError(f"repository writer-session policy is unavailable: {exc}") from exc
    if len(raw) > 64 * 1024:
        raise ConfigurationError("repository writer-session policy is oversized")
    return raw


def _strict_policy_document(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > 64 * 1024:
        raise ConfigurationError(f"{label} repository writer-session policy is oversized")
    try:
        policy = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"{label} repository writer-session policy is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(policy, dict) or set(policy) != {"schema", "required", "providers"}:
        raise ConfigurationError(f"{label} repository writer-session policy has an unexpected schema")
    if policy.get("schema") != POLICY_SCHEMA or policy.get("required") is not True:
        raise ConfigurationError(f"{label} repository writer-session policy must be strict and required")
    records = policy.get("providers")
    if not isinstance(records, list) or not records:
        raise ConfigurationError(f"{label} repository writer-session policy requires at least one provider")
    return policy


def _policy_bytes(repo: Path) -> bytes | None:
    """Bind managed status to HEAD and require unambiguous index/worktree agreement."""

    head = _head_policy(repo)
    index = _index_policy(repo)
    worktree = _worktree_policy(repo)
    if head is not None:
        _strict_policy_document(head, label="committed")
        if index is None or worktree is None:
            raise ConfigurationError("committed repository writer-session policy is missing from index or worktree")
        if index != worktree:
            raise ConfigurationError("index and worktree writer-session policies disagree")
        return worktree
    if index is None and worktree is None:
        return None
    if worktree is None:
        raise ConfigurationError("new index repository writer-session policy is missing from worktree")
    if index is not None and index != worktree:
        raise ConfigurationError("new index and worktree writer-session policies disagree")
    return worktree


def discover_repository_policy(repo: Path) -> tuple[list[Provider], bool]:
    """Load a strict repo-local policy without allowing ambient discovery to replace it."""

    raw = _policy_bytes(repo)
    if raw is None:
        return [], False
    policy = _strict_policy_document(raw, label="current")
    records = policy["providers"]

    providers: list[Provider] = []
    for position, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {
            "argv",
            "source",
            "source_sha256",
            "modules",
            "resources",
        }:
            raise ConfigurationError(
                f"repository policy provider {position} has an unexpected schema"
            )
        source_raw = record.get("source")
        source_path = _repo_relative_path(repo, source_raw, field="provider source")
        source_sha256 = record.get("source_sha256")
        if (
            not isinstance(source_sha256, str)
            or len(source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in source_sha256)
        ):
            raise ConfigurationError(
                f"repository policy provider {position} source_sha256 is malformed"
            )
        argv = _expand_policy_argv(repo, record.get("argv"), position=position)
        expected_source_argv = str(source_path)
        if argv.count(expected_source_argv) != 1:
            raise ConfigurationError(
                f"repository policy provider {position} must bind its pinned source exactly once in argv"
            )
        if len(argv) < 2 or argv[0] != sys.executable or argv[1] != expected_source_argv:
            raise ConfigurationError(
                f"repository policy provider {position} must use {{python}} followed by its pinned source"
            )
        module_records = record.get("modules")
        if not isinstance(module_records, list):
            raise ConfigurationError(
                f"repository policy provider {position} modules must be an ordered array"
            )
        modules: list[ProviderModule] = []
        seen_names: set[str] = set()
        seen_paths = {source_path}
        for module_position, module_record in enumerate(module_records):
            if not isinstance(module_record, dict) or set(module_record) != {
                "name",
                "source",
                "source_sha256",
            }:
                raise ConfigurationError(
                    f"repository policy provider {position} module {module_position} has an unexpected schema"
                )
            name = module_record.get("name")
            if (
                not isinstance(name, str)
                or SAFE_MODULE_NAME_RE.fullmatch(name) is None
                or name in {"__main__", "builtins"}
                or name in seen_names
            ):
                raise ConfigurationError(
                    f"repository policy provider {position} module {module_position} name is unsafe or duplicate"
                )
            module_path = _repo_relative_path(
                repo,
                module_record.get("source"),
                field=f"provider module {name} source",
            )
            if module_path in seen_paths:
                raise ConfigurationError(
                    f"repository policy provider {position} module {name} source is duplicate"
                )
            module_sha256 = module_record.get("source_sha256")
            if (
                not isinstance(module_sha256, str)
                or len(module_sha256) != 64
                or any(character not in "0123456789abcdef" for character in module_sha256)
            ):
                raise ConfigurationError(
                    f"repository policy provider {position} module {name} source_sha256 is malformed"
                )
            seen_names.add(name)
            seen_paths.add(module_path)
            modules.append(
                ProviderModule(
                    name=name,
                    source_path=module_path,
                    source_sha256=module_sha256,
                )
            )
        resource_records = record.get("resources")
        if not isinstance(resource_records, list):
            raise ConfigurationError(
                f"repository policy provider {position} resources must be an array"
            )
        resources: list[ProviderResource] = []
        seen_resource_names: set[str] = set()
        for resource_position, resource_record in enumerate(resource_records):
            if not isinstance(resource_record, dict) or set(resource_record) != {
                "name",
                "source",
                "source_sha256",
            }:
                raise ConfigurationError(
                    f"repository policy provider {position} resource {resource_position} has an unexpected schema"
                )
            name = resource_record.get("name")
            if (
                not isinstance(name, str)
                or SAFE_RESOURCE_NAME_RE.fullmatch(name) is None
                or name in seen_resource_names
            ):
                raise ConfigurationError(
                    f"repository policy provider {position} resource {resource_position} name is unsafe or duplicate"
                )
            resource_path = _repo_relative_path(
                repo,
                resource_record.get("source"),
                field=f"provider resource {name} source",
            )
            if resource_path in seen_paths:
                raise ConfigurationError(
                    f"repository policy provider {position} resource {name} source is duplicate"
                )
            resource_sha256 = resource_record.get("source_sha256")
            if (
                not isinstance(resource_sha256, str)
                or len(resource_sha256) != 64
                or any(character not in "0123456789abcdef" for character in resource_sha256)
            ):
                raise ConfigurationError(
                    f"repository policy provider {position} resource {name} source_sha256 is malformed"
                )
            seen_resource_names.add(name)
            seen_paths.add(resource_path)
            resources.append(
                ProviderResource(
                    name=name,
                    source_path=resource_path,
                    source_sha256=resource_sha256,
                )
            )
        placeholders = [
            match.group(1)
            for value in argv
            if (match := RESOURCE_PLACEHOLDER_RE.fullmatch(value)) is not None
        ]
        if sorted(placeholders) != sorted(seen_resource_names) or len(placeholders) != len(set(placeholders)):
            raise ConfigurationError(
                f"repository policy provider {position} must reference every declared resource exactly once"
            )
        provider = Provider(
            argv=argv,
            label=f"repository-policy#{position}",
            source_path=source_path,
            source_sha256=source_sha256,
            modules=tuple(modules),
            resources=tuple(resources),
            repository_root=repo,
        )
        _verify_provider_source(provider)
        providers.append(provider)
    return providers, True


def _parse_json_argv(value: str, *, source: str, position: int) -> Provider:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{source} entry {position} is not valid JSON: {exc.msg}") from exc
    return _provider_from_argv(decoded, source=source, position=position)


def discover_providers(
    *,
    executables: Sequence[str] = (),
    json_commands: Sequence[str] = (),
    environ: Mapping[str, str] | None = None,
) -> list[Provider]:
    """Discover provider argv without interpreting any value as shell text.

    Explicit CLI providers take precedence over the environment. The environment
    takes precedence over the conventional PATH executable.
    """

    env = os.environ if environ is None else environ
    providers: list[Provider] = []
    if executables or json_commands:
        for position, executable in enumerate(executables):
            providers.append(
                _provider_from_argv(executable, source="--provider", position=position)
            )
        offset = len(providers)
        for position, command in enumerate(json_commands, start=offset):
            providers.append(
                _parse_json_argv(command, source="--provider-json", position=position)
            )
        return providers

    configured = env.get(PROVIDERS_ENV)
    if configured is not None:
        try:
            decoded = json.loads(configured)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"{PROVIDERS_ENV} is not valid JSON: {exc.msg}") from exc
        if not isinstance(decoded, list):
            raise ConfigurationError(f"{PROVIDERS_ENV} must be a JSON array")
        return [
            _provider_from_argv(entry, source=PROVIDERS_ENV, position=position)
            for position, entry in enumerate(decoded)
        ]

    discovered = shutil.which(DEFAULT_PROVIDER, path=env.get("PATH"))
    if discovered:
        providers.append(Provider(argv=(discovered,), label=f"{DEFAULT_PROVIDER}#0"))
    return providers


def _git(repo: Path, *args: str, allow_failure: bool = False) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        if allow_failure:
            return None
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ConfigurationError(detail)
    return completed.stdout.strip()


def repository_identity(repo: Path) -> dict[str, str | None]:
    root_text = _git(repo, "rev-parse", "--show-toplevel")
    assert root_text is not None
    root = Path(root_text).resolve()
    git_dir_text = _git(root, "rev-parse", "--absolute-git-dir")
    common_dir_text = _git(root, "rev-parse", "--git-common-dir")
    assert git_dir_text is not None and common_dir_text is not None
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = root / common_dir
    return {
        "root": str(root),
        "git_dir": str(Path(git_dir_text).resolve()),
        "git_common_dir": str(common_dir.resolve()),
        "head_oid": _git(root, "rev-parse", "--verify", "HEAD", allow_failure=True),
        "head_ref": _git(root, "symbolic-ref", "-q", "HEAD", allow_failure=True),
    }


def _request(
    *,
    operation: str,
    request_id: str,
    repository: Mapping[str, str | None],
    session: Mapping[str, str] | None,
    step_count: int,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "request_id": request_id,
        "operation": operation,
        "repository": dict(repository),
        "session": dict(session) if session is not None else None,
        "transaction": {"step_count": step_count},
    }


def _read_verified_source(path: Path, expected_sha256: str, *, label: str) -> bytes:
    held_fd: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        held_fd = os.open(path, flags)
        before = os.fstat(held_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PROVIDER_SOURCE_BYTES:
            raise ConfigurationError(f"provider {label} source is not a bounded regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(held_fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(held_fd)
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        content = b"".join(chunks)
        if (
            any(getattr(before, field) != getattr(after, field) for field in identity_fields)
            or len(content) != before.st_size
        ):
            raise ConfigurationError(f"provider {label} source changed while it was being read")
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ConfigurationError(
                f"provider {label} source digest does not match repository policy"
            )
        return content
    finally:
        if held_fd is not None:
            os.close(held_fd)


def _seal_verified_source(content: bytes, *, label: str) -> int:
    writer_fd: int | None = None
    reader_fd: int | None = None
    snapshot_path: str | None = None
    try:
        writer_fd, snapshot_path = tempfile.mkstemp(
            prefix="commit-provider-", suffix=".sealed"
        )
        written = 0
        while written < len(content):
            count = os.write(writer_fd, content[written:])
            if count < 1:
                raise ConfigurationError(f"provider {label} snapshot write was incomplete")
            written += count
        os.fsync(writer_fd)
        writer_metadata = os.fstat(writer_fd)
        read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        reader_fd = os.open(snapshot_path, read_flags)
        reader_metadata = os.fstat(reader_fd)
        if (
            writer_metadata.st_dev != reader_metadata.st_dev
            or writer_metadata.st_ino != reader_metadata.st_ino
            or reader_metadata.st_size != len(content)
            or not stat.S_ISREG(reader_metadata.st_mode)
        ):
            raise ConfigurationError(f"provider {label} snapshot identity is ambiguous")
        os.unlink(snapshot_path)
        snapshot_path = None
        os.close(writer_fd)
        writer_fd = None
        result = reader_fd
        reader_fd = None
        return result
    finally:
        if writer_fd is not None:
            os.close(writer_fd)
        if reader_fd is not None:
            os.close(reader_fd)
        if snapshot_path is not None:
            try:
                os.unlink(snapshot_path)
            except FileNotFoundError:
                pass


def hold_provider_sources(provider: Provider) -> HeldProviderSources | None:
    """Read and verify every pinned source exactly once, at acquisition.

    The runner used to re-read these files on every provider call, including the
    ``end`` call in its release path. A protected step that legitimately rewrote a
    pinned source (``git pull``, or a commit that lands a new provider revision)
    therefore poisoned its own release: the mutation landed, ``end`` failed with a
    digest mismatch, and the durable lease was left ``held``. Holding the verified
    bytes for the life of the transaction means the process executes exactly what
    it verified at acquisition, and on-disk churn afterwards can no longer strand a
    lease. The bytes are bounded by MAX_PROVIDER_SOURCE_BYTES per source.
    """

    if provider.source_path is None:
        return None
    assert provider.source_sha256 is not None
    entry = HeldSource(
        label="entry",
        name="",
        sha256=provider.source_sha256,
        content=_read_verified_source(
            provider.source_path, provider.source_sha256, label="entry"
        ),
    )
    modules = tuple(
        HeldSource(
            label=f"module {module.name}",
            name=module.name,
            sha256=module.source_sha256,
            content=_read_verified_source(
                module.source_path, module.source_sha256, label=f"module {module.name}"
            ),
        )
        for module in provider.modules
    )
    resources = tuple(
        HeldSource(
            label=f"resource {resource.name}",
            name=resource.name,
            sha256=resource.source_sha256,
            content=_read_verified_source(
                resource.source_path,
                resource.source_sha256,
                label=f"resource {resource.name}",
            ),
        )
        for resource in provider.resources
    )
    return HeldProviderSources(entry=entry, modules=modules, resources=resources)


def _seal_held_source(held: HeldSource) -> int:
    """Re-assert the acquisition digest immediately before sealing it into an fd."""

    if hashlib.sha256(held.content).hexdigest() != held.sha256:
        raise ConfigurationError(
            f"provider {held.label} held source no longer matches its acquisition digest"
        )
    return _seal_verified_source(held.content, label=held.label)


def _invoke(
    provider: Provider,
    request: Mapping[str, Any],
    *,
    timeout: float,
    held: HeldProviderSources | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Return decoded response, failure kind, and detail."""

    snapshot_reader_fds: list[int] = []
    try:
        request_payload = json.dumps(request, separators=(",", ":"))
        if len(request_payload.encode("utf-8")) > MAX_PROVIDER_REQUEST_BYTES:
            raise ConfigurationError("provider request exceeds the bounded stdin payload")
        invocation_argv = list(provider.argv)
        pass_fds: tuple[int, ...] = ()
        if provider.source_path is not None:
            assert provider.source_sha256 is not None and provider.repository_root is not None
            if held is None:
                raise ConfigurationError(
                    "pinned provider sources were never acquired for this transaction"
                )
            entry_fd = _seal_held_source(held.entry)
            snapshot_reader_fds.append(entry_fd)
            module_argv: list[str] = []
            for module in held.modules:
                module_fd = _seal_held_source(module)
                snapshot_reader_fds.append(module_fd)
                module_argv.extend([module.name, str(module_fd)])
            resource_fds: dict[str, int] = {}
            for resource in held.resources:
                resource_fd = _seal_held_source(resource)
                snapshot_reader_fds.append(resource_fd)
                resource_fds[resource.name] = resource_fd
            program_argv: list[str] = []
            for value in provider.argv[2:]:
                placeholder = RESOURCE_PLACEHOLDER_RE.fullmatch(value)
                if placeholder is None:
                    program_argv.append(value)
                else:
                    program_argv.append(f"/dev/fd/{resource_fds[placeholder.group(1)]}")
            invocation_argv = [
                sys.executable,
                "-c",
                SEALED_PYTHON_SOURCE_BOOTSTRAP,
                str(entry_fd),
                str(provider.repository_root),
                str(len(provider.modules)),
                *module_argv,
                *program_argv,
            ]
            pass_fds = tuple(snapshot_reader_fds)
        completed = subprocess.run(
            invocation_argv,
            input=request_payload,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            pass_fds=pass_fds,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout", f"provider exceeded {timeout:g}s timeout"
    except (OSError, ConfigurationError) as exc:
        return None, "invocation", str(exc)
    finally:
        for snapshot_reader_fd in snapshot_reader_fds:
            os.close(snapshot_reader_fd)

    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"provider exited {completed.returncode}"
        return None, "invocation", detail
    try:
        decoded = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, "schema", f"provider stdout is not one JSON object: {exc.msg}"
    if not isinstance(decoded, dict):
        return None, "schema", "provider response must be a JSON object"
    return decoded, None, None


def _candidate_session(response: Mapping[str, Any] | None) -> dict[str, str] | None:
    if response is None:
        return None
    session = response.get("session")
    if not isinstance(session, dict):
        return None
    session_id = session.get("id")
    token = session.get("fencing_token")
    if isinstance(session_id, str) and session_id and isinstance(token, str) and token:
        return {"id": session_id, "fencing_token": token}
    return None


def validate_response(
    response: Mapping[str, Any],
    *,
    operation: str,
    request_id: str,
) -> dict[str, Any]:
    base_keys = {"schema", "request_id", "operation", "verdict", "message"}
    allowed_keys = base_keys | ({"session"} if operation == "begin" else set())
    missing = sorted(base_keys - response.keys())
    unknown = sorted(response.keys() - allowed_keys)
    if missing:
        raise SchemaError(f"missing response fields: {', '.join(missing)}")
    if unknown:
        raise SchemaError(f"unknown response fields: {', '.join(unknown)}")
    if response["schema"] != SCHEMA:
        raise SchemaError(f"schema must be {SCHEMA}")
    if response["request_id"] != request_id:
        raise SchemaError("response request_id does not match the request")
    if response["operation"] != operation:
        raise SchemaError("response operation does not match the request")
    verdict = response["verdict"]
    if not isinstance(verdict, str) or verdict not in VERDICT_WEIGHT:
        raise SchemaError("verdict must be allow, blocked, or indeterminate")
    if not isinstance(response["message"], str):
        raise SchemaError("message must be a string")

    session = response.get("session")
    if operation == "begin" and verdict == "allow":
        if not isinstance(session, dict) or set(session) != {"id", "fencing_token"}:
            raise SchemaError("an allowed begin must return only session.id and session.fencing_token")
        if not all(isinstance(session[key], str) and session[key] for key in session):
            raise SchemaError("session.id and session.fencing_token must be non-empty strings")
    elif operation == "begin" and session is not None:
        raise SchemaError("a denied begin must return a null session or omit it")
    return dict(response)


def _call(
    state: ProviderState,
    *,
    operation: str,
    repository: Mapping[str, str | None],
    step_count: int,
    timeout: float,
) -> dict[str, Any]:
    request = _request(
        operation=operation,
        request_id=state.request_id,
        repository=repository,
        session=state.session,
        step_count=step_count,
    )
    raw, failure, detail = _invoke(
        state.provider, request, timeout=timeout, held=state.held
    )
    candidate = _candidate_session(raw) if operation == "begin" else None
    if candidate is not None:
        state.session = candidate
    if failure is not None:
        return {
            "provider": state.provider.label,
            "operation": operation,
            "verdict": "indeterminate",
            "failure": failure,
            "message": detail or failure,
        }
    assert raw is not None
    try:
        response = validate_response(raw, operation=operation, request_id=state.request_id)
    except SchemaError as exc:
        return {
            "provider": state.provider.label,
            "operation": operation,
            "verdict": "indeterminate",
            "failure": "schema",
            "message": str(exc),
        }
    if operation == "begin" and response["verdict"] == "allow":
        state.session = dict(response["session"])
    return {
        "provider": state.provider.label,
        "operation": operation,
        "verdict": response["verdict"],
        "failure": None,
        "message": response["message"],
    }


def worst_verdict(records: Sequence[Mapping[str, Any]]) -> str:
    if not records:
        return "allow"
    return max(
        (str(record.get("verdict", "indeterminate")) for record in records),
        key=lambda verdict: VERDICT_WEIGHT.get(verdict, VERDICT_WEIGHT["indeterminate"]),
    )


def parse_steps(values: Sequence[str], command: Sequence[str]) -> list[list[str]]:
    if values and command:
        raise ConfigurationError("use --step-json or a command after --, not both")
    steps: list[list[str]] = []
    for position, value in enumerate(values):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"--step-json entry {position} is invalid JSON: {exc.msg}") from exc
        if not isinstance(decoded, list) or not decoded or not all(
            isinstance(item, str) and item for item in decoded
        ):
            raise ConfigurationError(
                f"--step-json entry {position} must be a non-empty JSON argv array"
            )
        steps.append(decoded)
    if command:
        normalized = list(command)
        if normalized and normalized[0] == "--":
            normalized = normalized[1:]
        if normalized:
            steps.append(normalized)
    if not steps:
        raise ConfigurationError("provide at least one --step-json entry or a command after --")
    return steps


def _env_requires_provider(env: Mapping[str, str]) -> bool:
    value = env.get(REQUIRED_ENV)
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ConfigurationError(f"{REQUIRED_ENV} must be 1/0, true/false, or yes/no")


def run_transaction(
    *,
    repository: Mapping[str, str | None],
    providers: Sequence[Provider],
    steps: Sequence[Sequence[str]],
    timeout: float,
) -> tuple[dict[str, Any], int]:
    transaction_id = str(uuid.uuid4())
    states = [
        ProviderState(provider=provider, request_id=f"{transaction_id}:{position}")
        for position, provider in enumerate(providers)
    ]
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "transaction_id": transaction_id,
        "repository": dict(repository),
        "provider_count": len(states),
        "portable_no_provider": not states,
        "preflight_verdict": "indeterminate",
        "mutation_started": False,
        "step_results": [],
        "provider_results": [],
        "release_results": [],
    }
    exit_code = EXIT_INDETERMINATE

    # Acquire before the first begin: a source that is already unreadable or
    # already drifted must refuse at preflight, with nothing acquired and nothing
    # stranded. ConfigurationError here propagates to main() as
    # configuration_error with mutation_started false.
    acquisitions: list[dict[str, Any]] = []
    for state in states:
        state.held = hold_provider_sources(state.provider)
        acquisitions.append(
            {
                "provider": state.provider.label,
                "request_id": state.request_id,
                "provider_identity_sha256": provider_identity_sha256(state.provider),
                "pinned": state.held is not None,
                "digests": state.held.digests() if state.held is not None else {},
            }
        )
    receipt["provider_acquisitions"] = acquisitions

    try:
        begin_records: list[dict[str, Any]] = []
        for state in states:
            record = _call(
                state,
                operation="begin",
                repository=repository,
                step_count=len(steps),
                timeout=timeout,
            )
            state.begin = record
            begin_records.append(record)
        receipt["provider_results"].extend(begin_records)
        begin_verdict = worst_verdict(begin_records)

        if begin_verdict == "allow":
            check_records = [
                _call(
                    state,
                    operation="check",
                    repository=repository,
                    step_count=len(steps),
                    timeout=timeout,
                )
                for state in states
            ]
            receipt["provider_results"].extend(check_records)
            preflight_verdict = worst_verdict(check_records)
        else:
            preflight_verdict = begin_verdict

        receipt["preflight_verdict"] = preflight_verdict
        if preflight_verdict == "blocked":
            exit_code = EXIT_BLOCKED
        elif preflight_verdict == "indeterminate":
            exit_code = EXIT_INDETERMINATE
        else:
            receipt["mutation_started"] = True
            repo_root = str(repository["root"])
            exit_code = 0
            for position, argv in enumerate(steps):
                completed = subprocess.run(
                    list(argv),
                    cwd=repo_root,
                    check=False,
                    stdout=sys.stderr,
                    stderr=sys.stderr,
                    shell=False,
                )
                receipt["step_results"].append(
                    {"position": position, "returncode": completed.returncode}
                )
                if completed.returncode != 0:
                    exit_code = completed.returncode or 1
                    break
    finally:
        for state in reversed(states):
            receipt["release_results"].append(
                _call(
                    state,
                    operation="end",
                    repository=repository,
                    step_count=len(steps),
                    timeout=timeout,
                )
            )

    release_verdict = worst_verdict(receipt["release_results"])
    receipt["release_verdict"] = release_verdict
    if release_verdict != "allow":
        receipt["outcome"] = "release_failed_after_preflight"
        return receipt, EXIT_RELEASE_FAILED
    if receipt["preflight_verdict"] != "allow":
        receipt["outcome"] = "fenced_without_mutation"
    elif exit_code == 0:
        receipt["outcome"] = "completed"
    else:
        receipt["outcome"] = "mutation_command_failed"
    return receipt, exit_code


def _resolve_policy(
    repo_root: Path, policy_home_arg: str | None
) -> tuple[list[Provider], bool, Path | None]:
    """Choose which repository's writer-session policy governs this transaction.

    Without --policy-home the protected repository declares its own fence, which
    means a repository can only be fenced by an authority it already carries. That
    leaves every un-onboarded repository unfenceable: the honest options were to
    plant a policy file in each one or to mutate it with no fence at all.
    --policy-home supplies a trusted repository's pinned policy while the protected
    repository stays the mutation target, so one attested authority can fence many
    repositories. It never downgrades: a protected repository that declares its own
    policy keeps it, and the override is refused rather than silently ignored.
    """

    own_providers, own_required = discover_repository_policy(repo_root)
    if policy_home_arg is None:
        return own_providers, own_required, None
    home_root = Path(str(repository_identity(Path(policy_home_arg).resolve())["root"]))
    if home_root == repo_root:
        return own_providers, own_required, None
    if own_providers or own_required:
        raise ConfigurationError(
            "--policy-home is rejected: the protected repository declares its own "
            "writer-session policy, which is authoritative"
        )
    home_providers, home_required = discover_repository_policy(home_root)
    if not home_providers or not home_required:
        raise ConfigurationError(
            f"--policy-home {home_root} declares no strict writer-session policy"
        )
    return home_providers, home_required, home_root


def _load_recovery_receipt(
    path: Path,
    *,
    repository: Mapping[str, str | None],
    provider: Provider,
) -> str:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ConfigurationError("recovery receipt must be a regular non-symlink file")
        if metadata.st_size > MAX_PROVIDER_REQUEST_BYTES:
            raise ConfigurationError("recovery receipt is oversized")
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"recovery receipt is unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"recovery receipt is invalid JSON: {exc.msg}") from exc
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != SCHEMA
        or receipt.get("outcome") != "release_failed_after_preflight"
        or receipt.get("release_verdict") == "allow"
        or receipt.get("provider_count") != 1
    ):
        raise ConfigurationError(
            "recovery receipt must be a one-provider release_failed_after_preflight receipt"
        )
    original = receipt.get("repository")
    if not isinstance(original, dict):
        raise ConfigurationError("recovery receipt repository identity is missing")
    for field in ("root", "git_dir", "git_common_dir"):
        if original.get(field) != repository.get(field):
            raise ConfigurationError(
                f"recovery receipt repository {field} does not match current repository"
            )
    acquisitions = receipt.get("provider_acquisitions")
    if not isinstance(acquisitions, list) or len(acquisitions) != 1:
        raise ConfigurationError("recovery receipt must contain one provider acquisition")
    acquisition = acquisitions[0]
    if (
        not isinstance(acquisition, dict)
        or acquisition.get("provider") != provider.label
        or acquisition.get("provider_identity_sha256")
        != provider_identity_sha256(provider)
        or acquisition.get("pinned") is not True
    ):
        raise ConfigurationError(
            "recovery receipt provider identity does not match pinned policy"
        )
    request_id = acquisition.get("request_id")
    if request_id is None:
        transaction_id = receipt.get("transaction_id")
        request_id = f"{transaction_id}:0" if isinstance(transaction_id, str) else None
    if not isinstance(request_id, str) or SAFE_REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ConfigurationError("recovery receipt request id is missing or unsafe")
    return request_id


def recover_transaction(
    *,
    repository: Mapping[str, str | None],
    provider: Provider,
    request_id: str,
    timeout: float,
) -> tuple[dict[str, Any], int]:
    """Idempotently ask one pinned provider to end a stranded request."""

    if SAFE_REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ConfigurationError(
            "--recover-request-id must be 1-256 safe request-id characters"
        )
    state = ProviderState(provider=provider, request_id=request_id)
    state.held = hold_provider_sources(provider)
    assert state.held is not None
    result = _call(
        state,
        operation="end",
        repository=repository,
        step_count=1,
        timeout=timeout,
    )
    verdict = str(result["verdict"])
    receipt = {
        "schema": SCHEMA,
        "outcome": "recovered" if verdict == "allow" else "recovery_failed",
        "request_id": request_id,
        "repository": dict(repository),
        "mutation_started": False,
        "provider_count": 1,
        "provider_acquisitions": [
            {
                "provider": provider.label,
                "provider_identity_sha256": provider_identity_sha256(provider),
                "pinned": True,
                "digests": state.held.digests(),
            }
        ],
        "recovery_result": result,
        "release_verdict": verdict,
    }
    return receipt, 0 if verdict == "allow" else EXIT_RELEASE_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run argv-only mutation steps under commit-writer-session/v1 providers."
    )
    parser.add_argument("--repo", default=".", help="Git repository to protect")
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="print machine-readable runner capabilities and exit without touching a repo",
    )
    parser.add_argument(
        "--recover-receipt",
        metavar="PATH",
        help="idempotently end one stranded request bound to its failure receipt",
    )
    parser.add_argument(
        "--require-capability",
        action="append",
        default=[],
        metavar="CAPABILITY",
        help="fail before repo/provider access unless this runner provides the capability",
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        metavar="EXECUTABLE",
        help="explicit provider executable; repeat for multiple providers",
    )
    parser.add_argument(
        "--provider-json",
        action="append",
        default=[],
        metavar="JSON_ARGV",
        help="explicit provider JSON argv array; repeat for multiple providers",
    )
    parser.add_argument(
        "--require-provider",
        action="store_true",
        help="fail closed when discovery yields no providers, or any provider is unpinned",
    )
    parser.add_argument(
        "--allow-unpinned-provider",
        action="store_true",
        help=(
            "permit ambient (unpinned) providers under required-provider mode; "
            "an unpinned provider is an arbitrary executable, not an attested authority"
        ),
    )
    parser.add_argument(
        "--policy-home",
        default=os.environ.get(POLICY_HOME_ENV),
        metavar="DIR",
        help=(
            "read the writer-session policy from this trusted repository instead of "
            "the protected one; rejected when the protected repository declares its own"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="per-provider call timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--step-json",
        action="append",
        default=[],
        metavar="JSON_ARGV",
        help="protected command as a JSON argv array; repeat to hold one session across steps",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="one protected command after --")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.capabilities:
        if args.recover_receipt or args.require_capability or args.step_json or args.command:
            parser.error("--capabilities cannot be combined with recovery or mutation steps")
        print(
            json.dumps(
                {"schema": CAPABILITIES_SCHEMA, "capabilities": list(RUNNER_CAPABILITIES)},
                sort_keys=True,
            )
        )
        return 0
    try:
        missing_capabilities = sorted(set(args.require_capability) - set(RUNNER_CAPABILITIES))
        if missing_capabilities:
            raise ConfigurationError(
                "runner lacks required capabilities: " + ", ".join(missing_capabilities)
            )
        if args.timeout <= 0:
            raise ConfigurationError("--timeout must be greater than zero")
        if args.recover_receipt and (args.step_json or args.command):
            raise ConfigurationError(
                "--recover-receipt cannot be combined with mutation steps"
            )
        steps = [] if args.recover_receipt else parse_steps(args.step_json, args.command)
        repository = repository_identity(Path(args.repo).resolve())
        repo_root = Path(str(repository["root"]))
        policy_providers, policy_required, policy_home = _resolve_policy(
            repo_root, args.policy_home
        )
        ambient_providers = discover_providers(
            executables=args.provider,
            json_commands=args.provider_json,
        )
        providers = [*policy_providers, *ambient_providers]
        required = policy_required or args.require_provider or _env_requires_provider(os.environ)
        if "acquisition-sealing-v1" in args.require_capability:
            unsealed = [provider.label for provider in providers if provider.source_path is None]
            if unsealed:
                raise ConfigurationError(
                    "acquisition-sealing capability requires every provider to be pinned; "
                    "unsealed providers: " + ", ".join(unsealed)
                )
        if "receipt-bound-single-pinned-recovery-v1" in args.require_capability:
            if len(policy_providers) != 1 or ambient_providers:
                raise ConfigurationError(
                    "receipt-bound recovery capability requires exactly one pinned "
                    "policy provider and no ambient providers"
                )
        if args.recover_receipt:
            if ambient_providers:
                raise ConfigurationError(
                    "recovery forbids ambient providers; use one pinned repository policy"
                )
            if len(policy_providers) != 1 or policy_providers[0].source_path is None:
                raise ConfigurationError(
                    "recovery requires exactly one pinned repository-policy provider"
                )
            request_id = _load_recovery_receipt(
                Path(args.recover_receipt),
                repository=repository,
                provider=policy_providers[0],
            )
            receipt, exit_code = recover_transaction(
                repository=repository,
                provider=policy_providers[0],
                request_id=request_id,
                timeout=args.timeout,
            )
            receipt["repository_policy"] = policy_required
            if policy_home is not None:
                receipt["policy_home"] = str(policy_home)
            print(json.dumps(receipt, sort_keys=True))
            return exit_code
        if required and not providers:
            receipt = {
                "schema": SCHEMA,
                "outcome": "provider_required_but_missing",
                "preflight_verdict": "indeterminate",
                "mutation_started": False,
                "provider_count": 0,
            }
            print(json.dumps(receipt, sort_keys=True))
            return EXIT_PROVIDER_REQUIRED
        # Presence was never the promise required-provider mode makes. An ambient
        # provider carries no pinned source, so nothing attests that the executable
        # invoked is the authority the operator believes in. Extra ambient providers
        # are additive veto power and cannot weaken a pinned one, so the hole is
        # narrower than "any provider is unpinned": it is a required-provider run
        # satisfied by nothing but unattested executables.
        if required and not args.allow_unpinned_provider:
            unpinned = [
                provider.label for provider in providers if provider.source_path is None
            ]
            if unpinned and len(unpinned) == len(providers):
                receipt = {
                    "schema": SCHEMA,
                    "outcome": "provider_required_but_unpinned",
                    "preflight_verdict": "indeterminate",
                    "mutation_started": False,
                    "provider_count": len(providers),
                    "unpinned_providers": unpinned,
                    "message": (
                        "required-provider mode needs at least one pinned provider; declare "
                        "one in a repository policy (or --policy-home), or pass "
                        "--allow-unpinned-provider to accept an unattested executable"
                    ),
                }
                print(json.dumps(receipt, sort_keys=True))
                return EXIT_PROVIDER_REQUIRED
        receipt, exit_code = run_transaction(
            repository=repository,
            providers=providers,
            steps=steps,
            timeout=args.timeout,
        )
        receipt["repository_policy"] = policy_required
        if policy_home is not None:
            receipt["policy_home"] = str(policy_home)
        print(json.dumps(receipt, sort_keys=True))
        return exit_code
    except ConfigurationError as exc:
        receipt = {
            "schema": SCHEMA,
            "outcome": "configuration_error",
            "preflight_verdict": "indeterminate",
            "mutation_started": False,
            "message": str(exc),
        }
        print(json.dumps(receipt, sort_keys=True))
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
