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


class FakeHTTPResponse:
    def __init__(self, body: str | dict[str, object], status: int = 200) -> None:
        self.status = status
        self._body = mmd.json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body


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

    def test_builds_mmdx_document_from_markdown_charts(self) -> None:
        document = mmd.build_mmdx_document(
            """<!-- mmdx
{"entry":"main","links":[{"from":"main","label":"Open detail","to":"detail","actions":[{"type":"web","url":"https://example.com/detail","title":"Open detail on web"},{"type":"github","url":"http://github.com/build000r/skills"},{"type":"x","url":"javascript:alert(1)"},{"type":"email","url":"https://example.com/email"}]}]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Open detail] --> B[Next]
```

## chart detail Detail Chart
```mermaid
sequenceDiagram
  A->>B: detail
```
"""
        )

        self.assertEqual(document["entry"], "main")
        self.assertEqual([chart["id"] for chart in document["charts"]], ["main", "detail"])
        self.assertEqual(document["links"][0]["to"], "detail")
        self.assertEqual(
            document["links"][0]["actions"],
            [
                {
                    "type": "web",
                    "url": "https://example.com/detail",
                    "title": "Open detail on web",
                },
                {
                    "type": "github",
                    "url": "http://github.com/build000r/skills",
                },
            ],
        )

    def test_build_mmdx_document_rejects_duplicate_chart_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "MMDX chart IDs must be unique: main"):
            mmd.build_mmdx_document(
                """## chart main First
```mermaid
flowchart TD
  A[First] --> B[Next]
```

## chart main Second
```mermaid
flowchart TD
  C[Second] --> D[Done]
```
"""
            )

    def test_build_mmdx_document_rejects_blank_line_before_chart_fence(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be followed immediately by ```mermaid"):
            mmd.build_mmdx_document(
                """## chart main Main Chart

```mermaid
flowchart TD
  A --> B
```
"""
            )

    def test_main_encodes_mmdx_document_with_entry_chart(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmdx", delete=False) as handle:
            handle.write(
                """<!-- mmdx
{"entry":"main","links":[{"from":"main","label":"Open detail","to":"detail","actions":[{"type":"web","url":"https://example.com/detail"}]}]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Open detail] --> B[Next]
```

## chart detail Detail Chart
```mermaid
flowchart TD
  C[Detail] --> D[Done]
```
"""
            )
            path = handle.name
        stdout = StringIO()

        try:
            with redirect_stdout(stdout):
                exit_code = mmd.main([path, "--fragment-only", "--no-preflight"])
        finally:
            Path(path).unlink(missing_ok=True)

        decoded = mmd.decode_state(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        self.assertIn("Open detail", decoded["code"])
        self.assertEqual(decoded["buildooorMmdx"]["entry"], "main")
        self.assertEqual(len(decoded["buildooorMmdx"]["charts"]), 2)
        self.assertEqual(
            decoded["buildooorMmdx"]["links"][0]["actions"],
            [{"type": "web", "url": "https://example.com/detail"}],
        )

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

    def test_publish_link_dry_run_prints_payload_without_network(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()

        try:
            with patch.object(mmd.request, "urlopen") as urlopen:
                with redirect_stdout(stdout):
                    exit_code = mmd.main(
                        [
                            "publish-link",
                            path,
                            "--username",
                            "operator",
                            "--slug",
                            "abc123",
                            "--title",
                            "Demo diagram",
                            "--dry-run",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        body = mmd.json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()
        self.assertEqual(body["endpoint"], "https://buildooor.com/api/app-links/operator/abc123")
        self.assertEqual(body["url"], "https://buildooor.com/mmdx/operator/abc123")
        self.assertEqual(body["source_kind"], "mermaid")
        self.assertEqual(body["payload"]["title"], "Demo diagram")
        self.assertEqual(body["payload"]["metadata"]["diagram_state_format"], "mermaid-live-pako")
        self.assertEqual(mmd.decode_state(body["payload"]["metadata"]["diagram_state"])["code"], "flowchart TD\n  A --> B\n")

    def test_publish_link_dry_run_summary_omits_full_pako_payload(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()

        try:
            with redirect_stdout(stdout):
                exit_code = mmd.main(
                    [
                        "publish-link",
                        path,
                        "--username",
                        "operator",
                        "--slug",
                        "abc123",
                        "--dry-run",
                        "--summary",
                        "--no-preflight",
                    ]
                )
        finally:
            Path(path).unlink(missing_ok=True)

        body = mmd.json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertNotIn("payload", body)
        self.assertEqual(body["payload_summary"]["metadata"]["diagram_state_format"], "mermaid-live-pako")
        self.assertGreater(body["payload_summary"]["metadata"]["diagram_state_bytes"], 10)
        self.assertNotIn("diagram_state", body["payload_summary"]["metadata"])

    def test_publish_link_updates_and_verifies_live_fragment(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmdx", delete=False) as handle:
            handle.write(
                """<!-- mmdx
{"entry":"main","links":[]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Local] --> B[Published]
```
"""
            )
            path = handle.name
        stdout = StringIO()
        captured: dict[str, object] = {}

        def fake_urlopen(req, timeout=0):
            self.assertEqual(timeout, 20.0)
            if isinstance(req, request.Request) and req.get_method() == "PATCH":
                captured["request"] = req
                payload = mmd.json.loads(req.data.decode("utf-8"))
                captured["payload"] = payload
                return FakeHTTPResponse(
                    {
                        "success": True,
                        "data": {
                            "username": "operator",
                            "slug": "abc123",
                            "target_path": "/diagrams",
                        },
                    }
                )
            self.assertEqual(req.full_url, "https://buildooor.com/mmdx/operator/abc123")
            fragment = captured["payload"]["metadata"]["diagram_state"]
            next_data = {
                "props": {
                    "pageProps": {
                        "initialDiagramFragment": fragment,
                    }
                }
            }
            return FakeHTTPResponse(
                f'<html><script id="__NEXT_DATA__" type="application/json">{mmd.json.dumps(next_data)}</script></html>'
            )

        try:
            with patch.object(mmd.request, "urlopen", side_effect=fake_urlopen):
                with redirect_stdout(stdout):
                    exit_code = mmd.main(
                        [
                            "publish-link",
                            path,
                            "--username",
                            "operator",
                            "--slug",
                            "abc123",
                            "--access-token",
                            "access_123",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 0)
        sent = captured["request"]
        self.assertEqual(sent.full_url, "https://buildooor.com/api/app-links/operator/abc123")
        headers = {key.lower(): value for key, value in sent.header_items()}
        self.assertEqual(headers["authorization"], "Bearer access_123")
        self.assertEqual(headers["origin"], "https://buildooor.com")
        payload = captured["payload"]
        self.assertEqual(payload["resource_kind"], "mmdx-diagram")
        self.assertEqual(payload["metadata"]["source_kind"], "mmdx")
        self.assertIn("Updated https://buildooor.com/mmdx/operator/abc123", stdout.getvalue())
        self.assertIn("live_verification=OK", stdout.getvalue())

    def test_publish_link_requires_token_before_mutation(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stderr = StringIO()

        try:
            with patch.dict(mmd.os.environ, {}, clear=True):
                with patch.object(mmd.request, "urlopen") as urlopen:
                    with redirect_stderr(stderr):
                        exit_code = mmd.main(
                            [
                                "publish-link",
                                path,
                                "--username",
                                "operator",
                                "--slug",
                                "abc123",
                                "--no-preflight",
                            ]
                        )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 1)
        urlopen.assert_not_called()
        self.assertIn("publish-link requires --access-token", stderr.getvalue())

    def test_publish_link_accepts_spaps_access_token_env(self) -> None:
        with patch.dict(mmd.os.environ, {"SPAPS_ACCESS_TOKEN": "spaps_access_123"}, clear=True):
            args = mmd.parse_args(
                [
                    "publish-link",
                    "diagram.mmd",
                    "--username",
                    "operator",
                    "--slug",
                    "abc123",
                ]
            )

        self.assertEqual(mmd.resolve_publish_access_token(args), "spaps_access_123")

    def test_list_dry_run_prints_request_metadata_without_network_or_token_leak(self) -> None:
        stdout = StringIO()

        with patch.object(mmd.request, "urlopen") as urlopen:
            with redirect_stdout(stdout):
                exit_code = mmd.main(["list", "--dry-run", "--access-token", "secret-token"])

        body = mmd.json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()
        self.assertEqual(body["endpoint"], "https://buildooor.com/api/mmdx/diagrams")
        self.assertEqual(body["method"], "GET")
        self.assertEqual(body["upstream_path"], "/v1/mmdx/diagrams")
        self.assertEqual(body["headers"]["Authorization"], "Bearer <redacted>")
        self.assertEqual(body["headers"]["Origin"], "https://buildooor.com")
        self.assertNotIn("secret-token", stdout.getvalue())

    def test_list_dry_run_does_not_require_token(self) -> None:
        stdout = StringIO()

        with patch.dict(mmd.os.environ, {}, clear=True):
            with patch.object(mmd.request, "urlopen") as urlopen:
                with redirect_stdout(stdout):
                    exit_code = mmd.main(["list", "--dry-run"])

        body = mmd.json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()
        self.assertEqual(body["headers"]["Authorization"], "<missing>")
        self.assertEqual(body["auth_source"], "missing")

    def test_list_requires_token_before_network(self) -> None:
        stderr = StringIO()

        with patch.dict(mmd.os.environ, {}, clear=True):
            with patch.object(mmd.request, "urlopen") as urlopen:
                with redirect_stderr(stderr):
                    exit_code = mmd.main(["list"])

        self.assertEqual(exit_code, 1)
        urlopen.assert_not_called()
        self.assertIn("list requires --access-token", stderr.getvalue())

    def test_list_prints_owner_diagram_table(self) -> None:
        stdout = StringIO()
        captured: dict[str, object] = {}

        def fake_urlopen(req, timeout=0):
            captured["request"] = req
            captured["timeout"] = timeout
            return FakeHTTPResponse(
                {
                    "profile": {"username": "operator"},
                    "items": [
                        {
                            "id": "diag_1",
                            "chart_slug": "architecture-overview",
                            "title": "Architecture overview",
                            "visibility": "private",
                            "updated_at": "2026-05-28T05:00:00Z",
                        }
                    ],
                }
            )

        with patch.object(mmd.request, "urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                exit_code = mmd.main(["list", "--access-token", "access_123"])

        sent = captured["request"]
        headers = {key.lower(): value for key, value in sent.header_items()}
        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["timeout"], 20.0)
        self.assertEqual(sent.get_method(), "GET")
        self.assertEqual(sent.full_url, "https://buildooor.com/api/mmdx/diagrams")
        self.assertEqual(headers["authorization"], "Bearer access_123")
        self.assertEqual(headers["origin"], "https://buildooor.com")
        self.assertIn("id", stdout.getvalue())
        self.assertIn("slug", stdout.getvalue())
        self.assertIn("diag_1", stdout.getvalue())
        self.assertIn("architecture-overview", stdout.getvalue())
        self.assertIn("private", stdout.getvalue())

    def test_list_json_emits_raw_owner_payload(self) -> None:
        stdout = StringIO()
        payload = {
            "profile": {"username": "operator"},
            "items": [
                {
                    "id": "diag_1",
                    "chart_slug": "architecture-overview",
                    "title": "Architecture overview",
                    "visibility": "private",
                    "updated_at": "2026-05-28T05:00:00Z",
                }
            ],
        }

        with patch.object(mmd.request, "urlopen", return_value=FakeHTTPResponse(payload)):
            with redirect_stdout(stdout):
                exit_code = mmd.main(["list", "--access-token", "access_123", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(mmd.json.loads(stdout.getvalue()), payload)

    def test_save_dry_run_create_prints_private_diagram_payload_without_token_leak(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmdx", delete=False) as handle:
            handle.write(
                """<!-- mmdx
{"entry":"main","links":[]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Local] --> B[Private]
```
"""
            )
            path = handle.name
        stdout = StringIO()

        try:
            with patch.object(mmd.request, "urlopen") as urlopen:
                with redirect_stdout(stdout):
                    exit_code = mmd.main(
                        [
                            "save",
                            path,
                            "--title",
                            "Private proof",
                            "--chart-slug",
                            "private-proof",
                            "--access-token",
                            "secret-token",
                            "--dry-run",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        body = mmd.json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()
        self.assertEqual(body["operation"], "create")
        self.assertEqual(body["endpoint"], "https://buildooor.com/api/mmdx/diagrams")
        self.assertEqual(body["headers"]["Authorization"], "Bearer <redacted>")
        self.assertEqual(body["payload"]["title"], "Private proof")
        self.assertEqual(body["payload"]["chart_slug"], "private-proof")
        self.assertEqual(body["payload"]["entry_chart_id"], "main")
        self.assertIn("mmdx_text", body["payload"])
        self.assertNotIn("secret-token", stdout.getvalue())

    def test_save_dry_run_summary_omits_full_source_text(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()

        try:
            with patch.object(mmd.request, "urlopen") as urlopen:
                with redirect_stdout(stdout):
                    exit_code = mmd.main(
                        [
                            "save",
                            path,
                            "--title",
                            "Private proof",
                            "--dry-run",
                            "--summary",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        body = mmd.json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()
        self.assertNotIn("payload", body)
        self.assertEqual(body["payload_summary"]["mmdx_text"], "<omitted>")
        self.assertEqual(body["payload_summary"]["mmdx_text_bytes"], len("flowchart TD\n  A --> B\n".encode("utf-8")))
        self.assertEqual(body["payload_summary"]["mmdx_text_sha256"], body["source_sha256"])

    def test_save_create_posts_and_verifies_latest_source(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stdout = StringIO()
        captured: list[request.Request] = []

        def fake_urlopen(req, timeout=0):
            captured.append(req)
            if req.get_method() == "POST":
                self.assertEqual(req.full_url, "https://buildooor.com/api/mmdx/diagrams")
                return FakeHTTPResponse(
                    {
                        "diagram": {"id": "diag_1", "latest_version_id": "version_1"},
                        "version": {"id": "version_1", "diagram_id": "diag_1"},
                        "nav": {"latest_version_id": "version_1"},
                    }
                )
            self.assertEqual(req.full_url, "https://buildooor.com/api/mmdx/diagrams/diag_1/latest")
            return FakeHTTPResponse(
                {
                    "diagram": {"id": "diag_1", "latest_version_id": "version_1"},
                    "version": {"id": "version_1", "diagram_id": "diag_1", "mmdx_text": "flowchart TD\n  A --> B\n"},
                    "nav": {"latest_version_id": "version_1"},
                }
            )

        try:
            with patch.object(mmd.request, "urlopen", side_effect=fake_urlopen):
                with redirect_stdout(stdout):
                    exit_code = mmd.main(
                        [
                            "save",
                            path,
                            "--title",
                            "Created from agent",
                            "--access-token",
                            "access_123",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 0)
        self.assertEqual([req.get_method() for req in captured], ["POST", "GET"])
        post_headers = {key.lower(): value for key, value in captured[0].header_items()}
        self.assertEqual(post_headers["authorization"], "Bearer access_123")
        self.assertEqual(post_headers["origin"], "https://buildooor.com")
        self.assertIn("Saved durable MMDX diagram diag_1", stdout.getvalue())
        self.assertIn("latest_verification=OK", stdout.getvalue())

    def test_save_append_resolves_latest_when_base_version_missing(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> C\n")
            path = handle.name
        captured_payloads: list[dict[str, object]] = []

        def fake_urlopen(req, timeout=0):
            if req.get_method() == "GET" and req.full_url.endswith("/latest"):
                return FakeHTTPResponse(
                    {
                        "diagram": {"id": "diag_1", "latest_version_id": "version_before"},
                        "version": {"id": "version_before", "diagram_id": "diag_1", "mmdx_text": "flowchart TD\n  A --> C\n"},
                        "nav": {"latest_version_id": "version_before", "current_version_id": "version_before"},
                    }
                )
            self.assertEqual(req.full_url, "https://buildooor.com/api/mmdx/diagrams/diag_1/versions")
            payload = mmd.json.loads(req.data.decode("utf-8"))
            captured_payloads.append(payload)
            return FakeHTTPResponse(
                {
                    "diagram": {"id": "diag_1", "latest_version_id": "version_after"},
                    "version": {"id": "version_after", "diagram_id": "diag_1"},
                    "nav": {"latest_version_id": "version_after"},
                }
            )

        try:
            with patch.object(mmd.request, "urlopen", side_effect=fake_urlopen):
                with redirect_stdout(StringIO()):
                    exit_code = mmd.main(
                        [
                            "save",
                            path,
                            "--diagram-id",
                            "diag_1",
                            "--save-note",
                            "agent update",
                            "--access-token",
                            "access_123",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured_payloads[0]["base_version_id"], "version_before")
        self.assertEqual(captured_payloads[0]["parent_version_id"], "version_before")
        self.assertEqual(captured_payloads[0]["save_note"], "agent update")
        self.assertEqual(captured_payloads[0]["mmdx_text"], "flowchart TD\n  A --> C\n")

    def test_save_requires_token_before_mutation(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stderr = StringIO()

        try:
            with patch.dict(mmd.os.environ, {}, clear=True):
                with patch.object(mmd.request, "urlopen") as urlopen:
                    with redirect_stderr(stderr):
                        exit_code = mmd.main(["save", path, "--title", "No token", "--no-preflight"])
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 1)
        urlopen.assert_not_called()
        self.assertIn("save requires --access-token", stderr.getvalue())

    def test_publish_link_rejects_non_https_api_base_before_sending_token(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stderr = StringIO()

        try:
            with patch.object(mmd.request, "urlopen") as urlopen:
                with redirect_stderr(stderr):
                    exit_code = mmd.main(
                        [
                            "publish-link",
                            path,
                            "--username",
                            "operator",
                            "--slug",
                            "abc123",
                            "--api-base-url",
                            "http://api.example.test/api/app-links",
                            "--access-token",
                            "access_123",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 1)
        urlopen.assert_not_called()
        self.assertIn("API base URL must be https", stderr.getvalue())

    def test_publish_link_allows_localhost_http_api_base(self) -> None:
        mmd.require_secure_publish_api_base_url("http://localhost:3000/api/app-links")
        mmd.require_secure_publish_api_base_url("http://127.0.0.1:3000/api/app-links")

    def test_publish_link_fails_on_live_fragment_mismatch(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False) as handle:
            handle.write("flowchart TD\n  A --> B\n")
            path = handle.name
        stderr = StringIO()

        def fake_urlopen(req, timeout=0):
            if isinstance(req, request.Request) and req.get_method() == "PATCH":
                return FakeHTTPResponse({"success": True, "data": {"username": "operator", "slug": "abc123"}})
            next_data = {"props": {"pageProps": {"initialDiagramFragment": mmd.encode_state(mmd.build_state("flowchart TD\n  X --> Y\n"))}}}
            return FakeHTTPResponse(
                f'<script id="__NEXT_DATA__" type="application/json">{mmd.json.dumps(next_data)}</script>'
            )

        try:
            with patch.object(mmd.request, "urlopen", side_effect=fake_urlopen):
                with redirect_stderr(stderr):
                    exit_code = mmd.main(
                        [
                            "publish-link",
                            path,
                            "--username",
                            "operator",
                            "--slug",
                            "abc123",
                            "--access-token",
                            "access_123",
                            "--no-preflight",
                        ]
                    )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(exit_code, 1)
        self.assertIn("live initialDiagramFragment does not match local source", stderr.getvalue())

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
        self.assertIn("missing .mmd/.mmdx path", stderr.getvalue())

    def test_main_help_lists_subcommands(self) -> None:
        stdout = StringIO()

        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(stdout):
                mmd.parse_args(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Subcommands: save", stdout.getvalue())
        self.assertIn("publish-link", stdout.getvalue())

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

    def test_main_adds_source_metadata_for_mmdx_tmux_input(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmdx", delete=False) as handle:
            handle.write(
                """<!-- mmdx
{"entry":"main","links":[{"from":"main","label":"Open detail","to":"detail"}]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Open detail] --> B[Next]
```

## chart detail Detail Chart
```mermaid
flowchart TD
  C[Detail] --> D[Done]
```
"""
            )
            path = handle.name
        stdout = StringIO()
        handoff = {
            "version": 1,
            "endpoint": "http://127.0.0.1:49152/send",
            "token": "secret-token",
            "tmuxTarget": "%12",
            "mmdCommand": "python3 '/opt/mmd/scripts/mmd.py'",
            "sourceEditable": True,
        }

        try:
            with patch.object(mmd, "start_handoff_channel", return_value=handoff) as start_handoff:
                with redirect_stdout(stdout):
                    exit_code = mmd.main([path, "--fragment-only", "--tmux", "--no-preflight"])
        finally:
            Path(path).unlink(missing_ok=True)

        decoded = mmd.decode_state(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        self.assertEqual(decoded["buildooorHandoff"], handoff)
        self.assertEqual(decoded["buildooorSource"]["path"], str(Path(path).resolve()))
        self.assertEqual(start_handoff.call_args.kwargs["source_path"], str(Path(path).resolve()))

    def test_handoff_default_ttl_is_short_lived(self) -> None:
        self.assertEqual(mmd.DEFAULT_HANDOFF_TTL_SECONDS, 10 * 60)

    def test_handoff_origin_defaults_to_output_url_origin(self) -> None:
        self.assertEqual(
            mmd.resolve_handoff_origin(
                explicit_origin=None,
                output_base_url="http://localhost:3000/diagrams",
            ),
            "http://localhost:3000",
        )
        self.assertEqual(
            mmd.resolve_handoff_origin(
                explicit_origin=" https://preview.example/diagrams ",
                output_base_url="https://buildooor.com/diagrams",
            ),
            "https://preview.example",
        )

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
                allowed_origin="https://buildooor.com",
            )

        self.assertEqual(handoff["mmdCommand"], f"/usr/bin/python3 {mmd.shlex.quote(str(Path(mmd.__file__).resolve()))}")
        self.assertTrue(handoff["sourceEditable"])
        self.assertTrue(handoff["submitOnSend"])
        popen.assert_called_once()
        popen_args = popen.call_args.args[0]
        self.assertIn("--handoff-origin", popen_args)
        self.assertIn("https://buildooor.com", popen_args)

    def test_start_handoff_channel_passes_paid_resource_config_without_leaking_key(self) -> None:
        with (
            patch.object(mmd, "resolve_tmux_target", return_value="%12"),
            patch.object(mmd, "describe_tmux_target", return_value="work:1.2"),
            patch.object(mmd.secrets, "token_urlsafe", return_value="secret-token"),
            patch.object(mmd, "find_available_port", return_value=49152),
            patch.object(mmd, "wait_for_handoff_server"),
            patch.object(mmd.subprocess, "Popen") as popen,
        ):
            handoff = mmd.start_handoff_channel(
                host="127.0.0.1",
                tmux_target=None,
                ttl_seconds=60,
                source_path=None,
                submit_on_send=False,
                allowed_origin="https://buildooor.com",
                paid_resource={
                    "verify_url": "https://spaps.example/api/x402/handoff/verify",
                    "api_key": "pk_test",
                    "resource_key": "handoff-send",
                    "action_key": "handoff-send",
                    "target": "mmdx-send",
                },
            )

        popen_args = popen.call_args.args[0]
        self.assertTrue(handoff["paidAuthorizationRequired"])
        self.assertNotIn("pk_test", str(handoff))
        self.assertIn("--paid-resource-verify-url", popen_args)
        self.assertIn("--paid-resource-resource-key", popen_args)
        self.assertIn("--paid-resource-action-key", popen_args)
        self.assertIn("handoff-send", popen_args)
        self.assertNotIn("--paid-resource-api-key", popen_args)
        self.assertNotIn("pk_test", popen_args)
        self.assertEqual(popen.call_args.kwargs["env"]["SPAPS_API_KEY"], "pk_test")
        self.assertIn("--paid-resource-target", popen_args)
        self.assertIn("mmdx-send", popen_args)

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

    def test_paid_handoff_requires_authorization_before_tmux(self) -> None:
        with patch.object(mmd, "send_prompt_to_tmux") as send_prompt:
            status, body = post_handoff_json(
                {"token": "secret-token", "prompt": "hello"},
                paid_resource={
                    "verify_url": "https://spaps.example/api/x402/handoff/verify",
                    "api_key": "pk_test",
                    "target": "mmdx-send",
                },
            )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "x402_handoff_authorization_required")
        send_prompt.assert_not_called()

    def test_paid_handoff_verifies_authorization_with_configured_target(self) -> None:
        paid_resource = {
            "verify_url": "https://spaps.example/api/x402/handoff/verify",
            "api_key": "pk_test",
            "resource_key": "handoff-send",
            "action_key": "handoff-send",
            "target": "mmdx-send",
        }
        with (
            patch.object(
                mmd,
                "verify_spaps_authorization",
                return_value={
                    "valid": True,
                    "resource_key": "handoff-send",
                    "action_key": "handoff-send",
                    "target": "mmdx-send",
                },
            ) as verify,
            patch.object(mmd, "send_prompt_to_tmux") as send_prompt,
        ):
            status, body = post_handoff_json(
                {
                    "token": "secret-token",
                    "prompt": "hello",
                    "authorization_token": "opaque-handoff-token",
                },
                paid_resource=paid_resource,
            )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        verify.assert_called_once_with(
            paid_resource["verify_url"],
            paid_resource["api_key"],
            "opaque-handoff-token",
            resource_key="handoff-send",
            action_key="handoff-send",
            target="mmdx-send",
            bridge_token="secret-token",
        )
        send_prompt.assert_called_once_with("%12", "hello", submit=False)

    def test_paid_handoff_ignores_payload_target_override(self) -> None:
        paid_resource = {
            "verify_url": "https://spaps.example/api/x402/handoff/verify",
            "api_key": "pk_test",
            "resource_key": "handoff-send",
            "action_key": "handoff-send",
            "target": "mmdx-send",
        }
        with (
            patch.object(
                mmd,
                "verify_spaps_authorization",
                return_value={
                    "valid": True,
                    "resource_key": "handoff-send",
                    "action_key": "handoff-send",
                    "target": "mmdx-send",
                },
            ) as verify,
            patch.object(mmd, "send_prompt_to_tmux"),
        ):
            status, body = post_handoff_json(
                {
                    "token": "secret-token",
                    "prompt": "hello",
                    "authorization_token": "opaque-handoff-token",
                    "target": "custom-target",
                },
                paid_resource=paid_resource,
            )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(verify.call_args.kwargs["resource_key"], "handoff-send")
        self.assertEqual(verify.call_args.kwargs["action_key"], "handoff-send")
        self.assertEqual(verify.call_args.kwargs["target"], "mmdx-send")
        self.assertEqual(verify.call_args.kwargs["bridge_token"], "secret-token")

    def test_paid_handoff_rejects_authorization_for_other_resource(self) -> None:
        paid_resource = {
            "verify_url": "https://spaps.example/api/x402/handoff/verify",
            "api_key": "pk_test",
            "resource_key": "handoff-send",
            "action_key": "handoff-send",
            "target": "mmdx-send",
        }
        with (
            patch.object(
                mmd,
                "verify_spaps_authorization",
                return_value={
                    "valid": True,
                    "resource_key": "other-resource",
                    "action_key": "handoff-send",
                    "target": "mmdx-send",
                },
            ),
            patch.object(mmd, "send_prompt_to_tmux") as send_prompt,
        ):
            status, body = post_handoff_json(
                {
                    "token": "secret-token",
                    "prompt": "hello",
                    "authorization_token": "opaque-handoff-token",
                },
                paid_resource=paid_resource,
            )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "x402_handoff_authorization_required")
        send_prompt.assert_not_called()

    def test_paid_handoff_rejects_authorization_for_other_action(self) -> None:
        paid_resource = {
            "verify_url": "https://spaps.example/api/x402/handoff/verify",
            "api_key": "pk_test",
            "resource_key": "handoff-send",
            "action_key": "handoff-send",
            "target": "mmdx-send",
        }
        with (
            patch.object(
                mmd,
                "verify_spaps_authorization",
                return_value={
                    "valid": True,
                    "resource_key": "handoff-send",
                    "action_key": "other-action",
                    "target": "mmdx-send",
                },
            ),
            patch.object(mmd, "send_prompt_to_tmux") as send_prompt,
        ):
            status, body = post_handoff_json(
                {
                    "token": "secret-token",
                    "prompt": "hello",
                    "authorization_token": "opaque-handoff-token",
                },
                paid_resource=paid_resource,
            )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "x402_handoff_authorization_required")
        send_prompt.assert_not_called()

    def test_paid_handoff_rejects_authorization_for_other_target(self) -> None:
        paid_resource = {
            "verify_url": "https://spaps.example/api/x402/handoff/verify",
            "api_key": "pk_test",
            "resource_key": "handoff-send",
            "action_key": "handoff-send",
            "target": "mmdx-send",
        }
        with (
            patch.object(
                mmd,
                "verify_spaps_authorization",
                return_value={
                    "valid": True,
                    "resource_key": "handoff-send",
                    "action_key": "handoff-send",
                    "target": "other-target",
                },
            ),
            patch.object(mmd, "send_prompt_to_tmux") as send_prompt,
        ):
            status, body = post_handoff_json(
                {
                    "token": "secret-token",
                    "prompt": "hello",
                    "authorization_token": "opaque-handoff-token",
                },
                paid_resource=paid_resource,
            )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "x402_handoff_authorization_required")
        send_prompt.assert_not_called()

    def test_paid_handoff_requires_configured_target(self) -> None:
        paid_resource = {
            "verify_url": "https://spaps.example/api/x402/handoff/verify",
            "api_key": "pk_test",
            "resource_key": "handoff-send",
            "action_key": "handoff-send",
        }
        with (
            patch.object(mmd, "verify_spaps_authorization") as verify,
            patch.object(mmd, "send_prompt_to_tmux") as send_prompt,
        ):
            status, body = post_handoff_json(
                {
                    "token": "secret-token",
                    "prompt": "hello",
                    "authorization_token": "opaque-handoff-token",
                },
                paid_resource=paid_resource,
            )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "x402_handoff_authorization_required")
        verify.assert_not_called()
        send_prompt.assert_not_called()

    def test_verify_spaps_authorization_unwraps_response_envelope(self) -> None:
        class FakeResponse:
            def __enter__(self):
                self.status = 200
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return mmd.json.dumps(
                    {
                        "success": True,
                        "data": {
                            "valid": True,
                            "receipt_id": "rcpt_123",
                            "entitlement_id": None,
                            "resource_key": "handoff-send",
                            "action_key": "handoff-send",
                        },
                    }
                ).encode("utf-8")

        with patch.object(mmd.request, "urlopen", return_value=FakeResponse()) as urlopen:
            result = mmd.verify_spaps_authorization(
                "https://spaps.example/api/x402/handoff/verify",
                "pk_test",
                "opaque-handoff-token",
                resource_key="handoff-send",
                action_key="handoff-send",
                target="mmdx-send",
                bridge_token="local-bridge-token",
            )

        sent = mmd.json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(result["valid"], True)
        self.assertEqual(sent["token"], "opaque-handoff-token")
        self.assertEqual(sent["resource_key"], "handoff-send")
        self.assertEqual(sent["action_key"], "handoff-send")
        self.assertEqual(sent["target"], "mmdx-send")
        self.assertEqual(sent["bridge_token"], "local-bridge-token")

    def test_handoff_post_rejects_bad_token(self) -> None:
        status, body = post_handoff_json({"token": "wrong", "prompt": "hello"})

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "handoff token mismatch")

    def test_handoff_post_rejects_wrong_origin_before_token(self) -> None:
        status, body = post_handoff_json(
            {"token": "secret-token", "prompt": "hello"},
            origin="https://evil.example",
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "handoff origin mismatch")

    def test_handoff_post_rejects_missing_origin(self) -> None:
        status, body = post_handoff_json(
            {"token": "secret-token", "prompt": "hello"},
            origin=None,
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "missing Origin header")

    def test_handoff_preflight_pins_allowed_origin(self) -> None:
        status, headers, body = options_handoff_response(origin="https://buildooor.com")

        self.assertEqual(status, 204)
        self.assertEqual(body, "")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "https://buildooor.com")
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")

    def test_handoff_preflight_rejects_wrong_origin(self) -> None:
        status, headers, body = options_handoff_response(origin="https://evil.example")

        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(mmd.json.loads(body)["error"], "handoff origin mismatch")

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
        preflight.assert_called_once_with("flowchart TD\n  A --> C\n", auto_install=True)

    def test_handoff_source_preflight_validates_mmdx_stack(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mmdx", delete=False) as handle:
            handle.write(
                """<!-- mmdx
{"entry":"main","links":[{"from":"main","label":"Open detail","to":"detail"}]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Open detail] --> B[Next]
```

## chart detail Detail Chart
```mermaid
flowchart TD
  C[Detail] --> D[Done]
```
"""
            )
            path = handle.name

        try:
            with patch.object(mmd, "preflight_mermaid", return_value={"diagramType": "flowchart-v2"}) as preflight:
                status, body = post_handoff_json(
                    {"token": "secret-token"},
                    path="/source/preflight",
                    source_path=path,
                )
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(status, 200)
        self.assertEqual(body["preflight"]["kind"], "mmdx")
        self.assertEqual(body["preflight"]["entry"], "main")
        self.assertEqual(body["preflight"]["chartCount"], 2)
        self.assertEqual(len(body["preflight"]["charts"]), 2)
        self.assertEqual(preflight.call_count, 2)

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

    def test_handoff_source_write_validates_mmdx_before_saving(self) -> None:
        original = """<!-- mmdx
{"entry":"main","links":[]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Old] --> B[Next]
```
"""
        updated = """<!-- mmdx
{"entry":"main","links":[{"from":"main","label":"Open detail","to":"detail"}]}
-->
## chart main Main Chart
```mermaid
flowchart TD
  A[Open detail] --> B[Next]
```

## chart detail Detail Chart
```mermaid
flowchart TD
  C[Detail] --> D[Done]
```
"""
        with tempfile.NamedTemporaryFile("w", suffix=".mmdx", delete=False) as handle:
            handle.write(original)
            path = handle.name

        try:
            with patch.object(mmd, "preflight_mermaid", return_value={"diagramType": "flowchart-v2"}) as preflight:
                status, body = post_handoff_json(
                    {"token": "secret-token", "code": updated},
                    path="/source/write",
                    source_path=path,
                )
            saved = Path(path).read_text(encoding="utf-8")
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(status, 200)
        self.assertEqual(body["preflight"]["kind"], "mmdx")
        self.assertEqual(body["preflight"]["chartCount"], 2)
        self.assertEqual(preflight.call_count, 2)
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

    def test_paid_resource_public_state_strips_private_fields(self) -> None:
        state = mmd.build_state(
            "flowchart TD\n  A --> B\n",
            paid_resource={
                "resource_key": "devnet-smoke-handoff",
                "action_key": "handoff-send",
                "target": "mmdx-send",
                "verify_url": "https://spaps.example/api/x402/handoff/verify",
                "api_key": "spaps_sec_leak",
                "bridge_token": "local-bridge-token",
                "bridgeToken": "local-bridge-token",
            },
        )

        paid_state = state["buildooorPaidResource"]
        self.assertEqual(paid_state["resource_key"], "devnet-smoke-handoff")
        self.assertEqual(paid_state["action_key"], "handoff-send")
        self.assertNotIn("target", paid_state)
        self.assertNotIn("verify_url", paid_state)
        self.assertNotIn("api_key", paid_state)
        self.assertNotIn("bridge_token", paid_state)
        self.assertNotIn("bridgeToken", paid_state)

    def test_ambient_spaps_api_key_does_not_enable_paid_handoff(self) -> None:
        args = mmd.parse_args(["diagram.mmd"])

        with patch.dict(mmd.os.environ, {"SPAPS_API_KEY": "spaps_sec_ambient"}, clear=True):
            self.assertIsNone(mmd._resolve_paid_resource(args))

    def test_resolve_paid_resource_uses_metadata_with_environment_defaults(self) -> None:
        args = mmd.parse_args(
            [
                "diagram.mmd",
                "--paid-resource",
                mmd.json.dumps(
                    {
                        "resourceKey": "metadata-resource",
                        "actionKey": "metadata-action",
                        "target": "metadata-target",
                    }
                ),
            ]
        )

        with patch.dict(
            mmd.os.environ,
            {
                "SPAPS_HANDOFF_VERIFY_URL": "https://spaps.example/handoff/verify",
                "SPAPS_API_KEY": "pk_env",
            },
            clear=True,
        ):
            paid_resource = mmd._resolve_paid_resource(args)

        self.assertEqual(
            paid_resource,
            {
                "verify_url": "https://spaps.example/handoff/verify",
                "api" + "_key": "pk_env",
                "resource_key": "metadata-resource",
                "action_key": "metadata-action",
                "target": "metadata-target",
            },
        )

    def test_resolve_paid_resource_prefers_cli_flags_over_env_and_metadata(self) -> None:
        args = mmd.parse_args(
            [
                "diagram.mmd",
                "--paid-resource",
                mmd.json.dumps(
                    {
                        "resource_key": "metadata-resource",
                        "action_key": "metadata-action",
                        "target": "metadata-target",
                    }
                ),
                "--paid-resource-verify-url",
                "https://cli.example/handoff/verify",
                "--paid-resource-api" + "-key",
                "pk_cli",
                "--paid-resource-resource-key",
                "cli-resource",
                "--paid-resource-action-key",
                "cli-action",
                "--paid-resource-target",
                "cli-target",
            ]
        )

        with patch.dict(
            mmd.os.environ,
            {
                "SPAPS_HANDOFF_VERIFY_URL": "https://env.example/handoff/verify",
                "SPAPS_API_KEY": "pk_env",
                "SPAPS_HANDOFF_RESOURCE_KEY": "env-resource",
                "SPAPS_HANDOFF_ACTION_KEY": "env-action",
                "SPAPS_HANDOFF_TARGET": "env-target",
            },
            clear=True,
        ):
            paid_resource = mmd._resolve_paid_resource(args)

        self.assertEqual(
            paid_resource,
            {
                "verify_url": "https://cli.example/handoff/verify",
                "api" + "_key": "pk_cli",
                "resource_key": "cli-resource",
                "action_key": "cli-action",
                "target": "cli-target",
            },
        )

    def test_resolve_paid_resource_reports_missing_required_fields(self) -> None:
        cases = [
            (
                ["diagram.mmd", "--paid-resource-resource-key", "resource", "--paid-resource-action-key", "action"],
                "requires both a verify URL",
            ),
            (
                [
                    "diagram.mmd",
                    "--paid-resource-verify-url",
                    "https://spaps.example/handoff/verify",
                    "--paid-resource-api" + "-key",
                    "pk_cli",
                    "--paid-resource-target",
                    "target",
                ],
                "requires resource and action keys",
            ),
            (
                [
                    "diagram.mmd",
                    "--paid-resource-verify-url",
                    "https://spaps.example/handoff/verify",
                    "--paid-resource-api" + "-key",
                    "pk_cli",
                    "--paid-resource-resource-key",
                    "resource",
                    "--paid-resource-action-key",
                    "action",
                ],
                "requires a target",
            ),
            (
                ["diagram.mmd", "--paid-resource", "[]"],
                "--paid-resource must be a JSON object",
            ),
        ]

        with patch.dict(mmd.os.environ, {}, clear=True):
            for argv, message in cases:
                with self.subTest(argv=argv):
                    args = mmd.parse_args(argv)
                    with self.assertRaisesRegex(ValueError, message):
                        mmd._resolve_paid_resource(args)

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

class ResponseErrorMessageTests(unittest.TestCase):
    def test_extracts_message_from_error_dict(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": {"message": "rate limited"}}, "fallback"),
            "rate limited",
        )

    def test_extracts_code_from_error_dict(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": {"code": "RATE_LIMIT"}}, "fallback"),
            "RATE_LIMIT",
        )

    def test_extracts_error_string(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": "something broke"}, "fallback"),
            "something broke",
        )

    def test_extracts_top_level_message(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"message": "top level"}, "fallback"),
            "top level",
        )

    def test_returns_fallback_for_empty_payload(self) -> None:
        self.assertEqual(
            mmd.response_error_message({}, "fallback"),
            "fallback",
        )

    def test_returns_fallback_for_blank_strings(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": "  ", "message": "  "}, "fallback"),
            "fallback",
        )

    def test_strips_whitespace(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": "  oops  "}, "fallback"),
            "oops",
        )

    def test_prefers_error_dict_over_top_level_message(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": {"message": "inner"}, "message": "outer"}, "fallback"),
            "inner",
        )

    def test_error_dict_with_empty_message_falls_through(self) -> None:
        self.assertEqual(
            mmd.response_error_message({"error": {"message": ""}, "message": "outer"}, "fallback"),
            "outer",
        )


def post_handoff_json(
    payload: dict[str, object],
    *,
    path: str = "/send",
    source_path: str | None = None,
    submit_on_send: bool = False,
    origin: str | None = "https://buildooor.com",
    paid_resource: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    status, _headers, body = post_handoff_json_response(
        payload,
        path=path,
        source_path=source_path,
        submit_on_send=submit_on_send,
        origin=origin,
        paid_resource=paid_resource,
    )
    return status, body


def post_handoff_json_response(
    payload: dict[str, object],
    *,
    path: str = "/send",
    source_path: str | None = None,
    submit_on_send: bool = False,
    origin: str | None = "https://buildooor.com",
    paid_resource: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, object]]:
    server = mmd.HandoffHTTPServer(("127.0.0.1", 0), mmd.HandoffRequestHandler)
    server.token = "secret-token"
    server.tmux_target = "%12"
    server.source_path = source_path
    server.submit_on_send = submit_on_send
    server.expires_at = time.time() + 10
    server.allowed_origin = "https://buildooor.com"
    server.paid_resource = paid_resource
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}{path}"
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        req = request.Request(
            endpoint,
            data=mmd.json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=2) as response:
                return response.status, dict(response.headers), mmd.json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            return exc.code, dict(exc.headers), mmd.json.loads(exc.read().decode("utf-8"))
    finally:
        thread.join(timeout=2)
        server.server_close()


def options_handoff_response(
    *,
    origin: str | None = "https://buildooor.com",
) -> tuple[int, dict[str, str], str]:
    server = mmd.HandoffHTTPServer(("127.0.0.1", 0), mmd.HandoffRequestHandler)
    server.token = "secret-token"
    server.tmux_target = "%12"
    server.source_path = None
    server.submit_on_send = False
    server.expires_at = time.time() + 10
    server.allowed_origin = "https://buildooor.com"
    server.paid_resource = None
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/send"
        headers = {}
        if origin is not None:
            headers["Origin"] = origin
            headers["Access-Control-Request-Private-Network"] = "true"
        req = request.Request(endpoint, headers=headers, method="OPTIONS")
        try:
            with request.urlopen(req, timeout=2) as response:
                return response.status, dict(response.headers), response.read().decode("utf-8")
        except error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read().decode("utf-8")
    finally:
        thread.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    unittest.main()
