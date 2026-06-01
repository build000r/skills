import json
import subprocess
import sys
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "manage_overlays.py"


def write_overlay(path: Path, client_id: str, cwd_match: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "client": {
                    "id": client_id,
                    "label": client_id,
                    "context": {"cwd_match": [cwd_match]},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def write_context(path: Path, client_id: str, cwd_match: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "cwd_match": [cwd_match],
                "client_id": client_id,
                "client_dir": str(path.parent),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_match_scans_all_upward_config_roots_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "opensource" / "project"
    repo.mkdir(parents=True)
    inner_root = tmp_path / "repos" / "opensource" / "skillbox-config" / "clients"
    outer_root = tmp_path / "repos" / "skillbox-config" / "clients"
    write_overlay(inner_root / "other" / "overlay.yaml", "other", str(tmp_path / "other"))
    write_overlay(outer_root / "project" / "overlay.yaml", "project", str(repo))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "match", "--cwd", str(repo), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["config_roots"] == [str(inner_root), str(outer_root)]
    assert [match["client_id"] for match in data["matches"]] == ["project"]
    assert data["matches"][0]["config_root"] == str(outer_root)


def test_match_prefers_repo_local_buildooor_root_on_tie(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "project"
    repo.mkdir(parents=True)
    local_root = repo / ".buildooor" / "skillbox-config" / "clients"
    outer_root = tmp_path / "repos" / "skillbox-config" / "clients"
    write_overlay(local_root / "project-local" / "overlay.yaml", "project-local", str(repo))
    write_overlay(outer_root / "project-global" / "overlay.yaml", "project-global", str(repo))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "match", "--cwd", str(repo), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["config_roots"] == [str(local_root), str(outer_root)]
    assert [match["client_id"] for match in data["matches"]] == ["project-local"]
    assert data["matches"][0]["config_root"] == str(local_root)


def test_match_scans_from_supplied_cwd_not_process_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "project"
    repo.mkdir(parents=True)
    local_root = repo / ".buildooor" / "skillbox-config" / "clients"
    write_overlay(local_root / "project" / "overlay.yaml", "project", str(repo))

    outside = tmp_path / "outside"
    outside.mkdir()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "match", "--cwd", str(repo), "--json"],
        cwd=outside,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["config_roots"] == [str(local_root)]
    assert [match["client_id"] for match in data["matches"]] == ["project"]


def test_match_miss_reports_target_cwd_fallback_root(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "project"
    repo.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "match", "--cwd", str(repo), "--json"],
        cwd=outside,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["config_roots"] == [str(repo / ".buildooor" / "skillbox-config" / "clients")]
    assert data["matches"] == []


def test_match_with_explicit_config_root_remains_scoped(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "opensource" / "project"
    repo.mkdir(parents=True)
    inner_root = tmp_path / "repos" / "opensource" / "skillbox-config" / "clients"
    outer_root = tmp_path / "repos" / "skillbox-config" / "clients"
    write_overlay(inner_root / "other" / "overlay.yaml", "other", str(tmp_path / "other"))
    write_overlay(outer_root / "project" / "overlay.yaml", "project", str(repo))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config-root",
            str(inner_root),
            "match",
            "--cwd",
            str(repo),
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["matches"] == []


def test_list_reports_non_mapping_overlay_without_crashing(tmp_path: Path) -> None:
    root = tmp_path / "clients"
    bad_overlay = root / "bad" / "overlay.yaml"
    bad_overlay.parent.mkdir(parents=True)
    bad_overlay.write_text("- not\n- a mapping\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--config-root", str(root), "list", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["overlays"] == [
        {
            "client_id": "bad",
            "path": str(bad_overlay),
            "error": "overlay.yaml must contain a YAML mapping, got list",
        }
    ]


def test_create_defaults_to_repo_local_buildooor_root(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "project"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    outer_root = tmp_path / "repos" / "skillbox-config" / "clients"
    write_overlay(outer_root / "existing" / "overlay.yaml", "existing", str(tmp_path / "other"))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "create",
            "--client-id",
            "project",
            "--cwd",
            str(repo),
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    target = repo / ".buildooor" / "skillbox-config" / "clients" / "project" / "overlay.yaml"
    assert json.loads(result.stdout)["created"] == str(target)
    assert target.is_file()


def test_match_uses_path_segment_boundaries(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "htma_server"
    repo.mkdir(parents=True)
    root = tmp_path / "repos" / "skillbox-config" / "clients"
    write_overlay(root / "htma" / "overlay.yaml", "htma", str(tmp_path / "repos" / "htma"))
    write_overlay(root / "server" / "overlay.yaml", "server", str(repo))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "match", "--cwd", str(repo), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert [match["client_id"] for match in json.loads(result.stdout)["matches"]] == ["server"]


def test_generated_context_can_match_placeholder_overlay(tmp_path: Path) -> None:
    repo = tmp_path / "repos" / "opensource" / "spaps-website"
    repo.mkdir(parents=True)
    root = tmp_path / "repos" / "skillbox-config" / "clients"
    overlay = root / "spaps-website" / "overlay.yaml"
    write_overlay(
        overlay,
        "spaps-website",
        "${SKILLBOX_MONOSERVER_ROOT}/opensource/spaps-website",
    )
    write_context(root / "spaps-website" / "context.yaml", "spaps-website", str(repo))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "match", "--cwd", str(repo), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    matches = json.loads(result.stdout)["matches"]
    assert [match["client_id"] for match in matches] == ["spaps-website"]
    assert matches[0]["path"] == str(overlay)
    assert matches[0]["source_kind"] == "context"
