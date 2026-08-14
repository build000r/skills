#!/usr/bin/env python3
"""Run a mutation transaction behind provider-neutral writer-session fences."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping, Sequence
import uuid


SCHEMA = "commit-writer-session/v1"
CAPABILITIES_SCHEMA = "commit-writer-session-runner-capabilities/v1"
RUNNER_CAPABILITIES = (
    "acquisition-sealing-v1",
    "policy-home-v1",
    "receipt-bound-single-pinned-recovery-v1",
    "prebound-intent-recovery-v1",
)
PREBOUND_INTENT_SCHEMA = "commit-writer-session-prebound-intent/v1"
PREBOUND_JOURNAL_SCHEMA = "commit-writer-session-prebound-journal/v1"
PREBOUND_TERMINAL_SCHEMA = "commit-writer-session-prebound-terminal/v1"
RECOVERY_MANIFEST_SCHEMA = "commit-writer-session-recovery-provider-manifest/v1"
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
MAX_INTENT_BYTES = 256 * 1024
MAX_JOURNAL_EVENTS = 128
INTENT_FD_ENV = "COMMIT_WRITER_TRANSACTION_INTENT_FD"
MAX_CHILD_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_CHILD_STREAM_BYTES = 2 * 1024 * 1024
CHILD_CLEANUP_SECONDS = 0.5
FIXED_CHILD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_PLATFORM_GIT_CACHE: str | None = None
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
CHILD_GATE_BOOTSTRAP = r'''import json, os, sys
fd = int(sys.argv[1])
argv = json.loads(sys.argv[2])
token = os.read(fd, 1)
os.close(fd)
if token != b"1" or not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
    raise SystemExit(125)
os.execve(argv[0], argv, os.environ)
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


class ChildLifecycleError(RuntimeError):
    """A private child process group did not terminate with bounded certainty."""

    def __init__(self, *, extinct: bool = False, pgid: int | None = None) -> None:
        super().__init__("bounded child command failed")
        self.extinct = extinct
        self.pgid = pgid


def _closed_child_env(*, intent_fd: int | None = None) -> dict[str, str]:
    result = {
        "PATH": FIXED_CHILD_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    if intent_fd is not None:
        result[INTENT_FD_ENV] = str(intent_fd)
    return result


def _closed_git_env() -> dict[str, str]:
    result = _closed_child_env()
    result.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
        }
    )
    return result


def _validate_platform_executable(path: str) -> str:
    if not os.path.isabs(path) or os.path.realpath(path) != path:
        raise ConfigurationError("platform Git resolution failed")
    try:
        metadata = os.lstat(path)
    except OSError:
        raise ConfigurationError("platform Git resolution failed") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o111 == 0
    ):
        raise ConfigurationError("platform Git executable is not approved")
    return path


def _platform_git() -> str:
    global _PLATFORM_GIT_CACHE
    if _PLATFORM_GIT_CACHE is not None:
        return _validate_platform_executable(_PLATFORM_GIT_CACHE)
    if sys.platform == "darwin":
        completed = _run_child(
            ["/usr/bin/xcrun", "--find", "git"],
            cwd="/",
            env=_closed_child_env(),
            timeout=5,
        )
        if completed.returncode != 0:
            raise ConfigurationError("platform Git resolution failed")
        try:
            selected = completed.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise ConfigurationError("platform Git resolution failed") from None
        _PLATFORM_GIT_CACHE = _validate_platform_executable(selected)
        return _PLATFORM_GIT_CACHE
    for candidate in ("/usr/bin/git", "/bin/git"):
        try:
            _PLATFORM_GIT_CACHE = _validate_platform_executable(candidate)
            return _PLATFORM_GIT_CACHE
        except ConfigurationError:
            continue
    raise ConfigurationError("platform Git resolution failed")


def _child_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_child_group(process: subprocess.Popen[bytes]) -> None:
    pending: BaseException | None = None

    def remember(exc: BaseException) -> None:
        nonlocal pending
        if pending is None:
            pending = exc

    def alive() -> bool:
        try:
            return _child_group_alive(process.pid)
        except BaseException as exc:
            remember(exc)
            return True

    def nap() -> None:
        try:
            time.sleep(0.01)
        except BaseException as exc:
            remember(exc)

    def direct_kill() -> None:
        try:
            if process.poll() is None:
                process.kill()
        except ProcessLookupError:
            pass
        except BaseException as exc:
            remember(exc)

    def reap_once() -> None:
        if process.returncode is not None:
            return
        try:
            child, status = os.waitpid(process.pid, os.WNOHANG)
        except InterruptedError:
            return
        except ChildProcessError:
            try:
                process.poll()
            except BaseException as exc:
                remember(exc)
            return
        except BaseException as exc:
            remember(exc)
            return
        if child == process.pid:
            try:
                process.returncode = os.waitstatus_to_exitcode(status)
            except BaseException as exc:
                remember(exc)

    if alive():
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            remember(exc)
            try:
                if process.poll() is None:
                    process.terminate()
            except BaseException as fallback:
                remember(fallback)
    for _ in range(50):
        if not alive():
            break
        reap_once()
        nap()
    if alive():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            remember(exc)
            direct_kill()
    for _ in range(50):
        reap_once()
        if process.returncode is not None:
            break
        direct_kill()
        nap()
    # A successful direct-child wait is not enough: inherited fds remain live
    # while any same-group descendant survives.
    for _ in range(50):
        if not alive():
            break
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            break
        except BaseException as exc:
            remember(exc)
            direct_kill()
        reap_once()
        nap()
    reap_once()
    if alive() or process.returncode is None:
        raise ChildLifecycleError(pgid=process.pid)
    if pending is not None:
        if isinstance(pending, (KeyboardInterrupt, SystemExit)):
            raise pending
        raise ChildLifecycleError(extinct=True, pgid=process.pid) from None


def _run_child(
    argv: Sequence[str],
    *,
    cwd: str | None,
    env: Mapping[str, str],
    timeout: float,
    input_bytes: bytes | None = None,
    pass_fds: Sequence[int] = (),
    on_spawn: Callable[[int], None] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    valid_timeout = (
        (type(timeout) is int and 0 < timeout <= 300)
        or (type(timeout) is float and math.isfinite(timeout) and 0 < timeout <= 300)
    )
    normalized_argv = list(argv)
    if normalized_argv and not os.path.isabs(normalized_argv[0]):
        selected = shutil.which(normalized_argv[0], path=env.get("PATH"))
        if selected is None:
            raise ChildLifecycleError()
        normalized_argv[0] = os.path.realpath(selected)
    if (
        not argv
        or not all(type(item) is str and item for item in argv)
        or not os.path.isabs(normalized_argv[0])
        or not valid_timeout
        or (cwd is not None and not os.path.isabs(cwd))
    ):
        raise ChildLifecycleError()
    try:
        deadline = time.monotonic() + float(timeout)
    except BaseException:
        raise ChildLifecycleError(extinct=True) from None
    try:
        gate_reader, gate_writer = os.pipe()
    except Exception:
        raise ChildLifecycleError(extinct=True) from None
    except BaseException:
        raise ChildLifecycleError(extinct=True) from None
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", CHILD_GATE_BOOTSTRAP, str(gate_reader), json.dumps(normalized_argv)],
            cwd=cwd, env=dict(env),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            pass_fds=tuple([*pass_fds, gate_reader]),
        )
    except Exception:
        os.close(gate_reader)
        os.close(gate_writer)
        raise ChildLifecycleError(extinct=True) from None
    except BaseException:
        os.close(gate_reader)
        os.close(gate_writer)
        raise ChildLifecycleError(extinct=False) from None
    os.close(gate_reader)
    gate_reader = -1
    selector: selectors.BaseSelector | None = None
    success = False
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        assert process.stdout is not None and process.stderr is not None
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        if process.stdin is not None:
            os.set_blocking(process.stdin.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        if input_bytes is not None:
            assert process.stdin is not None
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        if on_spawn is not None:
            on_spawn(process.pid)
        if os.write(gate_writer, b"1") != 1:
            raise ChildLifecycleError()
        os.close(gate_writer)
        gate_writer = -1
        offset = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ChildLifecycleError()
            for key, mask in selector.select(min(remaining, 0.05)):
                if key.data == "stdin":
                    if offset >= len(input_bytes or b""):
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    try:
                        count = os.write(
                            key.fileobj.fileno(), (input_bytes or b"")[offset:offset + 65536]
                        )
                    except BrokenPipeError:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    except BlockingIOError:
                        continue
                    if type(count) is not int or count <= 0:
                        raise ChildLifecycleError()
                    offset += count
                    continue
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(chunk)
                if (
                    len(buffers[key.data]) > MAX_CHILD_STREAM_BYTES
                    or sum(len(value) for value in buffers.values()) > MAX_CHILD_OUTPUT_BYTES
                ):
                    raise ChildLifecycleError()
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise ChildLifecycleError() from None
        _terminate_child_group(process)
        success = True
        return subprocess.CompletedProcess(
            normalized_argv, int(process.returncode), bytes(buffers["stdout"]), bytes(buffers["stderr"])
        )
    except Exception as exc:
        if isinstance(exc, ChildLifecycleError):
            raise
        raise ChildLifecycleError() from None
    finally:
        original = sys.exc_info()[1]
        cleanup_error: BaseException | None = None
        if not success:
            try:
                _terminate_child_group(process)
            except BaseException as exc:
                cleanup_error = exc
        for stream in (selector, process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except BaseException as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
        for gate_fd in (gate_reader, gate_writer):
            if gate_fd >= 0:
                try:
                    os.close(gate_fd)
                except BaseException as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
        if cleanup_error is not None:
            try:
                extinct = not _child_group_alive(process.pid) and process.returncode is not None
            except BaseException:
                extinct = False
            if isinstance(original, (KeyboardInterrupt, SystemExit)) and extinct:
                pass
            elif isinstance(cleanup_error, (KeyboardInterrupt, SystemExit)) and extinct:
                raise cleanup_error
            else:
                raise ChildLifecycleError(extinct=extinct, pgid=process.pid) from None
        elif isinstance(original, ChildLifecycleError):
            try:
                original.extinct = (
                    not _child_group_alive(process.pid) and process.returncode is not None
                )
                original.pgid = process.pid
            except BaseException:
                original.extinct = False


def _canonical_uuid_v4(value: object) -> str:
    if type(value) is not str:
        raise ConfigurationError("transaction id must be a canonical UUID v4")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ConfigurationError("transaction id must be a canonical UUID v4") from None
    if (
        str(parsed) != value
        or parsed.version != 4
        or parsed.variant != uuid.RFC_4122
    ):
        raise ConfigurationError("transaction id must be a canonical UUID v4")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_all(fd: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(fd, content[offset:])
        if type(written) is not int or written <= 0:
            raise ConfigurationError("transaction intent write failed")
        offset += written


def _open_private_parent(path: Path) -> int:
    if not path.is_absolute():
        raise ConfigurationError("transaction artifact path must be absolute")
    normalized = Path(os.path.abspath(path))
    if normalized != path or path.name in {"", ".", ".."}:
        raise ConfigurationError("transaction artifact path is not normalized")
    fd = os.open("/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for component in path.parent.parts[1:]:
            next_fd = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=fd,
            )
            os.close(fd)
            fd = next_fd
        metadata = os.fstat(fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ConfigurationError("transaction artifact parent must be owned mode 0700")
        result = fd
        fd = -1
        return result
    except OSError:
        raise ConfigurationError("transaction artifact parent is unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _outside_roots(path: Path, forbidden_roots: Sequence[Path]) -> None:
    candidate = str(path)
    for root in forbidden_roots:
        try:
            common = os.path.commonpath((candidate, str(root)))
        except ValueError:
            continue
        if common == str(root):
            raise ConfigurationError("transaction artifact must be outside protected roots")


def _open_prebound_intent(
    path: Path,
    payload: Mapping[str, object],
    *,
    forbidden_roots: Sequence[Path] = (),
) -> tuple[int, str]:
    _outside_roots(path, forbidden_roots)
    content = _canonical_json_bytes(dict(payload))
    if len(content) > MAX_INTENT_BYTES:
        raise ConfigurationError("transaction intent is oversized")
    parent_fd = _open_private_parent(path)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
    except OSError:
        os.close(parent_fd)
        raise ConfigurationError("transaction intent already exists or is unavailable") from None
    identity = os.fstat(fd)
    owned = True
    try:
        metadata = identity
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ConfigurationError("transaction intent is not a private regular file")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _write_all(fd, content)
        os.fsync(fd)
        os.fsync(parent_fd)
        os.lseek(fd, 0, os.SEEK_SET)
        owned = False
        return fd, hashlib.sha256(content).hexdigest()
    finally:
        if owned:
            try:
                current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if current.st_dev != identity.st_dev or current.st_ino != identity.st_ino:
                    raise ConfigurationError("transaction intent cleanup identity is uncertain")
                os.unlink(path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                raise ConfigurationError("transaction intent cleanup is uncertain") from None
            finally:
                os.close(fd)
        os.close(parent_fd)


def _read_locked_intent(
    path: Path, *, forbidden_roots: Sequence[Path] = ()
) -> tuple[int, dict[str, object], bytes]:
    if not path.is_absolute():
        raise ConfigurationError("--recover-intent must be an absolute path")
    _outside_roots(path, forbidden_roots)
    parent_fd = _open_private_parent(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path.name, flags, dir_fd=parent_fd)
    except OSError:
        os.close(parent_fd)
        raise ConfigurationError("recovery intent is unavailable") from None
    os.close(parent_fd)
    keep = False
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > MAX_INTENT_BYTES
        ):
            raise ConfigurationError("recovery intent must be a bounded private regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConfigurationError("original transaction is still active") from None
        chunks: list[bytes] = []
        remaining = MAX_INTENT_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        stable_fields = (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if len(raw) > MAX_INTENT_BYTES or any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            raise ConfigurationError("recovery intent changed while being read")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConfigurationError("recovery intent is invalid") from None
        if type(value) is not dict or _canonical_json_bytes(value) != raw:
            raise ConfigurationError("recovery intent is not canonical")
        keep = True
        return fd, value, raw
    finally:
        if not keep:
            os.close(fd)


def _terminal_identity(metadata: os.stat_result) -> dict[str, int]:
    return {
        "dev": metadata.st_dev,
        "ino": metadata.st_ino,
        "uid": metadata.st_uid,
        "mode": stat.S_IMODE(metadata.st_mode),
        "nlink": metadata.st_nlink,
    }


def _reserve_terminal_result(path: Path) -> ReservedTerminal:
    parent_fd = _open_private_parent(path)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
    except OSError:
        os.close(parent_fd)
        raise ConfigurationError("transaction terminal result collision") from None
    try:
        metadata = os.fstat(fd)
        identity = _terminal_identity(metadata)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or identity["uid"] != os.getuid()
            or identity["mode"] != 0o600
            or identity["nlink"] != 1
            or metadata.st_size != 0
        ):
            raise ConfigurationError("terminal result reservation identity is unsafe")
        os.fsync(fd)
        os.fsync(parent_fd)
        return ReservedTerminal(fd=fd, path=path, identity=identity)
    except BaseException:
        os.close(fd)
        raise
    finally:
        os.close(parent_fd)


def _open_reserved_terminal(path: Path, expected: Mapping[str, object]) -> ReservedTerminal:
    parent_fd = _open_private_parent(path)
    try:
        fd = os.open(
            path.name,
            os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except OSError:
        os.close(parent_fd)
        raise ConfigurationError("terminal result reservation is unavailable") from None
    os.close(parent_fd)
    metadata = os.fstat(fd)
    if (
        _terminal_identity(metadata) != expected
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        os.close(fd)
        raise ConfigurationError("terminal result reservation identity changed")
    return ReservedTerminal(fd=fd, path=path, identity=dict(expected))


def _write_terminal_result(
    reserved: ReservedTerminal, receipt: Mapping[str, object]
) -> str:
    content = _canonical_json_bytes(dict(receipt))
    if len(content) > MAX_INTENT_BYTES:
        raise ConfigurationError("transaction terminal result is oversized")
    content_sha256 = hashlib.sha256(content).hexdigest()
    pending_name = f".pending-result-{content_sha256}.tmp"
    parent_fd = _open_private_parent(reserved.path)
    pending_fd = -1
    try:
        try:
            pending_fd = os.open(
                pending_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            _write_all(pending_fd, content)
            os.fsync(pending_fd)
        except FileExistsError:
            pass
        except OSError:
            raise ConfigurationError("terminal result pending publication failed") from None
        finally:
            if pending_fd >= 0:
                os.close(pending_fd)
        _reconcile_terminal_publication(
            reserved.path,
            original_identity=reserved.identity,
            content=content,
            content_sha256=content_sha256,
            parent_fd=parent_fd,
        )
        return content_sha256
    finally:
        os.close(parent_fd)


def _read_terminal_entry(
    parent_fd: int, name: str, *, maximum: int = MAX_INTENT_BYTES
) -> tuple[bytes, os.stat_result] | None:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        return None
    except OSError:
        raise ConfigurationError("terminal result artifact is unavailable") from None
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink not in {1, 2}
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > maximum
        ):
            raise ConfigurationError("terminal result artifact identity is unsafe")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        fields = (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if len(raw) > maximum or any(
            getattr(before, field) != getattr(after, field) for field in fields
        ):
            raise ConfigurationError("terminal result artifact changed while read")
        return raw, after
    finally:
        os.close(fd)


def _reconcile_terminal_publication(
    path: Path,
    *,
    original_identity: Mapping[str, object],
    content: bytes,
    content_sha256: str,
    parent_fd: int | None = None,
) -> str:
    if hashlib.sha256(content).hexdigest() != content_sha256:
        raise ConfigurationError("terminal result payload digest is invalid")
    owned_parent = parent_fd is None
    if parent_fd is None:
        parent_fd = _open_private_parent(path)
    pending_name = f".pending-result-{content_sha256}.tmp"
    try:
        pending = _read_terminal_entry(parent_fd, pending_name)
        final = _read_terminal_entry(parent_fd, path.name)
        if pending is not None and pending[0] != content:
            quarantine_name = (
                ".quarantine-result-"
                + hashlib.sha256(pending[0]).hexdigest()
                + ".artifact"
            )
            try:
                os.link(
                    pending_name,
                    quarantine_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                source = os.stat(pending_name, dir_fd=parent_fd, follow_symlinks=False)
                target = os.stat(quarantine_name, dir_fd=parent_fd, follow_symlinks=False)
                if (source.st_dev, source.st_ino) != (target.st_dev, target.st_ino):
                    raise ConfigurationError("terminal result quarantine collision") from None
            except OSError:
                raise ConfigurationError("terminal result quarantine failed") from None
            try:
                os.fsync(parent_fd)
                os.unlink(pending_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                raise ConfigurationError("terminal result quarantine failed") from None
            pending = None
        if final is not None and final[0] == content:
            if pending is not None:
                if (final[1].st_dev, final[1].st_ino) != (
                    pending[1].st_dev, pending[1].st_ino
                ):
                    raise ConfigurationError("terminal result pending inode conflicts")
                try:
                    os.unlink(pending_name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except OSError:
                    raise ConfigurationError("terminal result pending cleanup failed") from None
            stable = _read_terminal_entry(parent_fd, path.name)
            if stable is None or stable[0] != content or stable[1].st_nlink != 1:
                raise ConfigurationError("terminal result stable reopen failed")
            try:
                os.fsync(parent_fd)
            except OSError:
                raise ConfigurationError("terminal result parent fsync failed") from None
            return content_sha256
        if final is not None:
            if final[0] != b"" or _terminal_identity(final[1]) != dict(original_identity):
                raise ConfigurationError("terminal result reservation identity changed")
            try:
                os.unlink(path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                raise ConfigurationError("terminal result reservation release failed") from None
        if pending is None:
            try:
                pending_fd = os.open(
                    pending_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    _write_all(pending_fd, content)
                    os.fsync(pending_fd)
                finally:
                    os.close(pending_fd)
            except OSError:
                raise ConfigurationError("terminal result pending reconstruction failed") from None
            pending = _read_terminal_entry(parent_fd, pending_name)
            if pending is None or pending[0] != content:
                raise ConfigurationError("terminal result pending reconstruction is invalid")
        try:
            pending_fd = os.open(
                pending_name,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
            try:
                os.fsync(pending_fd)
            finally:
                os.close(pending_fd)
        except OSError:
            raise ConfigurationError("terminal result pending fsync failed") from None
        try:
            os.link(
                pending_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.fsync(parent_fd)
        except FileExistsError:
            raise ConfigurationError("terminal result publication collision") from None
        except OSError:
            raise ConfigurationError("terminal result publication failed") from None
        final = _read_terminal_entry(parent_fd, path.name)
        pending = _read_terminal_entry(parent_fd, pending_name)
        if (
            final is None
            or pending is None
            or final[0] != content
            or pending[0] != content
            or (final[1].st_dev, final[1].st_ino)
            != (pending[1].st_dev, pending[1].st_ino)
        ):
            raise ConfigurationError("terminal result published identity is invalid")
        try:
            os.unlink(pending_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except OSError:
            raise ConfigurationError("terminal result pending cleanup failed") from None
        stable = _read_terminal_entry(parent_fd, path.name)
        if stable is None or stable[0] != content or stable[1].st_nlink != 1:
            raise ConfigurationError("terminal result stable reopen failed")
        return content_sha256
    finally:
        if owned_parent:
            os.close(parent_fd)


def _make_terminal_payload(
    receipt: Mapping[str, object],
    *,
    transaction_intent: Mapping[str, object],
    transaction_result: Path,
    transaction_journal: Path,
    journal_prefix_sha256: str,
    provider_identity: str,
    provider_digests: Mapping[str, str],
    request_id: str,
    step_count: int,
    steps_sha256: str,
    policy_home: Path | None,
    repository_policy: bool,
    exit_code: int,
) -> dict[str, object]:
    receipt_copy = dict(receipt)
    receipt_sha256 = hashlib.sha256(_canonical_json_bytes(receipt_copy)).hexdigest()
    payload: dict[str, object] = {
        "schema": PREBOUND_TERMINAL_SCHEMA,
        "transaction_id": receipt_copy.get("transaction_id"),
        "request_id": request_id,
        "repository": receipt_copy.get("repository"),
        "policy_home": str(policy_home) if policy_home is not None else None,
        "repository_policy": repository_policy,
        "transaction_intent": dict(transaction_intent),
        "transaction_result": str(transaction_result),
        "transaction_journal": str(transaction_journal),
        "journal_prefix_sha256": journal_prefix_sha256,
        "provider_identity_sha256": provider_identity,
        "provider_digests": dict(provider_digests),
        "step_count": step_count,
        "steps_sha256": steps_sha256,
        "outcome": receipt_copy.get("outcome"),
        "exit_code": exit_code,
        "receipt_sha256": receipt_sha256,
        "receipt": receipt_copy,
    }
    _validate_terminal_payload(
        payload,
        expected_payload_sha256=hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
        expected_prefix_sha256=journal_prefix_sha256,
    )
    return payload


def _validate_terminal_payload(
    payload: object,
    *,
    expected_payload_sha256: object,
    expected_prefix_sha256: object,
) -> dict[str, object]:
    expected_keys = {
        "schema", "transaction_id", "request_id", "repository", "policy_home",
        "repository_policy", "transaction_intent", "transaction_result",
        "transaction_journal", "journal_prefix_sha256", "provider_identity_sha256",
        "provider_digests", "step_count", "steps_sha256", "outcome", "exit_code",
        "receipt_sha256", "receipt",
    }
    if type(payload) is not dict or set(payload) != expected_keys:
        raise ConfigurationError("terminal payload keyset is invalid")
    canonical = _canonical_json_bytes(payload)
    canonical_sha256 = hashlib.sha256(canonical).hexdigest()
    if (
        payload.get("schema") != PREBOUND_TERMINAL_SCHEMA
        or type(expected_payload_sha256) is not str
        or canonical_sha256 != expected_payload_sha256
        or type(expected_prefix_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_prefix_sha256) is None
        or payload.get("journal_prefix_sha256") != expected_prefix_sha256
    ):
        raise ConfigurationError("terminal payload digest binding is invalid")
    transaction_id = payload.get("transaction_id")
    if type(transaction_id) is not str or _canonical_uuid_v4(transaction_id) != transaction_id:
        raise ConfigurationError("terminal transaction id is invalid")
    request_id = payload.get("request_id")
    if type(request_id) is not str or request_id != f"{transaction_id}:0":
        raise ConfigurationError("terminal request id is invalid")
    repository = payload.get("repository")
    if (
        type(repository) is not dict
        or set(repository)
        != {"root", "git_dir", "git_common_dir", "head_oid", "head_ref"}
        or not all(value is None or type(value) is str for value in repository.values())
    ):
        raise ConfigurationError("terminal repository identity is invalid")
    transaction_intent = payload.get("transaction_intent")
    if (
        type(transaction_intent) is not dict
        or set(transaction_intent) != {"path", "sha256"}
        or type(transaction_intent.get("path")) is not str
        or type(transaction_intent.get("sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", transaction_intent["sha256"]) is None
    ):
        raise ConfigurationError("terminal intent binding is invalid")
    if (
        type(payload.get("transaction_result")) is not str
        or type(payload.get("transaction_journal")) is not str
        or type(payload.get("policy_home")) not in {str, type(None)}
        or type(payload.get("repository_policy")) is not bool
        or type(payload.get("provider_identity_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", payload["provider_identity_sha256"]) is None
        or type(payload.get("provider_digests")) is not dict
        or not payload["provider_digests"]
        or not all(
            type(key) is str
            and type(value) is str
            and re.fullmatch(r"[0-9a-f]{64}", value) is not None
            for key, value in payload["provider_digests"].items()
        )
        or type(payload.get("step_count")) is not int
        or payload["step_count"] < 1
        or type(payload.get("steps_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", payload["steps_sha256"]) is None
        or type(payload.get("outcome")) is not str
        or type(payload.get("exit_code")) is not int
    ):
        raise ConfigurationError("terminal payload field type is invalid")
    receipt = payload.get("receipt")
    if type(receipt) is not dict:
        raise ConfigurationError("terminal embedded receipt is invalid")
    receipt_sha256 = hashlib.sha256(_canonical_json_bytes(receipt)).hexdigest()
    acquisitions = receipt.get("provider_acquisitions")
    if (
        payload.get("receipt_sha256") != receipt_sha256
        or receipt.get("schema") != SCHEMA
        or receipt.get("transaction_id") != transaction_id
        or receipt.get("repository") != repository
        or receipt.get("outcome") != payload.get("outcome")
        or type(acquisitions) is not list
        or len(acquisitions) != 1
        or type(acquisitions[0]) is not dict
        or acquisitions[0].get("request_id") != request_id
        or acquisitions[0].get("provider_identity_sha256")
        != payload.get("provider_identity_sha256")
        or acquisitions[0].get("digests") != payload.get("provider_digests")
        or acquisitions[0].get("pinned") is not True
    ):
        raise ConfigurationError("terminal embedded receipt binding is invalid")
    return dict(payload)


def _open_journal(path: Path, *, create: bool) -> DurableJournal:
    parent_fd = _open_private_parent(path)
    try:
        if create:
            os.mkdir(path.name, 0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        fd = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except OSError:
        os.close(parent_fd)
        raise ConfigurationError("transaction journal collision or unavailable") from None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ConfigurationError("transaction journal is not a private directory")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConfigurationError("transaction journal is already active") from None
        result = DurableJournal(fd=fd, path=path)
        fd = -1
        return result
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent_fd)


def _cleanup_preprovider_reservations(
    *,
    journal: DurableJournal | None,
    reserved_terminal: ReservedTerminal | None,
) -> None:
    """Remove only exact artifacts owned before any provider begin was attempted."""

    failure = False
    if journal is not None:
        journal_identity = os.fstat(journal.fd)
        try:
            names = os.listdir(journal.fd)
            for name in names:
                if _FINAL_EVENT_RE.fullmatch(name) is None and _PENDING_EVENT_RE.fullmatch(name) is None:
                    raise ConfigurationError("pre-provider journal cleanup found foreign evidence")
                metadata = os.stat(name, dir_fd=journal.fd, follow_symlinks=False)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_nlink not in {1, 2}
                ):
                    raise ConfigurationError("pre-provider journal cleanup identity is unsafe")
                os.unlink(name, dir_fd=journal.fd)
            os.fsync(journal.fd)
        except BaseException:
            failure = True
        finally:
            os.close(journal.fd)
        try:
            parent_fd = _open_private_parent(journal.path)
            try:
                current = os.stat(journal.path.name, dir_fd=parent_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (
                    journal_identity.st_dev,
                    journal_identity.st_ino,
                ):
                    raise ConfigurationError("pre-provider journal cleanup identity changed")
                os.rmdir(journal.path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except BaseException:
            failure = True
    if reserved_terminal is not None:
        try:
            parent_fd = _open_private_parent(reserved_terminal.path)
            try:
                current = os.stat(
                    reserved_terminal.path.name, dir_fd=parent_fd, follow_symlinks=False
                )
                if _terminal_identity(current) != reserved_terminal.identity:
                    raise ConfigurationError("pre-provider result cleanup identity changed")
                os.unlink(reserved_terminal.path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except BaseException:
            failure = True
        finally:
            os.close(reserved_terminal.fd)
    if failure:
        raise ConfigurationError("pre-provider reservation cleanup is indeterminate")


def _cleanup_preprovider_intent(path: Path, fd: int) -> None:
    identity = os.fstat(fd)
    try:
        parent_fd = _open_private_parent(path)
        try:
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise ConfigurationError("pre-provider intent cleanup identity changed")
            os.unlink(path.name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        raise ConfigurationError("pre-provider intent cleanup is indeterminate") from None
    finally:
        os.close(fd)


def _read_private_bytes(path: Path, *, maximum: int = MAX_INTENT_BYTES) -> bytes:
    parent_fd = _open_private_parent(path)
    try:
        fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except OSError:
        os.close(parent_fd)
        raise ConfigurationError("private transaction artifact is unavailable") from None
    os.close(parent_fd)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > maximum
        ):
            raise ConfigurationError("private transaction artifact has unsafe identity")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        fields = (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if len(raw) > maximum or any(
            getattr(before, field) != getattr(after, field) for field in fields
        ):
            raise ConfigurationError("private transaction artifact changed while read")
        return raw
    finally:
        os.close(fd)


def _read_canonical_object(path: Path) -> tuple[dict[str, object], bytes]:
    raw = _read_private_bytes(path)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ConfigurationError("private transaction artifact is invalid JSON") from None
    if type(value) is not dict or _canonical_json_bytes(value) != raw:
        raise ConfigurationError("private transaction artifact is not canonical")
    return value, raw


def _validate_journal(raw: bytes) -> tuple[list[dict[str, object]], str]:
    if not raw or len(raw) > MAX_INTENT_BYTES:
        raise ConfigurationError("transaction journal is empty or oversized")
    records: list[dict[str, object]] = []
    previous = "0" * 64
    for sequence, line in enumerate(raw.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            raise ConfigurationError("transaction journal has a truncated record")
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConfigurationError("transaction journal record is invalid") from None
        if (
            type(record) is not dict
            or set(record) != {"schema", "sequence", "previous_sha256", "event", "detail"}
            or record.get("schema") != PREBOUND_JOURNAL_SCHEMA
            or type(record.get("sequence")) is not int
            or record.get("sequence") != sequence
            or record.get("previous_sha256") != previous
            or type(record.get("event")) is not str
            or not record.get("event")
            or type(record.get("detail")) is not dict
            or _canonical_json_bytes(record) != line
        ):
            raise ConfigurationError("transaction journal chain is invalid")
        previous = hashlib.sha256(line).hexdigest()
        records.append(record)
    return records, previous


_FINAL_EVENT_RE = re.compile(r"^(?P<sequence>[0-9]{8})-(?P<event>[a-z][a-z0-9_]{0,63})\.json$")
_PENDING_EVENT_RE = re.compile(
    r"^\.pending-(?P<sequence>[0-9]{8})-(?P<event>[a-z][a-z0-9_]{0,63})-"
    r"(?P<sha256>[0-9a-f]{64})\.tmp$"
)


def _read_event_fd(fd: int, *, allow_two_links: bool = False) -> tuple[bytes, os.stat_result]:
    before = os.fstat(fd)
    allowed_links = {1, 2} if allow_two_links else {1}
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink not in allowed_links
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size > MAX_INTENT_BYTES
    ):
        raise ConfigurationError("transaction journal event identity is unsafe")
    chunks: list[bytes] = []
    remaining = MAX_INTENT_BYTES + 1
    while remaining:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    after = os.fstat(fd)
    fields = (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
        "st_size", "st_mtime_ns", "st_ctime_ns",
    )
    if len(raw) > MAX_INTENT_BYTES or any(
        getattr(before, field) != getattr(after, field) for field in fields
    ):
        raise ConfigurationError("transaction journal event changed while read")
    return raw, after


def _decode_event_record(
    raw: bytes, *, sequence: int, event: str, previous_sha256: str
) -> dict[str, object]:
    try:
        record = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ConfigurationError("transaction journal event is invalid") from None
    if (
        type(record) is not dict
        or set(record) != {"schema", "sequence", "previous_sha256", "event", "detail"}
        or record.get("schema") != PREBOUND_JOURNAL_SCHEMA
        or type(record.get("sequence")) is not int
        or record.get("sequence") != sequence
        or record.get("previous_sha256") != previous_sha256
        or record.get("event") != event
        or type(record.get("detail")) is not dict
        or _canonical_json_bytes(record) != raw
    ):
        raise ConfigurationError("transaction journal event chain is invalid")
    return record


def _quarantine_pending_event(journal: DurableJournal, name: str) -> None:
    """Move an untrusted named temp out of the event namespace without replacement."""

    try:
        os.mkdir(".quarantine", 0o700, dir_fd=journal.fd)
        os.fsync(journal.fd)
    except FileExistsError:
        pass
    except OSError:
        raise ConfigurationError("transaction journal quarantine is unavailable") from None
    try:
        quarantine_fd = os.open(
            ".quarantine",
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=journal.fd,
        )
    except OSError:
        raise ConfigurationError("transaction journal quarantine is unavailable") from None
    try:
        metadata = os.fstat(quarantine_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ConfigurationError("transaction journal quarantine is unsafe")
        quarantine_name = hashlib.sha256(name.encode("utf-8")).hexdigest() + ".quarantine"
        try:
            os.link(
                name,
                quarantine_name,
                src_dir_fd=journal.fd,
                dst_dir_fd=quarantine_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            source = os.stat(name, dir_fd=journal.fd, follow_symlinks=False)
            target = os.stat(quarantine_name, dir_fd=quarantine_fd, follow_symlinks=False)
            if (source.st_dev, source.st_ino) != (target.st_dev, target.st_ino):
                raise ConfigurationError("transaction journal quarantine collision") from None
        except OSError:
            raise ConfigurationError("transaction journal quarantine failed") from None
        os.fsync(quarantine_fd)
        os.unlink(name, dir_fd=journal.fd)
        os.fsync(journal.fd)
    finally:
        os.close(quarantine_fd)


def _reconcile_pending_events(journal: DurableJournal) -> None:
    """Publish complete self-manifesting temps or quarantine malformed names."""

    try:
        names = sorted(os.listdir(journal.fd))
    except OSError:
        raise ConfigurationError("transaction journal directory is unavailable") from None
    final_names = [name for name in names if _FINAL_EVENT_RE.fullmatch(name)]
    records: list[dict[str, object]] = []
    final_raw: list[bytes] = []
    final_identity: list[tuple[int, int]] = []
    chain = "0" * 64
    for sequence, name in enumerate(final_names):
        match = _FINAL_EVENT_RE.fullmatch(name)
        assert match is not None
        if int(match.group("sequence")) != sequence:
            raise ConfigurationError("transaction journal event sequence has a gap")
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=journal.fd)
        except OSError:
            raise ConfigurationError("transaction journal event is unavailable") from None
        try:
            raw, metadata = _read_event_fd(fd, allow_two_links=True)
        finally:
            os.close(fd)
        record = _decode_event_record(
            raw,
            sequence=sequence,
            event=match.group("event"),
            previous_sha256=chain,
        )
        chain = hashlib.sha256(raw).hexdigest()
        records.append(record)
        final_raw.append(raw)
        final_identity.append((metadata.st_dev, metadata.st_ino))
    pending_names = [name for name in names if name.startswith(".pending-")]
    for name in sorted(pending_names):
        match = _PENDING_EVENT_RE.fullmatch(name)
        if match is None:
            _quarantine_pending_event(journal, name)
            continue
        sequence = int(match.group("sequence"))
        event = match.group("event")
        try:
            pending_fd = os.open(
                name, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), dir_fd=journal.fd
            )
        except OSError:
            raise ConfigurationError("transaction journal pending event is unavailable") from None
        try:
            raw, pending_metadata = _read_event_fd(pending_fd, allow_two_links=True)
        except ConfigurationError:
            os.close(pending_fd)
            _quarantine_pending_event(journal, name)
            continue
        else:
            try:
                os.fsync(pending_fd)
            except OSError:
                os.close(pending_fd)
                raise ConfigurationError("transaction journal pending event fsync failed") from None
            os.close(pending_fd)
        if hashlib.sha256(raw).hexdigest() != match.group("sha256"):
            _quarantine_pending_event(journal, name)
            continue
        if sequence > len(records):
            raise ConfigurationError("transaction journal pending event sequence has a gap")
        # A link succeeded and the subsequent pending-name unlink or directory
        # fsync failed.  Reconcile that publication boundary before semantic
        # append validation: appending a duplicate record to ``records`` would
        # make otherwise valid paired events (prepared/intent_ready,
        # terminal_intent/terminal_done) look duplicated and quarantine the
        # exact owned hard link.
        if sequence < len(records):
            final_name = f"{sequence:08d}-{event}.json"
            if (
                final_names[sequence] != final_name
                or final_raw[sequence] != raw
                or final_identity[sequence]
                != (pending_metadata.st_dev, pending_metadata.st_ino)
            ):
                raise ConfigurationError(
                    "transaction journal pending event conflicts with final event"
                )
            try:
                os.unlink(name, dir_fd=journal.fd)
                os.fsync(journal.fd)
            except OSError:
                raise ConfigurationError(
                    "transaction journal pending cleanup failed"
                ) from None
            continue
        previous_sha256 = (
            "0" * 64
            if sequence == 0
            else hashlib.sha256(_canonical_json_bytes(records[sequence - 1])).hexdigest()
        )
        record = _decode_event_record(
            raw, sequence=sequence, event=event, previous_sha256=previous_sha256
        )
        if records and records[0].get("event") == "prepared":
            try:
                _validate_event_semantics([*records, record])
            except ConfigurationError:
                _quarantine_pending_event(journal, name)
                continue
        final_name = f"{sequence:08d}-{event}.json"
        try:
            os.link(
                name,
                final_name,
                src_dir_fd=journal.fd,
                dst_dir_fd=journal.fd,
                follow_symlinks=False,
            )
            os.fsync(journal.fd)
        except FileExistsError:
            raise ConfigurationError("transaction journal pending publication collided") from None
        except OSError:
            raise ConfigurationError("transaction journal pending publication failed") from None
        records.append(record)
        final_names.append(final_name)
        final_raw.append(raw)
        final_identity.append((pending_metadata.st_dev, pending_metadata.st_ino))
        try:
            os.unlink(name, dir_fd=journal.fd)
            os.fsync(journal.fd)
        except OSError:
            raise ConfigurationError("transaction journal pending cleanup failed") from None


def _read_journal_directory(journal: DurableJournal) -> tuple[list[dict[str, object]], str]:
    _reconcile_pending_events(journal)
    try:
        names = sorted(os.listdir(journal.fd))
    except OSError:
        raise ConfigurationError("transaction journal directory is unavailable") from None
    names = [name for name in names if name != ".quarantine"]
    if not names or len(names) > MAX_JOURNAL_EVENTS:
        raise ConfigurationError("transaction journal event count is invalid")
    records: list[dict[str, object]] = []
    chain = "0" * 64
    for sequence, name in enumerate(names):
        match = _FINAL_EVENT_RE.fullmatch(name)
        if match is None or int(match.group("sequence")) != sequence:
            raise ConfigurationError("transaction journal event name is invalid")
        try:
            event_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=journal.fd,
            )
        except OSError:
            raise ConfigurationError("transaction journal event is unavailable") from None
        try:
            raw, _ = _read_event_fd(event_fd)
        finally:
            os.close(event_fd)
        record = _decode_event_record(
            raw,
            sequence=sequence,
            event=match.group("event"),
            previous_sha256=chain,
        )
        chain = hashlib.sha256(raw).hexdigest()
        records.append(record)
    _validate_event_semantics(records)
    return records, chain


def _validate_event_semantics(records: Sequence[Mapping[str, object]]) -> None:
    expected_keys: dict[str, set[str]] = {
        "prepared": {
            "transaction_id", "request_id", "repository", "step_count", "steps_sha256",
            "manifest_sha256", "result_path", "result_identity",
        },
        "intent_ready": {"intent_sha256"},
        "provider_intent": {"operation"},
        "provider_done": {"operation", "verdict", "failure"},
        "step_intent": {"position", "argv_sha256"},
        "step_done": {"position", "returncode"},
        "child_spawned": {"kind", "operation", "position", "pgid"},
        "gate_abandoned": {"kind", "operation", "position", "group_extinct"},
        "child_lifecycle": {"position", "group_extinct", "pgid"},
        "release_suppressed": {"reason"},
        "release_uncertain": {"verdict"},
        "recovery_intent": {"request_id", "prior_event_count"},
        "recovery_done": {"verdict"},
        "recovery_uncertain": {"verdict"},
        "terminal_intent": {"payload_sha256", "payload"},
        "terminal_done": {"result_sha256"},
    }
    if len(records) < 2 or [records[0].get("event"), records[1].get("event")] != [
        "prepared", "intent_ready"
    ]:
        raise ConfigurationError("transaction journal prefix is invalid")
    seen_terminal = False
    seen_recovery = False
    provider_operations: list[str] = []
    step_positions: list[int] = []
    for position, record in enumerate(records):
        event = record.get("event")
        detail = record.get("detail")
        if type(event) is not str or event not in expected_keys or type(detail) is not dict:
            raise ConfigurationError("transaction journal event semantic is invalid")
        if set(detail) != expected_keys[event]:
            raise ConfigurationError("transaction journal event detail keyset is invalid")
        if event == "prepared":
            repository = detail.get("repository")
            result_identity = detail.get("result_identity")
            if (
                position != 0
                or type(detail.get("transaction_id")) is not str
                or type(detail.get("request_id")) is not str
                or type(repository) is not dict
                or set(repository)
                != {"root", "git_dir", "git_common_dir", "head_oid", "head_ref"}
                or not all(value is None or type(value) is str for value in repository.values())
                or type(detail.get("step_count")) is not int
                or detail["step_count"] < 1
                or type(detail.get("result_path")) is not str
                or type(result_identity) is not dict
                or set(result_identity) != {"dev", "ino", "uid", "mode", "nlink"}
                or not all(type(value) is int for value in result_identity.values())
            ):
                raise ConfigurationError("transaction journal prepared detail is invalid")
            for key in ("steps_sha256", "manifest_sha256"):
                if type(detail.get(key)) is not str or re.fullmatch(
                    r"[0-9a-f]{64}", detail[key]
                ) is None:
                    raise ConfigurationError("transaction journal prepared digest is invalid")
        if event == "intent_ready" and position != 1:
            raise ConfigurationError("transaction journal intent-ready position is invalid")
        if event in {"provider_intent", "provider_done"} and detail.get("operation") not in {
            "begin", "check", "end"
        }:
            raise ConfigurationError("transaction journal provider operation is invalid")
        if event == "provider_intent":
            provider_operations.append(str(detail["operation"]))
            if provider_operations.count(str(detail["operation"])) > 1:
                raise ConfigurationError("transaction journal provider operation is duplicated")
        if event in {"provider_done", "recovery_done"} and detail.get("verdict") not in {
            "allow", "blocked", "indeterminate"
        }:
            raise ConfigurationError("transaction journal verdict is invalid")
        if event == "provider_done" and detail.get("failure") not in {
            None, "provider_failure", "child_lifecycle"
        }:
            raise ConfigurationError("transaction journal provider failure is invalid")
        if event in {"step_intent", "step_done"} and (
            type(detail.get("position")) is not int or detail["position"] < 0
        ):
            raise ConfigurationError("transaction journal step position is invalid")
        if event == "step_intent":
            step_position = int(detail["position"])
            if step_position != len(step_positions):
                raise ConfigurationError("transaction journal step sequence is invalid")
            step_positions.append(step_position)
            if type(detail.get("argv_sha256")) is not str or re.fullmatch(
                r"[0-9a-f]{64}", detail["argv_sha256"]
            ) is None:
                raise ConfigurationError("transaction journal step argv digest is invalid")
        if event == "step_done" and type(detail.get("returncode")) is not int:
            raise ConfigurationError("transaction journal step return code is invalid")
        if event == "child_lifecycle" and (
            type(detail.get("group_extinct")) is not bool
            or (
                detail.get("position") is not None
                and type(detail.get("position")) is not int
            )
            or (
                detail.get("pgid") is not None
                and type(detail.get("pgid")) is not int
            )
        ):
            raise ConfigurationError("transaction journal lifecycle detail is invalid")
        if event == "child_spawned" and (
            detail.get("kind") not in {"provider", "step", "recovery"}
            or type(detail.get("pgid")) is not int
            or detail["pgid"] <= 0
            or (
                detail.get("kind") == "step"
                and (
                    type(detail.get("position")) is not int
                    or detail["position"] < 0
                    or detail.get("operation") is not None
                )
            )
            or (
                detail.get("kind") in {"provider", "recovery"}
                and (
                    detail.get("position") is not None
                    or detail.get("operation") not in {"begin", "check", "end"}
                )
            )
        ):
            raise ConfigurationError("transaction journal child spawn detail is invalid")
        if event == "gate_abandoned" and (
            detail.get("kind") not in {"provider", "step", "recovery"}
            or detail.get("group_extinct") is not True
            or (
                detail.get("kind") == "step"
                and (
                    type(detail.get("position")) is not int
                    or detail["position"] < 0
                    or detail.get("operation") is not None
                )
            )
            or (
                detail.get("kind") in {"provider", "recovery"}
                and (
                    detail.get("position") is not None
                    or detail.get("operation") not in {"begin", "check", "end"}
                )
            )
        ):
            raise ConfigurationError("transaction journal abandoned gate detail is invalid")
        if event in {"intent_ready", "terminal_done"}:
            key = "intent_sha256" if event == "intent_ready" else "result_sha256"
            if type(detail.get(key)) is not str or re.fullmatch(r"[0-9a-f]{64}", detail[key]) is None:
                raise ConfigurationError("transaction journal digest is invalid")
        if event == "terminal_intent" and (
            type(detail.get("payload")) is not dict
            or type(detail.get("payload_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", detail["payload_sha256"]) is None
        ):
            raise ConfigurationError("transaction journal terminal payload is invalid")
        if event == "terminal_intent":
            if seen_terminal:
                raise ConfigurationError("transaction journal terminal intent is duplicated")
            seen_terminal = True
            _validate_terminal_payload(
                detail["payload"],
                expected_payload_sha256=detail["payload_sha256"],
                expected_prefix_sha256=record.get("previous_sha256"),
            )
        if event == "recovery_intent":
            prior_abandoned_recovery = (
                position > 0
                and records[position - 1].get("event") == "gate_abandoned"
                and records[position - 1].get("detail", {}).get("kind") == "recovery"
            )
            if seen_recovery and not prior_abandoned_recovery:
                raise ConfigurationError("transaction journal recovery is duplicated")
            seen_recovery = True
            if (
                type(detail.get("request_id")) is not str
                or SAFE_REQUEST_ID_RE.fullmatch(detail["request_id"]) is None
                or type(detail.get("prior_event_count")) is not int
                or detail["prior_event_count"] != position
            ):
                raise ConfigurationError("transaction journal recovery intent is invalid")
        if event in {"release_uncertain", "recovery_uncertain"} and detail.get(
            "verdict"
        ) not in {"blocked", "indeterminate"}:
            raise ConfigurationError("transaction journal uncertain verdict is invalid")
        if event == "release_suppressed" and detail.get("reason") != "group_extinction_unproven":
            raise ConfigurationError("transaction journal release suppression is invalid")
        if position >= 2:
            previous_event = records[position - 1].get("event")
            if event == "provider_done" and previous_event not in {
                "provider_intent", "child_spawned"
            }:
                raise ConfigurationError("provider done lacks adjacent intent")
            if event == "step_done" and previous_event not in {"step_intent", "child_spawned"}:
                raise ConfigurationError("step done lacks adjacent intent")
            if event == "terminal_done" and previous_event != "terminal_intent":
                raise ConfigurationError("terminal done lacks adjacent intent")
            if event == "recovery_done" and previous_event not in {
                "recovery_intent", "child_spawned"
            }:
                raise ConfigurationError("recovery done lacks adjacent intent")
            if previous_event == "terminal_done":
                raise ConfigurationError("transaction journal continues after terminal completion")
            if previous_event == "terminal_intent" and event != "terminal_done":
                raise ConfigurationError("transaction journal terminal intent is not finalized")
            if previous_event == "provider_intent" and event not in {
                "provider_done", "child_spawned", "child_lifecycle", "gate_abandoned"
            }:
                raise ConfigurationError("transaction journal provider intent is unresolved")
            if previous_event == "step_intent" and event not in {
                "step_done", "child_spawned", "child_lifecycle", "gate_abandoned"
            }:
                raise ConfigurationError("transaction journal step intent is unresolved")
            if previous_event == "recovery_intent" and event not in {
                "recovery_done", "child_spawned", "child_lifecycle", "gate_abandoned"
            }:
                raise ConfigurationError("transaction journal recovery intent is unresolved")
            if previous_event == "child_spawned" and event not in {
                "provider_done", "step_done", "recovery_done", "child_lifecycle"
            }:
                raise ConfigurationError("transaction journal spawned child is unresolved")
            if previous_event == "child_spawned":
                spawned = records[position - 1]["detail"]
                if (
                    (event == "provider_done" and (
                        spawned.get("kind") != "provider"
                        or spawned.get("operation") != detail.get("operation")
                    ))
                    or (event == "step_done" and (
                        spawned.get("kind") != "step"
                        or spawned.get("position") != detail.get("position")
                    ))
                    or (event == "recovery_done" and spawned.get("kind") != "recovery")
                    or (event == "child_lifecycle" and spawned.get("pgid") != detail.get("pgid"))
                ):
                    raise ConfigurationError("transaction journal child completion mismatches spawn")
    if provider_operations and provider_operations[0] != "begin":
        raise ConfigurationError("transaction journal provider begin is missing")
    if "check" in provider_operations and provider_operations.index("check") != 1:
        raise ConfigurationError("transaction journal provider check ordering is invalid")
    if "end" in provider_operations and provider_operations[-1] != "end":
        raise ConfigurationError("transaction journal provider end ordering is invalid")


def _resume_journal(path: Path) -> tuple[DurableJournal, list[dict[str, object]]]:
    journal = _open_journal(path, create=False)
    records, chain = _read_journal_directory(journal)
    journal.sequence = len(records)
    journal.chain_sha256 = chain
    return journal, records


def _load_recovery_manifest(
    path: Path,
    *,
    provider: Provider,
    acquired_digests: Mapping[str, str],
) -> tuple[list[dict[str, str]], str]:
    value, raw = _read_canonical_object(path)
    if set(value) != {"schema", "provider_identity_sha256", "allowed_provider_digests"}:
        raise ConfigurationError("recovery provider manifest keyset is invalid")
    if value.get("schema") != RECOVERY_MANIFEST_SCHEMA:
        raise ConfigurationError("recovery provider manifest schema is invalid")
    if value.get("provider_identity_sha256") != provider_identity_sha256(provider):
        raise ConfigurationError("recovery provider manifest topology does not match")
    candidates = value.get("allowed_provider_digests")
    expected_keys = set(acquired_digests)
    if type(candidates) is not list or len(candidates) != 1:
        raise ConfigurationError("generic recovery provider manifest must authorize one current map")
    normalized: list[dict[str, str]] = []
    for candidate in candidates:
        if (
            type(candidate) is not dict
            or set(candidate) != expected_keys
            or not all(type(k) is str and type(v) is str for k, v in candidate.items())
            or not all(re.fullmatch(r"[0-9a-f]{64}", v) for v in candidate.values())
        ):
            raise ConfigurationError("recovery provider manifest digest map is invalid")
        item = dict(candidate)
        if item in normalized:
            raise ConfigurationError("recovery provider manifest contains a duplicate map")
        normalized.append(item)
    if dict(acquired_digests) not in normalized:
        raise ConfigurationError("recovery provider manifest omits acquired provider bytes")
    return normalized, hashlib.sha256(raw).hexdigest()


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
    intent_fd: int | None = None


@dataclass
class DurableJournal:
    fd: int
    path: Path
    sequence: int = 0
    chain_sha256: str = "0" * 64

    def append(self, event: str, detail: Mapping[str, object]) -> str:
        if (
            type(event) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event) is None
            or type(detail) is not dict
            or self.sequence >= MAX_JOURNAL_EVENTS
        ):
            raise ConfigurationError("transaction journal event is invalid")
        record = {
            "schema": PREBOUND_JOURNAL_SCHEMA,
            "sequence": self.sequence,
            "previous_sha256": self.chain_sha256,
            "event": event,
            "detail": dict(detail),
        }
        encoded = _canonical_json_bytes(record)
        name = f"{self.sequence:08d}-{event}.json"
        encoded_sha256 = hashlib.sha256(encoded).hexdigest()
        pending_name = f".pending-{self.sequence:08d}-{event}-{encoded_sha256}.tmp"
        pending_fd = -1
        try:
            pending_fd = os.open(
                pending_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self.fd,
            )
        except OSError:
            raise ConfigurationError("transaction journal pending event collision") from None
        try:
            _write_all(pending_fd, encoded)
            os.fsync(pending_fd)
            pending_metadata = os.fstat(pending_fd)
            if (
                not stat.S_ISREG(pending_metadata.st_mode)
                or pending_metadata.st_uid != os.getuid()
                or stat.S_IMODE(pending_metadata.st_mode) != 0o600
                or pending_metadata.st_nlink != 1
                or pending_metadata.st_size != len(encoded)
            ):
                raise ConfigurationError("transaction journal pending event identity is unsafe")
            os.link(
                pending_name,
                name,
                src_dir_fd=self.fd,
                dst_dir_fd=self.fd,
                follow_symlinks=False,
            )
            os.fsync(self.fd)
            published = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if (
                published.st_dev != pending_metadata.st_dev
                or published.st_ino != pending_metadata.st_ino
                or published.st_nlink != 2
            ):
                raise ConfigurationError("transaction journal event publication is unsafe")
            os.unlink(pending_name, dir_fd=self.fd)
            os.fsync(self.fd)
            final_metadata = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if final_metadata.st_nlink != 1:
                raise ConfigurationError("transaction journal event publication is incomplete")
        except ConfigurationError:
            raise
        except OSError:
            raise ConfigurationError("transaction journal event publication failed") from None
        finally:
            if pending_fd >= 0:
                os.close(pending_fd)
        self.chain_sha256 = encoded_sha256
        self.sequence += 1
        return self.chain_sha256


@dataclass
class ReservedTerminal:
    fd: int
    path: Path
    identity: dict[str, int]


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
        completed = _run_child(
            [_platform_git(), "-C", str(repo), *args],
            cwd=str(repo.resolve()),
            env=_closed_git_env(),
            timeout=5,
        )
    except (ChildLifecycleError, OSError):
        raise ConfigurationError("repository policy Git read failed") from None
    if completed.returncode != 0:
        raise ConfigurationError("repository policy Git read failed")
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
    try:
        completed = _run_child(
            [_platform_git(), "-C", str(repo), *args],
            cwd=str(repo.resolve()),
            env=_closed_git_env(),
            timeout=5,
        )
    except (ChildLifecycleError, OSError):
        if allow_failure:
            return None
        raise ConfigurationError("git command failed") from None
    if completed.returncode != 0:
        if allow_failure:
            return None
        raise ConfigurationError("git command failed")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ConfigurationError("git command failed") from None


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
    intent_fd: int | None = None,
    on_spawn: Callable[[int], None] | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Return decoded response, failure kind, and detail."""

    snapshot_reader_fds: list[int] = []
    try:
        request_payload = json.dumps(request, separators=(",", ":")).encode("utf-8")
        if len(request_payload) > MAX_PROVIDER_REQUEST_BYTES:
            raise ConfigurationError("provider request exceeds the bounded stdin payload")
        invocation_argv = list(provider.argv)
        inherited_fds: list[int] = [intent_fd] if intent_fd is not None else []
        pass_fds: tuple[int, ...] = tuple(inherited_fds)
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
            pass_fds = tuple([*inherited_fds, *snapshot_reader_fds])
        completed = _run_child(
            invocation_argv,
            input_bytes=request_payload,
            timeout=timeout,
            pass_fds=pass_fds,
            cwd=os.path.abspath(os.getcwd()),
            env=_closed_child_env(intent_fd=intent_fd),
            on_spawn=on_spawn,
        )
    except ChildLifecycleError as exc:
        if not exc.extinct:
            raise
        return None, "timeout", "provider command did not complete safely"
    except ConfigurationError as exc:
        return None, "invocation", str(exc)
    finally:
        for snapshot_reader_fd in snapshot_reader_fds:
            os.close(snapshot_reader_fd)

    if completed.returncode != 0:
        detail = f"provider exited {completed.returncode}"
        return None, "invocation", detail
    try:
        decoded = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "schema", "provider stdout is not one JSON object"
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
        raise SchemaError("provider response keyset is invalid")
    if unknown:
        raise SchemaError("provider response keyset is invalid")
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
    on_spawn: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    request = _request(
        operation=operation,
        request_id=state.request_id,
        repository=repository,
        session=state.session,
        step_count=step_count,
    )
    raw, failure, detail = _invoke(
        state.provider,
        request,
        timeout=timeout,
        held=state.held,
        intent_fd=state.intent_fd,
        on_spawn=on_spawn,
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
        "message": f"provider returned {response['verdict']}",
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
    transaction_id: str | None = None,
    transaction_intent: Path | None = None,
    transaction_result: Path | None = None,
    transaction_journal: Path | None = None,
    recovery_provider_manifest: Path | None = None,
    policy_home: Path | None = None,
    repository_policy: bool = False,
) -> tuple[dict[str, Any], int]:
    transaction_id = (
        _canonical_uuid_v4(transaction_id)
        if transaction_id is not None
        else str(uuid.uuid4())
    )
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

    intent_fd: int | None = None
    journal: DurableJournal | None = None
    reserved_terminal: ReservedTerminal | None = None
    if transaction_intent is not None:
        if transaction_result is None or transaction_journal is None or recovery_provider_manifest is None:
            raise ConfigurationError(
                "prebound intent requires result, journal, and recovery provider manifest"
            )
        if len(states) != 1 or states[0].held is None:
            raise ConfigurationError(
                "prebound intent requires exactly one pinned policy provider"
            )
        initial_digests = states[0].held.digests()
        step_payload = [list(step) for step in steps]
        steps_sha256 = hashlib.sha256(_canonical_json_bytes(step_payload)).hexdigest()
        intent_payload: dict[str, object] = {
            "schema": PREBOUND_INTENT_SCHEMA,
            "transaction_id": transaction_id,
            "request_id": states[0].request_id,
            "repository": dict(repository),
            "policy_home": str(policy_home) if policy_home is not None else None,
            "provider": states[0].provider.label,
            "provider_identity_sha256": provider_identity_sha256(states[0].provider),
            "allowed_provider_digests": [],
            "step_count": len(steps),
            "steps_sha256": steps_sha256,
            "transaction_result": str(transaction_result),
            "transaction_result_identity": {},
            "transaction_journal": str(transaction_journal),
            "recovery_provider_manifest": str(recovery_provider_manifest),
            "recovery_provider_manifest_sha256": "",
        }
        forbidden_roots = [
            Path(str(repository[field]))
            for field in ("root", "git_dir", "git_common_dir")
            if repository.get(field) is not None
        ]
        if policy_home is not None:
            forbidden_roots.append(policy_home)
        for artifact in (transaction_result, transaction_journal, recovery_provider_manifest):
            _outside_roots(artifact, forbidden_roots)
            if artifact.parent != transaction_intent.parent:
                raise ConfigurationError("prebound artifacts must share one private parent")
        if len(
            {
                str(transaction_intent), str(transaction_result),
                str(transaction_journal), str(recovery_provider_manifest),
            }
        ) != 4:
            raise ConfigurationError("prebound artifact paths must be distinct")
        allowed_maps, manifest_sha256 = _load_recovery_manifest(
            recovery_provider_manifest,
            provider=states[0].provider,
            acquired_digests=initial_digests,
        )
        intent_payload["allowed_provider_digests"] = allowed_maps
        intent_payload["recovery_provider_manifest_sha256"] = manifest_sha256
        reserved_terminal = _reserve_terminal_result(transaction_result)
        intent_payload["transaction_result_identity"] = reserved_terminal.identity
        try:
            journal = _open_journal(transaction_journal, create=True)
        except BaseException as exc:
            _cleanup_preprovider_reservations(
                journal=None, reserved_terminal=reserved_terminal
            )
            reserved_terminal = None
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise ConfigurationError("pre-provider admission failed") from None
        try:
            journal.append(
                "prepared",
                {
                    "transaction_id": transaction_id,
                    "request_id": states[0].request_id,
                    "repository": dict(repository),
                    "step_count": len(steps),
                    "steps_sha256": steps_sha256,
                    "manifest_sha256": manifest_sha256,
                    "result_path": str(transaction_result),
                    "result_identity": reserved_terminal.identity,
                },
            )
            intent_fd, intent_sha256 = _open_prebound_intent(
                transaction_intent, intent_payload, forbidden_roots=forbidden_roots
            )
        except BaseException as exc:
            _cleanup_preprovider_reservations(
                journal=journal, reserved_terminal=reserved_terminal
            )
            journal = None
            reserved_terminal = None
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise ConfigurationError("pre-provider admission failed") from None
        receipt["transaction_intent"] = {
            "path": str(transaction_intent),
            "sha256": intent_sha256,
        }
        receipt["transaction_result"] = str(transaction_result)
        receipt["transaction_journal"] = str(transaction_journal)
        receipt["recovery_provider_manifest"] = {
            "path": str(recovery_provider_manifest),
            "sha256": manifest_sha256,
        }
        try:
            journal.append("intent_ready", {"intent_sha256": intent_sha256})
        except BaseException as exc:
            _cleanup_preprovider_intent(transaction_intent, intent_fd)
            intent_fd = None
            _cleanup_preprovider_reservations(
                journal=journal, reserved_terminal=reserved_terminal
            )
            journal = None
            reserved_terminal = None
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise ConfigurationError("pre-provider admission failed") from None
        states[0].intent_fd = intent_fd

    release_permitted = True
    lifecycle_indeterminate = False
    try:
        begin_records: list[dict[str, Any]] = []
        for state in states:
            if journal is not None:
                journal.append("provider_intent", {"operation": "begin"})
            record = _call(
                state,
                operation="begin",
                repository=repository,
                step_count=len(steps),
                timeout=timeout,
                on_spawn=(
                    (lambda pgid: journal.append(
                        "child_spawned",
                        {"kind": "provider", "operation": "begin", "position": None, "pgid": pgid},
                    ))
                    if journal is not None
                    else None
                ),
            )
            state.begin = record
            begin_records.append(record)
            if journal is not None:
                journal.append(
                    "provider_done",
                    {
                        "operation": "begin",
                        "verdict": str(record.get("verdict", "indeterminate")),
                        "failure": "provider_failure" if record.get("failure") is not None else None,
                    },
                )
        receipt["provider_results"].extend(begin_records)
        begin_verdict = worst_verdict(begin_records)

        if begin_verdict == "allow":
            check_records = []
            for state in states:
                if journal is not None:
                    journal.append("provider_intent", {"operation": "check"})
                check_record = _call(
                    state,
                    operation="check",
                    repository=repository,
                    step_count=len(steps),
                    timeout=timeout,
                    on_spawn=(
                        (lambda pgid: journal.append(
                            "child_spawned",
                            {"kind": "provider", "operation": "check", "position": None, "pgid": pgid},
                        ))
                        if journal is not None
                        else None
                    ),
                )
                check_records.append(check_record)
                if journal is not None:
                    journal.append(
                        "provider_done",
                        {
                            "operation": "check",
                            "verdict": str(check_record.get("verdict", "indeterminate")),
                            "failure": (
                                "provider_failure"
                                if check_record.get("failure") is not None
                                else None
                            ),
                        },
                    )
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
                if journal is not None:
                    journal.append(
                        "step_intent",
                        {
                            "position": position,
                            "argv_sha256": hashlib.sha256(
                                _canonical_json_bytes(list(argv))
                            ).hexdigest(),
                        },
                    )
                step_env = _closed_child_env(intent_fd=intent_fd)
                pass_fds: tuple[int, ...] = ()
                if intent_fd is not None:
                    pass_fds = (intent_fd,)
                try:
                    completed = _run_child(
                        list(argv),
                        cwd=repo_root,
                        env=step_env,
                        pass_fds=pass_fds,
                        timeout=timeout,
                        on_spawn=(
                            (lambda pgid, position=position: journal.append(
                                "child_spawned",
                                {"kind": "step", "operation": None, "position": position, "pgid": pgid},
                            ))
                            if journal is not None
                            else None
                        ),
                    )
                except ChildLifecycleError as exc:
                    receipt["step_results"].append(
                        {
                            "position": position,
                            "returncode": None,
                            "failure": "child_lifecycle",
                            "group_extinct": exc.extinct,
                            "pgid": exc.pgid,
                        }
                    )
                    if journal is not None:
                        journal.append(
                            "child_lifecycle",
                            {
                                "position": position,
                                "group_extinct": exc.extinct,
                                "pgid": exc.pgid,
                            },
                        )
                    release_permitted = exc.extinct
                    lifecycle_indeterminate = True
                    exit_code = EXIT_INDETERMINATE
                    break
                receipt["step_results"].append(
                    {"position": position, "returncode": completed.returncode}
                )
                if journal is not None:
                    journal.append(
                        "step_done",
                        {"position": position, "returncode": completed.returncode},
                    )
                if completed.returncode != 0:
                    exit_code = completed.returncode or 1
                    break
    except ChildLifecycleError as exc:
        release_permitted = exc.extinct
        lifecycle_indeterminate = True
        receipt["provider_lifecycle"] = {
            "failure": "child_lifecycle",
            "group_extinct": exc.extinct,
            "pgid": exc.pgid,
        }
        if journal is not None:
            journal.append(
                "child_lifecycle",
                {"position": None, "group_extinct": exc.extinct, "pgid": exc.pgid},
            )
        exit_code = EXIT_INDETERMINATE
    finally:
        if release_permitted:
            for state in reversed(states):
                if journal is not None:
                    journal.append("provider_intent", {"operation": "end"})
                release_observed = True
                try:
                    release_record = _call(
                        state,
                        operation="end",
                        repository=repository,
                        step_count=len(steps),
                        timeout=timeout,
                        on_spawn=(
                            (lambda pgid: journal.append(
                                "child_spawned",
                                {"kind": "provider", "operation": "end", "position": None, "pgid": pgid},
                            ))
                            if journal is not None
                            else None
                        ),
                    )
                except ChildLifecycleError as exc:
                    release_observed = False
                    release_permitted = exc.extinct
                    lifecycle_indeterminate = True
                    release_record = {
                        "provider": state.provider.label,
                        "operation": "end",
                        "verdict": "indeterminate",
                        "failure": "child_lifecycle",
                        "message": "provider end did not complete safely",
                    }
                    if journal is not None:
                        journal.append(
                            "child_lifecycle",
                            {"position": None, "group_extinct": exc.extinct, "pgid": exc.pgid},
                        )
                receipt["release_results"].append(release_record)
                if journal is not None and release_observed:
                    journal.append(
                        "provider_done",
                        {
                            "operation": "end",
                            "verdict": str(release_record.get("verdict", "indeterminate")),
                            "failure": (
                                "provider_failure"
                                if release_record.get("failure") is not None
                                else None
                            ),
                        },
                    )
                if not release_permitted:
                    break

    if not release_permitted:
        receipt["release_verdict"] = "indeterminate"
        receipt["outcome"] = "child_lifecycle_indeterminate"
        if journal is not None:
            journal.append("release_suppressed", {"reason": "group_extinction_unproven"})
            os.close(journal.fd)
        if intent_fd is not None:
            os.close(intent_fd)
        if reserved_terminal is not None:
            os.close(reserved_terminal.fd)
        return receipt, EXIT_INDETERMINATE

    release_verdict = worst_verdict(receipt["release_results"])
    receipt["release_verdict"] = release_verdict
    if release_verdict != "allow":
        preflight_timeout = any(
            type(record) is dict and record.get("failure") == "timeout"
            for record in receipt.get("provider_results", [])
        )
        receipt["outcome"] = (
            "child_lifecycle_indeterminate"
            if lifecycle_indeterminate
            else "release_failed_after_preflight"
        )
        if journal is not None:
            journal.append("release_uncertain", {"verdict": release_verdict})
            os.close(journal.fd)
        if intent_fd is not None:
            os.close(intent_fd)
        if reserved_terminal is not None:
            os.close(reserved_terminal.fd)
        return (
            receipt,
            EXIT_INDETERMINATE
            if lifecycle_indeterminate or preflight_timeout
            else EXIT_RELEASE_FAILED,
        )
    if lifecycle_indeterminate:
        receipt["outcome"] = "child_lifecycle_failed"
    elif receipt["preflight_verdict"] != "allow":
        receipt["outcome"] = "fenced_without_mutation"
    elif exit_code == 0:
        receipt["outcome"] = "completed"
    else:
        receipt["outcome"] = "mutation_command_failed"
    if intent_fd is not None:
        assert transaction_result is not None
        assert journal is not None
        receipt["repository_policy"] = repository_policy
        if policy_home is not None:
            receipt["policy_home"] = str(policy_home)
        receipt["exit_code"] = exit_code
        receipt["journal_prefix_sha256"] = journal.chain_sha256
        assert reserved_terminal is not None
        assert transaction_result is not None
        assert transaction_journal is not None
        assert states[0].held is not None
        terminal_payload = _make_terminal_payload(
            receipt,
            transaction_intent=receipt["transaction_intent"],
            transaction_result=transaction_result,
            transaction_journal=transaction_journal,
            journal_prefix_sha256=journal.chain_sha256,
            provider_identity=provider_identity_sha256(states[0].provider),
            provider_digests=states[0].held.digests(),
            request_id=states[0].request_id,
            step_count=len(steps),
            steps_sha256=steps_sha256,
            policy_home=policy_home,
            repository_policy=repository_policy,
            exit_code=exit_code,
        )
        terminal_payload_sha256 = hashlib.sha256(
            _canonical_json_bytes(terminal_payload)
        ).hexdigest()
        # The exact canonical payload is durable before its reserved inode is populated.
        # Recovery can therefore finish a partial terminal publication without end replay.
        journal.append(
            "terminal_intent",
            {"payload_sha256": terminal_payload_sha256, "payload": terminal_payload},
        )
        result_sha256 = _write_terminal_result(reserved_terminal, terminal_payload)
        journal.append("terminal_done", {"result_sha256": result_sha256})
        os.close(journal.fd)
        os.close(intent_fd)
        os.close(reserved_terminal.fd)
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
    step_count: int = 1,
    held: HeldProviderSources | None = None,
    intent_fd: int | None = None,
    on_spawn: Callable[[int], None] | None = None,
) -> tuple[dict[str, Any], int]:
    """Idempotently ask one pinned provider to end a stranded request."""

    if SAFE_REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ConfigurationError(
            "--recover-request-id must be 1-256 safe request-id characters"
        )
    state = ProviderState(provider=provider, request_id=request_id)
    state.held = held if held is not None else hold_provider_sources(provider)
    state.intent_fd = intent_fd
    assert state.held is not None
    result = _call(
        state,
        operation="end",
        repository=repository,
        step_count=step_count,
        timeout=timeout,
        on_spawn=on_spawn,
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
                "request_id": request_id,
                "provider_identity_sha256": provider_identity_sha256(provider),
                "pinned": True,
                "digests": state.held.digests(),
            }
        ],
        "recovery_result": result,
        "release_verdict": verdict,
    }
    return receipt, 0 if verdict == "allow" else EXIT_RELEASE_FAILED


