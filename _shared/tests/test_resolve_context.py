from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "_shared" / "scripts" / "resolve_context.py"


def _load_module():
    script_dir = SCRIPT_PATH.parent
    spec = importlib.util.spec_from_file_location("resolve_context_for_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class ResolveContextTests(unittest.TestCase):
    def test_placeholder_cwd_match_expands_for_local_overlay_resolution(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repos_root = root / "repos"
            repo_cwd = repos_root / "skillbox-config"
            overlay_dir = repo_cwd / "clients" / "personal"
            overlay_dir.mkdir(parents=True, exist_ok=True)

            (overlay_dir / "overlay.yaml").write_text(
                "version: 1\n"
                "client:\n"
                "  id: personal\n"
                "  label: Personal\n"
                "  default_cwd: ${SKILLBOX_MONOSERVER_ROOT}/skillbox-config\n"
                "  context:\n"
                "    cwd_match:\n"
                "      - ${SKILLBOX_MONOSERVER_ROOT}\n"
                "    workflow_builder:\n"
                "      invocation_root: invocations\n",
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {"SKILLBOX_MONOSERVER_ROOT": str(repos_root)},
                clear=False,
            ):
                payload = module.resolve(str(repo_cwd))

        self.assertIsNotNone(payload)
        self.assertEqual(payload["id"], "personal")
        self.assertEqual(payload["context"]["cwd_match"], ["${SKILLBOX_MONOSERVER_ROOT}"])


if __name__ == "__main__":
    unittest.main()
