#!/usr/bin/env python3
"""Generate and inspect Mermaid pako URLs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
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
from typing import Any, Literal
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse


DEFAULT_BASE_URL = "https://buildooor.com/diagrams"
DEFAULT_VIEW_URL = "https://buildooor.com/diagrams"
DEFAULT_APP_LINKS_API_BASE_URL = "https://buildooor.com/api/app-links"
DEFAULT_MMDX_API_BASE_URL = "https://buildooor.com/api/mmdx"
DEFAULT_MMDX_SHORT_LINK_BASE_URL = "https://buildooor.com/mmdx"
DEFAULT_PUBLISH_TIMEOUT_SECONDS = 20.0
DIAGRAMS_PRO_PRICE_DISPLAY = "$15/month"
# SPAPS device-code auth (the flow that mints the bearer token `save`/`list`/
# `publish-link` need). `--server-url` is the SPAPS API base the CLI polls;
# the human approves at the Buildooor verifier URL. The device-code client id
# is the Buildooor public client; do not confuse it with app-link payload
# metadata such as `"app_slug": "mmdx"`.
DEFAULT_SPAPS_SERVER_URL = "https://api.sweetpotato.dev"
SPAPS_DEVICE_VERIFIER_URL = "https://buildooor.com/auth/device"
SPAPS_APP_SLUG = "buildooor"
SCRIPT_DIR = Path(__file__).resolve().parent
PARSER_SCRIPT = SCRIPT_DIR / "validate_mermaid.mjs"
PARSER_PACKAGE = SCRIPT_DIR / "package.json"
PARSER_MODULE = SCRIPT_DIR / "node_modules" / "mermaid"
# Bounds so a hung node/npm toolchain fails fast instead of consuming the
# caller's whole timeout budget (e.g. the status-proof mmdx_preflight gate).
PARSER_INSTALL_TIMEOUT_S = 180
PARSER_PARSE_TIMEOUT_S = 45
DEFAULT_HANDOFF_HOST = "127.0.0.1"
DEFAULT_HANDOFF_TTL_SECONDS = 10 * 60
MAX_HANDOFF_BODY_BYTES = 512 * 1024
PUBLIC_PAID_RESOURCE_KEYS = {
    "resource_key",
    "resourceKey",
    "action_key",
    "actionKey",
    "price_display",
    "priceDisplay",
}
MMDX_EXTERNAL_ACTION_TYPES = {"web", "github", "x"}
EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_AUTH = 2
EXIT_NETWORK_VERIFICATION = 3
SaveVerificationStatus = Literal["ok", "mismatch", "indeterminate"]


class MmdAuthError(RuntimeError):
    """Authentication is missing, rejected, or cannot be resolved."""


class MmdNetworkVerificationError(RuntimeError):
    """Network I/O or remote verification failed after local validation passed."""


class MmdAppLinkMutationError(MmdNetworkVerificationError):
    """Buildooor app-link create/update failed after local validation passed."""

    def __init__(
        self,
        *,
        operation: str,
        status_code: int,
        payload: dict[str, Any],
        message: str,
    ) -> None:
        self.operation = operation
        self.status_code = status_code
        self.payload = payload
        self.error_code = response_error_code(payload)
        super().__init__(message)


class MmdPaywallError(MmdAppLinkMutationError):
    """Buildooor rejected the mutation because Diagrams Pro is required."""

    def __init__(
        self,
        *,
        operation: str,
        status_code: int,
        payload: dict[str, Any],
        price_display: str = DIAGRAMS_PRO_PRICE_DISPLAY,
    ) -> None:
        self.price_display = price_display
        code = response_error_code(payload) or "DIAGRAMS_PRO_REQUIRED"
        message = response_error_message(payload, "Diagrams Pro is required for hosted diagram share links.")
        super().__init__(
            operation=operation,
            status_code=status_code,
            payload=payload,
            message=f"{operation} failed ({status_code}): {code}: {message} ({price_display})",
        )


class MmdSaveVerificationError(MmdNetworkVerificationError):
    """Remote save verification completed but did not prove the local source is current."""

    def __init__(self, latest_verification: SaveVerificationStatus, message: str) -> None:
        self.latest_verification = latest_verification
        super().__init__(message)


class MmdxLinkLabelError(ValueError):
    """MMDX drilldown link labels do not match visible source chart text."""

    def __init__(self, link_checks: dict[str, Any]) -> None:
        self.link_checks = link_checks
        self.issues = [issue for issue in link_checks.get("issues", []) if isinstance(issue, dict)]
        super().__init__(
            _format_mmdx_link_label_issue(self.issues[0]) if self.issues else "MMDX link label validation failed"
        )


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
    paid_resource: dict[str, Any] | None = None,
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
    if paid_resource is not None:
        public_paid_resource = _public_paid_resource_metadata(paid_resource)
        if public_paid_resource:
            state["buildooorPaidResource"] = public_paid_resource
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
    _reject_mmdx_chart_heading_blank_lines(markdown)
    charts = _parse_mmdx_charts(markdown)
    if not charts:
        raise ValueError("MMDX document must contain at least one '## chart <id>' Mermaid fence")

    seen_chart_ids = set()
    duplicate_chart_ids = []
    for chart in charts:
        chart_id = chart["id"]
        if chart_id in seen_chart_ids and chart_id not in duplicate_chart_ids:
            duplicate_chart_ids.append(chart_id)
        seen_chart_ids.add(chart_id)
    if duplicate_chart_ids:
        raise ValueError(f"MMDX chart IDs must be unique: {', '.join(duplicate_chart_ids)}")

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
        actions = _read_mmdx_external_actions(item.get("actions"))
        if actions:
            link["actions"] = actions
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


def build_state_for_source(
    path: str,
    code: str,
    *,
    config: str | None = None,
    theme: str = "default",
    grid: bool = True,
    pan_zoom: bool = True,
    rough: bool = False,
    handoff: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    paid_resource: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    mmdx_document = build_mmdx_document(code) if is_mmdx_input(path, code) else None
    diagram_code = get_mmdx_entry_code(mmdx_document) if mmdx_document else code
    source_kind = "mmdx" if mmdx_document else "mermaid"
    state = build_state(
        diagram_code,
        config=config,
        theme=theme,
        grid=grid,
        pan_zoom=pan_zoom,
        rough=rough,
        handoff=handoff,
        source=source,
        mmdx=mmdx_document,
        paid_resource=paid_resource,
    )
    return state, source_kind, mmdx_document


def normalize_mmdx_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


# Ported from /srv/skillbox/repos/buildooor/lib/diagrams/mmdx.ts:54-76,182-201 so CLI MMDX
# preflight matches the frontend label-link resolver: exact normalized labels
# win first, then a link label may match inside the visible source chart text
# only when both sides are bounded by non-[a-z0-9] characters.
def mmdx_label_matches_visible_text(visible_text: str, label: str) -> bool:
    normalized_text = normalize_mmdx_label(visible_text)
    normalized_label = normalize_mmdx_label(label)
    if not normalized_text or not normalized_label:
        return False
    if normalized_text == normalized_label:
        return True
    return contains_mmdx_label_with_boundary(normalized_text, normalized_label)


def contains_mmdx_label_with_boundary(value: str, label: str) -> bool:
    if not label:
        return False

    index = value.find(label)
    while index != -1:
        before = index - 1
        after = index + len(label)
        if is_mmdx_label_boundary(value, before) and is_mmdx_label_boundary(value, after):
            return True
        index = value.find(label, index + 1)

    return False


def is_mmdx_label_boundary(value: str, index: int) -> bool:
    if index < 0 or index >= len(value):
        return True
    return re.search(r"[a-z0-9]", value[index]) is None


def _format_mmdx_link_label_issue(issue: dict[str, str]) -> str:
    return (
        f"MMDX link label mismatch in chart {issue['from']!r}: "
        f"label {issue['label']!r} is not visible in source chart text"
    )


def build_mmdx_link_label_checks(document: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    charts_by_id = {chart["id"]: chart for chart in document["charts"]}
    issues: list[dict[str, str]] = []
    severity = "error" if strict else "warning"

    for link in document["links"]:
        source_chart = charts_by_id.get(link["from"])
        if source_chart is None:
            continue
        if mmdx_label_matches_visible_text(source_chart["code"], link["label"]):
            continue
        issue = {
            "severity": severity,
            "from": link["from"],
            "label": link["label"],
            "to": link["to"],
        }
        issue["message"] = _format_mmdx_link_label_issue(issue)
        issues.append(issue)

    return {
        "ok": len(issues) == 0,
        "strict": strict,
        "checked": len(document["links"]),
        "issues": issues,
    }


def warn_mmdx_link_label_checks(link_checks: dict[str, Any]) -> None:
    for issue in link_checks.get("issues", []):
        if isinstance(issue, dict) and isinstance(issue.get("message"), str):
            print(f"mmd: warning: {issue['message']}", file=sys.stderr)


def enforce_mmdx_link_label_checks(link_checks: dict[str, Any]) -> None:
    issues = [issue for issue in link_checks.get("issues", []) if isinstance(issue, dict)]
    if issues:
        raise MmdxLinkLabelError(link_checks)


def preflight_mmdx_document(document: dict[str, Any], *, auto_install: bool = True) -> list[dict[str, Any]]:
    results = []
    for chart in document["charts"]:
        try:
            result = preflight_mermaid(chart["code"], auto_install=auto_install)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            raise ValueError(f"MMDX chart {chart['id']!r} failed Mermaid preflight: {exc}") from exc
        results.append({"id": chart["id"], **result})
    return results


def preflight_source_code(
    code: str,
    source_path: str | Path | None,
    *,
    auto_install: bool = True,
    strict_links: bool = False,
) -> dict[str, Any]:
    source_name = str(source_path or "-")
    if is_mmdx_input(source_name, code):
        document = build_mmdx_document(code)
        results = preflight_mmdx_document(document, auto_install=auto_install)
        link_checks = build_mmdx_link_label_checks(document, strict=strict_links)
        if strict_links:
            enforce_mmdx_link_label_checks(link_checks)
        return {
            "kind": "mmdx",
            "entry": document["entry"],
            "chartCount": len(document["charts"]),
            "charts": results,
            "linkChecks": link_checks,
        }
    return preflight_mermaid(code, auto_install=auto_install)


def _diagram_type_from_preflight(result: dict[str, Any]) -> str:
    diagram_type = result.get("diagramType") or result.get("diagram_type")
    return diagram_type if isinstance(diagram_type, str) and diagram_type.strip() else "unknown"


def build_preflight_json_success(
    *,
    document: dict[str, Any] | None,
    parse_results: list[dict[str, Any]],
    link_checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if document is not None:
        result_by_id = {
            result["id"]: result
            for result in parse_results
            if isinstance(result.get("id"), str)
        }
        charts = []
        for chart in document["charts"]:
            parser_result = dict(result_by_id.get(chart["id"], {}))
            parser_result.pop("id", None)
            charts.append(
                {
                    "id": chart["id"],
                    "title": chart.get("title"),
                    "diagram_type": _diagram_type_from_preflight(parser_result),
                    "preflight": parser_result,
                }
            )
        ids = [chart["id"] for chart in document["charts"]]
        entry = document["entry"]
        links = document["links"]
        kind = "mmdx"
    else:
        parser_result = parse_results[0] if parse_results else {}
        charts = [
            {
                "id": None,
                "title": None,
                "diagram_type": _diagram_type_from_preflight(parser_result),
                "preflight": parser_result,
            }
        ]
        ids = []
        entry = None
        links = []
        kind = "mermaid"

    return {
        "ok": True,
        "kind": kind,
        "entry": entry,
        "ids": ids,
        "links": links,
        "charts": charts,
        "chart_count": len(charts),
        "link_checks": link_checks,
        "errors": [],
    }


def build_preflight_json_error(exc: BaseException, exit_code: int) -> dict[str, Any]:
    link_checks = None
    if isinstance(exc, MmdxLinkLabelError):
        link_checks = exc.link_checks
    return {
        "ok": False,
        "kind": "mmdx" if link_checks else "unknown",
        "entry": None,
        "ids": [],
        "links": [],
        "charts": [],
        "chart_count": 0,
        "link_checks": link_checks,
        "errors": [
            {
                "type": exc.__class__.__name__,
                "message": str(exc),
            }
        ],
        "exit_code": exit_code,
    }


def _parse_mmdx_metadata(markdown: str) -> dict[str, Any]:
    match = re.search(r"<!--\s*mmdx\s*(\{.*?\})\s*-->", markdown, flags=re.DOTALL)
    if not match:
        return {}
    metadata = json.loads(match.group(1))
    if not isinstance(metadata, dict):
        raise ValueError("MMDX metadata must be a JSON object")
    return metadata


def _find_mmdx_metadata_match(markdown: str) -> re.Match[str] | None:
    return re.search(r"<!--\s*mmdx\s*(\{.*?\})\s*-->", markdown, flags=re.DOTALL)


def write_mmdx_short_link_metadata(path: str, *, username: str, slug: str) -> None:
    if path == "-":
        raise ValueError("--write-short-link-metadata requires a local .mmdx file path, not stdin")
    source_path = Path(path).expanduser()
    if source_path.suffix.lower() != ".mmdx":
        raise ValueError("--write-short-link-metadata requires a local .mmdx file")
    markdown = source_path.read_text(encoding="utf-8")
    match = _find_mmdx_metadata_match(markdown)
    if not match:
        raise ValueError("--write-short-link-metadata requires an MMDX metadata header")
    metadata = json.loads(match.group(1))
    if not isinstance(metadata, dict):
        raise ValueError("MMDX metadata must be a JSON object")
    metadata["shortLink"] = {
        "username": username,
        "slug": slug,
    }
    # Rewrite only the metadata comment. The source body remains byte-stable so
    # a first short-link mint does not churn authored chart content.
    replacement = f"<!-- mmdx\n{json.dumps(metadata, indent=2, ensure_ascii=False)}\n-->"
    updated = markdown[: match.start()] + replacement + markdown[match.end() :]
    source_path.write_text(updated, encoding="utf-8")


def _read_mmdx_external_actions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    actions = []
    for item in value:
        action = _read_mmdx_external_action(item)
        if action is not None:
            actions.append(action)
    return actions


def _read_mmdx_external_action(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    action_type = value.get("type")
    if not isinstance(action_type, str):
        return None
    action_type = action_type.strip().lower()
    if action_type not in MMDX_EXTERNAL_ACTION_TYPES:
        return None

    url = _read_safe_external_url(value.get("url"))
    if url is None:
        return None

    action = {
        "type": action_type,
        "url": url,
    }
    title = value.get("title")
    if isinstance(title, str) and title.strip():
        action["title"] = title.strip()
    return action


def _read_safe_external_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


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


def _reject_mmdx_chart_heading_blank_lines(markdown: str) -> None:
    pattern = re.compile(
        r"^(##\s+chart\s+[A-Za-z0-9_-]+[^\n]*\n)([ \t]*\n)+```mermaid",
        flags=re.MULTILINE,
    )
    match = pattern.search(markdown)
    if match:
        heading = match.group(1).strip()
        raise ValueError(
            f"{heading} must be followed immediately by ```mermaid; "
            "remove blank lines between MMDX chart headings and fences"
        )


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


def append_url_segments(base_url: str, *segments: str) -> str:
    return "/".join(
        [base_url.rstrip("/"), *[quote(segment.strip("/"), safe="") for segment in segments if segment.strip("/")]]
    )


def require_secure_api_base_url(url: str, label: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise ValueError(f"{label} API base URL must be https, except for localhost development")


def require_secure_publish_api_base_url(url: str) -> None:
    require_secure_api_base_url(url, "publish-link")


def resolve_handoff_origin(*, explicit_origin: str | None, output_base_url: str) -> str:
    return origin_from_url((explicit_origin or output_base_url).strip())


def _run_open_command(command: list[str], *, label: str) -> bool:
    try:
        subprocess.run(command, check=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"mmd: {label} failed: {exc}", file=sys.stderr)
        return False


def print_open_fallback(url: str, reason: str) -> None:
    print(f"mmd: {reason}; no browser was opened.", file=sys.stderr)
    print(f"mmd: hand this URL to the user: {url}", file=sys.stderr)


def open_generated_url(url: str) -> bool:
    if sys.platform.startswith("linux"):
        opener = shutil.which("xdg-open")
        if opener and _run_open_command([opener, url], label="xdg-open"):
            return True
        print_open_fallback(url, "xdg-open was not available")
        return False

    if sys.platform == "darwin":
        opener = shutil.which("open")
        if opener and _run_open_command([opener, url], label="open"):
            return True

        osascript = shutil.which("osascript")
        if osascript:
            script_path = Path(__file__).with_name("open_mermaid_live.applescript")
            if _run_open_command([osascript, str(script_path), url], label="osascript"):
                return True

        print_open_fallback(url, "macOS open/osascript opener was not available")
        return False

    print_open_fallback(url, f"no supported browser opener for platform {sys.platform!r}")
    return False


class HandoffHTTPServer(http.server.ThreadingHTTPServer):
    token: str
    tmux_target: str
    source_path: str | None
    submit_on_send: bool
    expires_at: float
    allowed_origin: str
    paid_resource: dict[str, str] | None


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

        if self.server.paid_resource is not None:
            authorization_token = payload.get("authorization_token")
            if not isinstance(authorization_token, str) or not authorization_token.strip():
                self._send_json(403, {"ok": False, "error": "x402_handoff_authorization_required"})
                return
            target = self.server.paid_resource.get("target")
            if not isinstance(target, str) or not target.strip():
                self._send_json(403, {"ok": False, "error": "x402_handoff_authorization_required"})
                return
            resource_key = self.server.paid_resource.get("resource_key")
            action_key = self.server.paid_resource.get("action_key")
            if (
                not isinstance(resource_key, str)
                or not resource_key.strip()
                or not isinstance(action_key, str)
                or not action_key.strip()
            ):
                self._send_json(403, {"ok": False, "error": "x402_handoff_authorization_required"})
                return
            try:
                result = verify_spaps_authorization(
                    self.server.paid_resource["verify_url"],
                    self.server.paid_resource["api_key"],
                    authorization_token.strip(),
                    resource_key=resource_key.strip(),
                    action_key=action_key.strip(),
                    target=target.strip(),
                    bridge_token=payload["token"],
                )
                if (
                    not result.get("valid")
                    or result.get("resource_key") != resource_key.strip()
                    or result.get("action_key") != action_key.strip()
                    or result.get("target") != target.strip()
                ):
                    self._send_json(403, {"ok": False, "error": "x402_handoff_authorization_required"})
                    return
            except HTTPError as exc:
                if exc.code == 403:
                    self._send_json(403, {"ok": False, "error": "x402_handoff_authorization_required"})
                else:
                    self._send_json(502, {"ok": False, "error": "x402_handoff_verification_failed"})
                return
            except (URLError, OSError, json.JSONDecodeError, ValueError):
                self._send_json(502, {"ok": False, "error": "x402_handoff_verification_failed"})
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
            result = preflight_source_code(code, source_path)
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
            result = preflight_source_code(code, source_path)
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


def verify_spaps_authorization(
    verify_url: str,
    api_key: str,
    authorization_token: str,
    resource_key: str,
    action_key: str,
    target: str,
    bridge_token: str,
) -> dict[str, Any]:
    """Call SPAPS to verify a handoff authorization token."""
    body: dict[str, Any] = {
        "token": authorization_token,
        "resource_key": resource_key,
        "action_key": action_key,
        "target": target,
        "bridge_token": bridge_token,
    }
    data = json.dumps(body).encode("utf-8")
    req = request.Request(
        verify_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        result = json.loads(response.read().decode("utf-8"))
    if isinstance(result.get("data"), dict):
        return result["data"]
    return result


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
    paid_resource: dict[str, str] | None = None,
) -> int:
    server = HandoffHTTPServer((host, port), HandoffRequestHandler)
    server.token = token
    server.tmux_target = tmux_target
    server.source_path = source_path
    server.submit_on_send = submit_on_send
    server.expires_at = time.time() + ttl_seconds
    server.allowed_origin = allowed_origin
    server.paid_resource = paid_resource
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
    paid_resource: dict[str, str] | None = None,
) -> dict[str, Any]:
    target = resolve_tmux_target(tmux_target)
    label = describe_tmux_target(target)
    token = secrets.token_urlsafe(24)
    port = find_available_port(host)
    endpoint = f"http://{host}:{port}/send"
    paid_resource_args: list[str] = []
    child_env = os.environ.copy()
    if paid_resource:
        paid_resource_args = [
            "--paid-resource-verify-url", paid_resource["verify_url"],
            "--paid-resource-resource-key", paid_resource["resource_key"],
            "--paid-resource-action-key", paid_resource["action_key"],
        ]
        child_env["SPAPS_API_KEY"] = paid_resource["api_key"]
        if paid_resource.get("target"):
            paid_resource_args.extend(["--paid-resource-target", paid_resource["target"]])
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
            *paid_resource_args,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=child_env,
        start_new_session=True,
    )
    wait_for_handoff_server(endpoint)
    handoff: dict[str, Any] = {
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
    if paid_resource:
        handoff["paidAuthorizationRequired"] = True
    return handoff


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
    try:
        subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund"],
            cwd=SCRIPT_DIR,
            check=True,
            timeout=PARSER_INSTALL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"npm install for the Mermaid parser timed out after {PARSER_INSTALL_TIMEOUT_S}s; "
            "run `python3 mmd.py --setup-parser` manually or pass --no-preflight"
        ) from exc


def preflight_mermaid(code: str, *, auto_install: bool = True) -> dict[str, Any]:
    setup_parser_dependencies(auto_install=auto_install)
    try:
        result = subprocess.run(
            ["node", str(PARSER_SCRIPT)],
            input=code,
            text=True,
            capture_output=True,
            check=False,
            timeout=PARSER_PARSE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        # A hung parser must fail fast with a clear cause, not silently consume
        # the caller's whole timeout budget (e.g. the status-proof mmdx gate).
        raise ValueError(
            f"Mermaid parser ({PARSER_SCRIPT.name}) did not return within "
            f"{PARSER_PARSE_TIMEOUT_S}s; the node/DOM toolchain may be hung "
            "(check the jsdom version pin in scripts/package.json)"
        ) from exc
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Mermaid parser failed"
        raise ValueError(message)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Mermaid parser returned invalid JSON: {result.stdout}") from exc


def parse_publish_link_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mmd.py publish-link",
        description="Create or update a Buildooor MMDX short link from a .mmd/.mmdx source.",
    )
    parser.add_argument("path", help="Mermaid .mmd/.mmdx file path, or '-' for stdin")
    parser.add_argument("--create", action="store_true", help="create a new authenticated short link")
    parser.add_argument("--username", help="short-link owner username; required when updating")
    parser.add_argument("--slug", help="existing short-link slug to update, or requested slug with --create")
    parser.add_argument("--title", help="short-link title; defaults to the source file stem")
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("BUILDOOOR_APP_LINKS_API_BASE_URL", DEFAULT_APP_LINKS_API_BASE_URL),
        help="Buildooor app-links API base URL",
    )
    parser.add_argument(
        "--live-base-url",
        default=os.environ.get("BUILDOOOR_MMDX_LIVE_BASE_URL", DEFAULT_MMDX_SHORT_LINK_BASE_URL),
        help="Buildooor MMDX short-link base URL used for verification",
    )
    parser.add_argument(
        "--origin",
        default=os.environ.get("BUILDOOOR_ORIGIN", origin_from_url(DEFAULT_MMDX_SHORT_LINK_BASE_URL)),
        help="Origin header to send to the Buildooor proxy",
    )
    parser.add_argument(
        "--access-token",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN") or os.environ.get("SPAPS_ACCESS_TOKEN"),
        help="bearer token from the existing Buildooor/SPAPS auth flow",
    )
    parser.add_argument(
        "--access-token-command",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN_COMMAND") or os.environ.get("SPAPS_TOKEN_COMMAND"),
        help="command that prints a bearer token from the existing device-code auth flow",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the update payload without mutating remote state")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="with --dry-run, omit the full pako payload and print only hashes/metadata",
    )
    parser.add_argument(
        "--skip-live-verify",
        action="store_true",
        help="skip fetching the live short link after publishing",
    )
    parser.add_argument(
        "--write-short-link-metadata",
        action="store_true",
        help="after --create succeeds, write returned username/slug into the local .mmdx shortLink header",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable publish result")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds",
    )
    parser.add_argument("--theme", default="default", help="Mermaid config theme name")
    parser.add_argument("--config", help="Mermaid config JSON string or path to a JSON file")
    parser.add_argument("--rough", action="store_true", help="enable Mermaid Live rough rendering")
    parser.add_argument("--no-grid", action="store_true", help="disable the editor grid")
    parser.add_argument("--no-pan-zoom", action="store_true", help="disable pan/zoom")
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
    args = parser.parse_args(argv)
    args.command = "publish-link"
    return args


def parse_list_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mmd.py list",
        description="List authenticated owner MMDX diagrams from the Buildooor MMDX service.",
    )
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("BUILDOOOR_MMDX_API_BASE_URL", DEFAULT_MMDX_API_BASE_URL),
        help="Buildooor MMDX API base URL",
    )
    parser.add_argument(
        "--origin",
        default=os.environ.get("BUILDOOOR_ORIGIN", origin_from_url(DEFAULT_MMDX_SHORT_LINK_BASE_URL)),
        help="Origin header to send to the Buildooor proxy",
    )
    parser.add_argument(
        "--access-token",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN") or os.environ.get("SPAPS_ACCESS_TOKEN"),
        help="bearer token from the existing Buildooor/SPAPS auth flow",
    )
    parser.add_argument(
        "--access-token-command",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN_COMMAND") or os.environ.get("SPAPS_TOKEN_COMMAND"),
        help="command that prints a bearer token from the existing device-code auth flow",
    )
    parser.add_argument("--visibility", choices=["private", "unlisted", "public"], help="filter by diagram visibility")
    parser.add_argument("--slug-contains", help="filter owner diagrams by slug substring")
    parser.add_argument("--limit", type=int, help="maximum diagrams to return")
    parser.add_argument("--offset", type=int, help="pagination offset")
    parser.add_argument("--json", action="store_true", help="print the raw owner-list JSON response")
    parser.add_argument("--dry-run", action="store_true", help="print request metadata without calling the network")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds",
    )
    args = parser.parse_args(argv)
    args.command = "list"
    return args


def add_mmdx_lifecycle_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("BUILDOOOR_MMDX_API_BASE_URL", DEFAULT_MMDX_API_BASE_URL),
        help="Buildooor MMDX API base URL",
    )
    parser.add_argument(
        "--origin",
        default=os.environ.get("BUILDOOOR_ORIGIN", origin_from_url(DEFAULT_MMDX_SHORT_LINK_BASE_URL)),
        help="Origin header to send to the Buildooor proxy",
    )
    parser.add_argument(
        "--access-token",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN") or os.environ.get("SPAPS_ACCESS_TOKEN"),
        help="bearer token from the existing Buildooor/SPAPS auth flow",
    )
    parser.add_argument(
        "--access-token-command",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN_COMMAND") or os.environ.get("SPAPS_TOKEN_COMMAND"),
        help="command that prints a bearer token from the existing device-code auth flow",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable response JSON")
    parser.add_argument("--dry-run", action="store_true", help="print request metadata without calling the network")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds",
    )


def parse_versions_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mmd.py versions",
        description="List versions for an authenticated owner MMDX diagram.",
    )
    parser.add_argument("diagram_id", help="durable MMDX diagram id")
    add_mmdx_lifecycle_auth_args(parser)
    args = parser.parse_args(argv)
    args.command = "versions"
    return args


def parse_sharing_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mmd.py sharing",
        description="Update sharing metadata for an authenticated owner MMDX diagram.",
    )
    parser.add_argument("diagram_id", help="durable MMDX diagram id")
    parser.add_argument("--visibility", choices=["private", "unlisted", "public"], help="new diagram visibility")
    parser.add_argument("--title", help="new diagram title")
    parser.add_argument("--chart-slug", help="new owner-scoped chart slug")
    add_mmdx_lifecycle_auth_args(parser)
    args = parser.parse_args(argv)
    args.command = "sharing"
    return args


def parse_delete_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mmd.py delete",
        description="Delete an authenticated owner MMDX diagram.",
    )
    parser.add_argument("diagram_id", help="durable MMDX diagram id")
    parser.add_argument("--yes", action="store_true", help="required confirmation before deleting")
    add_mmdx_lifecycle_auth_args(parser)
    args = parser.parse_args(argv)
    args.command = "delete"
    return args


def parse_save_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mmd.py save",
        description="Create a private Buildooor MMDX diagram or append a version to an owned diagram.",
    )
    parser.add_argument("path", help="Mermaid .mmd/.mmdx file path, or '-' for stdin")
    parser.add_argument(
        "--diagram-id",
        help="existing durable diagram id; when omitted, save creates a new private diagram",
    )
    parser.add_argument("--title", help="diagram title for creates; defaults to the source file stem")
    parser.add_argument("--description", help="optional diagram description for creates")
    parser.add_argument("--chart-slug", help="optional owner-scoped chart slug for creates")
    parser.add_argument(
        "--base-version-id",
        help="latest version id before append; if omitted with --diagram-id, save fetches /latest first",
    )
    parser.add_argument(
        "--parent-version-id",
        help="version id the edit was based on; defaults to the resolved base version for appends",
    )
    parser.add_argument("--save-note", help="optional note for appended versions")
    parser.add_argument("--entry-chart-id", help="entry chart id; defaults to the MMDX metadata entry when present")
    parser.add_argument("--source-app-link-id", help="optional source app-link id for creates")
    parser.add_argument(
        "--source-app-link-metadata",
        help="optional JSON object with source app-link metadata for creates",
    )
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("BUILDOOOR_MMDX_API_BASE_URL", DEFAULT_MMDX_API_BASE_URL),
        help="Buildooor MMDX API base URL",
    )
    parser.add_argument(
        "--origin",
        default=os.environ.get("BUILDOOOR_ORIGIN", origin_from_url(DEFAULT_MMDX_SHORT_LINK_BASE_URL)),
        help="Origin header to send to the Buildooor proxy",
    )
    parser.add_argument(
        "--access-token",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN") or os.environ.get("SPAPS_ACCESS_TOKEN"),
        help="bearer token from the existing Buildooor/SPAPS auth flow",
    )
    parser.add_argument(
        "--access-token-command",
        default=os.environ.get("BUILDOOOR_ACCESS_TOKEN_COMMAND") or os.environ.get("SPAPS_TOKEN_COMMAND"),
        help="command that prints a bearer token from the existing device-code auth flow",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable save response JSON")
    parser.add_argument("--dry-run", action="store_true", help="print request metadata without calling the network")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="allow save to exit 0 when /latest does not echo mmdx_text; reports latest_verification=indeterminate",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="with --dry-run, omit the full source text and print only hashes/metadata",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="skip Mermaid parser validation before saving",
    )
    parser.add_argument(
        "--no-parser-install",
        action="store_true",
        help="do not auto-install the parser dependency if missing",
    )
    args = parser.parse_args(argv)
    args.command = "save"
    return args


def parse_args(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "publish-link":
        return parse_publish_link_args(argv[1:])
    if argv and argv[0] == "list":
        return parse_list_args(argv[1:])
    if argv and argv[0] == "versions":
        return parse_versions_args(argv[1:])
    if argv and argv[0] == "sharing":
        return parse_sharing_args(argv[1:])
    if argv and argv[0] == "delete":
        return parse_delete_args(argv[1:])
    if argv and argv[0] == "save":
        return parse_save_args(argv[1:])

    parser = argparse.ArgumentParser(
        description="Generate buildooor diagrams pako URLs from .mmd or .mmdx source files.",
        epilog=(
            "Subcommands: save (create/append a private durable MMDX diagram), "
            "list (show owned durable diagrams), versions (show diagram history), "
            "sharing (update owner sharing metadata), delete (remove an owned diagram), "
            "publish-link (update an existing short link)."
        ),
    )
    parser.add_argument("path", nargs="?", help="Mermaid .mmd/.mmdx file path, or '-' for stdin")
    parser.add_argument("--open", action="store_true", help="best-effort open of the generated URL in a browser")
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
    parser.add_argument("--paid-resource-verify-url", help="SPAPS x402 handoff authorization verify URL")
    parser.add_argument("--paid-resource-api-key", help="SPAPS API key for x402 handoff verification")
    parser.add_argument("--paid-resource-resource-key", help="x402 resource key required for handoff sends")
    parser.add_argument("--paid-resource-action-key", help="x402 action key required for handoff sends")
    parser.add_argument("--paid-resource-target", help="x402 target bound to this handoff channel")
    parser.add_argument(
        "--paid-resource",
        help="JSON paid-resource metadata for x402 handoff authorization",
    )
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
        "--strict-links",
        action="store_true",
        help="fail MMDX preflight when a drilldown link label is not visible in its source chart",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --preflight-only, print a machine-readable preflight result",
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


def default_publish_title(path: str, source_kind: str) -> str:
    if path == "-":
        return "MMDX diagram" if source_kind == "mmdx" else "Mermaid diagram"
    stem = Path(path).expanduser().stem.strip()
    return stem or ("MMDX diagram" if source_kind == "mmdx" else "Mermaid diagram")


def default_short_link_title(source_kind: str) -> str:
    return "MMDX diagram" if source_kind == "mmdx" else "Mermaid diagram"


def build_publish_payload(args: argparse.Namespace, code: str) -> tuple[dict[str, Any], str, str, str]:
    state, source_kind, mmdx_document = build_state_for_source(
        args.path,
        code,
        config=args.config,
        theme=args.theme,
        grid=not args.no_grid,
        pan_zoom=not args.no_pan_zoom,
        rough=args.rough,
    )
    fragment = encode_state(state)
    source_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
    hosted_record_count = len(mmdx_document["charts"]) if mmdx_document is not None else 1
    hosted_record_count = max(1, int(hosted_record_count))
    metadata: dict[str, Any] = {
        "diagram_state": fragment,
        "diagram_state_format": "mermaid-live-pako",
        "source_kind": source_kind,
        "hosted_record_count": hosted_record_count,
    }
    if not getattr(args, "create", False):
        metadata["source_sha256"] = source_sha256
    if not getattr(args, "create", False) and args.path != "-":
        metadata["source_path"] = str(Path(args.path).expanduser())

    payload = {
        "app_slug": "mmdx",
        "resource_kind": "mmdx-diagram" if source_kind == "mmdx" else "mermaid-diagram",
        "target_path": "/diagrams",
        "title": args.title
        or (default_short_link_title(source_kind) if getattr(args, "create", False) else default_publish_title(args.path, source_kind)),
        "metadata": metadata,
    }
    if getattr(args, "create", False) and getattr(args, "slug", None):
        payload["slug"] = args.slug
    return payload, fragment, source_kind, source_sha256


def infer_entry_chart_id(path: str, code: str, explicit_entry: str | None = None) -> str | None:
    if explicit_entry is not None and explicit_entry.strip():
        return explicit_entry.strip()
    if is_mmdx_input(path, code):
        document = build_mmdx_document(code)
        entry = document.get("entry")
        return entry if isinstance(entry, str) and entry.strip() else None
    return None


def parse_optional_json_object(value: str | None, label: str) -> dict[str, Any] | None:
    if value is None or not value.strip():
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def build_create_diagram_payload(args: argparse.Namespace, code: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": args.title or default_publish_title(args.path, "mmdx" if is_mmdx_input(args.path, code) else "mermaid"),
        "mmdx_text": code,
    }
    optional_fields = {
        "description": args.description,
        "chart_slug": args.chart_slug,
        "entry_chart_id": infer_entry_chart_id(args.path, code, args.entry_chart_id),
        "source_app_link_id": args.source_app_link_id,
        "source_app_link_metadata": parse_optional_json_object(
            args.source_app_link_metadata,
            "--source-app-link-metadata",
        ),
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value
    return payload


def build_append_version_payload(
    args: argparse.Namespace,
    code: str,
    *,
    base_version_id: str,
    parent_version_id: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "base_version_id": base_version_id,
        "mmdx_text": code,
    }
    optional_fields = {
        "parent_version_id": parent_version_id,
        "entry_chart_id": infer_entry_chart_id(args.path, code, args.entry_chart_id),
        "save_note": args.save_note,
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value
    return payload


def resolve_spaps_server_url() -> str:
    """SPAPS API base for device-code auth, by the documented precedence.

    MMDX_SPAPS_SERVER_URL > SPAPS_API_URL > NEXT_PUBLIC_SPAPS_API_URL, then the
    production fallback. Lets the mint recipe print a real URL in local, staging,
    and prod shells instead of a stale hardcoded example.
    """
    for name in ("MMDX_SPAPS_SERVER_URL", "SPAPS_API_URL", "NEXT_PUBLIC_SPAPS_API_URL"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return DEFAULT_SPAPS_SERVER_URL


def resolve_spaps_client_id() -> str:
    """App slug for `spaps login --client-id`, overridable per environment."""
    for name in ("MMDX_SPAPS_CLIENT_ID", "SPAPS_CLIENT_ID"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return SPAPS_APP_SLUG


def missing_token_help(command_name: str) -> str:
    """Fail-open auth error: name the inputs, then hand over the exact mint recipe.

    Keeps the legacy ``<command> requires --access-token`` opening clause (the
    contract callers/tests rely on) and appends a copy-pasteable device-code
    login so an agent or operator never has to guess how to authenticate.
    """
    server_url = resolve_spaps_server_url()
    client_id = resolve_spaps_client_id()
    return (
        f"{command_name} requires --access-token, BUILDOOOR_ACCESS_TOKEN, "
        "SPAPS_ACCESS_TOKEN, or --access-token-command from the existing "
        "device-code auth flow.\n"
        "Mint one with the device-code login, then re-run:\n"
        f"  spaps login --server-url {server_url} --client-id {client_id}\n"
        f"  # approve in a browser at {SPAPS_DEVICE_VERIFIER_URL}?user_code=<code>\n"
        f'  export BUILDOOOR_ACCESS_TOKEN="$(spaps token --server-url {server_url})"\n'
        "Or pass it inline with: "
        f'--access-token-command "spaps token --server-url {server_url}"\n'
        "spaps not on PATH? Run it from the monorepo: "
        f"node ../sweet-potato/packages/spaps/bin/spaps.js login "
        f"--server-url {server_url} --client-id {client_id}"
    )


def resolve_publish_access_token(args: argparse.Namespace, *, command_name: str = "publish-link") -> str:
    token = (args.access_token or "").strip()
    if token:
        return token

    command = (args.access_token_command or "").strip()
    if command:
        completed = subprocess.run(
            shlex.split(command),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise MmdAuthError(f"access token command failed: {message}")
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if lines:
            return lines[-1]
        raise MmdAuthError("access token command did not print a token")

    raise MmdAuthError(missing_token_help(command_name))


def read_json_response(response: Any) -> dict[str, Any]:
    raw = response.read().decode("utf-8")
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("API response must be a JSON object")
    return payload


def read_http_error_json(exc: HTTPError) -> dict[str, Any]:
    raw = exc.read().decode("utf-8", errors="replace")
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": raw.strip()}
    return payload if isinstance(payload, dict) else {"error": payload}


def response_error_message(payload: dict[str, Any], fallback: str) -> str:
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        message = error_payload.get("message") or error_payload.get("code")
        if isinstance(message, str) and message.strip():
            return message.strip()
    if isinstance(error_payload, str) and error_payload.strip():
        return error_payload.strip()
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback


def response_error_code(payload: dict[str, Any]) -> str | None:
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        code = error_payload.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    code = payload.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def response_price_display(payload: dict[str, Any]) -> str | None:
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        for key in ("price_display", "priceDisplay"):
            value = error_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("price_display", "priceDisplay"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def app_link_from_response(payload: dict[str, Any]) -> dict[str, str]:
    candidate: Any = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(candidate, dict):
        raise MmdNetworkVerificationError("short-link response did not include a link")
    username = candidate.get("username")
    slug = candidate.get("slug")
    if not isinstance(username, str) or not username.strip() or not isinstance(slug, str) or not slug.strip():
        raise MmdNetworkVerificationError("short-link response was missing username or slug")
    return {
        "username": username.strip(),
        "slug": slug.strip(),
    }


def app_link_mutation_error(
    *,
    operation: str,
    status_code: int,
    payload: dict[str, Any],
    fallback: str,
) -> MmdAppLinkMutationError:
    code = response_error_code(payload)
    if status_code == 402 and code == "DIAGRAMS_PRO_REQUIRED":
        return MmdPaywallError(
            operation=operation,
            status_code=status_code,
            payload=payload,
            price_display=response_price_display(payload) or DIAGRAMS_PRO_PRICE_DISPLAY,
        )
    message = response_error_message(payload, fallback)
    return MmdAppLinkMutationError(
        operation=operation,
        status_code=status_code,
        payload=payload,
        message=f"{operation} failed ({status_code}): {message}",
    )


def mutate_app_link(
    endpoint: str,
    payload: dict[str, Any],
    *,
    access_token: str,
    origin: str,
    timeout: float,
    method: str,
    operation: str,
    user_agent: str,
) -> dict[str, Any]:
    req = request.Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Origin": origin,
            "User-Agent": user_agent,
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return read_json_response(response)
    except HTTPError as exc:
        payload = read_http_error_json(exc)
        message = response_error_message(payload, f"failed to {operation} short link")
        if exc.code in {401, 403}:
            raise MmdAuthError(f"{operation} failed ({exc.code}): {message}") from exc
        raise app_link_mutation_error(
            operation=operation,
            status_code=exc.code,
            payload=payload,
            fallback=f"failed to {operation} short link",
        ) from exc
    except URLError as exc:
        raise MmdNetworkVerificationError(f"{operation} failed: {exc.reason}") from exc


def create_app_link(
    endpoint: str,
    payload: dict[str, Any],
    *,
    access_token: str,
    origin: str,
    timeout: float,
) -> dict[str, Any]:
    return mutate_app_link(
        endpoint,
        payload,
        access_token=access_token,
        origin=origin,
        timeout=timeout,
        method="POST",
        operation="publish create",
        user_agent="buildooor-mmdx-publish-link/1.0",
    )


def patch_app_link(
    endpoint: str,
    payload: dict[str, Any],
    *,
    access_token: str,
    origin: str,
    timeout: float,
) -> dict[str, Any]:
    return mutate_app_link(
        endpoint,
        payload,
        access_token=access_token,
        origin=origin,
        timeout=timeout,
        method="PATCH",
        operation="publish update",
        user_agent="buildooor-mmdx-publish-link/1.0",
    )


def dry_run_auth_metadata(args: argparse.Namespace) -> dict[str, str]:
    if (args.access_token or "").strip():
        return {"Authorization": "Bearer <redacted>", "source": "argument-or-env"}
    if (args.access_token_command or "").strip():
        return {"Authorization": "Bearer <resolved by access-token-command>", "source": "command"}
    return {"Authorization": "<missing>", "source": "missing"}


def append_query_params(url: str, params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value is not None and value != ""}
    if not clean:
        return url
    return f"{url}?{urlencode(clean)}"


def validate_pagination_args(args: argparse.Namespace) -> None:
    if getattr(args, "limit", None) is not None and args.limit < 1:
        raise ValueError("--limit must be greater than zero")
    if getattr(args, "offset", None) is not None and args.offset < 0:
        raise ValueError("--offset must be zero or greater")


def build_owner_list_endpoint(args: argparse.Namespace) -> str:
    validate_pagination_args(args)
    return append_query_params(
        append_url_segments(args.api_base_url, "diagrams"),
        {
            "visibility": getattr(args, "visibility", None),
            "slug_contains": getattr(args, "slug_contains", None),
            "limit": getattr(args, "limit", None),
            "offset": getattr(args, "offset", None),
        },
    )


def dry_run_mmdx_request_body(
    args: argparse.Namespace,
    *,
    endpoint: str,
    method: str,
    upstream_path: str,
    user_agent: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    auth_metadata = dry_run_auth_metadata(args)
    body: dict[str, Any] = {
        "ok": True,
        "dry_run": True,
        "endpoint": endpoint,
        "method": method,
        "upstream_path": upstream_path,
        "headers": {
            "Accept": "application/json",
            "Authorization": auth_metadata["Authorization"],
            "Origin": args.origin,
            "User-Agent": user_agent,
        },
        "auth_source": auth_metadata["source"],
        "network": False,
    }
    if payload is not None:
        body["headers"]["Content-Type"] = "application/json"
        body["payload"] = payload
    return body


def get_mmdx_owner_list(
    endpoint: str,
    *,
    access_token: str,
    origin: str,
    timeout: float,
) -> dict[str, Any]:
    req = request.Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Origin": origin,
            "User-Agent": "buildooor-mmdx-list/1.0",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return read_json_response(response)
    except HTTPError as exc:
        payload = read_http_error_json(exc)
        message = response_error_message(payload, "failed to list MMDX diagrams")
        if exc.code in {401, 403}:
            raise MmdAuthError(f"MMDX list failed ({exc.code}): {message}") from exc
        raise MmdNetworkVerificationError(f"MMDX list failed ({exc.code}): {message}") from exc
    except URLError as exc:
        raise MmdNetworkVerificationError(f"MMDX list failed: {exc.reason}") from exc


def request_mmdx_json(
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    method: str,
    access_token: str,
    origin: str,
    timeout: float,
    label: str,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Origin": origin,
        "User-Agent": "buildooor-mmdx-save/1.0",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(endpoint, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return read_json_response(response)
    except HTTPError as exc:
        payload = read_http_error_json(exc)
        message = response_error_message(payload, f"failed to {label}")
        if exc.code in {401, 403}:
            raise MmdAuthError(f"MMDX {label} failed ({exc.code}): {message}") from exc
        raise MmdNetworkVerificationError(f"MMDX {label} failed ({exc.code}): {message}") from exc
    except URLError as exc:
        raise MmdNetworkVerificationError(f"MMDX {label} failed: {exc.reason}") from exc


def get_mmdx_latest_version(
    endpoint: str,
    *,
    access_token: str,
    origin: str,
    timeout: float,
) -> dict[str, Any]:
    return request_mmdx_json(
        endpoint,
        method="GET",
        access_token=access_token,
        origin=origin,
        timeout=timeout,
        label="latest lookup",
    )


def post_mmdx_save(
    endpoint: str,
    payload: dict[str, Any],
    *,
    access_token: str,
    origin: str,
    timeout: float,
    label: str,
) -> dict[str, Any]:
    return request_mmdx_json(
        endpoint,
        payload,
        method="POST",
        access_token=access_token,
        origin=origin,
        timeout=timeout,
        label=label,
    )


def owner_diagram_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def table_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def owner_diagram_row(item: dict[str, Any]) -> list[str]:
    return [
        table_value(item.get("id")),
        table_value(item.get("chart_slug") or item.get("slug")),
        table_value(item.get("title")),
        table_value(item.get("visibility")),
        table_value(item.get("updated_at") or item.get("latest_version_created_at")),
    ]


def print_owner_diagram_table(payload: dict[str, Any]) -> None:
    headers = ["id", "slug", "title", "visibility", "updated_at"]
    rows = [owner_diagram_row(item) for item in owner_diagram_items(payload)]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def version_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        versions = payload.get("versions")
        items = versions if isinstance(versions, list) else []
    return [item for item in items if isinstance(item, dict)]


def version_row(item: dict[str, Any]) -> list[str]:
    return [
        table_value(item.get("id") or item.get("version_id")),
        table_value(item.get("created_at")),
        table_value(item.get("save_note") or item.get("note")),
        table_value(item.get("parent_version_id")),
        table_value(item.get("mmdx_sha256") or item.get("source_sha256")),
    ]


def print_version_table(payload: dict[str, Any]) -> None:
    headers = ["id", "created_at", "save_note", "parent_version_id", "source_sha256"]
    rows = [version_row(item) for item in version_items(payload)]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def build_sharing_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.visibility is not None:
        payload["visibility"] = args.visibility
    if args.title is not None:
        payload["title"] = args.title
    if args.chart_slug is not None:
        payload["chart_slug"] = args.chart_slug
    if not payload:
        raise ValueError("sharing requires at least one of --visibility, --title, or --chart-slug")
    return payload


def find_key_recursive(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for item in value.values():
            found = find_key_recursive(item, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_key_recursive(item, key)
            if found is not None:
                return found
    return None


def extract_next_data_fragment(page_html: str) -> str:
    match = re.search(
        r"<script\b[^>]*\bid=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>",
        page_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise MmdNetworkVerificationError("live verification failed: __NEXT_DATA__ script was not found")
    next_data = json.loads(html.unescape(match.group(1)))
    fragment = find_key_recursive(next_data, "initialDiagramFragment")
    if not isinstance(fragment, str) or not fragment:
        raise MmdNetworkVerificationError("live verification failed: initialDiagramFragment was not found")
    return fragment


def fetch_live_diagram_fragment(live_url: str, *, timeout: float) -> str:
    req = request.Request(
        live_url,
        headers={"User-Agent": "buildooor-mmdx-publish-link/1.0"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return extract_next_data_fragment(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MmdNetworkVerificationError(f"live verification failed ({exc.code}) while fetching {live_url}") from exc
    except URLError as exc:
        raise MmdNetworkVerificationError(f"live verification failed while fetching {live_url}: {exc.reason}") from exc


def publish_link(args: argparse.Namespace) -> int:
    creating = bool(args.create)
    if not creating and (not args.username or not args.slug):
        raise ValueError("publish-link update requires --username and --slug; pass --create to mint a new short link")

    code = _read_text(args.path)
    if not args.no_preflight:
        preflight_source_code(code, args.path, auto_install=not args.no_parser_install)

    payload, fragment, source_kind, source_sha256 = build_publish_payload(args, code)
    fragment_sha256 = hashlib.sha256(fragment.encode("utf-8")).hexdigest()
    if not args.dry_run:
        require_secure_publish_api_base_url(args.api_base_url)
    operation = "create" if creating else "update"
    endpoint = (
        args.api_base_url.rstrip("/")
        if creating
        else append_url_segments(args.api_base_url, args.username, args.slug)
    )
    dry_run_username = args.username or "<created-username>"
    dry_run_slug = args.slug or "<created-slug>"

    if args.dry_run:
        live_url = (
            f"{args.live_base_url.rstrip('/')}/{dry_run_username}/{dry_run_slug}"
            if creating
            else append_url_segments(args.live_base_url, args.username, args.slug)
        )
        app_link = {
            "username": dry_run_username if creating else args.username,
            "slug": dry_run_slug if creating else args.slug,
        }
        body = dry_run_mmdx_request_body(
            args,
            endpoint=endpoint,
            method="POST" if creating else "PATCH",
            upstream_path="/api/app-links" if creating else f"/api/app-links/{args.username}/{args.slug}",
            user_agent="buildooor-mmdx-publish-link/1.0",
        )
        body.update(
            {
                "operation": operation,
                "url": live_url,
                "app_link": app_link,
                "username": app_link["username"],
                "slug": app_link["slug"],
                "source_kind": source_kind,
                "source_sha256": source_sha256,
                "fragment_sha256": fragment_sha256,
                "diagram_state_format": "mermaid-live-pako",
                "live_verification": "not_run",
                "metadata_written": False,
            }
        )
        if args.summary:
            body["payload_summary"] = {
                "app_slug": payload["app_slug"],
                "resource_kind": payload["resource_kind"],
                "target_path": payload["target_path"],
                "title": payload["title"],
                "slug": payload.get("slug"),
                "metadata": {
                    "diagram_state_format": payload["metadata"]["diagram_state_format"],
                    "source_kind": payload["metadata"]["source_kind"],
                    "hosted_record_count": payload["metadata"]["hosted_record_count"],
                    "source_sha256": source_sha256,
                    "diagram_state_bytes": len(fragment.encode("utf-8")),
                },
            }
        else:
            body["payload"] = payload
        print(
            json.dumps(
                body,
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    access_token = resolve_publish_access_token(args)
    if creating:
        response = create_app_link(
            endpoint,
            payload,
            access_token=access_token,
            origin=args.origin,
            timeout=args.timeout,
        )
        app_link = app_link_from_response(response)
    else:
        patch_app_link(
            endpoint,
            payload,
            access_token=access_token,
            origin=args.origin,
            timeout=args.timeout,
        )
        app_link = {
            "username": str(args.username),
            "slug": str(args.slug),
        }
    live_url = append_url_segments(args.live_base_url, app_link["username"], app_link["slug"])

    if args.skip_live_verify:
        verification = "skipped"
    else:
        live_fragment = fetch_live_diagram_fragment(live_url, timeout=args.timeout)
        if live_fragment != fragment:
            raise MmdNetworkVerificationError(
                "live verification failed: live initialDiagramFragment does not match local source"
            )
        verification = "OK"

    metadata_written = False
    if args.write_short_link_metadata:
        write_mmdx_short_link_metadata(args.path, username=app_link["username"], slug=app_link["slug"])
        metadata_written = True

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": False,
                    "operation": operation,
                    "url": live_url,
                    "app_link": app_link,
                    "username": app_link["username"],
                    "slug": app_link["slug"],
                    "source_kind": source_kind,
                    "source_sha256": source_sha256,
                    "fragment_sha256": fragment_sha256,
                    "diagram_state_format": "mermaid-live-pako",
                    "live_verification": verification,
                    "metadata_written": metadata_written,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        action_label = "Created" if creating else "Updated"
        print(f"{action_label} {live_url}")
        print(f"username={app_link['username']}")
        print(f"slug={app_link['slug']}")
        print(f"source_kind={source_kind}")
        print(f"source_sha256={source_sha256}")
        print(f"diagram_state_format=mermaid-live-pako")
        print(f"live_verification={verification}")
        if metadata_written:
            print("metadata_written=true")
    return 0


def list_mmdx_diagrams(args: argparse.Namespace) -> int:
    require_secure_api_base_url(args.api_base_url, "list")
    endpoint = build_owner_list_endpoint(args)

    if args.dry_run:
        body = dry_run_mmdx_request_body(
            args,
            endpoint=endpoint,
            method="GET",
            upstream_path="/v1/mmdx/diagrams",
            user_agent="buildooor-mmdx-list/1.0",
        )
        body["filters"] = {
            "visibility": args.visibility,
            "slug_contains": args.slug_contains,
            "limit": args.limit,
            "offset": args.offset,
        }
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0

    access_token = resolve_publish_access_token(args, command_name="list")
    payload = get_mmdx_owner_list(
        endpoint,
        access_token=access_token,
        origin=args.origin,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_owner_diagram_table(payload)
    return 0


def versions_mmdx_diagram(args: argparse.Namespace) -> int:
    require_secure_api_base_url(args.api_base_url, "versions")
    endpoint = append_url_segments(args.api_base_url, "diagrams", args.diagram_id, "versions")

    if args.dry_run:
        print(
            json.dumps(
                dry_run_mmdx_request_body(
                    args,
                    endpoint=endpoint,
                    method="GET",
                    upstream_path=f"/v1/mmdx/diagrams/{args.diagram_id}/versions",
                    user_agent="buildooor-mmdx-versions/1.0",
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    access_token = resolve_publish_access_token(args, command_name="versions")
    payload = request_mmdx_json(
        endpoint,
        method="GET",
        access_token=access_token,
        origin=args.origin,
        timeout=args.timeout,
        label="versions",
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_version_table(payload)
    return 0


def sharing_mmdx_diagram(args: argparse.Namespace) -> int:
    require_secure_api_base_url(args.api_base_url, "sharing")
    payload = build_sharing_payload(args)
    endpoint = append_url_segments(args.api_base_url, "diagrams", args.diagram_id, "sharing")

    if args.dry_run:
        print(
            json.dumps(
                dry_run_mmdx_request_body(
                    args,
                    endpoint=endpoint,
                    method="PATCH",
                    upstream_path=f"/v1/mmdx/diagrams/{args.diagram_id}/sharing",
                    user_agent="buildooor-mmdx-sharing/1.0",
                    payload=payload,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    access_token = resolve_publish_access_token(args, command_name="sharing")
    result = request_mmdx_json(
        endpoint,
        payload,
        method="PATCH",
        access_token=access_token,
        origin=args.origin,
        timeout=args.timeout,
        label="sharing",
    )
    if args.json:
        print(json.dumps({"ok": True, "diagram_id": args.diagram_id, "sharing": result}, indent=2, ensure_ascii=False))
    else:
        print(f"Updated MMDX sharing {args.diagram_id}")
        if args.visibility:
            print(f"visibility={args.visibility}")
        if args.title:
            print(f"title={args.title}")
        if args.chart_slug:
            print(f"chart_slug={args.chart_slug}")
    return 0


def delete_mmdx_diagram(args: argparse.Namespace) -> int:
    if not args.yes:
        raise ValueError("delete requires --yes to confirm the destructive operation")

    require_secure_api_base_url(args.api_base_url, "delete")
    endpoint = append_url_segments(args.api_base_url, "diagrams", args.diagram_id)

    if args.dry_run:
        print(
            json.dumps(
                dry_run_mmdx_request_body(
                    args,
                    endpoint=endpoint,
                    method="DELETE",
                    upstream_path=f"/v1/mmdx/diagrams/{args.diagram_id}",
                    user_agent="buildooor-mmdx-delete/1.0",
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    access_token = resolve_publish_access_token(args, command_name="delete")
    result = request_mmdx_json(
        endpoint,
        method="DELETE",
        access_token=access_token,
        origin=args.origin,
        timeout=args.timeout,
        label="delete",
    )
    if args.json:
        print(json.dumps({"ok": True, "diagram_id": args.diagram_id, "delete": result}, indent=2, ensure_ascii=False))
    else:
        deleted_id = result.get("id") if isinstance(result.get("id"), str) else args.diagram_id
        print(f"Deleted MMDX diagram {deleted_id}")
    return 0


def latest_version_id_from_response(payload: dict[str, Any]) -> str | None:
    nav = payload.get("nav")
    if isinstance(nav, dict):
        latest = nav.get("latest_version_id") or nav.get("current_version_id")
        if isinstance(latest, str) and latest.strip():
            return latest.strip()
    version = payload.get("version")
    if isinstance(version, dict):
        version_id = version.get("id")
        if isinstance(version_id, str) and version_id.strip():
            return version_id.strip()
    diagram = payload.get("diagram")
    if isinstance(diagram, dict):
        latest = diagram.get("latest_version_id")
        if isinstance(latest, str) and latest.strip():
            return latest.strip()
    return None


def latest_mmdx_text_from_response(payload: dict[str, Any]) -> str | None:
    version = payload.get("version")
    if isinstance(version, dict):
        text = version.get("mmdx_text")
        if isinstance(text, str):
            return text
    return None


def response_diagram_id(payload: dict[str, Any]) -> str | None:
    diagram = payload.get("diagram")
    if isinstance(diagram, dict):
        diagram_id = diagram.get("id")
        if isinstance(diagram_id, str) and diagram_id.strip():
            return diagram_id.strip()
    version = payload.get("version")
    if isinstance(version, dict):
        diagram_id = version.get("diagram_id")
        if isinstance(diagram_id, str) and diagram_id.strip():
            return diagram_id.strip()
    return None


def save_mmdx_diagram(args: argparse.Namespace) -> int:
    code = _read_text(args.path)
    if not args.no_preflight:
        preflight_source_code(code, args.path, auto_install=not args.no_parser_install)

    require_secure_api_base_url(args.api_base_url, "save")
    creating = not bool((args.diagram_id or "").strip())
    source_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
    latest_endpoint = (
        append_url_segments(args.api_base_url, "diagrams", args.diagram_id, "latest") if not creating else None
    )
    resolved_base_version_id = args.base_version_id
    resolved_parent_version_id = args.parent_version_id

    if creating:
        endpoint = append_url_segments(args.api_base_url, "diagrams")
        payload = build_create_diagram_payload(args, code)
        method_label = "create"
    else:
        endpoint = append_url_segments(args.api_base_url, "diagrams", args.diagram_id, "versions")
        method_label = "append"
        if args.dry_run and not resolved_base_version_id:
            resolved_base_version_id = "<resolved from /latest>"
        elif not resolved_base_version_id:
            access_token = resolve_publish_access_token(args, command_name="save")
            latest = get_mmdx_latest_version(
                latest_endpoint or "",
                access_token=access_token,
                origin=args.origin,
                timeout=args.timeout,
            )
            resolved_base_version_id = latest_version_id_from_response(latest)
            if not resolved_base_version_id:
                raise MmdNetworkVerificationError("MMDX latest lookup did not return a latest version id")
            if resolved_parent_version_id is None:
                resolved_parent_version_id = resolved_base_version_id
        payload = build_append_version_payload(
            args,
            code,
            base_version_id=resolved_base_version_id,
            parent_version_id=resolved_parent_version_id,
        )

    if args.dry_run:
        auth_metadata = dry_run_auth_metadata(args)
        body: dict[str, Any] = {
            "ok": True,
            "dry_run": True,
            "operation": method_label,
            "endpoint": endpoint,
            "latest_endpoint": latest_endpoint,
            "method": "POST",
            "source_sha256": source_sha256,
            "latest_verification": "not_run",
            "headers": {
                "Accept": "application/json",
                "Authorization": auth_metadata["Authorization"],
                "Origin": args.origin,
                "User-Agent": "buildooor-mmdx-save/1.0",
            },
            "auth_source": auth_metadata["source"],
            "network": False,
        }
        if args.summary:
            payload_summary = dict(payload)
            if "mmdx_text" in payload_summary:
                payload_summary["mmdx_text_sha256"] = source_sha256
                payload_summary["mmdx_text_bytes"] = len(code.encode("utf-8"))
                payload_summary["mmdx_text"] = "<omitted>"
            body["payload_summary"] = payload_summary
        else:
            body["payload"] = payload
        print(
            json.dumps(
                body,
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    access_token = resolve_publish_access_token(args, command_name="save")
    saved = post_mmdx_save(
        endpoint,
        payload,
        access_token=access_token,
        origin=args.origin,
        timeout=args.timeout,
        label=method_label,
    )
    diagram_id = response_diagram_id(saved) or args.diagram_id
    latest = get_mmdx_latest_version(
        append_url_segments(args.api_base_url, "diagrams", diagram_id, "latest"),
        access_token=access_token,
        origin=args.origin,
        timeout=args.timeout,
    )
    latest_text = latest_mmdx_text_from_response(latest)
    latest_verification: SaveVerificationStatus = "ok"
    verification_warning = None
    if latest_text is None:
        latest_verification = "indeterminate"
        verification_warning = "MMDX save verification indeterminate: server did not echo mmdx_text"
        if not args.allow_unverified:
            raise MmdSaveVerificationError(latest_verification, verification_warning)
    elif latest_text != code:
        raise MmdSaveVerificationError(
            "mismatch",
            "MMDX save verification failed: latest mmdx_text does not match local source",
        )

    if args.json:
        body: dict[str, Any] = {
            "ok": True,
            "latest_verification": latest_verification,
            "source_sha256": source_sha256,
            "diagram_id": diagram_id,
            "version_id": latest_version_id_from_response(saved) or latest_version_id_from_response(latest),
            "save": saved,
            "latest": latest,
        }
        if verification_warning is not None:
            body["warnings"] = [
                {
                    "type": "MmdSaveVerificationWarning",
                    "message": verification_warning,
                }
            ]
        print(json.dumps(body, indent=2, ensure_ascii=False))
    else:
        version_id = latest_version_id_from_response(saved) or latest_version_id_from_response(latest) or ""
        if verification_warning is not None:
            print(f"warning: {verification_warning}", file=sys.stderr)
        print(f"Saved durable MMDX diagram {diagram_id}")
        if version_id:
            print(f"version_id={version_id}")
        print(f"source_sha256={source_sha256}")
        print(f"latest_verification={latest_verification}")
    return 0


def _resolve_paid_resource(args: argparse.Namespace) -> dict[str, str] | None:
    metadata = _parse_paid_resource_metadata(args.paid_resource)
    paid_intent = bool(
        args.paid_resource
        or args.paid_resource_verify_url
        or args.paid_resource_api_key
        or args.paid_resource_resource_key
        or args.paid_resource_action_key
        or args.paid_resource_target
        or os.environ.get("SPAPS_HANDOFF_VERIFY_URL")
        or os.environ.get("SPAPS_HANDOFF_RESOURCE_KEY")
        or os.environ.get("SPAPS_HANDOFF_ACTION_KEY")
        or os.environ.get("SPAPS_HANDOFF_TARGET")
    )
    if not paid_intent:
        return None

    verify_url = args.paid_resource_verify_url or os.environ.get("SPAPS_HANDOFF_VERIFY_URL")
    api_key = args.paid_resource_api_key or os.environ.get("SPAPS_API_KEY")
    resource_key = (
        args.paid_resource_resource_key
        or os.environ.get("SPAPS_HANDOFF_RESOURCE_KEY")
        or str((metadata or {}).get("resource_key") or (metadata or {}).get("resourceKey") or "").strip()
    )
    action_key = (
        args.paid_resource_action_key
        or os.environ.get("SPAPS_HANDOFF_ACTION_KEY")
        or str((metadata or {}).get("action_key") or (metadata or {}).get("actionKey") or "").strip()
    )
    target = (
        args.paid_resource_target
        or os.environ.get("SPAPS_HANDOFF_TARGET")
        or str((metadata or {}).get("target") or "").strip()
    )
    if not verify_url or not api_key:
        raise ValueError(
            "paid resource requires both a verify URL "
            "(--paid-resource-verify-url or SPAPS_HANDOFF_VERIFY_URL) "
            "and an API key (--paid-resource-api-key or SPAPS_API_KEY)"
        )
    if not resource_key or not action_key:
        raise ValueError(
            "paid resource requires resource and action keys "
            "(--paid-resource-resource-key/--paid-resource-action-key, "
            "SPAPS_HANDOFF_RESOURCE_KEY/SPAPS_HANDOFF_ACTION_KEY, "
            "or paid-resource metadata resource_key/action_key)"
        )
    if not target:
        raise ValueError(
            "paid resource requires a target "
            "(--paid-resource-target, SPAPS_HANDOFF_TARGET, or paid-resource metadata target)"
        )
    result = {"verify_url": verify_url, "api_key": api_key}
    result["resource_key"] = resource_key
    result["action_key"] = action_key
    result["target"] = target
    return result


def _parse_paid_resource_metadata(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        raise ValueError("--paid-resource must be a JSON object")
    return metadata


def exit_code_for_exception(exc: BaseException) -> int:
    if isinstance(exc, MmdAuthError):
        return EXIT_AUTH
    if isinstance(exc, MmdNetworkVerificationError):
        return EXIT_NETWORK_VERIFICATION
    return EXIT_VALIDATION


def build_json_error(exc: BaseException, exit_code: int) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ok": False,
        "exit_code": exit_code,
        "errors": [
            {
                "type": exc.__class__.__name__,
                "message": str(exc),
            }
        ],
    }
    if isinstance(exc, MmdSaveVerificationError):
        body["latest_verification"] = exc.latest_verification
    if isinstance(exc, MmdAppLinkMutationError):
        body["status_code"] = exc.status_code
        body["operation"] = exc.operation
        body["error_code"] = exc.error_code
        body["error"] = exc.payload.get("error") if isinstance(exc.payload.get("error"), dict) else exc.payload
    if isinstance(exc, MmdPaywallError):
        body["price_display"] = exc.price_display
    return body


def _public_paid_resource_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key in PUBLIC_PAID_RESOURCE_KEYS and isinstance(value, (str, int, float, bool))
    }


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if getattr(args, "command", None) == "publish-link":
            return publish_link(args)
        if getattr(args, "command", None) == "list":
            return list_mmdx_diagrams(args)
        if getattr(args, "command", None) == "versions":
            return versions_mmdx_diagram(args)
        if getattr(args, "command", None) == "sharing":
            return sharing_mmdx_diagram(args)
        if getattr(args, "command", None) == "delete":
            return delete_mmdx_diagram(args)
        if getattr(args, "command", None) == "save":
            return save_mmdx_diagram(args)

        if args.handoff_server:
            if args.handoff_port is None or not args.handoff_token or not args.tmux_target:
                raise ValueError("--handoff-server requires --handoff-port, --handoff-token, and --tmux-target")
            allowed_origin = resolve_handoff_origin(
                explicit_origin=args.handoff_origin,
                output_base_url=DEFAULT_BASE_URL,
            )
            paid_resource = _resolve_paid_resource(args)
            return run_handoff_server(
                args.handoff_host,
                args.handoff_port,
                args.handoff_token,
                args.tmux_target,
                args.handoff_ttl,
                source_path=args.source_path,
                submit_on_send=args.tmux_submit,
                allowed_origin=allowed_origin,
                paid_resource=paid_resource,
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
        if not args.no_preflight:
            mmdx_document = build_mmdx_document(code) if is_mmdx_input(args.path, code) else None
            link_checks = None
            if mmdx_document:
                parse_results = preflight_mmdx_document(mmdx_document, auto_install=not args.no_parser_install)
                link_checks = build_mmdx_link_label_checks(mmdx_document, strict=args.strict_links)
                if args.strict_links:
                    enforce_mmdx_link_label_checks(link_checks)
                elif not args.json:
                    warn_mmdx_link_label_checks(link_checks)
            else:
                parse_results = [preflight_mermaid(code, auto_install=not args.no_parser_install)]
            if args.preflight_only:
                if mmdx_document:
                    if args.json:
                        print(
                            json.dumps(
                                build_preflight_json_success(
                                    document=mmdx_document,
                                    parse_results=parse_results,
                                    link_checks=link_checks,
                                ),
                                indent=2,
                                ensure_ascii=False,
                            )
                        )
                    else:
                        print(f"MMDX preflight OK: {len(parse_results)} charts")
                else:
                    if args.json:
                        print(
                            json.dumps(
                                build_preflight_json_success(
                                    document=None,
                                    parse_results=parse_results,
                                ),
                                indent=2,
                                ensure_ascii=False,
                            )
                        )
                    else:
                        diagram_type = parse_results[0].get("diagramType", "unknown")
                        print(f"Mermaid preflight OK: {diagram_type}")
                return 0
        elif args.preflight_only:
            raise ValueError("--preflight-only cannot be combined with --no-preflight")

        handoff = None
        source_metadata = None
        paid_resource_metadata = _parse_paid_resource_metadata(args.paid_resource)
        output_base_url = resolve_output_base_url(view=args.view, base_url=args.base_url)
        if args.tmux_handoff:
            source_metadata = build_source_metadata(args.path)
            allowed_origin = resolve_handoff_origin(
                explicit_origin=args.handoff_origin,
                output_base_url=output_base_url,
            )
            paid_resource = _resolve_paid_resource(args)
            handoff = start_handoff_channel(
                host=args.handoff_host,
                tmux_target=args.tmux_target,
                ttl_seconds=args.handoff_ttl,
                source_path=source_metadata["path"] if source_metadata else None,
                submit_on_send=args.tmux_submit,
                allowed_origin=allowed_origin,
                paid_resource=paid_resource,
            )

        state, _source_kind, _mmdx_document = build_state_for_source(
            args.path,
            code,
            config=args.config,
            theme=args.theme,
            grid=not args.no_grid,
            pan_zoom=not args.no_pan_zoom,
            rough=args.rough,
            handoff=handoff,
            source=source_metadata,
            paid_resource=paid_resource_metadata,
        )
        fragment = encode_state(state)
        output = fragment if args.fragment_only else build_url(fragment, base_url=output_base_url)
        print(output)
        if args.open:
            open_generated_url(output)
        return 0
    except (
        OSError,
        json.JSONDecodeError,
        MmdAuthError,
        MmdNetworkVerificationError,
        RuntimeError,
        ValueError,
        zlib.error,
        subprocess.CalledProcessError,
    ) as exc:
        exit_code = exit_code_for_exception(exc)
        if args is not None and getattr(args, "json", False):
            if getattr(args, "preflight_only", False):
                payload = build_preflight_json_error(exc, exit_code)
            else:
                payload = build_json_error(exc, exit_code)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"mmd: {exc}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