def recover_prebound_intent(
    *,
    path: Path,
    repository: Mapping[str, str | None],
    provider: Provider,
    policy_home: Path | None,
    timeout: float,
    expected_transaction_id: str,
    expected_intent_sha256: str,
    repository_policy: bool = False,
) -> tuple[dict[str, Any], int]:
    """End exactly one prebound request after proving its original holder is gone."""

    expected_transaction_id = _canonical_uuid_v4(expected_transaction_id)
    if re.fullmatch(r"[0-9a-f]{64}", expected_intent_sha256) is None:
        raise ConfigurationError("expected intent SHA-256 is invalid")
    forbidden_roots = [
        Path(str(repository[field]))
        for field in ("root", "git_dir", "git_common_dir")
        if repository.get(field) is not None
    ]
    if policy_home is not None:
        forbidden_roots.append(policy_home)
    fd, intent, raw = _read_locked_intent(path, forbidden_roots=forbidden_roots)
    try:
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        if raw_sha256 != expected_intent_sha256:
            raise ConfigurationError("recovery intent SHA-256 does not match caller expectation")
        expected_keys = {
            "schema", "transaction_id", "request_id", "repository", "policy_home",
            "provider", "provider_identity_sha256", "allowed_provider_digests",
            "step_count", "steps_sha256", "transaction_result", "transaction_journal",
            "recovery_provider_manifest", "recovery_provider_manifest_sha256",
            "transaction_result_identity",
        }
        if set(intent) != expected_keys or intent.get("schema") != PREBOUND_INTENT_SCHEMA:
            raise ConfigurationError("recovery intent schema is invalid")
        transaction_id = _canonical_uuid_v4(intent.get("transaction_id"))
        if transaction_id != expected_transaction_id:
            raise ConfigurationError("recovery transaction id does not match caller expectation")
        if intent.get("request_id") != f"{transaction_id}:0":
            raise ConfigurationError("recovery intent request id is invalid")
        if intent.get("repository") != dict(repository):
            raise ConfigurationError("recovery intent repository identity does not match")
        expected_home = str(policy_home) if policy_home is not None else None
        if intent.get("policy_home") != expected_home:
            raise ConfigurationError("recovery intent policy home does not match")
        result_raw = intent.get("transaction_result")
        if type(result_raw) is not str:
            raise ConfigurationError("recovery intent terminal result path is invalid")
        result_path = Path(result_raw)
        _outside_roots(result_path, forbidden_roots)
        if result_path.parent != path.parent:
            raise ConfigurationError("recovery intent terminal result parent does not match")
        result_identity = intent.get("transaction_result_identity")
        if (
            type(result_identity) is not dict
            or set(result_identity) != {"dev", "ino", "uid", "mode", "nlink"}
            or not all(type(value) is int for value in result_identity.values())
            or result_identity.get("uid") != os.getuid()
            or result_identity.get("mode") != 0o600
            or result_identity.get("nlink") != 1
        ):
            raise ConfigurationError("recovery terminal reservation identity is invalid")
        journal_raw = intent.get("transaction_journal")
        manifest_raw = intent.get("recovery_provider_manifest")
        manifest_sha256 = intent.get("recovery_provider_manifest_sha256")
        if (
            type(journal_raw) is not str
            or type(manifest_raw) is not str
            or type(manifest_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
        ):
            raise ConfigurationError("recovery intent support paths are invalid")
        journal_path = Path(journal_raw)
        manifest_path = Path(manifest_raw)
        for artifact in (journal_path, manifest_path):
            _outside_roots(artifact, forbidden_roots)
            if artifact.parent != path.parent:
                raise ConfigurationError("recovery intent support parent does not match")
        if (
            intent.get("provider") != provider.label
            or intent.get("provider_identity_sha256") != provider_identity_sha256(provider)
        ):
            raise ConfigurationError("recovery intent provider topology does not match")
        step_count = intent.get("step_count")
        steps_sha256 = intent.get("steps_sha256")
        if (
            type(step_count) is not int
            or step_count < 1
            or type(steps_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", steps_sha256) is None
        ):
            raise ConfigurationError("recovery intent step plan is invalid")
        allowed = intent.get("allowed_provider_digests")
        if type(allowed) is not list or not allowed:
            raise ConfigurationError("recovery intent provider digest allowlist is invalid")
        normalized: list[dict[str, str]] = []
        digest_keys: set[str] | None = None
        for candidate in allowed:
            if (
                type(candidate) is not dict
                or not candidate
                or not all(type(k) is str and type(v) is str for k, v in candidate.items())
                or not all(re.fullmatch(r"[0-9a-f]{64}", v) for v in candidate.values())
            ):
                raise ConfigurationError("recovery intent provider digest allowlist is invalid")
            item = dict(candidate)
            if digest_keys is None:
                digest_keys = set(item)
            if set(item) != digest_keys or item in normalized or len(normalized) >= 1:
                raise ConfigurationError("recovery intent provider digest allowlist is invalid")
            normalized.append(item)
        journal, records = _resume_journal(journal_path)
        expected_prepared = {
            "transaction_id": transaction_id,
            "request_id": f"{transaction_id}:0",
            "repository": dict(repository),
            "step_count": step_count,
            "steps_sha256": steps_sha256,
            "manifest_sha256": manifest_sha256,
            "result_path": str(result_path),
            "result_identity": dict(result_identity),
        }
        if (
            len(records) < 2
            or records[0].get("event") != "prepared"
            or records[0].get("detail") != expected_prepared
            or records[1].get("event") != "intent_ready"
            or records[1].get("detail") != {"intent_sha256": raw_sha256}
        ):
            os.close(journal.fd)
            raise ConfigurationError("recovery journal does not bind intent")

        terminal_done = [record for record in records if record.get("event") == "terminal_done"]
        terminal_intents = [record for record in records if record.get("event") == "terminal_intent"]
        if len(terminal_intents) > 1 or len(terminal_done) > 1:
            os.close(journal.fd)
            raise ConfigurationError("terminal journal state is ambiguous")
        if terminal_intents:
            terminal_detail = terminal_intents[0].get("detail")
            if (
                type(terminal_detail) is not dict
                or set(terminal_detail) != {"payload_sha256", "payload"}
                or type(terminal_detail.get("payload")) is not dict
            ):
                os.close(journal.fd)
                raise ConfigurationError("terminal intent payload is invalid")
            expected_terminal = dict(terminal_detail["payload"])
            expected_bytes = _canonical_json_bytes(expected_terminal)
            expected_sha = hashlib.sha256(expected_bytes).hexdigest()
            try:
                _validate_terminal_payload(
                    expected_terminal,
                    expected_payload_sha256=terminal_detail.get("payload_sha256"),
                    expected_prefix_sha256=terminal_intents[0].get("previous_sha256"),
                )
            except ConfigurationError:
                os.close(journal.fd)
                raise ConfigurationError("terminal intent does not bind recovery") from None
            if (
                terminal_detail.get("payload_sha256") != expected_sha
                or expected_terminal.get("transaction_id") != transaction_id
                or expected_terminal.get("repository") != dict(repository)
                or expected_terminal.get("transaction_intent")
                != {"path": str(path), "sha256": raw_sha256}
                or expected_terminal.get("transaction_result") != str(result_path)
                or expected_terminal.get("transaction_journal") != str(journal_path)
                or expected_terminal.get("provider_identity_sha256")
                != provider_identity_sha256(provider)
                or expected_terminal.get("step_count") != step_count
                or expected_terminal.get("steps_sha256") != steps_sha256
            ):
                os.close(journal.fd)
                raise ConfigurationError("terminal intent does not bind recovery")
            _reconcile_terminal_publication(
                result_path,
                original_identity=result_identity,
                content=expected_bytes,
                content_sha256=expected_sha,
            )
            if terminal_done:
                if terminal_done[0].get("detail") != {"result_sha256": expected_sha}:
                    os.close(journal.fd)
                    raise ConfigurationError("terminal result hash does not match journal")
            else:
                journal.append("terminal_done", {"result_sha256": expected_sha})
            os.close(journal.fd)
            return dict(expected_terminal["receipt"]), int(expected_terminal["exit_code"])

        if terminal_done:
            os.close(journal.fd)
            raise ConfigurationError("journal claims a missing terminal result")
        reserved_terminal = _open_reserved_terminal(result_path, result_identity)
        os.lseek(reserved_terminal.fd, 0, os.SEEK_SET)
        result_bytes = os.read(reserved_terminal.fd, MAX_INTENT_BYTES + 1)
        if result_bytes:
            os.close(reserved_terminal.fd)
            os.close(journal.fd)
            raise ConfigurationError("terminal reservation contains unbound bytes")
        for record in records:
            if record.get("event") == "child_lifecycle":
                detail = record.get("detail")
                if type(detail) is dict and detail.get("group_extinct") is False:
                    pgid = detail.get("pgid")
                    if type(pgid) is not int or pgid <= 0 or _child_group_alive(pgid):
                        os.close(reserved_terminal.fd)
                        os.close(journal.fd)
                        raise ConfigurationError("original child process group is not extinct")
        if records[-1].get("event") == "child_spawned":
            spawned_detail = records[-1].get("detail")
            pgid = spawned_detail.get("pgid") if type(spawned_detail) is dict else None
            if type(pgid) is not int or pgid <= 0 or _child_group_alive(pgid):
                os.close(reserved_terminal.fd)
                os.close(journal.fd)
                raise ConfigurationError("original child process group is not extinct")
            journal.append(
                "child_lifecycle",
                {
                    "position": (
                        spawned_detail.get("position")
                        if spawned_detail.get("kind") == "step"
                        else None
                    ),
                    "group_extinct": True,
                    "pgid": pgid,
                },
            )
            records, _chain = _read_journal_directory(journal)

        # A process that died after publishing an operation intent but before
        # publishing child_spawned never released the child-side gate. Holding
        # the intent flock proves the gated process group (which inherited the
        # fd) is gone. Resolve that prefix explicitly before the end-only
        # recovery intent; never reinterpret it as a completed provider/step.
        if records[-1].get("event") in {"provider_intent", "step_intent", "recovery_intent"}:
            unresolved = records[-1]
            detail = unresolved.get("detail")
            if type(detail) is not dict:
                os.close(reserved_terminal.fd)
                os.close(journal.fd)
                raise ConfigurationError("unresolved gated child intent is invalid")
            event = unresolved.get("event")
            journal.append(
                "gate_abandoned",
                {
                    "kind": (
                        "step" if event == "step_intent"
                        else "recovery" if event == "recovery_intent"
                        else "provider"
                    ),
                    "operation": detail.get("operation") if event != "step_intent" else None,
                    "position": detail.get("position") if event == "step_intent" else None,
                    "group_extinct": True,
                },
            )
            records, _chain = _read_journal_directory(journal)

        held = hold_provider_sources(provider)
        if held is None:
            os.close(journal.fd)
            os.close(reserved_terminal.fd)
            raise ConfigurationError("recovery provider was not held")
        manifest_maps, admitted_manifest_sha256 = _load_recovery_manifest(
            manifest_path,
            provider=provider,
            acquired_digests=held.digests(),
        )
        if admitted_manifest_sha256 != manifest_sha256 or manifest_maps != normalized:
            os.close(journal.fd)
            os.close(reserved_terminal.fd)
            raise ConfigurationError("recovery provider manifest does not match intent")
        if held.digests() not in normalized:
            os.close(journal.fd)
            os.close(reserved_terminal.fd)
            raise ConfigurationError("recovery provider bytes are not authorized by intent")
        journal.append(
            "recovery_intent",
            {"request_id": f"{transaction_id}:0", "prior_event_count": len(records)},
        )
        try:
            receipt, exit_code = recover_transaction(
                repository=repository,
                provider=provider,
                request_id=f"{transaction_id}:0",
                timeout=timeout,
                step_count=step_count,
                held=held,
                intent_fd=fd,
                on_spawn=lambda pgid: journal.append(
                    "child_spawned",
                    {"kind": "recovery", "operation": "end", "position": None, "pgid": pgid},
                ),
            )
        except ChildLifecycleError as exc:
            journal.append(
                "child_lifecycle",
                {"position": None, "group_extinct": exc.extinct, "pgid": exc.pgid},
            )
            os.close(journal.fd)
            os.close(reserved_terminal.fd)
            raise ConfigurationError("recovery provider lifecycle is indeterminate") from None
        receipt["transaction_id"] = transaction_id
        journal.append("recovery_done", {"verdict": str(receipt.get("release_verdict"))})
        receipt["transaction_intent"] = {
            "path": str(path),
            "sha256": raw_sha256,
        }
        receipt["original_mutation_state"] = "unknown"
        receipt["original_step_count"] = step_count
        receipt["original_steps_sha256"] = steps_sha256
        receipt["transaction_result"] = str(result_path)
        receipt["transaction_journal"] = str(journal_path)
        receipt["recovery_provider_manifest"] = {
            "path": str(manifest_path),
            "sha256": manifest_sha256,
        }
        receipt["repository_policy"] = repository_policy
        if policy_home is not None:
            receipt["policy_home"] = str(policy_home)
        if receipt.get("release_verdict") != "allow":
            journal.append("recovery_uncertain", {"verdict": receipt.get("release_verdict")})
            os.close(journal.fd)
            os.close(reserved_terminal.fd)
            return receipt, exit_code
        receipt["exit_code"] = exit_code
        receipt["journal_prefix_sha256"] = journal.chain_sha256
        terminal_payload = _make_terminal_payload(
            receipt,
            transaction_intent=receipt["transaction_intent"],
            transaction_result=result_path,
            transaction_journal=journal_path,
            journal_prefix_sha256=journal.chain_sha256,
            provider_identity=provider_identity_sha256(provider),
            provider_digests=held.digests(),
            request_id=f"{transaction_id}:0",
            step_count=step_count,
            steps_sha256=steps_sha256,
            policy_home=policy_home,
            repository_policy=repository_policy,
            exit_code=exit_code,
        )
        payload_sha256 = hashlib.sha256(_canonical_json_bytes(terminal_payload)).hexdigest()
        journal.append(
            "terminal_intent",
            {"payload_sha256": payload_sha256, "payload": terminal_payload},
        )
        result_sha256 = _write_terminal_result(reserved_terminal, terminal_payload)
        journal.append("terminal_done", {"result_sha256": result_sha256})
        os.close(journal.fd)
        os.close(reserved_terminal.fd)
        return receipt, exit_code
    finally:
        os.close(fd)


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
        "--recover-intent",
        metavar="ABS_PATH",
        help="end-only recovery of one inactive prebound transaction intent",
    )
    parser.add_argument(
        "--recover-transaction-id",
        metavar="UUID",
        help="caller-expected canonical UUID v4 for --recover-intent",
    )
    parser.add_argument(
        "--recover-intent-sha256",
        metavar="SHA256",
        help="caller-expected exact canonical intent bytes for --recover-intent",
    )
    parser.add_argument(
        "--transaction-id",
        metavar="UUID",
        help="caller-prebound canonical UUID v4 (requires --transaction-intent)",
    )
    parser.add_argument(
        "--transaction-intent",
        metavar="ABS_PATH",
        help="O_EXCL private single-use intent created and held before provider begin",
    )
    parser.add_argument(
        "--transaction-result",
        metavar="ABS_PATH",
        help="O_EXCL private terminal receipt paired with --transaction-intent",
    )
    parser.add_argument(
        "--transaction-journal",
        metavar="ABS_PATH",
        help="O_EXCL private directory of durable hash-chain event files",
    )
    parser.add_argument(
        "--recovery-provider-manifest",
        metavar="ABS_PATH",
        help="private canonical singleton current-provider digest manifest",
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
        if (
            args.recover_receipt
            or args.recover_intent
            or args.recover_transaction_id
            or args.recover_intent_sha256
            or args.transaction_id
            or args.transaction_intent
            or args.transaction_result
            or args.transaction_journal
            or args.recovery_provider_manifest
            or args.require_capability
            or args.step_json
            or args.command
        ):
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
        recovery_modes = int(bool(args.recover_receipt)) + int(bool(args.recover_intent))
        if recovery_modes > 1:
            raise ConfigurationError("choose exactly one recovery mode")
        if recovery_modes and (args.step_json or args.command):
            raise ConfigurationError(
                "recovery cannot be combined with mutation steps"
            )
        if args.recover_intent and not (
            args.recover_transaction_id and args.recover_intent_sha256
        ):
            raise ConfigurationError(
                "--recover-intent requires expected transaction UUID and intent SHA-256"
            )
        if not args.recover_intent and (
            args.recover_transaction_id or args.recover_intent_sha256
        ):
            raise ConfigurationError(
                "recovery expectations require --recover-intent"
            )
        if bool(args.transaction_id) != bool(args.transaction_intent):
            raise ConfigurationError(
                "--transaction-id and --transaction-intent are required together"
            )
        if not (
            bool(args.transaction_intent)
            == bool(args.transaction_result)
            == bool(args.transaction_journal)
            == bool(args.recovery_provider_manifest)
        ):
            raise ConfigurationError(
                "prebound intent, result, journal, and recovery manifest are required together"
            )
        if recovery_modes and (args.transaction_id or args.transaction_intent):
            raise ConfigurationError("recovery cannot create a transaction intent")
        steps = [] if recovery_modes else parse_steps(args.step_json, args.command)
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
        if "prebound-intent-recovery-v1" in args.require_capability:
            if len(policy_providers) != 1 or ambient_providers:
                raise ConfigurationError(
                    "prebound intent capability requires exactly one pinned policy "
                    "provider and no ambient providers"
                )
            if not (args.transaction_id and args.transaction_intent) and not args.recover_intent:
                raise ConfigurationError(
                    "prebound intent capability requires mutation intent or recovery intent"
                )
        if args.recover_intent:
            if ambient_providers or len(policy_providers) != 1:
                raise ConfigurationError(
                    "prebound recovery requires exactly one pinned repository-policy provider"
                )
            receipt, exit_code = recover_prebound_intent(
                path=Path(args.recover_intent),
                repository=repository,
                provider=policy_providers[0],
                policy_home=policy_home,
                timeout=args.timeout,
                expected_transaction_id=args.recover_transaction_id,
                expected_intent_sha256=args.recover_intent_sha256,
                repository_policy=policy_required,
            )
            receipt["repository_policy"] = policy_required
            if policy_home is not None:
                receipt["policy_home"] = str(policy_home)
            print(json.dumps(receipt, sort_keys=True))
            return exit_code
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
            transaction_id=args.transaction_id,
            transaction_intent=(
                Path(args.transaction_intent) if args.transaction_intent else None
            ),
            transaction_result=(
                Path(args.transaction_result) if args.transaction_result else None
            ),
            transaction_journal=(
                Path(args.transaction_journal) if args.transaction_journal else None
            ),
            recovery_provider_manifest=(
                Path(args.recovery_provider_manifest)
                if args.recovery_provider_manifest
                else None
            ),
            policy_home=policy_home,
            repository_policy=policy_required,
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
