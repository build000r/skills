from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_writer_fences.py"
SPEC = importlib.util.spec_from_file_location("run_writer_fences", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
writer_fences = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = writer_fences
SPEC.loader.exec_module(writer_fences)


FAKE_PROVIDER = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FAKE_PROVIDER_MODE", "allow")
log_path = Path(sys.argv[2] if len(sys.argv) > 2 else os.environ["FAKE_PROVIDER_LOG"])
request = json.load(sys.stdin)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(
        json.dumps(
            {
                "mode": mode,
                "operation": request["operation"],
                "root": request["repository"]["root"],
            }
        )
        + "\n"
    )

operation = request["operation"]
response = {
    "schema": "commit-writer-session/v1",
    "request_id": request["request_id"],
    "operation": operation,
    "verdict": "allow",
    "message": "ok",
}

if operation == "begin":
    if mode == "timeout_begin":
        time.sleep(1)
    if mode == "begin_blocked":
        response.update(verdict="blocked", message="busy", session=None)
    elif mode == "begin_indeterminate":
        response.update(verdict="indeterminate", message="unknown", session=None)
    else:
        response["session"] = {
            "id": f"session-{mode}",
            "fencing_token": f"token-{mode}",
        }
    if mode == "begin_schema":
        response.pop("message")
    elif mode == "begin_schema_session":
        response["schema"] = "wrong/v1"
elif operation == "check":
    if mode == "check_blocked":
        response.update(verdict="blocked", message="lost authority")
    elif mode == "check_indeterminate":
        response.update(verdict="indeterminate", message="cannot decide")
    elif mode == "check_schema":
        response["extra"] = "not allowed"
elif operation == "end":
    if mode == "end_indeterminate":
        response.update(verdict="indeterminate", message="release not confirmed")

print(json.dumps(response))
'''


class WriterFenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Writer Fence Test")
        (self.repo / "tracked.txt").write_text("seed\n", encoding="utf-8")
        self._git("add", "tracked.txt")
        self._git("commit", "-q", "-m", "seed")
        self.provider_script = self.root / "fake_provider.py"
        self.provider_script.write_text(textwrap.dedent(FAKE_PROVIDER), encoding="utf-8")
        self.provider_script.chmod(0o755)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
        return completed.stdout.strip()

    def _fingerprint(self) -> dict[str, str]:
        index_path = Path(self._git("rev-parse", "--git-path", "index"))
        if not index_path.is_absolute():
            index_path = self.repo / index_path
        return {
            "head": self._git("rev-parse", "HEAD"),
            "index": hashlib.sha256(index_path.read_bytes()).hexdigest(),
            "cached": self._git("diff", "--cached", "--binary"),
            "worktree": self._git("diff", "--binary"),
            "status": self._git("status", "--porcelain=v2", "--untracked-files=all"),
        }

    def _provider(self, mode: str, log: Path) -> list[str]:
        return [sys.executable, str(self.provider_script), mode, str(log)]

    def _init_repo(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        for args in (
            ("init", "-q"),
            ("config", "user.email", "test@example.invalid"),
            ("config", "user.name", "Writer Fence Test"),
        ):
            subprocess.run(
                ["git", "-C", str(path), *args], check=True, capture_output=True, shell=False
            )
        return path

    def _write_policy(
        self,
        mode: str,
        log: Path,
        *,
        modules: list[dict[str, str]] | None = None,
        resources: list[dict[str, str]] | None = None,
        resource_args: list[str] | None = None,
        repo: Path | None = None,
    ) -> tuple[Path, Path]:
        repo = repo if repo is not None else self.repo
        source = repo / "policy_provider.py"
        source.write_bytes(self.provider_script.read_bytes())
        policy = repo / writer_fences.POLICY_FILE
        policy.write_text(
            json.dumps(
                {
                    "schema": writer_fences.POLICY_SCHEMA,
                    "required": True,
                    "providers": [
                        {
                            "argv": [
                                "{python}",
                                "{repo}/policy_provider.py",
                                mode,
                                str(log),
                                *(resource_args or []),
                            ],
                            "source": "policy_provider.py",
                            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            "modules": modules or [],
                            "resources": resources or [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return policy, source

    def _run(
        self,
        *,
        providers: list[list[str]] | None,
        require_provider: bool = False,
        timeout: float = 0.25,
        marker_name: str = "marker.txt",
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
        steps: list[list[str]] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object], Path]:
        marker = self.repo / marker_name
        default_step = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path(r'%s').write_text('mutated', encoding='utf-8')"
            % marker,
        ]
        command = [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(self.repo),
            "--timeout",
            str(timeout),
        ]
        for step in steps if steps is not None else [default_step]:
            command.extend(["--step-json", json.dumps(step)])
        if require_provider:
            command.append("--require-provider")
        if extra_args:
            command.extend(extra_args)
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop(writer_fences.REQUIRED_ENV, None)
        if providers is None:
            env.pop(writer_fences.PROVIDERS_ENV, None)
        else:
            env[writer_fences.PROVIDERS_ENV] = json.dumps(providers)
        if extra_env:
            env.update(extra_env)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            shell=False,
        )
        receipt = json.loads(completed.stdout.strip().splitlines()[-1])
        return completed, receipt, marker

    @staticmethod
    def _operations(log: Path) -> list[str]:
        return [json.loads(line)["operation"] for line in log.read_text().splitlines()]

    def assert_fenced_without_change(
        self,
        completed: subprocess.CompletedProcess[str],
        receipt: dict[str, object],
        marker: Path,
        baseline: dict[str, str],
    ) -> None:
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(receipt["mutation_started"])
        self.assertFalse(marker.exists())
        self.assertEqual(self._fingerprint(), baseline)

    def test_discovers_environment_commands_and_path_fallback(self) -> None:
        env_provider = self._provider("allow", self.root / "env.log")
        providers = writer_fences.discover_providers(
            environ={writer_fences.PROVIDERS_ENV: json.dumps([env_provider]), "PATH": ""}
        )
        self.assertEqual(providers[0].argv, tuple(env_provider))

        with mock.patch.object(writer_fences.shutil, "which", return_value="/tmp/provider") as which:
            providers = writer_fences.discover_providers(environ={"PATH": "/tmp"})
        which.assert_called_once_with(writer_fences.DEFAULT_PROVIDER, path="/tmp")
        self.assertEqual(providers[0].argv, ("/tmp/provider",))

    def test_no_provider_is_portable_default(self) -> None:
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        self.assertTrue(receipt["portable_no_provider"])
        self.assertEqual(receipt["outcome"], "completed")

    def test_new_uncommitted_policy_protects_its_first_landing(self) -> None:
        log = self.root / "policy.log"
        self._write_policy("allow", log)
        self.assertEqual(self._git("ls-files", "--", writer_fences.POLICY_FILE), "")
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        self.assertTrue(receipt["repository_policy"])
        self.assertFalse(receipt["portable_no_provider"])
        self.assertEqual(self._operations(log), ["begin", "check", "end"])

    def test_repository_policy_block_wins_over_ambient_provider(self) -> None:
        policy_log = self.root / "policy-block.log"
        ambient_log = self.root / "ambient.log"
        self._write_policy("begin_blocked", policy_log)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[self._provider("allow", ambient_log)]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_BLOCKED)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(self._operations(policy_log), ["begin", "end"])
        self.assertEqual(self._operations(ambient_log), ["begin", "end"])

    def test_sealed_policy_timeout_still_runs_end_cleanup(self) -> None:
        log = self.root / "sealed-timeout.log"
        self._write_policy("timeout_begin", log)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[], timeout=0.05)
        self.assertEqual(completed.returncode, writer_fences.EXIT_INDETERMINATE)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(self._operations(log), ["begin", "end"])
        self.assertEqual(receipt["provider_results"][0]["failure"], "timeout")

    def test_tracked_policy_deletion_fails_closed(self) -> None:
        policy, source = self._write_policy("allow", self.root / "deleted.log")
        self._git("add", policy.name, source.name)
        self._git("commit", "-q", "-m", "add policy")
        policy.unlink()
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_staged_git_rm_of_committed_policy_cannot_downgrade_to_portable(self) -> None:
        policy, source = self._write_policy("allow", self.root / "git-rm.log")
        self._git("add", policy.name, source.name)
        self._git("commit", "-q", "-m", "add policy")
        self._git("rm", "-q", policy.name)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assertNotIn("portable_no_provider", receipt)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_staged_weakening_of_committed_policy_fails_closed(self) -> None:
        policy, source = self._write_policy("allow", self.root / "head.log")
        self._git("add", policy.name, source.name)
        self._git("commit", "-q", "-m", "add policy")
        policy.write_text(
            json.dumps(
                {"schema": writer_fences.POLICY_SCHEMA, "required": False, "providers": []}
            ),
            encoding="utf-8",
        )
        self._git("add", policy.name)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_staged_strict_policy_and_provider_hash_upgrade_is_committable(self) -> None:
        policy, source = self._write_policy("allow", self.root / "before.log")
        self._git("add", policy.name, source.name)
        self._git("commit", "-q", "-m", "add policy")
        source.write_bytes(source.read_bytes() + b"\n# reviewed provider upgrade\n")
        upgraded = json.loads(policy.read_text(encoding="utf-8"))
        upgraded["providers"][0]["argv"][-1] = str(self.root / "after.log")
        upgraded["providers"][0]["source_sha256"] = hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
        policy.write_text(json.dumps(upgraded), encoding="utf-8")
        self._git("add", policy.name, source.name)
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(receipt["repository_policy"])
        self.assertTrue(marker.exists())
        self.assertEqual(self._operations(self.root / "after.log"), ["begin", "check", "end"])

    def test_unstaged_policy_edit_disagrees_with_index_and_fails_closed(self) -> None:
        policy, source = self._write_policy("allow", self.root / "head.log")
        self._git("add", policy.name, source.name)
        self._git("commit", "-q", "-m", "add policy")
        replacement = json.loads(policy.read_text(encoding="utf-8"))
        replacement["providers"][0]["argv"][-1] = str(self.root / "unstaged.log")
        policy.write_text(json.dumps(replacement), encoding="utf-8")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_conflicted_policy_index_is_ambiguous_and_fails_closed(self) -> None:
        policy, source = self._write_policy("allow", self.root / "conflict.log")
        self._git("add", policy.name, source.name)
        self._git("commit", "-q", "-m", "add policy")
        weakened = json.dumps(
            {"schema": writer_fences.POLICY_SCHEMA, "required": False, "providers": []}
        ).encode()
        blob = subprocess.run(
            ["git", "-C", str(self.repo), "hash-object", "-w", "--stdin"],
            input=weakened,
            check=True,
            capture_output=True,
        ).stdout.decode().strip()
        head_blob = self._git("rev-parse", f"HEAD:{writer_fences.POLICY_FILE}")
        self._git("update-index", "--force-remove", writer_fences.POLICY_FILE)
        index_info = (
            f"100644 {head_blob} 1\t{writer_fences.POLICY_FILE}\n"
            f"100644 {blob} 2\t{writer_fences.POLICY_FILE}\n"
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "update-index", "--index-info"],
            input=index_info,
            check=True,
            text=True,
            capture_output=True,
        )
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_malformed_or_weakened_policy_fails_closed(self) -> None:
        for content in ("{", json.dumps({"schema": writer_fences.POLICY_SCHEMA, "required": False, "providers": []})):
            with self.subTest(content=content):
                (self.repo / writer_fences.POLICY_FILE).write_text(content, encoding="utf-8")
                baseline = self._fingerprint()
                completed, receipt, marker = self._run(providers=[])
                self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
                self.assertEqual(receipt["outcome"], "configuration_error")
                self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_policy_rejects_path_traversal_and_tampered_provider_source(self) -> None:
        policy, source = self._write_policy("allow", self.root / "tamper.log")
        decoded = json.loads(policy.read_text(encoding="utf-8"))
        decoded["providers"][0]["source"] = "../fake_provider.py"
        policy.write_text(json.dumps(decoded), encoding="utf-8")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

        _, source = self._write_policy("allow", self.root / "tamper.log")
        source.write_text("raise SystemExit(0)\n", encoding="utf-8")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_post_verification_in_place_rewrite_cannot_change_executed_bytes(self) -> None:
        source = self.repo / "sealed_provider.py"
        base_source = self.repo / "sealed_base.py"
        reader_source = self.repo / "sealed_reader.py"
        resource_source = self.repo / "sealed_decision.json"
        base_original = b'VALUE = "ONE:" + __file__ + ":" + _HELD_SOURCE_SHA256\n'
        reader_original = b'import sealed_base\nVALUE = sealed_base.VALUE + ":TWO:" + __file__ + ":" + _HELD_SOURCE_SHA256\n'
        resource_original = b'{"verdict":"blocked","suffix":"RESOURCE"}'
        original = textwrap.dedent(
            """\
            import json
            import sys
            import sealed_reader
            request = json.load(sys.stdin)
            decision_path = sys.argv[sys.argv.index("--decision") + 1]
            with open(decision_path, encoding="utf-8") as handle:
                decision = json.load(handle)
            print(json.dumps({
                "schema": request["schema"],
                "request_id": request["request_id"],
                "operation": request["operation"],
                "verdict": decision["verdict"],
                "message": "ORIGINAL:" + sealed_reader.VALUE + ":" + __file__ + ":" + _HELD_SOURCE_SHA256 + ":" + decision["suffix"] + ":" + request["request_id"],
                "session": None,
            }))
            """
        ).encode()
        base_rewritten = b'VALUE = "EVIL-ONE"\n'
        reader_rewritten = b'VALUE = "EVIL-TWO"\n'
        resource_rewritten = b'{"verdict":"allow","suffix":"EVIL-RESOURCE"}'
        rewritten = textwrap.dedent(
            """\
            import json
            import sys
            request = json.load(sys.stdin)
            print(json.dumps({
                "schema": request["schema"],
                "request_id": request["request_id"],
                "operation": request["operation"],
                "verdict": "allow",
                "message": "REWRITTEN",
                "session": {"id": "unverified", "fencing_token": "1"},
            }))
            """
        ).encode()
        base_source.write_bytes(base_original)
        reader_source.write_bytes(reader_original)
        resource_source.write_bytes(resource_original)
        source.write_bytes(original)
        provider = writer_fences.Provider(
            argv=(sys.executable, str(source), "--decision", "{resource:decision}"),
            label="sealed-rewrite",
            source_path=source,
            source_sha256=hashlib.sha256(original).hexdigest(),
            modules=(
                writer_fences.ProviderModule(
                    name="sealed_base",
                    source_path=base_source,
                    source_sha256=hashlib.sha256(base_original).hexdigest(),
                ),
                writer_fences.ProviderModule(
                    name="sealed_reader",
                    source_path=reader_source,
                    source_sha256=hashlib.sha256(reader_original).hexdigest(),
                ),
            ),
            resources=(
                writer_fences.ProviderResource(
                    name="decision",
                    source_path=resource_source,
                    source_sha256=hashlib.sha256(resource_original).hexdigest(),
                ),
            ),
            repository_root=self.repo,
        )
        request = {
            "schema": writer_fences.SCHEMA,
            "request_id": "sealed-request:0",
            "operation": "begin",
            "repository": {},
            "session": None,
            "transaction": {"step_count": 1},
        }
        original_inodes = {
            path: path.stat().st_ino
            for path in (source, base_source, reader_source, resource_source)
        }
        real_run = subprocess.run
        read_only_snapshot_proved = False

        def rewrite_at_subprocess_boundary(*args: object, **kwargs: object) -> object:
            nonlocal read_only_snapshot_proved
            invocation = args[0]
            self.assertIsInstance(invocation, list)
            assert isinstance(invocation, list)
            self.assertTrue(any(str(value).startswith("/dev/fd/") for value in invocation))
            rendered_argv = " ".join(str(value) for value in invocation)
            for live_path in (source, base_source, reader_source, resource_source):
                self.assertNotIn(str(live_path), rendered_argv)
            self.assertNotIn(resource_original.decode(), rendered_argv)
            self.assertNotIn("{resource:decision}", rendered_argv)
            pass_fds = kwargs.get("pass_fds")
            self.assertIsInstance(pass_fds, tuple)
            assert isinstance(pass_fds, tuple) and len(pass_fds) == 4
            for snapshot_fd in pass_fds:
                self.assertEqual(os.fstat(snapshot_fd).st_nlink, 0)
                with self.assertRaises(OSError) as write_error:
                    os.write(snapshot_fd, b"unverified")
                self.assertEqual(write_error.exception.errno, errno.EBADF)
            read_only_snapshot_proved = True
            for path, replacement in (
                (source, rewritten),
                (base_source, base_rewritten),
                (reader_source, reader_rewritten),
                (resource_source, resource_rewritten),
            ):
                with path.open("r+b") as handle:
                    handle.write(replacement)
                    handle.truncate()
                self.assertEqual(path.stat().st_ino, original_inodes[path])
            return real_run(*args, **kwargs)

        held = writer_fences.hold_provider_sources(provider)
        with mock.patch.object(
            writer_fences.subprocess,
            "run",
            side_effect=rewrite_at_subprocess_boundary,
        ):
            response, failure, detail = writer_fences._invoke(
                provider, request, timeout=2, held=held
            )
        self.assertIsNone(failure, detail)
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response["verdict"], "blocked")
        self.assertEqual(
            response["message"],
            "ORIGINAL:ONE:<sealed-module:sealed_base>:"
            + hashlib.sha256(base_original).hexdigest()
            + ":TWO:<sealed-module:sealed_reader>:"
            + hashlib.sha256(reader_original).hexdigest()
            + ":<sealed-provider-entry>:"
            + hashlib.sha256(original).hexdigest()
            + ":RESOURCE:sealed-request:0",
        )
        self.assertTrue(read_only_snapshot_proved)
        self.assertEqual(source.read_bytes(), rewritten)
        self.assertEqual(base_source.read_bytes(), base_rewritten)
        self.assertEqual(reader_source.read_bytes(), reader_rewritten)
        self.assertEqual(resource_source.read_bytes(), resource_rewritten)

    def test_oversized_provider_request_fails_before_invocation(self) -> None:
        provider = writer_fences.Provider(argv=("never-run",), label="bounded")
        request = {
            "schema": writer_fences.SCHEMA,
            "request_id": "bounded:0",
            "operation": "begin",
            "repository": {"root": "x" * writer_fences.MAX_PROVIDER_REQUEST_BYTES},
            "session": None,
            "transaction": {"step_count": 1},
        }
        with mock.patch.object(writer_fences.subprocess, "run") as invoked:
            response, failure, detail = writer_fences._invoke(
                provider, request, timeout=2, held=None
            )
        invoked.assert_not_called()
        self.assertIsNone(response)
        self.assertEqual(failure, "invocation")
        self.assertIn("bounded stdin payload", detail or "")

    def test_undeclared_local_import_cannot_fall_through_live_provider_directory(self) -> None:
        log = self.root / "undeclared.log"
        policy, source = self._write_policy("allow", log)
        nested = self.repo / "nested" / "provider-live"
        nested.mkdir(parents=True)
        (nested / "undeclared_local.py").write_text(
            "VERDICT = 'allow'\n", encoding="utf-8"
        )
        source.write_text(
            textwrap.dedent(
                """\
                import json
                import os
                import sys
                if os.environ.get("PYTHONPATH"):
                    sys.path.extend(os.environ["PYTHONPATH"].split(os.pathsep))
                import undeclared_local
                request = json.load(sys.stdin)
                response = {
                    "schema": request["schema"],
                    "request_id": request["request_id"],
                    "operation": request["operation"],
                    "verdict": undeclared_local.VERDICT,
                    "message": "live import must not authorize",
                }
                if request["operation"] == "begin":
                    response["session"] = {"id": "bad", "fencing_token": "1"}
                print(json.dumps(response))
                """
            ),
            encoding="utf-8",
        )
        decoded = json.loads(policy.read_text(encoding="utf-8"))
        decoded["providers"][0]["source_sha256"] = hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
        policy.write_text(json.dumps(decoded), encoding="utf-8")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[],
            cwd=nested,
            extra_env={"PYTHONPATH": str(nested)},
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_RELEASE_FAILED)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertTrue(
            any("No module named 'undeclared_local'" in row["message"] for row in receipt["provider_results"]),
            receipt,
        )

    def test_bad_bundle_order_fails_closed_without_live_import_fallback(self) -> None:
        dependency = self.repo / "ordered_dependency.py"
        consumer = self.repo / "ordered_consumer.py"
        dependency.write_text("VALUE = 'sealed'\n", encoding="utf-8")
        consumer.write_text(
            "import ordered_dependency\nVALUE = ordered_dependency.VALUE\n",
            encoding="utf-8",
        )
        modules = [
            {
                "name": "ordered_consumer",
                "source": consumer.name,
                "source_sha256": hashlib.sha256(consumer.read_bytes()).hexdigest(),
            },
            {
                "name": "ordered_dependency",
                "source": dependency.name,
                "source_sha256": hashlib.sha256(dependency.read_bytes()).hexdigest(),
            },
        ]
        policy, source = self._write_policy(
            "allow", self.root / "bad-order.log", modules=modules
        )
        source.write_text(
            "import ordered_consumer\nraise RuntimeError('entry must not run')\n",
            encoding="utf-8",
        )
        decoded = json.loads(policy.read_text(encoding="utf-8"))
        decoded["providers"][0]["source_sha256"] = hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
        policy.write_text(json.dumps(decoded), encoding="utf-8")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])
        self.assertEqual(completed.returncode, writer_fences.EXIT_RELEASE_FAILED)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertTrue(
            any("No module named 'ordered_dependency'" in row["message"] for row in receipt["provider_results"]),
            receipt,
        )

    def test_bundle_policy_rejects_unsafe_duplicate_missing_and_drifted_modules(self) -> None:
        first = self.repo / "first_module.py"
        second = self.repo / "second_module.py"
        first.write_text("VALUE = 1\n", encoding="utf-8")
        second.write_text("VALUE = 2\n", encoding="utf-8")
        digest_first = hashlib.sha256(first.read_bytes()).hexdigest()
        digest_second = hashlib.sha256(second.read_bytes()).hexdigest()
        variants = (
            [{"name": "bad-name", "source": first.name, "source_sha256": digest_first}],
            [
                {"name": "duplicate", "source": first.name, "source_sha256": digest_first},
                {"name": "duplicate", "source": second.name, "source_sha256": digest_second},
            ],
            [
                {"name": "first", "source": first.name, "source_sha256": digest_first},
                {"name": "second", "source": first.name, "source_sha256": digest_first},
            ],
            [{"name": "escape", "source": "../escape.py", "source_sha256": digest_first}],
            [{"name": "missing", "source": "missing.py", "source_sha256": digest_first}],
            [{"name": "drifted", "source": second.name, "source_sha256": digest_first}],
        )
        for position, modules in enumerate(variants):
            with self.subTest(position=position):
                self._write_policy(
                    "allow", self.root / f"invalid-{position}.log", modules=modules
                )
                baseline = self._fingerprint()
                completed, receipt, marker = self._run(providers=[])
                self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
                self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_resource_policy_rejects_unknown_duplicate_missing_and_drifted_inputs(self) -> None:
        resource = self.repo / "decision.json"
        other = self.repo / "other.json"
        resource.write_text('{"verdict":"blocked"}', encoding="utf-8")
        other.write_text('{"verdict":"other"}', encoding="utf-8")
        digest = hashlib.sha256(resource.read_bytes()).hexdigest()
        other_digest = hashlib.sha256(other.read_bytes()).hexdigest()
        variants = (
            (
                [{"name": "decision", "source": resource.name, "source_sha256": digest}],
                [],
            ),
            ([], ["{resource:unknown}"]),
            (
                [
                    {"name": "decision", "source": resource.name, "source_sha256": digest},
                    {"name": "decision", "source": other.name, "source_sha256": other_digest},
                ],
                ["{resource:decision}"],
            ),
            (
                [{"name": "escape", "source": "../escape.yaml", "source_sha256": digest}],
                ["{resource:escape}"],
            ),
            (
                [{"name": "missing", "source": "missing.yaml", "source_sha256": digest}],
                ["{resource:missing}"],
            ),
            (
                [{"name": "drift", "source": other.name, "source_sha256": digest}],
                ["{resource:drift}"],
            ),
            (
                [{"name": "decision", "source": resource.name, "source_sha256": digest}],
                ["{resource:decision}", "{resource:decision}"],
            ),
        )
        for position, (resources, resource_args) in enumerate(variants):
            with self.subTest(position=position):
                self._write_policy(
                    "allow",
                    self.root / f"invalid-resource-{position}.log",
                    resources=resources,
                    resource_args=resource_args,
                )
                baseline = self._fingerprint()
                completed, receipt, marker = self._run(providers=[])
                self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
                self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_step_rewriting_a_pinned_source_still_releases_its_session(self) -> None:
        """The release path must not re-read what a protected step legitimately rewrote.

        Landing a new provider revision, or pulling one, rewrites a pinned source
        mid-transaction. Re-reading it at ``end`` made the runner poison its own
        release: the mutation landed, release failed, and the durable lease stayed
        held until someone released it by hand.
        """

        log = self.root / "rewrite-during-steps.log"
        _, source = self._write_policy("allow", log)
        pinned_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        rewrite = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path(r'%s').write_text('# rewritten\\n', encoding='utf-8')"
            % source,
        ]
        completed, receipt, _ = self._run(providers=[], steps=[rewrite])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["outcome"], "completed")
        self.assertEqual(receipt["release_verdict"], "allow")
        self.assertEqual(self._operations(log), ["begin", "check", "end"])
        # The step really did invalidate the pin on disk.
        self.assertEqual(source.read_text(encoding="utf-8"), "# rewritten\n")
        self.assertNotEqual(hashlib.sha256(source.read_bytes()).hexdigest(), pinned_digest)
        # And every call executed the bytes verified at acquisition.
        acquisitions = receipt["provider_acquisitions"]
        assert isinstance(acquisitions, list)
        self.assertEqual(acquisitions[0]["digests"]["entry"], pinned_digest)

    def test_pinned_source_drift_before_the_run_refuses_at_preflight(self) -> None:
        """The other poison path: already-drifted sources must strand nothing."""

        log = self.root / "drift-before.log"
        _, source = self._write_policy("allow", log)
        source.write_text("# drifted before any fence\n", encoding="utf-8")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[])

        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assertIs(receipt["mutation_started"], False)
        self.assertIn("digest does not match repository policy", str(receipt["message"]))
        self.assertFalse(log.exists(), "no provider call may happen, so nothing is acquired")
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_required_provider_rejects_an_entirely_unpinned_provider_set(self) -> None:
        log = self.root / "unpinned.log"
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[self._provider("allow", log)], require_provider=True
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_PROVIDER_REQUIRED)
        self.assertEqual(receipt["outcome"], "provider_required_but_unpinned")
        self.assertEqual(
            receipt["unpinned_providers"], [f"{Path(sys.executable).name}#0"]
        )
        self.assertFalse(log.exists(), "the unattested executable must never be invoked")
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_unpinned_provider_runs_only_behind_the_explicit_opt_in(self) -> None:
        log = self.root / "unpinned-opt-in.log"
        completed, receipt, marker = self._run(
            providers=[self._provider("allow", log)],
            require_provider=True,
            extra_args=["--allow-unpinned-provider"],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        self.assertEqual(receipt["outcome"], "completed")

    def test_ambient_provider_stays_additive_alongside_a_pinned_one(self) -> None:
        """An extra unattested veto cannot weaken a pinned authority, so it is allowed."""

        policy_log = self.root / "additive-policy.log"
        ambient_log = self.root / "additive-ambient.log"
        self._write_policy("allow", policy_log)
        completed, receipt, marker = self._run(
            providers=[self._provider("allow", ambient_log)]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        self.assertEqual(receipt["provider_count"], 2)
        self.assertEqual(self._operations(policy_log), ["begin", "check", "end"])
        self.assertEqual(self._operations(ambient_log), ["begin", "check", "end"])

    def test_policy_home_fences_a_repository_that_declares_no_policy(self) -> None:
        log = self.root / "policy-home.log"
        home = self._init_repo(self.root / "trusted-home")
        self._write_policy("allow", log, repo=home)
        completed, receipt, marker = self._run(
            providers=[], extra_args=["--policy-home", str(home)]
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        self.assertIs(receipt["repository_policy"], True)
        self.assertEqual(receipt["policy_home"], str(home.resolve()))
        # The mutation target stays the protected repository, not the policy home.
        roots = {json.loads(line)["root"] for line in log.read_text().splitlines()}
        self.assertEqual(roots, {str(self.repo.resolve())})

    def test_policy_home_is_refused_when_the_protected_repository_declares_its_own(
        self,
    ) -> None:
        own_log = self.root / "own-policy.log"
        home_log = self.root / "home-policy.log"
        self._write_policy("allow", own_log)
        home = self._init_repo(self.root / "other-home")
        self._write_policy("allow", home_log, repo=home)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[], extra_args=["--policy-home", str(home)]
        )

        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assertIn("--policy-home is rejected", str(receipt["message"]))
        self.assertFalse(own_log.exists())
        self.assertFalse(home_log.exists())
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_policy_home_without_a_strict_policy_fails_closed(self) -> None:
        home = self._init_repo(self.root / "empty-home")
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[], extra_args=["--policy-home", str(home)]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertIn("declares no strict writer-session policy", str(receipt["message"]))
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_required_provider_fails_closed_without_mutation(self) -> None:
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(providers=[], require_provider=True)
        self.assertEqual(completed.returncode, writer_fences.EXIT_PROVIDER_REQUIRED)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_allowed_provider_runs_begin_check_end(self) -> None:
        log = self.root / "allow.log"
        completed, receipt, marker = self._run(providers=[self._provider("allow", log)])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        self.assertEqual(self._operations(log), ["begin", "check", "end"])
        self.assertEqual(receipt["preflight_verdict"], "allow")
        self.assertEqual(receipt["release_verdict"], "allow")

    def test_multiple_sessions_release_in_reverse_order(self) -> None:
        log = self.root / "ordered.log"
        completed, _, marker = self._run(
            providers=[self._provider("first", log), self._provider("second", log)]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(marker.exists())
        records = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(
            [(record["mode"], record["operation"]) for record in records],
            [
                ("first", "begin"),
                ("second", "begin"),
                ("first", "check"),
                ("second", "check"),
                ("second", "end"),
                ("first", "end"),
            ],
        )

    def test_blocked_begin_never_runs_mutation_and_still_ends(self) -> None:
        baseline = self._fingerprint()
        log = self.root / "blocked.log"
        completed, receipt, marker = self._run(
            providers=[self._provider("begin_blocked", log)]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_BLOCKED)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(self._operations(log), ["begin", "end"])

    def test_schema_failure_never_runs_mutation_and_releases_candidate_session(self) -> None:
        baseline = self._fingerprint()
        log = self.root / "schema.log"
        completed, receipt, marker = self._run(
            providers=[self._provider("begin_schema_session", log)]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_INDETERMINATE)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(self._operations(log), ["begin", "end"])
        self.assertEqual(receipt["provider_results"][0]["failure"], "schema")

    def test_timeout_never_runs_mutation_and_end_is_attempted_by_request_id(self) -> None:
        baseline = self._fingerprint()
        log = self.root / "timeout.log"
        completed, receipt, marker = self._run(
            providers=[self._provider("timeout_begin", log)], timeout=0.05
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_INDETERMINATE)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(self._operations(log), ["begin", "end"])
        self.assertEqual(receipt["provider_results"][0]["failure"], "timeout")

    def test_worst_verdict_blocks_all_mutations_and_releases_all_sessions(self) -> None:
        baseline = self._fingerprint()
        indeterminate_log = self.root / "indeterminate.log"
        blocked_log = self.root / "check-blocked.log"
        completed, receipt, marker = self._run(
            providers=[
                self._provider("check_indeterminate", indeterminate_log),
                self._provider("check_blocked", blocked_log),
            ]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_BLOCKED)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(receipt["preflight_verdict"], "blocked")
        self.assertEqual(self._operations(indeterminate_log), ["begin", "check", "end"])
        self.assertEqual(self._operations(blocked_log), ["begin", "check", "end"])

    def test_check_schema_failure_is_fail_closed(self) -> None:
        baseline = self._fingerprint()
        log = self.root / "check-schema.log"
        completed, receipt, marker = self._run(
            providers=[self._provider("check_schema", log)]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_INDETERMINATE)
        self.assert_fenced_without_change(completed, receipt, marker, baseline)
        self.assertEqual(self._operations(log), ["begin", "check", "end"])

    def test_release_failure_is_visible_after_an_authorized_mutation(self) -> None:
        log = self.root / "release.log"
        completed, receipt, marker = self._run(
            providers=[self._provider("end_indeterminate", log)]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_RELEASE_FAILED)
        self.assertTrue(marker.exists())
        self.assertTrue(receipt["mutation_started"])
        self.assertEqual(receipt["release_verdict"], "indeterminate")
        self.assertEqual(receipt["outcome"], "release_failed_after_preflight")
        self.assertEqual(self._operations(log), ["begin", "check", "end"])


if __name__ == "__main__":
    unittest.main()
