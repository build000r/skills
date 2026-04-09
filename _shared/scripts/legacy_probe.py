#!/usr/bin/env python3
"""Read-only probes for bootstrapping skillbox-config overlays."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

try:
    import yaml
except ModuleNotFoundError:
    yaml = None  # type: ignore[assignment]


ENV_CANDIDATES = (
    ".env",
    ".env.override",
)


@dataclass(frozen=True)
class ProbeFinding:
    key: str
    value: str
    source: str


def _normalize_path(value: str) -> str:
    return os.path.realpath(os.path.expanduser(value))


def _relative_source(path: Path, cwd: Path, line: int) -> str:
    try:
        label = str(path.resolve().relative_to(cwd.resolve()))
    except ValueError:
        label = str(path.resolve())
    return f"{label}:{line}"


def _suggest_client_id(cwd: str) -> str:
    raw = Path(cwd).name or "client"
    suggestion = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")
    return suggestion or "client"


def _titleize_client_id(client_id: str) -> str:
    return client_id.replace("-", " ").replace("_", " ").title()


def _scrub_url_password(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    if not parsed.scheme or "@" not in parsed.netloc:
        return value

    userinfo, hostinfo = parsed.netloc.rsplit("@", 1)
    if ":" not in userinfo:
        return value

    username, _password = userinfo.split(":", 1)
    scrubbed = SplitResult(
        scheme=parsed.scheme,
        netloc=f"{username}:***@{hostinfo}",
        path=parsed.path,
        query=parsed.query,
        fragment=parsed.fragment,
    )
    return urlunsplit(scrubbed)


def _parse_repo_slug(remote_url: str) -> str | None:
    ssh_match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return f"{ssh_match.group(1)}/{ssh_match.group(2)}"
    return None


def _env_probe(root: Path) -> list[ProbeFinding]:
    findings: list[ProbeFinding] = []
    env_files = [root / name for name in ENV_CANDIDATES]
    env_files.extend(sorted(root.glob(".env.production*")))

    for env_file in env_files:
        if not env_file.is_file():
            continue
        for line_no, raw_line in enumerate(env_file.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
            if not match:
                continue

            key, value = match.groups()
            if key != "DATABASE_URL":
                continue

            findings.append(
                ProbeFinding(
                    key="database_url",
                    value=_scrub_url_password(value.strip().strip("'").strip('"')),
                    source=_relative_source(env_file, root, line_no),
                )
            )
            return findings

    return findings


def _git_remote_probe(root: Path) -> list[ProbeFinding]:
    try:
        git_dir = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-dir"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return []

    git_dir_path = Path(git_dir)
    if not git_dir_path.is_absolute():
        git_dir_path = (root / git_dir_path).resolve()

    config_path = git_dir_path / "config"
    if not config_path.is_file():
        return []

    in_origin = False
    for line_no, raw_line in enumerate(config_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("[remote "):
            in_origin = stripped == '[remote "origin"]'
            continue
        if not in_origin or not stripped.startswith("url = "):
            continue
        repo_slug = _parse_repo_slug(stripped.split("=", 1)[1].strip())
        if repo_slug:
            return [
                ProbeFinding(
                    key="repo_slug",
                    value=repo_slug,
                    source=_relative_source(config_path, root, line_no),
                )
            ]
    return []


def _workflow_probe(root: Path) -> list[ProbeFinding]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []

    workflows = sorted(list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")))
    if not workflows:
        return []

    preferred = sorted(workflows, key=lambda path: ("deploy" not in path.name.lower(), path.name.lower()))
    selected = preferred[0]
    return [
        ProbeFinding(
            key="ci_workflow",
            value=_relative_source(selected, root, 1).rsplit(":", 1)[0],
            source=_relative_source(selected, root, 1),
        )
    ]


def _compose_candidates(root: Path) -> list[Path]:
    ordered: list[Path] = []
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        path = root / name
        if path.is_file() and path not in ordered:
            ordered.append(path)
    for pattern in ("docker-compose*.yml", "docker-compose*.yaml", "*compose*.yml", "*compose*.yaml"):
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in ordered:
                ordered.append(path)
    return ordered


def _first_service_line(path: Path) -> int:
    in_services = False
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw_line.strip() == "services:":
            in_services = True
            continue
        if in_services and re.match(r"^\s{2,}[A-Za-z0-9_.-]+:\s*$", raw_line):
            return line_no
    return 1


def _compose_probe(root: Path) -> list[ProbeFinding]:
    if yaml is None:
        return []

    for compose_file in _compose_candidates(root):
        try:
            data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        services = data.get("services")
        if not isinstance(services, dict) or not services:
            continue

        source_line = _first_service_line(compose_file)
        service_names = [str(name) for name in services.keys()]
        return [
            ProbeFinding(
                key="surface",
                value="docker_compose",
                source=_relative_source(compose_file, root, 1),
            ),
            ProbeFinding(
                key="compose_file",
                value=_relative_source(compose_file, root, 1).rsplit(":", 1)[0],
                source=_relative_source(compose_file, root, 1),
            ),
            ProbeFinding(
                key="containers",
                value=",".join(service_names),
                source=_relative_source(compose_file, root, source_line),
            ),
        ]
    return []


def probe_legacy_sources(cwd: str) -> list[ProbeFinding]:
    root = Path(_normalize_path(cwd))
    findings: list[ProbeFinding] = []
    for probe in (_env_probe, _git_remote_probe, _workflow_probe, _compose_probe):
        findings.extend(probe(root))
    return findings


def _stub_deploy_config(cwd: str, findings: list[ProbeFinding]) -> dict[str, Any]:
    values = {finding.key: finding.value for finding in findings}
    deploy: dict[str, Any] = {
        "mode_name": Path(cwd).name or "repo",
        "surface": values.get("surface", ""),
        "repo_root": cwd,
    }

    if "repo_slug" in values:
        deploy["repo_slug"] = values["repo_slug"]
    if "compose_file" in values:
        deploy["compose_file"] = values["compose_file"]
    if "ci_workflow" in values:
        deploy["ci_workflow"] = values["ci_workflow"]
    if "containers" in values:
        deploy["containers"] = values["containers"].split(",")

    return deploy


def build_overlay_stub(cwd: str, *, client_id: str | None = None) -> dict[str, Any]:
    cwd = _normalize_path(cwd)
    suggestion = client_id or _suggest_client_id(cwd)
    return {
        "version": 1,
        "client": {
            "id": suggestion,
            "label": _titleize_client_id(suggestion),
            "default_cwd": cwd,
            "repos": [],
            "logs": [],
            "context": {
                "cwd_match": [cwd],
                "deploy": _stub_deploy_config(cwd, probe_legacy_sources(cwd)),
            },
            "checks": [],
        },
    }


def format_legacy_transition_error(cwd: str) -> str:
    cwd = _normalize_path(cwd)
    findings = probe_legacy_sources(cwd)
    suggestion = _suggest_client_id(cwd)
    stub = build_overlay_stub(cwd, client_id=suggestion)

    lines = [f"Legacy transition: no skillbox-config overlay matches {cwd}."]
    lines.append(f"Probed legacy sources in {cwd} for inferable values:")
    if findings:
        for finding in findings:
            lines.append(f"{finding.key}: {finding.value}  # source: {finding.source}")
    else:
        lines.append("(none)")

    lines.append(f"Suggested overlay stub (paste into skillbox-config/clients/{suggestion}/overlay.yaml):")
    lines.append("---")
    if yaml is None:
        raise RuntimeError("PyYAML required but not installed")
    lines.extend(yaml.safe_dump(stub, sort_keys=False).rstrip().splitlines())
    lines.append("---")
    lines.append("Bootstrap with:")
    lines.append("  python3 ~/.claude/skills/skill-issue/scripts/manage_overlays.py create \\")
    lines.append(
        f"    --client-id {suggestion} --cwd {shlex.quote(cwd)} --json"
    )
    return "\n".join(lines)
