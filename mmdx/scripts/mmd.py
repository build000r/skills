#!/usr/bin/env python3
"""Generate and inspect Mermaid pako URLs."""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import urlparse


DEFAULT_BASE_URL = "https://buildooor.com/diagrams"
DEFAULT_VIEW_URL = "https://buildooor.com/diagrams"
SCRIPT_DIR = Path(__file__).resolve().parent
PARSER_SCRIPT = SCRIPT_DIR / "validate_mermaid.mjs"
PARSER_PACKAGE = SCRIPT_DIR / "package.json"
PARSER_MODULE = SCRIPT_DIR / "node_modules" / "mermaid"
DEFAULT_HANDOFF_HOST = "127.0.0.1"
DEFAULT_HANDOFF_TTL_SECONDS = 10 * 60
MAX_HANDOFF_BODY_BYTES = 512 * 1024


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).expanduser().read_text(encoding="utf-8")


def _load_config(value: str | None, theme: str) -> str:
    if value is None:
        config: Any = {"theme": theme}
    else:
        maybe_path = Path(value).expanduser()
        if maybe_path.exists():
            config = json.loads(maybe_path.read_text(encoding="utf-8"))
        else:
            config = json.loads(value)
    return json.dumps(config, indent=2, ensure_ascii=False)


def build_state(
    code: str,
    *,
    config: str | None = None,
    theme: str = "default",
    grid: bool = True,
    pan_zoom: bool = True,
    rough: bool = False,
    update_diagram: bool = True,
    handoff: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    mmdx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = {
        "code": code,
        "grid": grid,
        "mermaid": _load_config(config, theme),
        "panZoom": pan_zoom,
        "rough": rough,
        "updateDiagram": update_diagram,
    }
    if handoff is not None:
        state["buildooorHandoff"] = handoff
    if source is not None:
        state["buildooorSource"] = source
    if mmdx is not None:
        state["buildooorMmdx"] = mmdx
    return state


def build_source_metadata(path: str) -> dict[str, Any] | None:
    if path == "-":
        return None

    source_path = Path(path).expanduser()
    return {
        "version": 1,
        "kind": "file",
        "path": str(source_path.resolve(strict=False)),
        "cwd": str(Path.cwd()),
    }


def is_mmdx_input(path: str, code: str) -> bool:
    return (path != "-" and Path(path).suffix.lower() == ".mmdx") or "<!-- mmdx" in code


def build_mmdx_document(markdown: str) -> dict[str, Any]:
    metadata = _parse_mmdx_metadata(markdown)
    charts = _parse_mmdx_charts(markdown)
    if not charts:
        raise ValueError("MMDX document must contain at least one '## chart <id>' Mermaid fence")

    chart_ids = {chart["id"] for chart in charts}
    entry = str(metadata.get("entry") or charts[0]["id"])
    if entry not in chart_ids:
        raise ValueError(f"MMDX entry chart {entry!r} was not found")

    links = []
    for item in metadata.get("links", []):
        if not isinstance(item, dict):
            raise ValueError("MMDX links must be objects")
        from_chart = str(item.get("from", "")).strip()
        label = str(item.get("label", "")).strip()
        to_chart = str(item.get("to", "")).strip()
        if not from_chart or not label or not to_chart:
            raise ValueError("MMDX links require from, label, and to")
        if from_chart not in chart_ids:
            raise ValueError(f"MMDX link source chart {from_chart!r} was not found")
        if to_chart not in chart_ids:
            raise ValueError(f"MMDX link target chart {to_chart!r} was not found")
        link = {
            "from": from_chart,
            "label": label,
            "to": to_chart,
        }
        if isinstance(item.get("title"), str) and item["title"].strip():
            link["title"] = item["title"].strip()
        links.append(link)

    return {
        "version": 1,
        "entry": entry,
        "charts": charts,
        "links": links,
    }


def get_mmdx_entry_code(document: dict[str, Any]) -> str:
    entry = document["entry"]
    for chart in document["charts"]:
        if chart["id"] == entry:
            return chart["code"]
    raise ValueError(f"MMDX entry chart {entry!r} was not found")


def preflight_mmdx_document(document: dict[str, Any], *, auto_install: bool = True) -> list[dict[str, Any]]:
    results = []
    for chart in document["charts"]:
        try:
            result = preflight_mermaid(chart["code"], auto_install=auto_install)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            raise ValueError(f"MMDX chart {chart['id']!r} failed Mermaid preflight: {exc}") from exc
        results.append({"id": chart["id"], **result})
    return results


def _parse_mmdx_metadata(markdown: str) -> dict[str, Any]:
    match = re.search(r"<!--\s*mmdx\s*(\{.*?\})\s*-->", markdown, flags=re.DOTALL)
    if not match:
        return {}
    metadata = json.loads(match.group(1))
    if not isinstance(metadata, dict):
        raise ValueError("MMDX metadata must be a JSON object")
    return metadata


def _parse_mmdx_charts(markdown: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"^##\s+chart\s+([A-Za-z0-9_-]+)(?:\s+(.+?))?\s*\n```mermaid\s*\n(.*?)\n```",
        flags=re.MULTILINE | re.DOTALL,
    )
    charts = []
    for match in pattern.finditer(markdown):
        chart = {
            "id": match.group(1),
            "code": match.group(3).rstrip() + "\n",
        }
        title = (match.group(2) or "").strip()
        if title:
            chart["title"] = title
        charts.append(chart)
    return charts


def build_mmd_command() -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))}"


