#!/usr/bin/env python3
"""Tests for the Mermaid Live URL encoder."""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib import request, error

import mmd


OFFICIAL_DEFAULT_CODE = """flowchart TD
    A[Christmas] -->|Get money| B(Go shopping)
    B --> C{Let me think}
    C -->|One| D[Laptop]
    C -->|Two| E[iPhone]
    C -->|Three| F[fa:fa-car Car]
  """

OFFICIAL_DEFAULT_FRAGMENT = (
    "pako:eNpVjEFug0AMRa9iedVI4QIsKiXQZhOpXWRVyMICw4zKjEdmUFQBd--QtFLrlb_e-3_GRlrGHLtBbo0hjXApaw_pDlVh1I7R0XiFLHteThzBieevBY5PJ4HRSAjW97uHf9wkKObzpjFEY_3n-kDFvf_meYGyOlOIEq5_yeUmC7xU9t2k-f_EKKfWa9VR3lHWkEJBeldwj73aFvOoE-_RsTraIs4brTEadlxjnt6WO5qGWGPt11QL5D9E3G9TZeoNpvlhTGkKLUUuLfVKP8r6DdATXyM"
)


class MmdTests(unittest.TestCase):
    def test_matches_mermaid_live_official_snapshot(self) -> None:
        state = mmd.build_state(OFFICIAL_DEFAULT_CODE)
        self.assertEqual(mmd.encode_state(state), OFFICIAL_DEFAULT_FRAGMENT)

    def test_round_trip_pako_state(self) -> None:
        source = "flowchart TD\n  A --> B\n"
        state = mmd.build_state(source, theme="dark", rough=True)
        fragment = mmd.encode_state(state)
        decoded = mmd.decode_state(f"https://mermaid.live/edit#{fragment}")
        self.assertEqual(decoded, state)

    def test_round_trip_handoff_metadata(self) -> None:
        source = "flowchart TD\n  A --> B\n"
        handoff = {
            "version": 1,
            "endpoint": "http://127.0.0.1:49152/send",
            "token": "secret-token",
            "tmuxTarget": "%12",
            "tmuxLabel": "work:1.2",
            "mmdCommand": "python3 '/opt/mmd/scripts/mmd.py'",
        }
        state = mmd.build_state(source, handoff=handoff)
        decoded = mmd.decode_state(mmd.encode_state(state))

        self.assertEqual(decoded["buildooorHandoff"], handoff)

    def test_round_trip_source_metadata(self) -> None:
        source = "flowchart TD\n  A --> B\n"
        metadata = mmd.build_source_metadata(__file__)
        state = mmd.build_state(source, source=metadata)
        decoded = mmd.decode_state(mmd.encode_state(state))

        self.assertEqual(decoded["buildooorSource"]["kind"], "file")
        self.assertEqual(decoded["buildooorSource"]["path"], str(Path(__file__).resolve()))

    def test_stdin_has_no_source_metadata(self) -> None:
        self.assertIsNone(mmd.build_source_metadata("-"))

    def test_tmux_handoff_uses_bracketed_paste(self) -> None:
        with (
            patch.object(mmd.shutil, "which", return_value="/opt/homebrew/bin/tmux"),
            patch.object(mmd.secrets, "token_hex", return_value="abcd1234"),
            patch.object(mmd.subprocess, "run") as run,
        ):
            mmd.send_prompt_to_tmux("%12", "first line\nsecond line")

        run.assert_any_call(
            ["tmux", "paste-buffer", "-p", "-b", "buildooor-diagram-abcd1234", "-t", "%12"],
            check=True,
        )

    def test_tmux_handoff_can_submit_after_paste(self) -> None:
        with (
            patch.object(mmd.shutil, "which", return_value="/opt/homebrew/bin/tmux"),
            patch.object(mmd.secrets, "token_hex", return_value="abcd1234"),
            patch.object(mmd.subprocess, "run") as run,
        ):
            mmd.send_prompt_to_tmux("%12", "first line\nsecond line", submit=True)

        run.assert_any_call(
            ["tmux", "send-keys", "-t", "%12", "Enter"],
            check=True,
        )

    def test_main_prints_fragment_for_file_input(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()

        try:
            with redirect_stdout(stdout):
                exit_code = mmd.main([path, "--fragment-only", "--no-preflight"])
        finally:
            Path(path).unlink(missing_ok=True)

        fragment = stdout.getvalue().strip()
        self.assertEqual(exit_code, 0)
        self.assertTrue(fragment.startswith("pako:"))
        self.assertEqual(mmd.decode_state(fragment)["code"], "flowchart TD\n  A --> B\n")

    def test_main_preflight_only_reports_diagram_type(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()

        try:
            with patch.object(mmd, "preflight_mermaid", return_value={"diagramType": "flowchart-v2"}):
                with redirect_stdout(stdout):
                    exit_code = mmd.main([path, "--preflight-only"])
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 0)
        self.assertIn("Mermaid preflight OK: flowchart-v2", stdout.getvalue())

    def test_main_decode_code_only(self) -> None:
        fragment = mmd.encode_state(mmd.build_state("sequenceDiagram\n  A->>B: hi\n"))
        stdout = StringIO()

        with redirect_stdout(stdout):
            exit_code = mmd.main(["--decode", fragment, "--code-only"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "sequenceDiagram\n  A->>B: hi\n")

    def test_main_reports_missing_path_error(self) -> None:
        stderr = StringIO()

        with redirect_stderr(stderr):
            exit_code = mmd.main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("missing .mmd path", stderr.getvalue())

    def test_main_validates_handoff_server_arguments(self) -> None:
        stderr = StringIO()

        with redirect_stderr(stderr):
            exit_code = mmd.main(["--handoff-server", "--handoff-port", "1"])

        self.assertEqual(exit_code, 1)
        self.assertIn("--handoff-server requires", stderr.getvalue())

    def test_main_adds_handoff_and_source_metadata_for_tmux_file_input(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()
        handoff = {
            "version": 1,
            "endpoint": "http://127.0.0.1:49152/send",
            "token": "secret-token",
            "tmuxTarget": "%12",
            "mmdCommand": "python3 '/opt/mmd/scripts/mmd.py'",
            "submitOnSend": True,
        }

        try:
            with patch.object(mmd, "start_handoff_channel", return_value=handoff):
                with redirect_stdout(stdout):
                    exit_code = mmd.main([path, "--fragment-only", "--tmux", "--tmux-submit", "--no-preflight"])
        finally:
            Path(path).unlink(missing_ok=True)

        decoded = mmd.decode_state(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        self.assertEqual(decoded["buildooorHandoff"], handoff)
        self.assertEqual(decoded["buildooorSource"]["path"], str(Path(path).resolve()))

    def test_start_handoff_channel_adds_launcher_command(self) -> None:
        with (
            patch.object(mmd, "resolve_tmux_target", return_value="%12"),
            patch.object(mmd, "describe_tmux_target", return_value="work:1.2"),
            patch.object(mmd.secrets, "token_urlsafe", return_value="secret-token"),
            patch.object(mmd, "find_available_port", return_value=49152),
            patch.object(mmd, "wait_for_handoff_server"),
            patch.object(mmd.subprocess, "Popen") as popen,
            patch.object(mmd.sys, "executable", "/usr/bin/python3"),
        ):
            handoff = mmd.start_handoff_channel(
                host="127.0.0.1",
                tmux_target=None,
                ttl_seconds=60,
                source_path="/workspace/demo/diagram.mmd",
                submit_on_send=True,
            )

        self.assertEqual(handoff["mmdCommand"], f"/usr/bin/python3 {mmd.shlex.quote(str(Path(mmd.__file__).resolve()))}")
        self.assertTrue(handoff["sourceEditable"])
        self.assertTrue(handoff["submitOnSend"])
        popen.assert_called_once()

    def test_handoff_post_sends_prompt_to_tmux(self) -> None:
        with patch.object(mmd, "send_prompt_to_tmux") as send_prompt:
            status, body = post_handoff_json({"token": "secret-token", "prompt": "hello"})

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["submitOnSend"])
        send_prompt.assert_called_once_with("%12", "hello", submit=False)

    def test_handoff_post_can_submit_prompt_to_tmux(self) -> None:
        with patch.object(mmd, "send_prompt_to_tmux") as send_prompt:
            status, body = post_handoff_json({"token": "secret-token", "prompt": "hello"}, submit_on_send=True)

        self.assertEqual(status, 200)
        self.assertTrue(body["submitOnSend"])
        send_prompt.assert_called_once_with("%12", "hello", submit=True)

    def test_handoff_post_rejects_bad_token(self) -> None:
        status, body = post_handoff_json({"token": "wrong", "prompt": "hello"})

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "handoff token mismatch")

    def test_handoff_post_rejects_missing_prompt(self) -> None:
        status, body = post_handoff_json({"token": "secret-token", "prompt": "   "})

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "missing prompt")

    def test_handoff_source_read_returns_attached_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name

        try:
            status, body = post_handoff_json({"token": "secret-token"}, path="/source/read", source_path=path)
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(status, 200)
        self.assertEqual(body["code"], "flowchart TD\n  A --> B\n")
        self.assertEqual(body["path"], path)

    def test_handoff_source_preflight_validates_submitted_code(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name

        try:
            with patch.object(mmd, "preflight_mermaid", return_value={"diagramType": "flowchart-v2"}) as preflight:
                status, body = post_handoff_json(
                    {"token": "secret-token", "code": "flowchart TD\n  A --> C\n"},
                    path="/source/preflight",
                    source_path=path,
                )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(status, 200)
        self.assertEqual(body["preflight"]["diagramType"], "flowchart-v2")
        preflight.assert_called_once_with("flowchart TD\n  A --> C\n")

    def test_handoff_source_write_validates_before_saving(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        updated = "flowchart TD\n  A --> C\n"

        try:
            with patch.object(mmd, "preflight_mermaid", return_value={"diagramType": "flowchart-v2"}):
                status, body = post_handoff_json(
                    {"token": "secret-token", "code": updated},
                    path="/source/write",
                    source_path=path,
                )
            saved = Path(path).read_text(encoding="utf-8")
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(status, 200)
        self.assertEqual(body["preflight"]["diagramType"], "flowchart-v2")
        self.assertEqual(saved, updated)

    def test_handoff_source_write_does_not_save_invalid_code(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name

        try:
            with patch.object(mmd, "preflight_mermaid", side_effect=ValueError("Mermaid preflight failed")):
                status, body = post_handoff_json(
                    {"token": "secret-token", "code": "flowchart TD\n  A -->\n"},
                    path="/source/write",
                    source_path=path,
                )
            saved = Path(path).read_text(encoding="utf-8")
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(status, 422)
        self.assertIn("Mermaid preflight failed", body["error"])
        self.assertEqual(saved, "flowchart TD\n  A --> B\n")

    def test_handoff_source_endpoints_require_attached_file(self) -> None:
        status, body = post_handoff_json({"token": "secret-token"}, path="/source/read", source_path=None)

        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "no source file is attached")

    def test_fragment_has_no_base64_padding(self) -> None:
        fragment = mmd.encode_state(mmd.build_state("sequenceDiagram\n  A->>B: hi\n"))
        self.assertTrue(fragment.startswith("pako:"))
        self.assertNotIn("=", fragment)

    def test_default_url_targets_buildooor_diagrams(self) -> None:
        fragment = mmd.encode_state(mmd.build_state("flowchart TD\n  A --> B\n"))
        url = mmd.build_url(fragment)
        self.assertTrue(url.startswith("https://buildooor.com/diagrams#pako:"))
        self.assertNotIn("mermaid.live", url)

    def test_base_url_override_still_works(self) -> None:
        fragment = mmd.encode_state(mmd.build_state("flowchart TD\n  A --> B\n"))
        self.assertEqual(
            mmd.build_url(fragment, base_url="https://example.test/custom"),
            f"https://example.test/custom#{fragment}",
        )

    @unittest.skipUnless(shutil.which("node") and mmd.parser_dependencies_ready(), "Mermaid parser not installed")
    def test_preflight_accepts_valid_mermaid(self) -> None:
        result = mmd.preflight_mermaid("flowchart TD\n  A --> B\n", auto_install=False)
        self.assertEqual(result["diagramType"], "flowchart-v2")

    @unittest.skipUnless(shutil.which("node") and mmd.parser_dependencies_ready(), "Mermaid parser not installed")
    def test_preflight_rejects_invalid_mermaid(self) -> None:
        with self.assertRaisesRegex(ValueError, "Mermaid preflight failed"):
            mmd.preflight_mermaid("flowchart TD\n  A -->\n", auto_install=False)

def post_handoff_json(
    payload: dict[str, object],
    *,
    path: str = "/send",
    source_path: str | None = None,
    submit_on_send: bool = False,
) -> tuple[int, dict[str, object]]:
    server = mmd.HandoffHTTPServer(("127.0.0.1", 0), mmd.HandoffRequestHandler)
    server.token = "secret-token"
    server.tmux_target = "%12"
    server.source_path = source_path
    server.submit_on_send = submit_on_send
    server.expires_at = time.time() + 10
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}{path}"
        req = request.Request(
            endpoint,
            data=mmd.json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=2) as response:
                return response.status, mmd.json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            return exc.code, mmd.json.loads(exc.read().decode("utf-8"))
    finally:
        thread.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    unittest.main()
