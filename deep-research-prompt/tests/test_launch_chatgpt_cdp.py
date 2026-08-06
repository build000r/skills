from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socketserver
import stat
import struct
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "scripts"
    / "launch-chatgpt-cdp.sh"
)


class _FakeCdpHandler(socketserver.BaseRequestHandler):
    server: "_FakeCdpServer"

    def _read_exact(self, count: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < count:
            chunk = self.request.recv(count - len(chunks))
            if not chunk:
                raise ConnectionError("unexpected WebSocket EOF")
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_websocket_json(self) -> dict[str, object]:
        first, second = self._read_exact(2)
        if first & 0x0F != 1:
            raise ConnectionError("expected a text WebSocket frame")
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = bytearray(self._read_exact(length))
        if masked:
            for index in range(length):
                payload[index] ^= mask[index % 4]
        return json.loads(payload.decode("utf-8"))

    def _send_websocket_json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) < 126:
            header = bytes((0x81, len(encoded)))
        elif len(encoded) <= 0xFFFF:
            header = bytes((0x81, 126)) + struct.pack("!H", len(encoded))
        else:
            header = bytes((0x81, 127)) + struct.pack("!Q", len(encoded))
        self.request.sendall(header + encoded)

    def handle(self) -> None:
        request = bytearray()
        while b"\r\n\r\n" not in request:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            request.extend(chunk)
        header_text = request.decode("iso-8859-1")
        request_line, *header_lines = header_text.split("\r\n")
        headers = {}
        for line in header_lines:
            key, separator, value = line.partition(":")
            if separator:
                headers[key.lower()] = value.strip()

        if headers.get("upgrade", "").lower() != "websocket":
            body = json.dumps(
                {
                    "Browser": "Fake Chrome",
                    "webSocketDebuggerUrl": (
                        f"ws://127.0.0.1:{self.server.server_address[1]}"
                        "/devtools/browser/fake"
                    ),
                },
                separators=(",", ":"),
            ).encode("utf-8")
            self.request.sendall(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
                + body
            )
            return

        websocket_key = headers["sec-websocket-key"]
        accept = base64.b64encode(
            hashlib.sha1(
                (websocket_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(
                    "ascii"
                )
            ).digest()
        ).decode("ascii")
        self.request.sendall(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            + f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode("ascii")
        )

        for _ in range(3):
            message = self._read_websocket_json()
            self.server.messages.append(message)
            method = message.get("method")
            message_id = message["id"]
            if method == "SystemInfo.getProcessInfo":
                response = {
                    "id": message_id,
                    "result": {
                        "processInfo": [
                            {"type": "browser", "id": 4242, "cpuTime": 0.1}
                        ]
                    },
                }
            elif method == "Target.createTarget":
                response = {
                    "id": message_id,
                    "result": {"targetId": "real-cdp-target"},
                }
            elif method == "Target.getTargetInfo":
                response = {
                    "id": message_id,
                    "result": {
                        "targetInfo": {
                            "targetId": "real-cdp-target",
                            "type": "page",
                            "url": self.server.target_url,
                            "title": "ChatGPT",
                        }
                    },
                }
            else:
                response = {
                    "id": message_id,
                    "error": {"message": f"unexpected method: {method}"},
                }
            self._send_websocket_json(response)


class _FakeCdpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, target_url: str) -> None:
        super().__init__(("127.0.0.1", 0), _FakeCdpHandler)
        self.target_url = target_url
        self.messages: list[dict[str, object]] = []


class LaunchChatgptCdpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="oracle-launch-test-")
        self.root = Path(self.temporary.name)
        self.profile_root = self.root / "browser-profile"
        self.profile_directory = self.profile_root / "Profile 1"
        self.profile_directory.mkdir(parents=True)
        self.profile_root.chmod(0o700)
        self.profile_directory.chmod(0o700)
        self.runtime_root = self.root / "runtime"
        self.state_path = self.root / "cdp-ready"
        self.open_log = self.root / "open.log"
        self.port = "19444"
        self.app_path = self.root / "Applications" / "Google Chrome.app"
        self.chrome_executable = (
            self.app_path / "Contents" / "MacOS" / "Google Chrome"
        )
        self.chrome_executable.parent.mkdir(parents=True)
        self.chrome_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.chrome_executable.chmod(0o700)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self._write_fakes()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, name: str, body: str) -> Path:
        path = self.bin_dir / name
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _write_fakes(self) -> None:
        self.fake_curl = self._write_executable(
            "curl",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            args="$*"
            if [[ "$args" == *"/json/version"* ]]; then
              [ -f "$FAKE_CDP_STATE" ] || exit 7
              printf '{"Browser":"Fake Chrome","webSocketDebuggerUrl":"ws://127.0.0.1:%s/devtools/browser/fake"}\n' \
                "$FAKE_CDP_PORT"
              exit 0
            fi
            exit 9
            """,
        )
        self.fake_open = self._write_executable(
            "open",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            sleep "${FAKE_OPEN_DELAY:-0}"
            printf '%s\n' "$*" >> "$FAKE_OPEN_LOG"
            : > "$FAKE_CDP_STATE"
            """,
        )
        self.fake_node = self._write_executable(
            "node",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            [ -z "${NODE_OPTIONS:-}" ]
            [ -z "${NODE_PATH:-}" ]
            [ -z "${OPENSSL_CONF:-}" ]
            [ -z "${SSL_CERT_FILE:-}" ]
            [ -z "${DYLD_INSERT_LIBRARIES:-}" ]
            script="$(cat)"
            for required in \
              "SystemInfo.getProcessInfo" \
              "Target.createTarget" \
              "background: true" \
              "Target.getTargetInfo" \
              "target.targetId !== createdTargetId" \
              "allowedMethods"
            do
              [[ "$script" == *"$required"* ]] || {
                printf 'missing CDP contract: %s\n' "$required" >&2
                exit 12
              }
            done
            [ "$1" = "-" ]
            [[ "$2" == ws://127.0.0.1:* ]]
            [ "$3" = "${FAKE_REQUESTED_URL:-https://chatgpt.com/}" ]
            [ "$4" = "4242" ]
            sleep "${FAKE_NODE_DELAY:-0}"
            if [ "${FAKE_SWAP_AFTER_TARGET:-0}" = "1" ]; then
              : > "$FAKE_LISTENER_SWAP_STATE"
            fi
            printf '{"id":"%s","type":"page","url":"%s","browser_pid":%s}\n' \
              "${FAKE_TARGET_ID:-target-123}" \
              "${FAKE_TARGET_URL:-$3}" \
              "${FAKE_BROWSER_PID:-$4}"
            """,
        )
        self.fake_app_resolver = self._write_executable(
            "resolve-app",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            script="$(cat)"
            [[ "$script" == *"path to application appName"* ]]
            [ "$1" = "-" ]
            [ "$2" = "Google Chrome" ]
            printf '%s\n' "$FAKE_APP_PATH"
            """,
        )
        self.fake_lsof = self._write_executable(
            "lsof",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            [ -f "$FAKE_CDP_STATE" ] || exit 1
            listener_pid=4242
            if [ -f "$FAKE_LISTENER_SWAP_STATE" ]; then
              listener_pid=4343
            fi
            if [[ "$*" == *"-Fpun"* ]]; then
              printf 'p%s\nu%s\nf62\nn127.0.0.1:%s\n' \
                "$listener_pid" "$FAKE_LISTENER_UID" "$FAKE_CDP_PORT"
            else
              printf '%s\n' "$listener_pid"
              if [ "${FAKE_EXTRA_LISTENER:-0}" = "1" ]; then
                printf '4343\n'
              fi
            fi
            """,
        )
        self.fake_process_inspector = self._write_executable(
            "inspect-process",
            r"""
            #!/bin/bash -p
            exec /usr/bin/python3 -I - <<'PY'
            import json
            import os

            profile_root = (
                "/foreign"
                if os.environ.get("FAKE_FOREIGN_LISTENER") == "1"
                else os.environ["FAKE_PROFILE_ROOT"]
            )
            executable = os.environ.get(
                "FAKE_PROCESS_EXECUTABLE",
                os.environ["FAKE_CHROME_EXECUTABLE"],
            )
            print(json.dumps({
                "executable": executable,
                "argv": [
                    executable,
                    "--remote-debugging-address=127.0.0.1",
                    f"--remote-debugging-port={os.environ['FAKE_CDP_PORT']}",
                    f"--user-data-dir={profile_root}",
                    "--profile-directory=Profile 1",
                ],
            }, separators=(",", ":")))
            PY
            """,
        )
        self.fake_osascript = self._write_executable(
            "osascript",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            script="$(cat)"
            printf 'hide\n' >> "$FAKE_OSASCRIPT_LOG"
            [ "$1" = "-" ]
            [ "$2" = "4242" ]
            for required in \
              "first application process whose unix id is chromePid" \
              "set visible of chromeProcess to false" \
              "frontmost of chromeProcess" \
              "set position of chromeWindow to {-32000, -32000}"
            do
              [[ "$script" == *"$required"* ]] || {
                printf 'missing visibility contract: %s\n' "$required" >&2
                exit 13
              }
            done
            printf '%s\n' "${FAKE_VISIBILITY_OUTPUT:-false:false:true:0}"
            """,
        )
        self.fake_uname = self._write_executable(
            "uname",
            """
            #!/bin/bash -p
            printf 'Darwin\\n'
            """,
        )
        self.fake_codesign = self._write_executable(
            "codesign",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            printf '%s\n' "$*" >> "$FAKE_CODESIGN_LOG"
            cdhash="${FAKE_CHROME_CDHASH:-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee}"
            authority="Developer ID Application: Google LLC (EQHXZ8M8AV)"
            if [ "${FAKE_BAD_AUTHORITY:-0}" = "1" ]; then
              authority="Developer ID Application: Impostor LLC (AAAAAAAAAA)"
            fi
            if [[ "$*" == *"--verify +4242"* ]]; then
              [ "${FAKE_CODESIGN_VERIFY_FAIL:-0}" != "1" ]
              exit 0
            fi
            if [[ "$*" == *"-d --verbose=4 +4242"* ]]; then
              dynamic_cdhash="${FAKE_DYNAMIC_CDHASH:-$cdhash}"
              printf '%s\n' \
                "Executable=$FAKE_CHROME_EXECUTABLE" \
                "Identifier=com.google.Chrome" \
                "CodeDirectory v=20500 flags=0x12a00(kill,restrict,library-validation,runtime) hashes=13+7" \
                "CDHash=$dynamic_cdhash" \
                "Authority=$authority" \
                "Authority=Developer ID Certification Authority" \
                "Authority=Apple Root CA" \
                "TeamIdentifier=EQHXZ8M8AV"
              exit 0
            fi
            if [[ "$*" == *"-d --verbose=4"* ]]; then
              printf '%s\n' \
                "Executable=$FAKE_CHROME_EXECUTABLE" \
                "Identifier=com.google.Chrome" \
                "CodeDirectory v=20500 flags=0x12a00(kill,restrict,library-validation,runtime) hashes=13+7" \
                "CDHash=$cdhash" \
                "Authority=$authority" \
                "Authority=Developer ID Certification Authority" \
                "Authority=Apple Root CA" \
                "Notarization Ticket=stapled" \
                "TeamIdentifier=EQHXZ8M8AV"
              exit 0
            fi
            exit 19
            """,
        )
        self.fake_spctl = self._write_executable(
            "spctl",
            r"""
            #!/bin/bash -p
            set -euo pipefail
            printf '%s\n' "$*" >> "$FAKE_SPCTL_LOG"
            [ "${FAKE_SPCTL_FAIL:-0}" != "1" ]
            """,
        )

    def _environment(self, **updates: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "FAKE_CDP_PORT": self.port,
                "FAKE_CDP_STATE": str(self.state_path),
                "FAKE_CODESIGN_LOG": str(self.root / "codesign.log"),
                "FAKE_APP_PATH": str(self.app_path),
                "FAKE_CHROME_EXECUTABLE": str(self.chrome_executable.resolve()),
                "FAKE_SPCTL_LOG": str(self.root / "spctl.log"),
                "FAKE_LISTENER_UID": str(os.getuid()),
                "FAKE_LISTENER_SWAP_STATE": str(
                    self.root / "listener-swapped"
                ),
                "FAKE_OPEN_LOG": str(self.open_log),
                "FAKE_OSASCRIPT_LOG": str(self.root / "osascript.log"),
                "FAKE_PROFILE_ROOT": str(self.profile_root.resolve()),
                "FAKE_REQUESTED_URL": "https://chatgpt.com/",
                "ORACLE_LAUNCHER_TEST_MODE": "1",
                "ORACLE_APP_RESOLVER_BIN": str(self.fake_app_resolver),
                "ORACLE_BROWSER_WAIT_SECONDS": "1",
                "ORACLE_CURL_BIN": str(self.fake_curl),
                "ORACLE_CODESIGN_BIN": str(self.fake_codesign),
                "ORACLE_LSOF_BIN": str(self.fake_lsof),
                "ORACLE_NODE_BIN": str(self.fake_node),
                "ORACLE_OPEN_BIN": str(self.fake_open),
                "ORACLE_OSASCRIPT_BIN": str(self.fake_osascript),
                "ORACLE_PROCESS_INSPECTOR_BIN": str(self.fake_process_inspector),
                "ORACLE_SPCTL_BIN": str(self.fake_spctl),
                "ORACLE_UNAME_BIN": str(self.fake_uname),
                "ORACLE_SUBAGENT_RUNTIME_DIR": str(self.runtime_root),
            }
        )
        environment.update(updates)
        return environment

    def _run(
        self,
        *extra: str,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            str(SCRIPT),
            "--port",
            self.port,
            "--profile-root",
            str(self.profile_root),
            "--profile-directory",
            "Profile 1",
            "--no-submit-smoke",
            "--json",
            *extra,
        ]
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            env=env or self._environment(),
            cwd=cwd,
            check=False,
        )

    def test_cold_launch_is_persistent_hidden_loopback_and_exact_target(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["schema"], "oracle-subagent.browser-test.v1")
        self.assertEqual(receipt["state"], "test_ready")
        self.assertEqual(receipt["evidence_mode"], "test")
        self.assertFalse(receipt["production_evidence"])
        self.assertFalse(receipt["attestation_simulated"])
        self.assertFalse(receipt["chrome_signature_verified"])
        self.assertFalse(receipt["gatekeeper_assessed"])
        self.assertFalse(receipt["dynamic_code_verified"])
        self.assertTrue(receipt["cdp_browser_pid_verified"])
        self.assertEqual(receipt["target_id"], "target-123")
        self.assertEqual(receipt["bind"], "127.0.0.1")
        self.assertEqual(receipt["visibility"], "hidden-headful")
        self.assertTrue(receipt["visibility_verified"])
        self.assertTrue(receipt["target_observed"])
        self.assertEqual(receipt["target_url"], "https://chatgpt.com/")
        self.assertTrue(receipt["background_requested"])
        self.assertFalse(receipt["process_visible"])
        self.assertFalse(receipt["process_frontmost"])
        self.assertEqual(receipt["window_count"], 0)
        self.assertIsNone(receipt["windows_offscreen"])
        self.assertFalse(receipt["reused"])
        self.assertFalse(receipt["submit_performed"])
        self.assertTrue(receipt["no_submit_smoke"])
        self.assertEqual(receipt["profile_root"], str(self.profile_root.resolve()))

        launch_arguments = self.open_log.read_text(encoding="utf-8")
        self.assertIn(
            f"-n -g -a {self.app_path.resolve()} --args",
            launch_arguments,
        )
        self.assertIn("--remote-debugging-address=127.0.0.1", launch_arguments)
        self.assertIn(f"--remote-debugging-port={self.port}", launch_arguments)
        self.assertIn(f"--user-data-dir={self.profile_root.resolve()}", launch_arguments)
        self.assertIn("--window-position=-32000,-32000", launch_arguments)
        self.assertNotIn("chatgpt-cdp-profile", launch_arguments)

        receipt_path = self.runtime_root / "browser.json"
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)

    def test_real_node_cdp_sequence_is_launch_only_and_pid_bound(self) -> None:
        node = shutil.which("node")
        curl = shutil.which("curl")
        self.assertIsNotNone(node)
        self.assertIsNotNone(curl)
        server = _FakeCdpServer("https://chatgpt.com/")
        self.port = str(server.server_address[1])
        self.state_path.touch()
        preload_marker = self.root / "node-preload-ran"
        preload = self.root / "preload.cjs"
        preload.write_text(
            "require('node:fs').writeFileSync("
            + json.dumps(str(preload_marker))
            + ", 'loaded');\n",
            encoding="utf-8",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = self._run(
                env=self._environment(
                    ORACLE_CURL_BIN=str(curl),
                    ORACLE_NODE_BIN=str(node),
                    NODE_OPTIONS=f"--require={preload}",
                    NODE_PATH=str(self.root),
                )
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(preload_marker.exists())
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["target_id"], "real-cdp-target")
        self.assertTrue(receipt["cdp_browser_pid_verified"])
        self.assertEqual(
            [message["method"] for message in server.messages],
            [
                "SystemInfo.getProcessInfo",
                "Target.createTarget",
                "Target.getTargetInfo",
            ],
        )
        self.assertEqual(
            server.messages[1]["params"],
            {
                "url": "https://chatgpt.com/",
                "background": True,
                "newWindow": False,
            },
        )
        self.assertEqual(
            server.messages[2]["params"],
            {"targetId": "real-cdp-target"},
        )

    def test_test_only_attestation_executes_cold_cache_and_warm_dynamic_paths(
        self,
    ) -> None:
        environment = self._environment(
            ORACLE_LAUNCHER_TEST_ATTESTATION="1",
        )
        first = self._run(env=environment)
        second = self._run(env=environment)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_receipt = json.loads(first.stdout)
        second_receipt = json.loads(second.stdout)
        for receipt in (first_receipt, second_receipt):
            self.assertEqual(receipt["schema"], "oracle-subagent.browser-test.v1")
            self.assertTrue(receipt["attestation_simulated"])
            self.assertFalse(receipt["production_evidence"])
            self.assertFalse(receipt["gatekeeper_assessed"])
            self.assertFalse(receipt["dynamic_code_verified"])
            self.assertFalse(receipt["chrome_signature_verified"])

        spctl_calls = (self.root / "spctl.log").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(
            spctl_calls,
            [f"--assess --type execute {self.app_path.resolve()}"],
        )
        codesign_calls = (self.root / "codesign.log").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(
            sum(call == "--verify +4242" for call in codesign_calls),
            2,
        )
        self.assertEqual(
            sum(call == "-d --verbose=4 +4242" for call in codesign_calls),
            2,
        )
        attestation_path = self.runtime_root / "browser-attestation.json"
        self.assertEqual(stat.S_IMODE(attestation_path.stat().st_mode), 0o600)
        self.assertEqual(
            json.loads(attestation_path.read_text(encoding="utf-8")),
            {
                "schema": "oracle-subagent.browser-attestation-test.v1",
                "pid": 4242,
                "executable": str(self.chrome_executable.resolve()),
                "cdhash": "e" * 40,
                "gatekeeper_assessed": True,
                "dynamic_code_verified": True,
            },
        )

    def test_attestation_failures_never_emit_a_ready_receipt(self) -> None:
        gatekeeper = self._run(
            env=self._environment(
                ORACLE_LAUNCHER_TEST_ATTESTATION="1",
                FAKE_SPCTL_FAIL="1",
            )
        )
        self.assertEqual(gatekeeper.returncode, 5)
        self.assertIn("failed the macOS Gatekeeper assessment", gatekeeper.stderr)
        self.assertEqual(gatekeeper.stdout, "")
        self.assertFalse(self.state_path.exists())

        bad_authority = self._run(
            env=self._environment(
                ORACLE_LAUNCHER_TEST_ATTESTATION="1",
                FAKE_BAD_AUTHORITY="1",
            )
        )
        self.assertEqual(bad_authority.returncode, 2)
        self.assertIn("expected Google identity", bad_authority.stderr)
        self.assertEqual(bad_authority.stdout, "")

    def test_warm_attestation_cache_never_skips_dynamic_pid_validation(
        self,
    ) -> None:
        environment = self._environment(
            ORACLE_LAUNCHER_TEST_ATTESTATION="1",
        )
        first = self._run(env=environment)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run(
            env=self._environment(
                ORACLE_LAUNCHER_TEST_ATTESTATION="1",
                FAKE_CODESIGN_VERIFY_FAIL="1",
            )
        )
        self.assertEqual(second.returncode, 5)
        self.assertIn("identity could not be proven", second.stderr)
        self.assertEqual(second.stdout, "")
        self.assertEqual(
            len((self.root / "spctl.log").read_text(encoding="utf-8").splitlines()),
            1,
        )

    def test_attestation_rejects_dynamic_cdhash_drift(self) -> None:
        result = self._run(
            env=self._environment(
                ORACLE_LAUNCHER_TEST_ATTESTATION="1",
                FAKE_DYNAMIC_CDHASH="f" * 40,
            )
        )
        self.assertEqual(result.returncode, 5)
        self.assertIn("identity could not be proven", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_python_and_node_preload_environment_is_ignored(self) -> None:
        poison = self.root / "poison"
        poison.mkdir()
        python_marker = self.root / "python-poison-ran"
        poison_code = (
            f"open({str(python_marker)!r}, 'w').write('loaded')\n"
            "raise RuntimeError('poison module loaded')\n"
        )
        (poison / "json.py").write_text(poison_code, encoding="utf-8")
        (poison / "pathlib.py").write_text(poison_code, encoding="utf-8")
        node_marker = self.root / "node-poison-ran"
        preload = poison / "preload.cjs"
        preload.write_text(
            "require('node:fs').writeFileSync("
            + json.dumps(str(node_marker))
            + ", 'loaded');\n",
            encoding="utf-8",
        )
        result = self._run(
            env=self._environment(
                PYTHONPATH=str(poison),
                PYTHONHOME=str(poison),
                NODE_OPTIONS=f"--require={preload}",
                NODE_PATH=str(poison),
                OPENSSL_CONF=str(poison / "openssl.cnf"),
                SSL_CERT_FILE=str(poison / "cert.pem"),
                DYLD_INSERT_LIBRARIES=str(poison / "inject.dylib"),
            ),
            cwd=poison,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(python_marker.exists())
        self.assertFalse(node_marker.exists())

    def test_bash_startup_files_and_imported_functions_are_ignored(self) -> None:
        marker = self.root / "bash-startup-poison-ran"
        startup = self.root / "bash-env"
        startup.write_text(
            f"/bin/echo startup >> {str(marker)!r}\nexit 88\n",
            encoding="utf-8",
        )
        function_body = (
            "() { /bin/echo function >> "
            + repr(str(marker))
            + '; builtin printf "$@"; }'
        )
        result = self._run(
            env=self._environment(
                BASH_ENV=str(startup),
                **{"BASH_FUNC_printf%%": function_body},
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_path_poison_cannot_replace_launcher_utilities(self) -> None:
        poison_bin = self.root / "poison-bin"
        poison_bin.mkdir()
        marker = self.root / "path-poison-ran"
        for command in ("mkdir", "sed", "head"):
            executable = poison_bin / command
            executable.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' {command!r} >> {str(marker)!r}\n"
                "exit 97\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
        environment = self._environment()
        environment["PATH"] = f"{poison_bin}:{environment['PATH']}"
        result = self._run(env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_warm_launch_reuses_owned_process_and_creates_new_target(self) -> None:
        first = self._run()
        second = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(json.loads(second.stdout)["reused"])
        self.assertEqual(len(self.open_log.read_text(encoding="utf-8").splitlines()), 1)

    def test_foreign_listener_fails_closed(self) -> None:
        self.state_path.touch()
        result = self._run(env=self._environment(FAKE_FOREIGN_LISTENER="1"))
        self.assertEqual(result.returncode, 5)
        self.assertIn("does not match the exact Chrome/profile contract", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_listener_owned_by_another_uid_fails_closed(self) -> None:
        self.state_path.touch()
        result = self._run(env=self._environment(FAKE_LISTENER_UID="99999"))
        self.assertEqual(result.returncode, 5)
        self.assertIn("not owned by the current user", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_same_named_executable_at_another_path_fails_closed(self) -> None:
        self.state_path.touch()
        spoofed = (
            self.root
            / "spoof"
            / "Google Chrome.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome"
        )
        result = self._run(
            env=self._environment(FAKE_PROCESS_EXECUTABLE=str(spoofed))
        )
        self.assertEqual(result.returncode, 5)
        self.assertIn("does not match the exact Chrome/profile contract", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_multiple_listener_pids_fail_closed(self) -> None:
        self.state_path.touch()
        result = self._run(env=self._environment(FAKE_EXTRA_LISTENER="1"))
        self.assertEqual(result.returncode, 5)
        self.assertIn("multiple listener owners", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_target_creation_is_bound_to_verified_browser_pid(self) -> None:
        result = self._run(env=self._environment(FAKE_BROWSER_PID="4343"))
        self.assertEqual(result.returncode, 4)
        self.assertIn("did not satisfy the ChatGPT target contract", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_listener_swap_after_target_creation_fails_closed(self) -> None:
        result = self._run(env=self._environment(FAKE_SWAP_AFTER_TARGET="1"))
        self.assertEqual(result.returncode, 5)
        self.assertIn("listener changed during ownership verification", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_concurrent_launches_are_serialized_and_return_own_target(self) -> None:
        command = [
            str(SCRIPT),
            "--port",
            self.port,
            "--profile-root",
            str(self.profile_root),
            "--profile-directory",
            "Profile 1",
            "--no-submit-smoke",
            "--json",
        ]
        first = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._environment(
                FAKE_TARGET_ID="target-a",
                FAKE_OPEN_DELAY="0.2",
            ),
        )
        time.sleep(0.03)
        second = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._environment(FAKE_TARGET_ID="target-b"),
        )
        first_stdout, first_stderr = first.communicate(timeout=10)
        second_stdout, second_stderr = second.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, first_stderr)
        self.assertEqual(second.returncode, 0, second_stderr)
        self.assertEqual(json.loads(first_stdout)["target_id"], "target-a")
        self.assertEqual(json.loads(second_stdout)["target_id"], "target-b")
        self.assertEqual(len(self.open_log.read_text(encoding="utf-8").splitlines()), 1)

    def test_observed_target_url_must_equal_requested_normalized_url(self) -> None:
        requested = "https://chatgpt.com/g/g-project"
        result = self._run(
            "--url",
            requested,
            env=self._environment(
                FAKE_REQUESTED_URL=requested,
                FAKE_TARGET_URL="https://chatgpt.com/",
            ),
        )
        self.assertEqual(result.returncode, 4)
        self.assertIn("did not satisfy the ChatGPT target contract", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_base_url_is_normalized_before_target_creation(self) -> None:
        result = self._run(
            "--url",
            "https://chatgpt.com",
            env=self._environment(FAKE_REQUESTED_URL="https://chatgpt.com/"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["target_url"],
            "https://chatgpt.com/",
        )

    def test_visibility_must_be_observed_for_exact_listener_pid(self) -> None:
        result = self._run(
            env=self._environment(FAKE_VISIBILITY_OUTPUT="false:true:true:0")
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("failed visibility contract", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_hidden_reused_browser_accepts_macos_coordinate_clamping(self) -> None:
        self.state_path.touch()
        result = self._run(
            env=self._environment(
                FAKE_VISIBILITY_OUTPUT="false:false:false:2",
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["visibility_verified"])
        self.assertFalse(receipt["process_visible"])
        self.assertFalse(receipt["process_frontmost"])
        self.assertEqual(receipt["window_count"], 2)
        self.assertFalse(receipt["windows_offscreen"])

    def test_post_ownership_failure_rehides_before_exit(self) -> None:
        result = self._run(
            env=self._environment(
                FAKE_VISIBILITY_OUTPUT="false:true:true:0",
            )
        )
        self.assertNotEqual(result.returncode, 0)
        hide_calls = (self.root / "osascript.log").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertGreaterEqual(len(hide_calls), 2)

    def test_stale_dead_pid_lock_is_recovered(self) -> None:
        self.runtime_root.mkdir(mode=0o700)
        lock_path = self.runtime_root / "launcher.lock"
        lock_path.write_text(
            "pid=999999\ntoken=999999-1-2-3\n",
            encoding="utf-8",
        )
        lock_path.chmod(0o600)
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lock_path.exists())

    def test_failed_launch_invalidates_a_seeded_production_ready_receipt(self) -> None:
        self.runtime_root.mkdir(mode=0o700)
        receipt_path = self.runtime_root / "browser.json"
        receipt_path.write_text(
            json.dumps(
                {
                    "schema": "oracle-subagent.browser.v1",
                    "state": "ready",
                    "production_evidence": True,
                    "pid": 999999,
                    "target_id": "stale-target",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        receipt_path.chmod(0o600)
        result = self._run(
            env=self._environment(
                ORACLE_LAUNCHER_TEST_ATTESTATION="1",
                FAKE_BAD_AUTHORITY="1",
            )
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected Google identity", result.stderr)
        self.assertFalse(receipt_path.exists())

    def test_broad_runtime_is_rejected_before_receipt_invalidation(self) -> None:
        fake_home = self.root / "fake-home"
        fake_home.mkdir(mode=0o700)
        receipt_path = fake_home / "browser.json"
        original = '{"state":"unrelated-user-data"}\n'
        receipt_path.write_text(original, encoding="utf-8")
        receipt_path.chmod(0o600)
        result = self._run(
            env=self._environment(
                HOME=str(fake_home),
                ORACLE_SUBAGENT_RUNTIME_DIR=str(fake_home),
            )
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("runtime directory is too broad", result.stderr)
        self.assertEqual(receipt_path.read_text(encoding="utf-8"), original)

    def test_concurrent_stale_lock_recovery_remains_serialized(self) -> None:
        self.runtime_root.mkdir(mode=0o700)
        lock_path = self.runtime_root / "launcher.lock"
        lock_path.write_text(
            "pid=999999\ntoken=999999-1-2-3\n",
            encoding="utf-8",
        )
        lock_path.chmod(0o600)
        command = [
            str(SCRIPT),
            "--port",
            self.port,
            "--profile-root",
            str(self.profile_root),
            "--profile-directory",
            "Profile 1",
            "--no-submit-smoke",
            "--json",
        ]
        first = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._environment(
                FAKE_TARGET_ID="stale-target-a",
                ORACLE_LAUNCHER_TEST_RECLAIM_DELAY="0.2",
            ),
        )
        time.sleep(0.03)
        second = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._environment(FAKE_TARGET_ID="stale-target-b"),
        )
        first_stdout, first_stderr = first.communicate(timeout=10)
        second_stdout, second_stderr = second.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, first_stderr)
        self.assertEqual(second.returncode, 0, second_stderr)
        self.assertEqual(json.loads(first_stdout)["target_id"], "stale-target-a")
        self.assertEqual(json.loads(second_stdout)["target_id"], "stale-target-b")
        self.assertEqual(
            len(self.open_log.read_text(encoding="utf-8").splitlines()),
            1,
        )
        self.assertFalse(lock_path.exists())

    def test_old_lock_with_live_owner_is_not_reclaimed(self) -> None:
        self.runtime_root.mkdir(mode=0o700)
        lock_path = self.runtime_root / "launcher.lock"
        lock_record = f"pid={os.getpid()}\ntoken={os.getpid()}-1-2-3\n"
        lock_path.write_text(lock_record, encoding="utf-8")
        lock_path.chmod(0o600)
        old = time.time() - 10
        os.utime(lock_path, (old, old))
        result = self._run(
            env=self._environment(ORACLE_BROWSER_LOCK_WAIT_TENTHS="2")
        )
        self.assertEqual(result.returncode, 5)
        self.assertIn("timed out waiting", result.stderr)
        self.assertEqual(lock_path.read_text(encoding="utf-8"), lock_record)

    def test_lock_symlink_is_rejected_without_touching_target(self) -> None:
        self.runtime_root.mkdir(mode=0o700)
        symlink_target = self.root / "lock-target"
        symlink_target.mkdir(mode=0o755)
        (symlink_target / "sentinel").write_text("preserve", encoding="utf-8")
        (self.runtime_root / "launcher.lock").symlink_to(
            symlink_target,
            target_is_directory=True,
        )
        result = self._run()
        self.assertEqual(result.returncode, 5)
        self.assertIn("lock must not be a symlink", result.stderr)
        self.assertEqual(
            (symlink_target / "sentinel").read_text(encoding="utf-8"),
            "preserve",
        )

    def test_insecure_profile_permissions_fail_before_browser_contact(self) -> None:
        self.profile_root.chmod(0o755)
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not grant group/world access", result.stderr)
        self.assertFalse(self.state_path.exists())

    def test_non_chatgpt_url_is_rejected(self) -> None:
        result = self._run("--url", "https://example.com/")
        self.assertEqual(result.returncode, 2)
        self.assertIn("URL must use https://chatgpt.com", result.stderr)

    def test_chatgpt_url_query_is_rejected_before_browser_contact(self) -> None:
        result = self._run("--url", "https://chatgpt.com/?token=secret")
        self.assertEqual(result.returncode, 2)
        self.assertIn("without credentials, port, query, or fragment", result.stderr)
        self.assertFalse(self.state_path.exists())

    def test_profile_subdirectory_symlink_is_rejected(self) -> None:
        self.profile_directory.rmdir()
        outside_profile = self.root / "outside-profile"
        outside_profile.mkdir(mode=0o700)
        self.profile_directory.symlink_to(outside_profile, target_is_directory=True)
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("profile directory must not be a symlink", result.stderr)
        self.assertFalse(self.state_path.exists())

    def test_runtime_symlink_is_rejected_without_chmod_target(self) -> None:
        symlink_target = self.root / "runtime-target"
        symlink_target.mkdir()
        symlink_target.chmod(0o755)
        self.runtime_root.symlink_to(symlink_target, target_is_directory=True)
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("runtime directory must not be a symlink", result.stderr)
        self.assertEqual(stat.S_IMODE(symlink_target.stat().st_mode), 0o755)

    def test_source_contains_no_profile_clone_path(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("rsync", source)
        self.assertNotIn("chatgpt-cdp-profile", source)
        self.assertNotIn("mktemp -d", source)
        for clone_primitive in (
            "\ncp ",
            "\nditto ",
            "\npax ",
            "shutil.copy",
            "copyfile(",
            "clonefile(",
        ):
            self.assertNotIn(clone_primitive, source)
        for submit_primitive in (
            "Runtime.evaluate",
            "Input.dispatch",
            "DOM.set",
            "insertText",
        ):
            self.assertNotIn(submit_primitive, source)
        self.assertIn("--remote-debugging-address=127.0.0.1", source)
        self.assertIn("--window-position=-32000,-32000", source)
        self.assertIn('-a "$CHROME_APP_PATH"', source)
        self.assertNotIn('-a "$CHROME_APP"', source)
        self.assertIn("background: true", source)
        self.assertIn("Target.getTargetInfo", source)
        self.assertIn("SystemInfo.getProcessInfo", source)
        self.assertIn('SPCTL_BIN="/usr/sbin/spctl"', source)
        self.assertIn('--assess --type execute "$CHROME_APP_PATH"', source)
        self.assertIn('--verify "+$pid"', source)
        self.assertNotIn("--ignore-resources", source)
        self.assertNotIn('"$PYTHON_BIN" - ', source)
        self.assertNotIn('"$PYTHON_BIN" -c ', source)
        self.assertIn("node_environment=(", source)
        self.assertIn("/usr/bin/env\n  -i", source)
        self.assertIn('"$CURL_BIN" -q ', source)
        self.assertIn("launcher.lock", source)
        self.assertTrue(source.startswith("#!/bin/bash -p\n"))
        for path_resolved_utility in ("mkdir", "sed", "head"):
            self.assertNotRegex(
                source,
                rf"(?m)^[ \t]*(?:if ! )?{path_resolved_utility}[ \t]",
            )


if __name__ == "__main__":
    unittest.main()
