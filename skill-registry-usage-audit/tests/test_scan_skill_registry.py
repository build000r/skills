from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_skill_registry.py"
SPEC = importlib.util.spec_from_file_location("scan_skill_registry", SCRIPT)
assert SPEC and SPEC.loader
scan_skill_registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_skill_registry)


class OverlayDriftTests(unittest.TestCase):
    def test_standard_skillbox_overlay_nested_paths_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = root / "skillbox-config" / "clients" / "example" / "overlay.yaml"
            overlay.parent.mkdir(parents=True)
            missing_default = root / "missing-default"
            missing_match = root / "missing-match"
            issues: list[dict[str, str]] = []

            scan_skill_registry.check_overlay(
                overlay,
                {
                    "version": 1,
                    "client": {
                        "id": "example",
                        "default_cwd": str(missing_default),
                        "context": {"cwd_match": [str(missing_match)]},
                    },
                },
                issues,
            )

            messages = {issue["message"] for issue in issues}
            self.assertIn(
                f"client.default_cwd points at a missing path: {missing_default}",
                messages,
            )
            self.assertIn(
                f"client.context.cwd_match points at a missing path: {missing_match}",
                messages,
            )


if __name__ == "__main__":
    unittest.main()