def encode_state(state: dict[str, Any]) -> str:
    state_json = json.dumps(state, separators=(",", ":"), ensure_ascii=False)
    compressed = zlib.compress(state_json.encode("utf-8"), level=9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"pako:{encoded}"


def decode_state(fragment_or_url: str) -> dict[str, Any]:
    fragment = fragment_or_url.strip()
    if "#" in fragment:
        fragment = fragment.rsplit("#", 1)[1]
    if fragment.startswith("pako:"):
        payload = fragment.split(":", 1)[1]
        padded = payload + ("=" * (-len(payload) % 4))
        compressed = base64.urlsafe_b64decode(padded.encode("ascii"))
        state_json = zlib.decompress(compressed).decode("utf-8")
        return json.loads(state_json)
    if fragment.startswith("base64:"):
        payload = fragment.split(":", 1)[1]
        padded = payload + ("=" * (-len(payload) % 4))
        state_json = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        return json.loads(state_json)
    raise ValueError("expected a Mermaid Live fragment beginning with pako: or base64:")


def build_url(fragment: str, *, view: bool = False, base_url: str | None = None) -> str:
    if base_url is None:
        base_url = DEFAULT_VIEW_URL if view else DEFAULT_BASE_URL
    return f"{base_url}#{fragment}"


def resolve_output_base_url(*, view: bool = False, base_url: str | None = None) -> str:
    return base_url if base_url is not None else (DEFAULT_VIEW_URL if view else DEFAULT_BASE_URL)


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"expected an http(s) URL for handoff origin, got: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_handoff_origin(*, explicit_origin: str | None, output_base_url: str) -> str:
    return origin_from_url((explicit_origin or output_base_url).strip())


def open_with_applescript(url: str) -> None:
    script_path = Path(__file__).with_name("open_mermaid_live.applescript")
    if shutil.which("osascript"):
        subprocess.run(["osascript", str(script_path), url], check=True)
        return
    raise RuntimeError("osascript was not found; print the URL and open it manually")


class HandoffHTTPServer(http.server.ThreadingHTTPServer):
    token: str
    tmux_target: str
    source_path: str | None
    submit_on_send: bool
    expires_at: float
    allowed_origin: str


class HandoffRequestHandler(http.server.BaseHTTPRequestHandler):
    server: HandoffHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        if not self._require_handoff_origin():
            return
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/health":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        self._send_json(
            200,
            {
                "ok": True,
            },
        )

    def do_POST(self) -> None:
        if not self._require_handoff_origin():
            return
        if self.path == "/send":
            self._handle_send()
            return
        if self.path == "/source/read":
            self._handle_source_read()
            return
        if self.path == "/source/preflight":
            self._handle_source_preflight()
            return
        if self.path == "/source/write":
            self._handle_source_write()
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def _handle_send(self) -> None:
        payload = self._read_token_json_payload()
        if payload is None:
            return

        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self._send_json(400, {"ok": False, "error": "missing prompt"})
            return

        try:
            send_prompt_to_tmux(self.server.tmux_target, prompt, submit=self.server.submit_on_send)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            self._send_json(500, {"ok": False, "error": f"tmux handoff failed: {exc}"})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "tmuxTarget": self.server.tmux_target,
                "submitOnSend": self.server.submit_on_send,
            },
        )

    def _handle_source_read(self) -> None:
        payload = self._read_token_json_payload()
        if payload is None:
            return
        source_path = self._attached_source_path()
        if source_path is None:
            return

        try:
            code = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._send_json(500, {"ok": False, "error": f"source read failed: {exc}"})
            return

        self._send_json(200, {"ok": True, "path": str(source_path), "code": code})

    def _handle_source_preflight(self) -> None:
        payload = self._read_token_json_payload()
        if payload is None:
            return
        source_path = self._attached_source_path()
        if source_path is None:
            return

        code = payload.get("code")
        if code is None:
            try:
                code = source_path.read_text(encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"ok": False, "error": f"source read failed: {exc}"})
                return
        if not isinstance(code, str) or not code.strip():
            self._send_json(400, {"ok": False, "error": "missing source code"})
            return

        try:
            result = preflight_mermaid(code)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            self._send_json(422, {"ok": False, "error": str(exc)})
            return

        self._send_json(200, {"ok": True, "path": str(source_path), "preflight": result})

    def _handle_source_write(self) -> None:
        payload = self._read_token_json_payload()
        if payload is None:
            return
        source_path = self._attached_source_path()
        if source_path is None:
            return

        code = payload.get("code")
        if not isinstance(code, str) or not code.strip():
            self._send_json(400, {"ok": False, "error": "missing source code"})
            return

        try:
            result = preflight_mermaid(code)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            self._send_json(422, {"ok": False, "error": str(exc)})
            return

        try:
            source_path.write_text(code, encoding="utf-8")
        except OSError as exc:
            self._send_json(500, {"ok": False, "error": f"source write failed: {exc}"})
            return

        self._send_json(200, {"ok": True, "path": str(source_path), "preflight": result})

    def _read_token_json_payload(self) -> dict[str, Any] | None:
        if time.time() > self.server.expires_at:
            self._send_json(410, {"ok": False, "error": "handoff expired"})
            return None

        payload = self._read_json_payload()
        if payload is None:
            return None

        if payload.get("token") != self.server.token:
            self._send_json(403, {"ok": False, "error": "handoff token mismatch"})
            return None

        return payload

    def _read_json_payload(self) -> dict[str, Any] | None:
        if self.command != "POST":
            self._send_json(405, {"ok": False, "error": "method not allowed"})
            return None

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "invalid content length"})
            return None
        if content_length <= 0:
            self._send_json(400, {"ok": False, "error": "empty request body"})
            return None
        if content_length > MAX_HANDOFF_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "request body is too large"})
            return None

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return None
        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "error": "JSON body must be an object"})
            return None
        return payload

    def _attached_source_path(self) -> Path | None:
        if not self.server.source_path:
            self._send_json(404, {"ok": False, "error": "no source file is attached"})
            return None
        return Path(self.server.source_path)

    def _require_handoff_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            self._send_json(403, {"ok": False, "error": "missing Origin header"})
            return False
        if origin != self.server.allowed_origin:
            self._send_json(403, {"ok": False, "error": "handoff origin mismatch"})
            return False
        return True

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin == self.server.allowed_origin:
            self.send_header("Access-Control-Allow-Origin", self.server.allowed_origin)
        self.send_header("Vary", "Origin")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def send_prompt_to_tmux(target: str, prompt: str, *, submit: bool = False) -> None:
    if not shutil.which("tmux"):
        raise RuntimeError("tmux was not found")

    buffer_name = f"buildooor-diagram-{secrets.token_hex(4)}"
    fd, temp_path = tempfile.mkstemp(prefix="buildooor-diagram-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prompt)
        subprocess.run(["tmux", "load-buffer", "-b", buffer_name, temp_path], check=True)
        subprocess.run(["tmux", "paste-buffer", "-p", "-b", buffer_name, "-t", target], check=True)
        if submit:
            subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=True)
    finally:
        subprocess.run(["tmux", "delete-buffer", "-b", buffer_name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(temp_path).unlink(missing_ok=True)


def run_handoff_server(
    host: str,
    port: int,
    token: str,
    tmux_target: str,
    ttl_seconds: int,
    *,
    source_path: str | None,
    submit_on_send: bool,
    allowed_origin: str,
) -> int:
    server = HandoffHTTPServer((host, port), HandoffRequestHandler)
    server.token = token
    server.tmux_target = tmux_target
    server.source_path = source_path
    server.submit_on_send = submit_on_send
    server.expires_at = time.time() + ttl_seconds
    server.allowed_origin = allowed_origin
    server.timeout = 1

    while time.time() <= server.expires_at:
        server.handle_request()
    return 0


def find_available_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def resolve_tmux_target(explicit_target: str | None) -> str:
    if explicit_target:
        return explicit_target
    env_target = os.environ.get("TMUX_PANE")
    if env_target:
        return env_target
    if os.environ.get("TMUX"):
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{pane_id}"],
            capture_output=True,
            text=True,
            check=True,
        )
        target = result.stdout.strip()
        if target:
            return target
    raise RuntimeError("no tmux target found; run inside tmux or pass --tmux-target")


def describe_tmux_target(target: str) -> str:
    result = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target, "#S:#I.#P"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() or target


def wait_for_handoff_server(endpoint: str) -> None:
    health_url = endpoint.rsplit("/", 1)[0] + "/health"
    last_error: Exception | None = None
    for _ in range(20):
        try:
            with request.urlopen(health_url, timeout=0.2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - exact startup timing is platform-specific
            last_error = exc
            time.sleep(0.05)
    raise RuntimeError(f"handoff server did not start: {last_error}")


def start_handoff_channel(
    *,
    host: str,
    tmux_target: str | None,
    ttl_seconds: int,
    source_path: str | None,
    submit_on_send: bool,
    allowed_origin: str,
) -> dict[str, Any]:
    target = resolve_tmux_target(tmux_target)
    label = describe_tmux_target(target)
    token = secrets.token_urlsafe(24)
    port = find_available_port(host)
    endpoint = f"http://{host}:{port}/send"
    subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--handoff-server",
            "--handoff-host",
            host,
            "--handoff-port",
            str(port),
            "--handoff-token",
            token,
            "--tmux-target",
            target,
            "--handoff-ttl",
            str(ttl_seconds),
            "--handoff-origin",
            allowed_origin,
            *(["--source-path", source_path] if source_path else []),
            *(["--tmux-submit"] if submit_on_send else []),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    wait_for_handoff_server(endpoint)
    return {
        "version": 1,
        "endpoint": endpoint,
        "token": token,
        "tmuxTarget": target,
        "tmuxLabel": label,
        "mmdCommand": build_mmd_command(),
        "sourceEditable": source_path is not None,
        "submitOnSend": submit_on_send,
        "expiresAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + ttl_seconds)),
    }


def parser_dependencies_ready() -> bool:
    return PARSER_MODULE.exists()


def setup_parser_dependencies(*, auto_install: bool = True) -> None:
    if not shutil.which("node"):
        raise RuntimeError("node was not found; install Node.js or pass --no-preflight")
    if parser_dependencies_ready():
        return
    if not auto_install:
        raise RuntimeError(
            "Mermaid parser dependency is not installed; run "
            "`python3 mmd.py --setup-parser` or pass --no-preflight"
        )
    if not shutil.which("npm"):
        raise RuntimeError("npm was not found; install npm or pass --no-preflight")
    if not PARSER_PACKAGE.exists():
        raise RuntimeError(f"missing parser package manifest: {PARSER_PACKAGE}")
    subprocess.run(
        ["npm", "install", "--silent", "--no-audit", "--no-fund"],
        cwd=SCRIPT_DIR,
        check=True,
    )


def preflight_mermaid(code: str, *, auto_install: bool = True) -> dict[str, Any]:
    setup_parser_dependencies(auto_install=auto_install)
    result = subprocess.run(
        ["node", str(PARSER_SCRIPT)],
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Mermaid parser failed"
        raise ValueError(message)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Mermaid parser returned invalid JSON: {result.stdout}") from exc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate buildooor diagrams pako URLs from .mmd or .mmdx source files."
    )
    parser.add_argument("path", nargs="?", help="Mermaid .mmd/.mmdx file path, or '-' for stdin")
    parser.add_argument("--open", action="store_true", help="open the generated URL in a browser")
    parser.add_argument("--view", action="store_true", help="accepted for compatibility; buildooor diagrams uses one URL")
    parser.add_argument("--fragment-only", action="store_true", help="print only the pako: fragment")
    parser.add_argument("--base-url", help="override the base URL before the # fragment")
    parser.add_argument(
        "--tmux",
        "--tmux-handoff",
        dest="tmux_handoff",
        action="store_true",
        help="open with a local handoff channel so /diagrams can send the prompt back to tmux",
    )
    parser.add_argument("--tmux-target", help="tmux target pane for --tmux; defaults to the current pane")
    parser.add_argument(
        "--tmux-submit",
        action="store_true",
        help="with --tmux, press Enter in the target pane after pasting the edit packet",
    )
    parser.add_argument(
        "--handoff-host",
        default=DEFAULT_HANDOFF_HOST,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--handoff-ttl",
        type=int,
        default=DEFAULT_HANDOFF_TTL_SECONDS,
        help="seconds before a --tmux handoff channel expires",
    )
    parser.add_argument(
        "--handoff-origin",
        help="browser origin allowed to call the local handoff bridge; defaults to the output URL origin",
    )
    parser.add_argument("--handoff-server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--handoff-port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--handoff-token", help=argparse.SUPPRESS)
    parser.add_argument("--source-path", help=argparse.SUPPRESS)
    parser.add_argument("--theme", default="default", help="Mermaid config theme name")
    parser.add_argument("--config", help="Mermaid config JSON string or path to a JSON file")
    parser.add_argument("--rough", action="store_true", help="enable Mermaid Live rough rendering")
    parser.add_argument("--no-grid", action="store_true", help="disable the editor grid")
    parser.add_argument("--no-pan-zoom", action="store_true", help="disable pan/zoom")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate Mermaid syntax and exit without printing a URL",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="skip Mermaid parser validation before encoding",
    )
    parser.add_argument(
        "--no-parser-install",
        action="store_true",
        help="do not auto-install the parser dependency if missing",
    )
    parser.add_argument(
        "--setup-parser",
        action="store_true",
        help="install the bundled Mermaid parser dependency and exit",
    )
    parser.add_argument(
        "--decode",
        metavar="URL_OR_FRAGMENT",
        help="decode an existing Mermaid Live URL or pako:/base64: fragment to JSON",
    )
    parser.add_argument(
        "--code-only",
        action="store_true",
        help="with --decode, print only the decoded Mermaid source",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.handoff_server:
            if args.handoff_port is None or not args.handoff_token or not args.tmux_target:
                raise ValueError("--handoff-server requires --handoff-port, --handoff-token, and --tmux-target")
            allowed_origin = resolve_handoff_origin(
                explicit_origin=args.handoff_origin,
                output_base_url=DEFAULT_BASE_URL,
            )
            return run_handoff_server(
                args.handoff_host,
                args.handoff_port,
                args.handoff_token,
                args.tmux_target,
                args.handoff_ttl,
                source_path=args.source_path,
                submit_on_send=args.tmux_submit,
                allowed_origin=allowed_origin,
            )

        if args.setup_parser:
            setup_parser_dependencies(auto_install=True)
            print("Mermaid parser dependency is installed.")
            return 0

        if args.decode:
            state = decode_state(args.decode)
            if args.code_only:
                code = str(state.get("code", ""))
                print(code, end="" if code.endswith("\n") else "\n")
            else:
                print(json.dumps(state, indent=2, ensure_ascii=False))
            return 0

        if not args.path:
            raise ValueError("missing .mmd/.mmdx path; pass a file path, '-' for stdin, or --decode")

        code = _read_text(args.path)
        mmdx_document = build_mmdx_document(code) if is_mmdx_input(args.path, code) else None
        diagram_code = get_mmdx_entry_code(mmdx_document) if mmdx_document else code
        if not args.no_preflight:
            if mmdx_document:
                parse_results = preflight_mmdx_document(mmdx_document, auto_install=not args.no_parser_install)
            else:
                parse_results = [preflight_mermaid(code, auto_install=not args.no_parser_install)]
            if args.preflight_only:
                if mmdx_document:
                    print(f"MMDX preflight OK: {len(parse_results)} charts")
                else:
                    diagram_type = parse_results[0].get("diagramType", "unknown")
                    print(f"Mermaid preflight OK: {diagram_type}")
                return 0
        elif args.preflight_only:
            raise ValueError("--preflight-only cannot be combined with --no-preflight")

        handoff = None
        source_metadata = None
        output_base_url = resolve_output_base_url(view=args.view, base_url=args.base_url)
        if args.tmux_handoff:
            source_metadata = None if mmdx_document else build_source_metadata(args.path)
            allowed_origin = resolve_handoff_origin(
                explicit_origin=args.handoff_origin,
                output_base_url=output_base_url,
            )
            handoff = start_handoff_channel(
                host=args.handoff_host,
                tmux_target=args.tmux_target,
                ttl_seconds=args.handoff_ttl,
                source_path=source_metadata["path"] if source_metadata else None,
                submit_on_send=args.tmux_submit,
                allowed_origin=allowed_origin,
            )

        state = build_state(
            diagram_code,
            config=args.config,
            theme=args.theme,
            grid=not args.no_grid,
            pan_zoom=not args.no_pan_zoom,
            rough=args.rough,
            handoff=handoff,
            source=source_metadata,
            mmdx=mmdx_document,
        )
        fragment = encode_state(state)
        output = fragment if args.fragment_only else build_url(fragment, base_url=output_base_url)
        print(output)
        if args.open:
            open_with_applescript(output)
        return 0
    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
        zlib.error,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"mmd: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
