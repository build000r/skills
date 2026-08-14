from __future__ import annotations

import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
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
state_path = log_path.with_suffix(".state.json")
fail_end_path = log_path.with_suffix(".fail-end")
request = json.load(sys.stdin)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(
        json.dumps(
            {
                "mode": mode,
                "operation": request["operation"],
                "root": request["repository"]["root"],
                "request_id": request["request_id"],
                "session": request["session"],
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
    if mode == "stateful":
        state_path.write_text(
            json.dumps({"request_id": request["request_id"], "root": request["repository"]["root"]}),
            encoding="utf-8",
        )
    if mode == "timeout_begin":
        time.sleep(10)
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
    if mode == "stateful" and not state_path.exists():
        response.update(verdict="blocked", message="no held state")
    if mode == "check_blocked":
        response.update(verdict="blocked", message="lost authority")
    elif mode == "check_indeterminate":
        response.update(verdict="indeterminate", message="cannot decide")
    elif mode == "check_schema":
        response["extra"] = "not allowed"
elif operation == "end":
    if mode == "end_indeterminate":
        response.update(verdict="indeterminate", message="release not confirmed")
    elif mode == "stateful" and fail_end_path.exists():
        response.update(verdict="indeterminate", message="simulated uncertain release")
    elif mode == "stateful" and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state != {"request_id": request["request_id"], "root": request["repository"]["root"]}:
            response.update(verdict="blocked", message="recovery binding mismatch")
        else:
            state_path.unlink()

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
        timeout: float = 2.0,
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

    def _prebound_args(self, intent: Path, transaction_id: str) -> tuple[list[str], Path, Path]:
        canonical_repo = Path(os.path.realpath(self.repo))
        providers, required = writer_fences.discover_repository_policy(canonical_repo)
        self.assertTrue(required)
        self.assertEqual(len(providers), 1)
        held = writer_fences.hold_provider_sources(providers[0])
        self.assertIsNotNone(held)
        assert held is not None
        manifest = intent.with_name(intent.stem + "-provider-manifest.json")
        manifest.write_bytes(
            writer_fences._canonical_json_bytes(
                {
                    "schema": writer_fences.RECOVERY_MANIFEST_SCHEMA,
                    "provider_identity_sha256": writer_fences.provider_identity_sha256(
                        providers[0]
                    ),
                    "allowed_provider_digests": [held.digests()],
                }
            )
        )
        manifest.chmod(0o600)
        result = intent.with_name(intent.stem + "-result.json")
        journal = intent.with_name(intent.stem + "-journal.jsonl")
        return [
            "--require-capability", "prebound-intent-recovery-v1",
            "--transaction-id", transaction_id,
            "--transaction-intent", str(intent),
            "--transaction-result", str(result),
            "--transaction-journal", str(journal),
            "--recovery-provider-manifest", str(manifest),
        ], result, journal

    def _journal_records(self, path: Path) -> list[dict[str, object]]:
        journal = writer_fences._open_journal(path, create=False)
        try:
            records, _chain = writer_fences._read_journal_directory(journal)
            return records
        finally:
            os.close(journal.fd)

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
        completed, receipt, marker = self._run(providers=[], timeout=2.0)
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
        real_child = writer_fences._run_child
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
            return real_child(*args, **kwargs)

        held = writer_fences.hold_provider_sources(provider)
        with mock.patch.object(
            writer_fences,
            "_run_child",
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
        self.assertTrue(all(row["message"] == "provider exited 1" for row in receipt["provider_results"]), receipt)

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
        self.assertTrue(all(row["message"] == "provider exited 1" for row in receipt["provider_results"]), receipt)

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
        module = self.repo / "held_module.py"
        resource = self.repo / "held_resource.json"
        module.write_text("VALUE = 1\n", encoding="utf-8")
        resource.write_text('{"version":1}\n', encoding="utf-8")
        policy, source = self._write_policy(
            "allow",
            log,
            modules=[
                {
                    "name": "held_module",
                    "source": module.name,
                    "source_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
                }
            ],
            resources=[
                {
                    "name": "held_resource",
                    "source": resource.name,
                    "source_sha256": hashlib.sha256(resource.read_bytes()).hexdigest(),
                }
            ],
            resource_args=["{resource:held_resource}"],
        )
        pinned_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        rewrite = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "[(Path(p).write_text(v, encoding='utf-8')) for p, v in %r]"
                % [
                    (str(policy), "{}\n"),
                    (str(source), "# rewritten\n"),
                    (str(module), "VALUE = 2\n"),
                    (str(resource), '{"version":2}\n'),
                ]
            ),
        ]
        completed, receipt, _ = self._run(providers=[], steps=[rewrite])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["outcome"], "completed")
        self.assertEqual(receipt["release_verdict"], "allow")
        self.assertEqual(self._operations(log), ["begin", "check", "end"])
        # The step really did invalidate the pin on disk.
        self.assertEqual(source.read_text(encoding="utf-8"), "# rewritten\n")
        self.assertEqual(policy.read_text(encoding="utf-8"), "{}\n")
        self.assertEqual(module.read_text(encoding="utf-8"), "VALUE = 2\n")
        self.assertEqual(resource.read_text(encoding="utf-8"), '{"version":2}\n')
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

    def test_capabilities_are_machine_readable_without_repo_or_step(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--capabilities"],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], writer_fences.CAPABILITIES_SCHEMA)
        self.assertEqual(payload["capabilities"], list(writer_fences.RUNNER_CAPABILITIES))
        self.assertIn("acquisition-sealing-v1", payload["capabilities"])
        self.assertIn("receipt-bound-single-pinned-recovery-v1", payload["capabilities"])
        self.assertIn("prebound-intent-recovery-v1", payload["capabilities"])

    def test_prebound_intent_is_private_single_use_and_passed_to_step(self) -> None:
        log = self.root / "prebound.log"
        self._write_policy("allow", log)
        intent = Path(os.path.realpath(self.root)) / "intent.json"
        transaction_id = "a1b2c3d4-1234-4abc-8def-1234567890ab"
        marker = self.repo / "intent-fd.txt"
        step = [
            sys.executable,
            "-c",
            (
                "import os,pathlib,stat;"
                "fd=int(os.environ['COMMIT_WRITER_TRANSACTION_INTENT_FD']);"
                "m=os.fstat(fd);"
                "assert stat.S_ISREG(m.st_mode) and stat.S_IMODE(m.st_mode)==0o600;"
                f"pathlib.Path({str(marker)!r}).write_text(os.read(fd,1).decode())"
            ),
        ]
        args, result, journal = self._prebound_args(intent, transaction_id)
        completed, receipt, _ = self._run(providers=[], extra_args=args, steps=[step])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["transaction_id"], transaction_id)
        self.assertEqual(marker.read_text(), "{")
        self.assertEqual(intent.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(intent.read_text())["request_id"], f"{transaction_id}:0")
        self.assertEqual(json.loads(result.read_text())["outcome"], "completed")
        records = self._journal_records(journal)
        self.assertEqual(records[-1]["event"], "terminal_done")
        before = log.read_bytes()
        repeated, repeated_receipt, _ = self._run(
            providers=[], extra_args=args, steps=[step], marker_name="replay-marker"
        )
        self.assertEqual(repeated.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(repeated_receipt["outcome"], "configuration_error")
        self.assertEqual(log.read_bytes(), before)

    def test_preprovider_admission_faults_remove_only_owned_reservations(self) -> None:
        cases = ("journal_open", "prepared", "intent_open", "intent_ready")
        real_open_journal = writer_fences._open_journal
        real_open_intent = writer_fences._open_prebound_intent
        real_append = writer_fences.DurableJournal.append
        for position, case in enumerate(cases):
            with self.subTest(case=case):
                log = self.root / f"preprovider-{case}.log"
                self._write_policy("allow", log)
                intent = Path(os.path.realpath(self.root)) / f"preprovider-{case}.json"
                transaction_id = f"{position + 7}1b2c3d4-1234-4abc-8def-1234567890ab"
                _args, result, journal_path = self._prebound_args(intent, transaction_id)
                manifest = intent.with_name(intent.stem + "-provider-manifest.json")
                providers, required = writer_fences.discover_repository_policy(self.repo.resolve())
                self.assertTrue(required)

                def open_journal(path: Path, *, create: bool):
                    if case == "journal_open" and create:
                        raise OSError("secret-journal-open")
                    return real_open_journal(path, create=create)

                def open_intent(path: Path, payload: object, **kwargs: object):
                    if case == "intent_open":
                        raise OSError("secret-intent-open")
                    return real_open_intent(path, payload, **kwargs)

                def append(journal: object, event: str, detail: object):
                    if case == event:
                        raise OSError("secret-event-write")
                    return real_append(journal, event, detail)

                with mock.patch.object(writer_fences, "_open_journal", side_effect=open_journal), \
                     mock.patch.object(writer_fences, "_open_prebound_intent", side_effect=open_intent), \
                     mock.patch.object(writer_fences.DurableJournal, "append", new=append):
                    with self.assertRaises(BaseException) as raised:
                        writer_fences.run_transaction(
                            repository=writer_fences.repository_identity(self.repo.resolve()),
                            providers=providers,
                            steps=[[sys.executable, "-c", "pass"]],
                            timeout=1,
                            transaction_id=transaction_id,
                            transaction_intent=intent,
                            transaction_result=result,
                            transaction_journal=journal_path,
                            recovery_provider_manifest=manifest,
                            policy_home=None,
                            repository_policy=True,
                        )
                self.assertNotIn("secret", str(raised.exception))
                self.assertFalse(intent.exists())
                self.assertFalse(result.exists())
                self.assertFalse(journal_path.exists())
                self.assertTrue(manifest.exists())
                self.assertFalse(log.exists())

    def test_child_gate_records_pgid_before_program_bytes_can_execute(self) -> None:
        marker = self.root / "gated-program-ran"
        observed: list[int] = []

        def admit(pgid: int) -> None:
            self.assertFalse(marker.exists())
            # Exercise more admission latency than the former 250 ms fixture
            # deadline. The child must remain gated and still retain enough of
            # the functional deadline to execute after durable admission.
            time.sleep(0.35)
            self.assertFalse(marker.exists())
            observed.append(pgid)

        completed = writer_fences._run_child(
            [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"],
            cwd=str(self.repo),
            env=writer_fences._closed_child_env(),
            timeout=2,
            on_spawn=admit,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(marker.exists())
        self.assertEqual(len(observed), 1)
        marker.unlink()

        def refuse(_pgid: int) -> None:
            raise OSError("secret-journal-failure")

        with self.assertRaises(writer_fences.ChildLifecycleError) as raised:
            writer_fences._run_child(
                [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"],
                cwd=str(self.repo),
                env=writer_fences._closed_child_env(),
                timeout=2,
                on_spawn=refuse,
            )
        self.assertTrue(raised.exception.extinct)
        self.assertFalse(marker.exists())

    def test_child_gate_setup_faults_execute_zero_program_bytes(self) -> None:
        for phase in ("set_blocking", "selector_init", "register"):
            with self.subTest(phase=phase):
                marker = self.root / f"setup-fault-{phase}-ran"
                command = [
                    sys.executable, "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
                ]
                selector = mock.MagicMock()
                selector.register.side_effect = OSError("secret-register")
                if phase == "set_blocking":
                    patcher = mock.patch.object(
                        writer_fences.os, "set_blocking", side_effect=OSError("secret-blocking")
                    )
                elif phase == "selector_init":
                    patcher = mock.patch.object(
                        writer_fences.selectors, "DefaultSelector",
                        side_effect=OSError("secret-selector"),
                    )
                else:
                    patcher = mock.patch.object(
                        writer_fences.selectors, "DefaultSelector", return_value=selector
                    )
                with patcher, self.assertRaises(writer_fences.ChildLifecycleError) as raised:
                    writer_fences._run_child(
                        command,
                        cwd=str(self.repo),
                        env=writer_fences._closed_child_env(),
                        timeout=2,
                    )
                self.assertTrue(raised.exception.extinct)
                self.assertFalse(marker.exists())

    def test_provider_schema_key_errors_never_echo_hostile_names(self) -> None:
        secret = "SECRET_TOKEN_NAME_123"
        response = {
            "schema": writer_fences.SCHEMA,
            "request_id": "request:0",
            "operation": "check",
            "verdict": "allow",
            "message": "ok",
            secret: "value",
        }
        with self.assertRaises(writer_fences.SchemaError) as raised:
            writer_fences.validate_response(
                response, operation="check", request_id="request:0"
            )
        self.assertEqual(str(raised.exception), "provider response keyset is invalid")
        self.assertNotIn(secret, str(raised.exception))

    def test_prebound_recovery_refuses_while_original_holds_intent(self) -> None:
        intent = Path(os.path.realpath(self.root)) / "held-intent.json"
        payload = {
            "schema": writer_fences.PREBOUND_INTENT_SCHEMA,
            "transaction_id": "a1b2c3d4-1234-4abc-8def-1234567890ab",
        }
        fd, _digest = writer_fences._open_prebound_intent(intent, payload)
        try:
            with self.assertRaisesRegex(writer_fences.ConfigurationError, "still active"):
                writer_fences._read_locked_intent(intent)
        finally:
            os.close(fd)

    def test_prebound_recovery_is_end_only_after_lost_release_response(self) -> None:
        log = self.root / "prebound-recovery.log"
        self._write_policy("stateful", log)
        log.with_suffix(".fail-end").write_text("fail once\n", encoding="utf-8")
        intent = Path(os.path.realpath(self.root)) / "recovery-intent.json"
        transaction_id = "b1b2c3d4-1234-4abc-8def-1234567890ab"
        args, result, journal = self._prebound_args(intent, transaction_id)
        failed, failed_receipt, _ = self._run(
            providers=[],
            extra_args=args,
        )
        self.assertEqual(failed.returncode, writer_fences.EXIT_RELEASE_FAILED)
        self.assertEqual(failed_receipt["transaction_id"], transaction_id)
        operations_before = self._operations(log)
        log.with_suffix(".fail-end").unlink()
        command = [
            sys.executable, str(SCRIPT), "--repo", str(self.repo),
            "--policy-home", str(self.repo),
            "--require-capability", "prebound-intent-recovery-v1",
            "--recover-intent", str(intent),
            "--recover-transaction-id", transaction_id,
            "--recover-intent-sha256", failed_receipt["transaction_intent"]["sha256"],
        ]
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, shell=False,
        )
        receipt = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["outcome"], "recovered")
        self.assertEqual(receipt["request_id"], f"{transaction_id}:0")
        self.assertEqual(self._operations(log)[len(operations_before):], ["end"])

    def test_prebound_recovery_resolves_spawned_response_loss_without_step_replay(self) -> None:
        log = self.root / "spawn-response-loss.log"
        self._write_policy("stateful", log)
        log.with_suffix(".fail-end").write_text("fail once\n", encoding="utf-8")
        intent = Path(os.path.realpath(self.root)) / "spawn-response-loss.json"
        transaction_id = "d1b2c3d4-1234-4abc-8def-1234567890ab"
        args, result, journal_path = self._prebound_args(intent, transaction_id)
        completed, receipt, marker = self._run(providers=[], extra_args=args)
        self.assertEqual(completed.returncode, writer_fences.EXIT_RELEASE_FAILED)
        self.assertTrue(marker.exists())
        records = self._journal_records(journal_path)
        spawn_position = next(
            position
            for position, record in enumerate(records)
            if record["event"] == "child_spawned"
            and record["detail"]["kind"] == "provider"
            and record["detail"]["operation"] == "begin"
        )
        for path in sorted(journal_path.glob("[0-9]*-*.json")):
            if int(path.name.split("-", 1)[0]) > spawn_position:
                path.unlink()
        result.write_bytes(b"")
        log.with_suffix(".fail-end").unlink()
        operations_before = self._operations(log)
        recovered = subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo", str(self.repo),
                "--require-capability", "prebound-intent-recovery-v1",
                "--recover-intent", str(intent),
                "--recover-transaction-id", transaction_id,
                "--recover-intent-sha256", receipt["transaction_intent"]["sha256"],
            ],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, shell=False,
        )
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(self._operations(log)[len(operations_before):], ["end"])
        self.assertTrue(marker.exists())
        final_records = self._journal_records(journal_path)
        self.assertEqual(final_records[-1]["event"], "terminal_done")

    def test_existing_terminal_recovery_is_zero_provider_call(self) -> None:
        log = self.root / "terminal-zero-call.log"
        self._write_policy("allow", log)
        intent = Path(os.path.realpath(self.root)) / "terminal-intent.json"
        transaction_id = "c1b2c3d4-1234-4abc-8def-1234567890ab"
        args, result, _journal = self._prebound_args(intent, transaction_id)
        completed, receipt, _ = self._run(providers=[], extra_args=args)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        terminal_bytes = result.read_bytes()
        before = log.read_bytes()
        recovered = subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo", str(self.repo),
                "--require-capability", "prebound-intent-recovery-v1",
                "--recover-intent", str(intent),
                "--recover-transaction-id", transaction_id,
                "--recover-intent-sha256", receipt["transaction_intent"]["sha256"],
            ],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, shell=False,
        )
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        terminal = json.loads(terminal_bytes)
        self.assertEqual(terminal["schema"], writer_fences.PREBOUND_TERMINAL_SCHEMA)
        self.assertEqual(json.loads(recovered.stdout), terminal["receipt"])

    def test_recovery_rejects_rechained_prepared_detail_substitution(self) -> None:
        substitutions = {
            "transaction_id": "f1b2c3d4-1234-4abc-8def-1234567890ab",
            "request_id": "f1b2c3d4-1234-4abc-8def-1234567890ab:0",
            "repository": {
                "root": "/wrong", "git_dir": "/wrong/.git",
                "git_common_dir": "/wrong/.git", "head_oid": None, "head_ref": None,
            },
            "step_count": 2,
            "steps_sha256": "1" * 64,
            "manifest_sha256": "2" * 64,
            "result_path": "/wrong/result.json",
            "result_identity": {"dev": 1, "ino": 2, "uid": os.getuid(), "mode": 0o600, "nlink": 1},
        }
        for position, (field, replacement) in enumerate(substitutions.items()):
            with self.subTest(field=field):
                log = self.root / f"prepared-substitution-{field}.log"
                self._write_policy("allow", log)
                intent = Path(os.path.realpath(self.root)) / f"prepared-substitution-{field}.json"
                transaction_id = f"{position + 1}ab2c3d4-1234-4abc-8def-1234567890ab"
                args, _result, journal = self._prebound_args(intent, transaction_id)
                completed, receipt, _ = self._run(providers=[], extra_args=args)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                records = self._journal_records(journal)
                records[0]["detail"][field] = replacement
                previous = "0" * 64
                for record in records:
                    record["previous_sha256"] = previous
                    raw = writer_fences._canonical_json_bytes(record)
                    event_path = journal / f"{record['sequence']:08d}-{record['event']}.json"
                    event_path.write_bytes(raw)
                    event_path.chmod(0o600)
                    previous = hashlib.sha256(raw).hexdigest()
                before = log.read_bytes()
                recovered = subprocess.run(
                    [
                        sys.executable, str(SCRIPT), "--repo", str(self.repo),
                        "--require-capability", "prebound-intent-recovery-v1",
                        "--recover-intent", str(intent),
                        "--recover-transaction-id", transaction_id,
                        "--recover-intent-sha256", receipt["transaction_intent"]["sha256"],
                    ],
                    check=False, capture_output=True, text=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, shell=False,
                )
                self.assertEqual(recovered.returncode, writer_fences.EXIT_USAGE)
                self.assertEqual(recovered.stderr, "")
                self.assertEqual(log.read_bytes(), before)
        self.assertEqual(log.read_bytes(), before)

    def test_event_publish_uses_durable_self_hashed_pending_before_final_name(self) -> None:
        journal_path = Path(os.path.realpath(self.root)) / "publish-journal"
        journal = writer_fences._open_journal(journal_path, create=True)
        real_link = os.link
        observed: list[bytes] = []

        def inspect_link(src: str, dst: str, **kwargs: object) -> None:
            self.assertTrue(src.startswith(".pending-"))
            self.assertFalse((journal_path / dst).exists())
            raw = (journal_path / src).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), src.rsplit("-", 1)[1][:-4])
            observed.append(raw)
            real_link(src, dst, **kwargs)

        try:
            with mock.patch.object(writer_fences.os, "link", side_effect=inspect_link):
                journal.append("provider_intent", {"operation": "begin"})
            self.assertEqual(len(observed), 1)
            self.assertTrue((journal_path / "00000000-provider_intent.json").is_file())
            self.assertFalse(any(path.name.startswith(".pending-") for path in journal_path.iterdir()))
        finally:
            os.close(journal.fd)

    def test_event_recovery_publishes_complete_pending_and_quarantines_bad_temp(self) -> None:
        journal_path = Path(os.path.realpath(self.root)) / "pending-journal"
        journal = writer_fences._open_journal(journal_path, create=True)
        try:
            repository = writer_fences.repository_identity(self.repo.resolve())
            journal.append(
                "prepared",
                {
                    "transaction_id": "a1b2c3d4-1234-4abc-8def-1234567890ab",
                    "request_id": "a1b2c3d4-1234-4abc-8def-1234567890ab:0",
                    "repository": repository,
                    "step_count": 1,
                    "steps_sha256": "1" * 64,
                    "manifest_sha256": "2" * 64,
                    "result_path": str(self.root / "result.json"),
                    "result_identity": {"dev": 1, "ino": 2, "uid": os.getuid(), "mode": 0o600, "nlink": 1},
                },
            )
            journal.append("intent_ready", {"intent_sha256": "3" * 64})
            record = {
                "schema": writer_fences.PREBOUND_JOURNAL_SCHEMA,
                "sequence": 2,
                "previous_sha256": journal.chain_sha256,
                "event": "provider_intent",
                "detail": {"operation": "begin"},
            }
            raw = writer_fences._canonical_json_bytes(record)
            pending = journal_path / (
                ".pending-00000002-provider_intent-"
                + hashlib.sha256(raw).hexdigest()
                + ".tmp"
            )
            pending.write_bytes(raw)
            pending.chmod(0o600)
            bad = journal_path / ".pending-hostile.tmp"
            bad.write_bytes(b"hostile")
            bad.chmod(0o600)
            records, _ = writer_fences._read_journal_directory(journal)
            self.assertEqual(records[-1], record)
            self.assertFalse(pending.exists())
            self.assertTrue((journal_path / "00000002-provider_intent.json").is_file())
            self.assertFalse(bad.exists())
            self.assertEqual(len(list((journal_path / ".quarantine").iterdir())), 1)
        finally:
            os.close(journal.fd)

    def test_event_publication_fault_never_exposes_partial_final_name(self) -> None:
        journal_path = Path(os.path.realpath(self.root)) / "partial-journal"
        journal = writer_fences._open_journal(journal_path, create=True)

        def partial_write(fd: int, data: bytes) -> None:
            os.write(fd, data[: max(1, len(data) // 2)])
            raise OSError("injected-secret-short-write")

        try:
            with mock.patch.object(writer_fences, "_write_all", side_effect=partial_write):
                with self.assertRaisesRegex(
                    writer_fences.ConfigurationError, "publication failed"
                ):
                    journal.append("provider_intent", {"operation": "begin"})
            self.assertFalse((journal_path / "00000000-provider_intent.json").exists())
            writer_fences._reconcile_pending_events(journal)
            self.assertFalse(any(path.name.startswith(".pending-") for path in journal_path.iterdir()))
            self.assertEqual(len(list((journal_path / ".quarantine").iterdir())), 1)
        finally:
            os.close(journal.fd)

    def test_event_publish_recovers_fsync_link_unlink_and_dirsync_faults(self) -> None:
        cases = ("temp_fsync", "link", "unlink", "publish_dirsync")
        for case in cases:
            with self.subTest(case=case):
                journal_path = Path(os.path.realpath(self.root)) / f"fault-{case}-journal"
                journal = writer_fences._open_journal(journal_path, create=True)
                real_fsync = os.fsync
                real_link = os.link
                real_unlink = os.unlink
                fsync_calls = 0

                def fsync_fault(fd: int) -> None:
                    nonlocal fsync_calls
                    fsync_calls += 1
                    if case == "temp_fsync" and fsync_calls == 1:
                        raise OSError("secret-temp-fsync")
                    if case == "publish_dirsync" and fsync_calls == 2:
                        raise OSError("secret-dir-fsync")
                    real_fsync(fd)

                def link_fault(src: str, dst: str, **kwargs: object) -> None:
                    if case == "link":
                        raise OSError("secret-link")
                    real_link(src, dst, **kwargs)

                def unlink_fault(path: str, **kwargs: object) -> None:
                    if case == "unlink":
                        raise OSError("secret-unlink")
                    real_unlink(path, **kwargs)

                try:
                    with mock.patch.object(writer_fences.os, "fsync", side_effect=fsync_fault), \
                         mock.patch.object(writer_fences.os, "link", side_effect=link_fault), \
                         mock.patch.object(writer_fences.os, "unlink", side_effect=unlink_fault):
                        with self.assertRaises(writer_fences.ConfigurationError) as raised:
                            journal.append("provider_intent", {"operation": "begin"})
                    self.assertNotIn("secret", str(raised.exception))
                    writer_fences._reconcile_pending_events(journal)
                    final = journal_path / "00000000-provider_intent.json"
                    self.assertTrue(final.is_file())
                    self.assertEqual(final.stat().st_nlink, 1)
                    self.assertFalse(
                        any(path.name.startswith(".pending-") for path in journal_path.iterdir())
                    )
                finally:
                    os.close(journal.fd)

    def test_event_recovery_unlinks_same_inode_duplicate_at_paired_dfa_boundaries(self) -> None:
        cases = {
            "prepared": "41b2c3d4-1234-4abc-8def-1234567890ab",
            "intent_ready": "51b2c3d4-1234-4abc-8def-1234567890ab",
            "terminal_done": "61b2c3d4-1234-4abc-8def-1234567890ab",
        }
        for event, transaction_id in cases.items():
            with self.subTest(event=event):
                log = self.root / f"same-inode-{event}.log"
                self._write_policy("allow", log)
                intent = Path(os.path.realpath(self.root)) / f"same-inode-{event}.json"
                args, _result, journal_path = self._prebound_args(intent, transaction_id)
                completed, _receipt, _ = self._run(providers=[], extra_args=args)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                final = next(journal_path.glob(f"*-{event}.json"))
                raw = final.read_bytes()
                record = json.loads(raw)
                pending = journal_path / (
                    f".pending-{record['sequence']:08d}-{event}-"
                    f"{hashlib.sha256(raw).hexdigest()}.tmp"
                )
                os.link(final, pending)
                self.assertEqual(final.stat().st_ino, pending.stat().st_ino)
                journal = writer_fences._open_journal(journal_path, create=False)
                try:
                    records, _chain = writer_fences._read_journal_directory(journal)
                finally:
                    os.close(journal.fd)
                self.assertFalse(pending.exists())
                self.assertEqual(records[record["sequence"]]["event"], event)
                self.assertEqual(final.stat().st_nlink, 1)

    def test_terminal_reserved_inode_repairs_partial_write_without_replacement(self) -> None:
        result = Path(os.path.realpath(self.root)) / "reserved-result.json"
        reserved = writer_fences._reserve_terminal_result(result)
        identity = dict(reserved.identity)
        payload = {"schema": "test/v1", "value": "bounded"}

        def partial(fd: int, data: bytes) -> None:
            os.write(fd, data[:3])
            raise OSError("secret-terminal-write")

        try:
            with mock.patch.object(writer_fences, "_write_all", side_effect=partial):
                with self.assertRaisesRegex(
                    writer_fences.ConfigurationError, "publication failed"
                ):
                    writer_fences._write_terminal_result(reserved, payload)
            self.assertEqual(writer_fences._terminal_identity(result.stat()), identity)
            digest = writer_fences._write_terminal_result(reserved, payload)
            expected = writer_fences._canonical_json_bytes(payload)
            self.assertEqual(result.read_bytes(), expected)
            self.assertEqual(digest, hashlib.sha256(expected).hexdigest())
            self.assertNotEqual(writer_fences._terminal_identity(result.stat()), identity)
            old_inode = writer_fences._terminal_identity(os.fstat(reserved.fd))
            self.assertEqual((old_inode["dev"], old_inode["ino"]), (identity["dev"], identity["ino"]))
            self.assertEqual(old_inode["nlink"], 0)
            self.assertEqual(len(list(result.parent.glob(".quarantine-result-*"))), 1)
        finally:
            os.close(reserved.fd)

    def test_terminal_reconcile_covers_absent_linked_complete_and_conflicting_states(self) -> None:
        content = writer_fences._canonical_json_bytes({"schema": "test/v1", "value": 7})
        digest = hashlib.sha256(content).hexdigest()
        for state in ("pending_only", "linked_pair", "complete"):
            with self.subTest(state=state):
                case_dir = self.root / f"terminal-{state}"
                case_dir.mkdir(mode=0o700)
                result = Path(os.path.realpath(case_dir / "result.json"))
                reserved = writer_fences._reserve_terminal_result(result)
                identity = dict(reserved.identity)
                pending = case_dir / f".pending-result-{digest}.tmp"
                if state != "complete":
                    pending.write_bytes(content)
                    pending.chmod(0o600)
                    result.unlink()
                    if state == "linked_pair":
                        os.link(pending, result)
                else:
                    writer_fences._write_terminal_result(reserved, json.loads(content))
                writer_fences._reconcile_terminal_publication(
                    result,
                    original_identity=identity,
                    content=content,
                    content_sha256=digest,
                )
                self.assertEqual(result.read_bytes(), content)
                self.assertEqual(result.stat().st_nlink, 1)
                self.assertFalse(pending.exists())
                os.close(reserved.fd)

        conflict_dir = self.root / "terminal-conflict"
        conflict_dir.mkdir(mode=0o700)
        result = Path(os.path.realpath(conflict_dir / "result.json"))
        reserved = writer_fences._reserve_terminal_result(result)
        identity = dict(reserved.identity)
        result.write_bytes(content)
        pending = conflict_dir / f".pending-result-{digest}.tmp"
        pending.write_bytes(content)
        pending.chmod(0o600)
        with self.assertRaisesRegex(writer_fences.ConfigurationError, "inode conflicts"):
            writer_fences._reconcile_terminal_publication(
                result,
                original_identity=identity,
                content=content,
                content_sha256=digest,
            )
        os.close(reserved.fd)

    def test_terminal_publication_recovers_each_file_and_parent_fsync_boundary(self) -> None:
        payload = {"schema": "test/v1", "value": "fsync"}
        content = writer_fences._canonical_json_bytes(payload)
        digest = hashlib.sha256(content).hexdigest()
        for failing_call in range(1, 5):
            with self.subTest(failing_call=failing_call):
                case_dir = self.root / f"terminal-fsync-{failing_call}"
                case_dir.mkdir(mode=0o700)
                result = Path(os.path.realpath(case_dir / "result.json"))
                reserved = writer_fences._reserve_terminal_result(result)
                identity = dict(reserved.identity)
                real_fsync = os.fsync
                calls = 0

                def fail_once(fd: int) -> None:
                    nonlocal calls
                    calls += 1
                    if calls == failing_call:
                        raise OSError("secret-terminal-fsync")
                    real_fsync(fd)

                try:
                    with mock.patch.object(writer_fences.os, "fsync", side_effect=fail_once):
                        with self.assertRaises(writer_fences.ConfigurationError) as raised:
                            writer_fences._write_terminal_result(reserved, payload)
                    self.assertNotIn("secret", str(raised.exception))
                    writer_fences._reconcile_terminal_publication(
                        result,
                        original_identity=identity,
                        content=content,
                        content_sha256=digest,
                    )
                    self.assertEqual(result.read_bytes(), content)
                    self.assertEqual(result.stat().st_nlink, 1)
                finally:
                    os.close(reserved.fd)

    def test_pending_quarantine_collisions_fail_closed(self) -> None:
        journal_path = Path(os.path.realpath(self.root)) / "quarantine-collision-journal"
        journal = writer_fences._open_journal(journal_path, create=True)
        bad_name = ".pending-hostile.tmp"
        (journal_path / bad_name).write_bytes(b"one")
        (journal_path / bad_name).chmod(0o600)
        quarantine = journal_path / ".quarantine"
        quarantine.mkdir(mode=0o700)
        quarantine_name = hashlib.sha256(bad_name.encode()).hexdigest() + ".quarantine"
        (quarantine / quarantine_name).write_bytes(b"two")
        (quarantine / quarantine_name).chmod(0o600)
        try:
            with self.assertRaisesRegex(writer_fences.ConfigurationError, "collision"):
                writer_fences._reconcile_pending_events(journal)
        finally:
            os.close(journal.fd)

        result_dir = self.root / "result-quarantine-collision"
        result_dir.mkdir(mode=0o700)
        result = Path(os.path.realpath(result_dir / "result.json"))
        reserved = writer_fences._reserve_terminal_result(result)
        content = b'{"schema":"test/v1"}\n'
        digest = hashlib.sha256(content).hexdigest()
        pending = result_dir / f".pending-result-{digest}.tmp"
        pending.write_bytes(b"bad")
        pending.chmod(0o600)
        quarantine_result = result_dir / (
            ".quarantine-result-" + hashlib.sha256(b"bad").hexdigest() + ".artifact"
        )
        quarantine_result.write_bytes(b"other")
        quarantine_result.chmod(0o600)
        try:
            with self.assertRaisesRegex(writer_fences.ConfigurationError, "collision"):
                writer_fences._reconcile_terminal_publication(
                    result,
                    original_identity=reserved.identity,
                    content=content,
                    content_sha256=digest,
                )
        finally:
            os.close(reserved.fd)

    def test_terminal_intent_recovers_absent_or_pending_result_and_pending_done_without_end(self) -> None:
        for state in ("result_absent", "result_pending", "done_pending"):
            with self.subTest(state=state):
                log = self.root / f"terminal-crash-{state}.log"
                self._write_policy("allow", log)
                intent = Path(os.path.realpath(self.root)) / f"terminal-crash-{state}.json"
                transaction_id = {
                    "result_absent": "11b2c3d4-1234-4abc-8def-1234567890ab",
                    "result_pending": "21b2c3d4-1234-4abc-8def-1234567890ab",
                    "done_pending": "31b2c3d4-1234-4abc-8def-1234567890ab",
                }[state]
                args, result, journal = self._prebound_args(intent, transaction_id)
                completed, receipt, _ = self._run(providers=[], extra_args=args)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                terminal_bytes = result.read_bytes()
                terminal_sha = hashlib.sha256(terminal_bytes).hexdigest()
                done = journal / "00000008-terminal_done.json"
                if not done.exists():
                    done = next(journal.glob("*-terminal_done.json"))
                done_raw = done.read_bytes()
                done_record = json.loads(done_raw)
                done.unlink()
                if state == "result_absent":
                    result.unlink()
                elif state == "result_pending":
                    pending_result = result.parent / f".pending-result-{terminal_sha}.tmp"
                    os.link(result, pending_result)
                    result.unlink()
                else:
                    pending_done = journal / (
                        f".pending-{done_record['sequence']:08d}-terminal_done-"
                        + hashlib.sha256(done_raw).hexdigest()
                        + ".tmp"
                    )
                    pending_done.write_bytes(done_raw)
                    pending_done.chmod(0o600)
                before = log.read_bytes()
                recovered = subprocess.run(
                    [
                        sys.executable, str(SCRIPT), "--repo", str(self.repo),
                        "--require-capability", "prebound-intent-recovery-v1",
                        "--recover-intent", str(intent),
                        "--recover-transaction-id", transaction_id,
                        "--recover-intent-sha256", receipt["transaction_intent"]["sha256"],
                    ],
                    check=False, capture_output=True, text=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, shell=False,
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                self.assertEqual(log.read_bytes(), before)
                self.assertEqual(result.read_bytes(), terminal_bytes)
                self.assertTrue(any(journal.glob("*-terminal_done.json")))

    def test_generic_prebound_manifest_rejects_successor_map_before_begin(self) -> None:
        log = self.root / "successor-recovery.log"
        _policy, source = self._write_policy("stateful", log)
        intent = Path(os.path.realpath(self.root)) / "successor-intent.json"
        transaction_id = "d1b2c3d4-1234-4abc-8def-1234567890ab"
        args, _result, _journal = self._prebound_args(intent, transaction_id)
        manifest = intent.with_name(intent.stem + "-provider-manifest.json")
        manifest_value = json.loads(manifest.read_text())
        successor_bytes = source.read_bytes() + b"\n# authorized successor\n"
        successor_map = {
            key: hashlib.sha256(successor_bytes).hexdigest() if key == "entry" else value
            for key, value in manifest_value["allowed_provider_digests"][0].items()
        }
        manifest_value["allowed_provider_digests"].append(successor_map)
        manifest.write_bytes(writer_fences._canonical_json_bytes(manifest_value))
        manifest.chmod(0o600)
        failed, failed_receipt, _ = self._run(providers=[], extra_args=args)
        self.assertEqual(failed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(failed_receipt["outcome"], "configuration_error")
        self.assertFalse(log.exists())

    def test_uuid_v4_type_and_shape_are_strict(self) -> None:
        for value in (False, 1, "A1B2C3D4-1234-4ABC-8DEF-1234567890AB", "not-a-uuid"):
            with self.subTest(value=value):
                with self.assertRaises(writer_fences.ConfigurationError):
                    writer_fences._canonical_uuid_v4(value)

    def test_bounded_child_rejects_bool_huge_and_nonfinite_timeouts(self) -> None:
        command = [sys.executable, "-c", "pass"]
        for timeout in (True, False, 0, -1, 301, float("inf"), float("nan")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(writer_fences.ChildLifecycleError):
                    writer_fences._run_child(
                        command,
                        cwd=str(self.repo.resolve()),
                        env=writer_fences._closed_child_env(),
                        timeout=timeout,
                    )

    def test_bounded_child_caps_output_and_reaps_group(self) -> None:
        with self.assertRaises(writer_fences.ChildLifecycleError) as raised:
            writer_fences._run_child(
                [
                    sys.executable,
                    "-c",
                    "import sys,time;sys.stdout.buffer.write(b'x'*(3*1024*1024));sys.stdout.flush();time.sleep(60)",
                ],
                cwd=str(self.repo.resolve()),
                env=writer_fences._closed_child_env(),
                timeout=2,
            )
        self.assertTrue(raised.exception.extinct)

    def test_bounded_child_timeout_kills_term_resistant_held_pipe_descendant(self) -> None:
        pid_path = Path(os.path.realpath(self.root)) / "held-descendant.pid"
        code = textwrap.dedent(
            f"""
            import os, signal, subprocess, sys, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            child = subprocess.Popen([
                sys.executable, '-c',
                'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'
            ], close_fds=False)
            open({str(pid_path)!r}, 'w').write(str(child.pid))
            time.sleep(60)
            """
        )
        with self.assertRaises(writer_fences.ChildLifecycleError) as raised:
            writer_fences._run_child(
                [sys.executable, "-c", code],
                cwd=str(self.repo.resolve()),
                env=writer_fences._closed_child_env(),
                timeout=0.2,
            )
        self.assertTrue(raised.exception.extinct)
        descendant = int(pid_path.read_text())
        for _ in range(50):
            try:
                os.kill(descendant, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            self.fail("same-group held-pipe descendant survived return")

    def test_bounded_child_setup_and_read_baseexceptions_reap_before_propagation(self) -> None:
        for target, effect in (
            ("os.set_blocking", RuntimeError("hostile-secret-setblocking")),
            ("selectors.DefaultSelector", KeyboardInterrupt()),
        ):
            with self.subTest(target=target):
                patcher = (
                    mock.patch.object(writer_fences.os, "set_blocking", side_effect=effect)
                    if target.startswith("os.")
                    else mock.patch.object(
                        writer_fences.selectors, "DefaultSelector", side_effect=effect
                    )
                )
                with patcher:
                    with self.assertRaises((writer_fences.ChildLifecycleError, KeyboardInterrupt)):
                        writer_fences._run_child(
                            [sys.executable, "-c", "import time;time.sleep(60)"],
                            cwd=str(self.repo.resolve()),
                            env=writer_fences._closed_child_env(),
                            timeout=1,
                        )

    def test_hash_chain_journal_rejects_truncate_reorder_duplicate_and_tamper(self) -> None:
        records = []
        previous = "0" * 64
        for sequence, event in enumerate(("prepared", "intent_ready", "terminal_intent")):
            record = {
                "schema": writer_fences.PREBOUND_JOURNAL_SCHEMA,
                "sequence": sequence,
                "previous_sha256": previous,
                "event": event,
                "detail": {},
            }
            line = writer_fences._canonical_json_bytes(record)
            records.append(line)
            previous = hashlib.sha256(line).hexdigest()
        writer_fences._validate_journal(b"".join(records))
        variants = (
            b"".join(records)[:-1],
            records[1] + records[0] + records[2],
            records[0] + records[1] + records[1] + records[2],
            records[0].replace(b'"prepared"', b'"tampered"') + b"".join(records[1:]),
        )
        for value in variants:
            with self.subTest(value=value[:40]):
                with self.assertRaises(writer_fences.ConfigurationError):
                    writer_fences._validate_journal(value)

    def test_abandoned_gate_transition_resolves_intent_before_end_only_recovery(self) -> None:
        repository = writer_fences.repository_identity(self.repo.resolve())
        prepared = {
            "transaction_id": "a1b2c3d4-1234-4abc-8def-1234567890ab",
            "request_id": "a1b2c3d4-1234-4abc-8def-1234567890ab:0",
            "repository": repository,
            "step_count": 1,
            "steps_sha256": "1" * 64,
            "manifest_sha256": "2" * 64,
            "result_path": str((self.root / "result.json").resolve()),
            "result_identity": {"dev": 1, "ino": 2, "uid": os.getuid(), "mode": 0o600, "nlink": 1},
        }
        records: list[dict[str, object]] = []
        previous = "0" * 64
        events = (
            ("prepared", prepared),
            ("intent_ready", {"intent_sha256": "3" * 64}),
            ("step_intent", {"position": 0, "argv_sha256": "4" * 64}),
            ("gate_abandoned", {"kind": "step", "operation": None, "position": 0, "group_extinct": True}),
            ("recovery_intent", {"request_id": prepared["request_id"], "prior_event_count": 4}),
        )
        for sequence, (event, detail) in enumerate(events):
            record = {
                "schema": writer_fences.PREBOUND_JOURNAL_SCHEMA,
                "sequence": sequence,
                "previous_sha256": previous,
                "event": event,
                "detail": detail,
            }
            raw = writer_fences._canonical_json_bytes(record)
            previous = hashlib.sha256(raw).hexdigest()
            records.append(record)
        writer_fences._validate_event_semantics(records)
        records[3]["detail"]["group_extinct"] = False
        with self.assertRaises(writer_fences.ConfigurationError):
            writer_fences._validate_event_semantics(records)

    def test_event_dfa_and_terminal_schema_reject_extra_reordered_and_bool_fields(self) -> None:
        log = self.root / "dfa.log"
        self._write_policy("allow", log)
        intent = Path(os.path.realpath(self.root)) / "dfa-intent.json"
        args, result, journal = self._prebound_args(
            intent, "f1b2c3d4-1234-4abc-8def-1234567890ab"
        )
        completed, _receipt, _ = self._run(providers=[], extra_args=args)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        records = self._journal_records(journal)
        terminal = json.loads(result.read_text())
        self.assertEqual(set(terminal), {
            "schema", "transaction_id", "request_id", "repository", "policy_home",
            "repository_policy", "transaction_intent", "transaction_result",
            "transaction_journal", "journal_prefix_sha256", "provider_identity_sha256",
            "provider_digests", "step_count", "steps_sha256", "outcome", "exit_code",
            "receipt_sha256", "receipt",
        })
        step_done_index = next(
            index for index, record in enumerate(records) if record["event"] == "step_done"
        )
        variants = []
        duplicated = [dict(record) for record in records]
        duplicated.insert(2, dict(records[1]))
        variants.append(duplicated)
        after_terminal = [dict(record) for record in records] + [dict(records[1])]
        variants.append(after_terminal)
        bool_return = json.loads(json.dumps(records))
        bool_return[step_done_index]["detail"]["returncode"] = True
        variants.append(bool_return)
        hostile_failure = json.loads(json.dumps(records))
        provider_done = next(
            record for record in hostile_failure if record["event"] == "provider_done"
        )
        provider_done["detail"]["failure"] = "credential-value"
        variants.append(hostile_failure)
        for variant in variants:
            with self.subTest(events=[record["event"] for record in variant]):
                with self.assertRaises(writer_fences.ConfigurationError):
                    writer_fences._validate_event_semantics(variant)
        altered = dict(terminal)
        altered["extra"] = "forbidden"
        with self.assertRaisesRegex(writer_fences.ConfigurationError, "keyset"):
            writer_fences._validate_terminal_payload(
                altered,
                expected_payload_sha256=hashlib.sha256(
                    writer_fences._canonical_json_bytes(altered)
                ).hexdigest(),
                expected_prefix_sha256=terminal["journal_prefix_sha256"],
            )
        bool_exit = dict(terminal)
        bool_exit["exit_code"] = False
        with self.assertRaises(writer_fences.ConfigurationError):
            writer_fences._validate_terminal_payload(
                bool_exit,
                expected_payload_sha256=hashlib.sha256(
                    writer_fences._canonical_json_bytes(bool_exit)
                ).hexdigest(),
                expected_prefix_sha256=terminal["journal_prefix_sha256"],
            )

    def test_terminal_tamper_recovery_fails_before_provider_call(self) -> None:
        log = self.root / "terminal-tamper.log"
        self._write_policy("allow", log)
        intent = Path(os.path.realpath(self.root)) / "tamper-intent.json"
        transaction_id = "e1b2c3d4-1234-4abc-8def-1234567890ab"
        args, result, _journal = self._prebound_args(intent, transaction_id)
        completed, receipt, _ = self._run(providers=[], extra_args=args)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        terminal = json.loads(result.read_text())
        terminal["outcome"] = "tampered"
        result.write_bytes(writer_fences._canonical_json_bytes(terminal))
        before = log.read_bytes()
        recovered = subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo", str(self.repo),
                "--require-capability", "prebound-intent-recovery-v1",
                "--recover-intent", str(intent),
                "--recover-transaction-id", transaction_id,
                "--recover-intent-sha256", receipt["transaction_intent"]["sha256"],
            ],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, shell=False,
        )
        self.assertEqual(recovered.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(log.read_bytes(), before)

    def test_unproven_step_group_suppresses_provider_end_and_journals_reason(self) -> None:
        evidence = Path(os.path.realpath(self.root))
        intent = evidence / "suppressed-intent.json"
        result = evidence / "suppressed-result.json"
        journal = evidence / "suppressed-journal.jsonl"
        manifest = evidence / "suppressed-manifest.json"
        provider = writer_fences.Provider(argv=(sys.executable,), label="held#0")
        held_bytes = b"held-provider"
        held = writer_fences.HeldProviderSources(
            entry=writer_fences.HeldSource(
                label="entry",
                name="",
                sha256=hashlib.sha256(held_bytes).hexdigest(),
                content=held_bytes,
            )
        )
        manifest.write_bytes(
            writer_fences._canonical_json_bytes(
                {
                    "schema": writer_fences.RECOVERY_MANIFEST_SCHEMA,
                    "provider_identity_sha256": writer_fences.provider_identity_sha256(provider),
                    "allowed_provider_digests": [held.digests()],
                }
            )
        )
        manifest.chmod(0o600)
        operations: list[str] = []

        def fake_call(_state: object, *, operation: str, **_kwargs: object) -> dict[str, object]:
            operations.append(operation)
            return {
                "provider": "held#0", "operation": operation, "verdict": "allow",
                "failure": None, "message": "ok",
            }

        repository = writer_fences.repository_identity(self.repo.resolve())
        with (
            mock.patch.object(writer_fences, "hold_provider_sources", return_value=held),
            mock.patch.object(writer_fences, "_call", side_effect=fake_call),
            mock.patch.object(
                writer_fences,
                "_run_child",
                side_effect=writer_fences.ChildLifecycleError(extinct=False, pgid=424242),
            ),
        ):
            receipt, exit_code = writer_fences.run_transaction(
                repository=repository,
                providers=[provider],
                steps=[[sys.executable, "-c", "pass"]],
                timeout=1,
                transaction_id="f1b2c3d4-1234-4abc-8def-1234567890ab",
                transaction_intent=intent,
                transaction_result=result,
                transaction_journal=journal,
                recovery_provider_manifest=manifest,
                repository_policy=True,
            )
        self.assertEqual(exit_code, writer_fences.EXIT_INDETERMINATE)
        self.assertEqual(receipt["outcome"], "child_lifecycle_indeterminate")
        self.assertEqual(operations, ["begin", "check"])
        self.assertTrue(result.exists())
        self.assertEqual(result.stat().st_size, 0)
        records = self._journal_records(journal)
        self.assertEqual(records[-1]["event"], "release_suppressed")

    def test_closed_child_env_excludes_ambient_secrets_and_provider_controls(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HOSTILE_SECRET": "credential-value",
                writer_fences.PROVIDERS_ENV: "hostile-provider",
                writer_fences.POLICY_HOME_ENV: "/hostile-policy",
                "PATH": "/hostile-path",
            },
            clear=False,
        ):
            child_env = writer_fences._closed_child_env()
        self.assertNotIn("HOSTILE_SECRET", child_env)
        self.assertNotIn(writer_fences.PROVIDERS_ENV, child_env)
        self.assertNotIn(writer_fences.POLICY_HOME_ENV, child_env)
        self.assertEqual(child_env["PATH"], writer_fences.FIXED_CHILD_PATH)

    def test_provider_and_step_failures_never_echo_hostile_output(self) -> None:
        secret = "credential-DO-NOT-ECHO"
        provider = writer_fences.Provider(
            argv=(
                sys.executable,
                "-c",
                f"import sys;sys.stderr.write({secret!r});raise SystemExit(9)",
            ),
            label="noecho",
        )
        response, failure, detail = writer_fences._invoke(
            provider,
            {
                "schema": writer_fences.SCHEMA,
                "request_id": "noecho:0",
                "operation": "begin",
                "repository": {},
                "session": None,
                "transaction": {"step_count": 1},
            },
            timeout=1,
            held=None,
        )
        self.assertIsNone(response)
        self.assertEqual(failure, "invocation")
        self.assertNotIn(secret, detail or "")
        completed, receipt, _marker = self._run(
            providers=[],
            steps=[[sys.executable, "-c", f"import sys;sys.stderr.write({secret!r});raise SystemExit(7)"]],
        )
        self.assertEqual(completed.returncode, 7)
        self.assertNotIn(secret, completed.stderr)
        self.assertNotIn(secret, json.dumps(receipt))

    def test_required_capability_is_checked_inside_mutation_invocation(self) -> None:
        log = self.root / "required-capability.log"
        self._write_policy("allow", log)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[], extra_args=["--require-capability", "future-capability-v9"]
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertIn("runner lacks required capabilities", str(receipt["message"]))
        self.assertFalse(log.exists())
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_recovery_capability_enforces_recoverable_provider_topology(self) -> None:
        policy_log = self.root / "topology-policy.log"
        ambient_log = self.root / "topology-ambient.log"
        self._write_policy("allow", policy_log)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[self._provider("allow", ambient_log)],
            extra_args=[
                "--require-capability",
                "receipt-bound-single-pinned-recovery-v1",
            ],
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertIn("requires exactly one pinned", str(receipt["message"]))
        self.assertFalse(policy_log.exists())
        self.assertFalse(ambient_log.exists())
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_acquisition_sealing_capability_rejects_unpinned_provider(self) -> None:
        policy_log = self.root / "sealed-policy.log"
        ambient_log = self.root / "unsealed-ambient.log"
        self._write_policy("allow", policy_log)
        baseline = self._fingerprint()
        completed, receipt, marker = self._run(
            providers=[self._provider("allow", ambient_log)],
            extra_args=["--require-capability", "acquisition-sealing-v1"],
        )

        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertEqual(receipt["outcome"], "configuration_error")
        self.assertFalse(receipt["mutation_started"])
        self.assertFalse(marker.exists())
        self.assertFalse(policy_log.exists())
        self.assertFalse(ambient_log.exists())
        self.assert_fenced_without_change(completed, receipt, marker, baseline)

    def test_receipt_bound_recovery_clears_state_and_repeats_idempotently(self) -> None:
        log = self.root / "recovery.log"
        self._write_policy("stateful", log)
        fail_end = log.with_suffix(".fail-end")
        fail_end.write_text("fail once\n", encoding="utf-8")
        baseline = self._fingerprint()
        failed, failed_receipt, _ = self._run(providers=[])
        self.assertEqual(failed.returncode, writer_fences.EXIT_RELEASE_FAILED)
        state_path = log.with_suffix(".state.json")
        self.assertTrue(state_path.exists())
        receipt_path = self.root / "failed-receipt.json"
        receipt_path.write_text(json.dumps(failed_receipt), encoding="utf-8")
        fail_end.unlink()
        self._write_policy("allow", log)
        wrong_provider = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--recover-receipt",
                str(receipt_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            shell=False,
        )
        self.assertEqual(wrong_provider.returncode, writer_fences.EXIT_USAGE)
        self.assertIn("provider identity does not match", wrong_provider.stdout)
        self.assertTrue(state_path.exists())
        self._write_policy("stateful", log)
        baseline = self._fingerprint()
        command = [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(self.repo),
            "--recover-receipt",
            str(receipt_path),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            shell=False,
        )
        receipt = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["outcome"], "recovered")
        self.assertIs(receipt["mutation_started"], False)
        self.assertFalse(state_path.exists())
        self.assertEqual(self._fingerprint(), baseline)
        repeated = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            shell=False,
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["outcome"], "recovered")

    def test_recovery_rejects_wrong_repository_receipt_without_invocation(self) -> None:
        log = self.root / "wrong-repo-recovery.log"
        self._write_policy("allow", log)
        receipt_path = self.root / "wrong-repo-receipt.json"
        receipt_path.write_text(
            json.dumps(
                {
                    "schema": writer_fences.SCHEMA,
                    "outcome": "release_failed_after_preflight",
                    "release_verdict": "indeterminate",
                    "transaction_id": "transaction-123",
                    "provider_count": 1,
                    "repository": {**writer_fences.repository_identity(self.repo), "root": "/wrong"},
                    "provider_acquisitions": [
                        {
                            "provider": "repository-policy#0",
                            "provider_identity_sha256": "0" * 64,
                            "pinned": True,
                            "digests": {},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--recover-receipt",
                str(receipt_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            shell=False,
        )
        self.assertEqual(completed.returncode, writer_fences.EXIT_USAGE)
        self.assertFalse(log.exists())
        self.assertIn("does not match current repository", completed.stdout)

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
            providers=[self._provider("timeout_begin", log)], timeout=2.0
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
