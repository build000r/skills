#!/usr/bin/env python3
"""Portability tests for the MMDX skill-family helper paths."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PortablePathTests(unittest.TestCase):
    def test_mmdx_index_defaults_are_checkout_relative(self) -> None:
        module = load_module(
            "mmdx_index_under_test",
            SKILLS_ROOT / "mmdx" / "scripts" / "mmdx_index.py",
        )

        self.assertEqual(module.default_scan_roots(), [SKILLS_ROOT])
        self.assertEqual(
            module.DEFAULT_OUTPUT,
            SKILLS_ROOT / "mmdx" / "scripts" / "INDEX.mmdx",
        )

    def test_mmdx_index_resolves_configurable_paths(self) -> None:
        module = load_module(
            "mmdx_index_under_test_configurable",
            SKILLS_ROOT / "mmdx" / "scripts" / "mmdx_index.py",
        )
        root = SKILLS_ROOT / "project-status-mmdx"
        output = SKILLS_ROOT / "mmdx" / "scripts" / "custom-index.mmdx"

        self.assertEqual(module.resolve_scan_roots([str(root)]), [root.resolve()])
        self.assertEqual(module.resolve_output(str(output)), output.resolve())

    def test_registry_scanner_default_mmd_script_is_sibling_skill(self) -> None:
        module = load_module(
            "scan_mmdx_registry_under_test",
            SKILLS_ROOT
            / "mmdx-registry-usage-audit"
            / "scripts"
            / "scan_mmdx_registry.py",
        )

        self.assertEqual(
            module.DEFAULT_MMD_SCRIPT,
            SKILLS_ROOT / "mmdx" / "scripts" / "mmd.py",
        )


if __name__ == "__main__":
    unittest.main()
