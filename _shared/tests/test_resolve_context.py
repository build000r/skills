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

    def test_generated_local_context_beats_unexpanded_overlay_placeholders(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repos_root = root / "repos"
            overlay_root = repos_root / "skillbox-config"
            overlay_dir = overlay_root / "clients" / "personal"
            overlay_dir.mkdir(parents=True, exist_ok=True)

            (overlay_dir / "overlay.yaml").write_text(
                "version: 1\n"
                "client:\n"
                "  id: personal\n"
                "  context:\n"
                "    cwd_match:\n"
                "      - ${SKILLBOX_MONOSERVER_ROOT}\n"
                "    plans:\n"
                "      plan_index: ${SKILLBOX_MONOSERVER_ROOT}/skillbox-config/clients/personal/plans/INDEX.md\n",
                encoding="utf-8",
            )
            (overlay_dir / "context.yaml").write_text(
                "cwd_match:\n"
                f"  - {repos_root}\n"
                "plans:\n"
                f"  plan_index: {overlay_dir / 'plans' / 'INDEX.md'}\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SKILLBOX_MONOSERVER_ROOT", None)
                os.environ.pop("SKILLBOX_CLIENT_CONTEXT", None)
                payload = module.resolve(str(repos_root), section="plans")

        self.assertEqual(
            payload,
            {"plan_index": str(overlay_dir / "plans" / "INDEX.md")},
        )

    def test_env_context_wraps_scalar_sections_like_local_context(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            context_path = Path(tmpdir) / "context.yaml"
            context_path.write_text(
                "cwd_match:\n"
                "  - /tmp\n"
                "feature_flag: enabled\n",
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {"SKILLBOX_CLIENT_CONTEXT": str(context_path)},
                clear=False,
            ):
                payload = module.resolve("/tmp", section="feature_flag")

        self.assertEqual(payload, {"value": "enabled"})

    def test_workspace_context_wraps_scalar_sections_like_local_context(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            cwd_root = root / "example"
            cwd = cwd_root / "app"
            cwd.mkdir(parents=True)
            context_path = root / "clients" / "example" / "context.yaml"
            context_path.parent.mkdir(parents=True)
            context_path.write_text(
                "cwd_match:\n"
                f"  - {cwd_root}\n"
                "feature_flag: enabled\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "WORKSPACE_CLIENTS_GLOB", str(context_path)):
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("SKILLBOX_CLIENT_CONTEXT", None)
                    payload = module.resolve(str(cwd), section="feature_flag")

        self.assertEqual(payload, {"value": "enabled"})


if __name__ == "__main__":
    unittest.main()
