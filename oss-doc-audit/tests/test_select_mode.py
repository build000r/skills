import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "select_mode.py"


class OssDocAuditSelectModeTests(unittest.TestCase):
    def test_resolves_overlay_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "example-client"
            repo.mkdir()

            overlay = {
                "version": 1,
                "client": {
                    "id": "example-client",
                    "label": "Example Client",
                    "default_cwd": str(repo),
                    "repos": [],
                    "logs": [],
                    "context": {
                        "cwd_match": [str(repo)],
                        "oss_doc_audit": {
                            "mode_name": "example-client",
                            "active_codebase_path": "packages/python-server-quickstart/",
                            "deprecated_paths": ["src/"],
                            "baseline_commands": ["python3 scripts/check-oss-hygiene.py"],
                        },
                    },
                    "checks": [],
                },
            }
            overlay_path = root / "skillbox-config" / "clients" / "example-client" / "overlay.yaml"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo), "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["MODE_NAME"], "example-client")
            self.assertEqual(payload["MODE_ACTIVE_CODEBASE_PATH"], "packages/python-server-quickstart/")
            self.assertEqual(payload["MODE_DEPRECATED_PATHS"], "src/")

    def test_errors_when_overlay_matches_but_section_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(os.path.realpath(tmpdir))
            repo = root / "repo"
            repo.mkdir()

            overlay = {
                "version": 1,
                "client": {
                    "id": "example",
                    "label": "Example",
                    "default_cwd": str(repo),
                    "repos": [],
                    "logs": [],
                    "context": {
                        "cwd_match": [str(repo)],
                    },
                    "checks": [],
                },
            }
            overlay_path = root / "skillbox-config" / "clients" / "example" / "overlay.yaml"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("No oss_doc_audit section found in the matching skillbox-config overlay", result.stderr)

    def test_surfaces_legacy_transition_when_no_overlay_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(os.path.realpath(tmpdir))

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Legacy transition: no skillbox-config overlay matches", result.stderr)


if __name__ == "__main__":
    unittest.main()
