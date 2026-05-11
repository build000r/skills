from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "_shared" / "scripts" / "domain_context_snapshot.py"


def _load_module():
    script_dir = SCRIPT_PATH.parent
    spec = importlib.util.spec_from_file_location("domain_context_snapshot_for_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class DomainContextSnapshotTests(unittest.TestCase):
    def test_snapshot_reports_overlay_paths_and_slice_files(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repos_root = root / "repos"
            cwd = repos_root / "app"
            overlay_dir = repos_root / "skillbox-config" / "clients" / "example"
            plan_root = overlay_dir / "plans" / "released"
            plan_dir = plan_root / "billing"
            repo_dir = repos_root / "backend"
            cwd.mkdir(parents=True)
            plan_dir.mkdir(parents=True)
            repo_dir.mkdir(parents=True)
            (plan_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
            (plan_dir / "shared.md").write_text("# Shared\n", encoding="utf-8")
            (overlay_dir / "context.yaml").write_text(
                "cwd_match:\n"
                f"  - {repos_root}\n"
                "plans:\n"
                f"  plan_root: {plan_root}\n"
                f"  plan_index: {overlay_dir / 'plans' / 'INDEX.md'}\n"
                "backend:\n"
                f"  repo: {repo_dir}\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SKILLBOX_CLIENT_CONTEXT", None)
                snapshot = module.build_snapshot(str(cwd), "billing")

        self.assertEqual(snapshot["cwd"], str(cwd))
        self.assertIn("plans", snapshot["sections"])
        self.assertTrue(snapshot["sections"]["backend"]["paths"]["repo"]["exists"])
        self.assertTrue(snapshot["slice"]["required_plan_files"]["plan.md"])
        self.assertFalse(snapshot["slice"]["required_plan_files"]["backend.md"])


if __name__ == "__main__":
    unittest.main()
