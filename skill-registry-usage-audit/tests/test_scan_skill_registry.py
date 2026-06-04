from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_skill_registry.py"
SPEC = importlib.util.spec_from_file_location("scan_skill_registry", SCRIPT)
assert SPEC and SPEC.loader
scan_skill_registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_skill_registry)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def skill_manifest(name: str, description: str | None = "Reusable workflow.") -> str:
    body = f"---\nname: {name}\n"
    if description is not None:
        body += f"description: {description}\n"
    return body + "---\n\n# Skill\n"


class OverlayDriftTests(unittest.TestCase):
    def test_scan_root_collects_inventory_and_cross_surface_drift(self) -> None:
        if scan_skill_registry.yaml is None:
            self.skipTest("PyYAML is required for YAML surface scanning")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "alpha" / "SKILL.md", skill_manifest("alpha"))
            write(root / "alpha-copy" / "SKILL.md", skill_manifest("alpha"))
            write(root / "no-desc" / "SKILL.md", skill_manifest("no-desc", None))
            write(root / "skills-src" / "alpha" / "SKILL.md", skill_manifest("alpha"))
            write(
                root / "skill-repos.yaml",
                """
skill_repos:
  - name: local
    path: ./skills-src
    pick:
      - alpha
      - absent
""",
            )
            write(
                root / "skill-scope.yaml",
                """
skill_source_roots:
  - ./skills-src
global_allowlist:
  - alpha
  - ghost
rules:
  - id: first
    allow_global: true
    skills:
      - alpha
  - id: second
    skills:
      - alpha
      - ghost
""",
            )
            write(
                root / "default-skills.manifest.yaml",
                """
skills:
  - name: duplicate
    path: ./skills-src
    pick:
      - absent-runtime
  - name: duplicate
""",
            )
            write(
                root / "skillbox-config" / "clients" / "demo" / "overlay.yaml",
                """
client:
  default_cwd: ./missing-default
""",
            )
            write(
                root / ".mcp.json",
                json.dumps({"mcpServers": {"alpha": {"command": "alpha"}}}),
            )
            write(root / ".codex" / "config.toml", "[mcp_servers.beta]\ncommand = 'beta'\n")

            result = scan_skill_registry.scan_root(root)

        inventory = result["inventory"]
        self.assertEqual(inventory["skill_repos_yaml"], 1)
        self.assertEqual(inventory["skill_manifests"], 4)
        self.assertEqual(inventory["skill_scope_yaml"], 1)
        self.assertEqual(inventory["runtime_manifest_files"], 1)
        self.assertEqual(inventory["client_overlays"], 1)
        self.assertEqual(inventory["claude_mcp_configs"], 1)
        self.assertEqual(inventory["codex_mcp_configs"], 1)

        issues = result["issues"]
        messages = {issue["message"] for issue in issues}
        codes = {issue["code"] for issue in issues}
        self.assertIn("manifest-drift", codes)
        self.assertIn("missing-registry-source", codes)
        self.assertIn("scope-drift", codes)
        self.assertIn("bundle-drift", codes)
        self.assertIn("overlay-drift", codes)
        self.assertIn("mcp-parity-drift", codes)
        self.assertIn("SKILL.md is missing a description.", messages)
        self.assertTrue(
            any("Duplicate skill name `alpha`" in message for message in messages),
            messages,
        )
        self.assertIn("Picked skill `absent` is missing under ./skills-src.", messages)
        self.assertIn(
            "Picked skill `absent-runtime` is missing under ./skills-src.",
            messages,
        )
        self.assertIn("Runtime manifest lists `duplicate` 2 times.", messages)
        self.assertIn(
            "client.default_cwd points at a missing path: ./missing-default",
            messages,
        )
        self.assertTrue(
            any("Claude/Codex MCP server sets differ" in message for message in messages),
            messages,
        )

        report = scan_skill_registry.text_report([result])
        self.assertIn("skill registry scan (read-only)", report)
        self.assertIn("issues:", report)

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
