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
