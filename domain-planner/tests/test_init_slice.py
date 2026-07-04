import json
import tempfile
import unittest
import unittest.mock
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "init_slice",
    str((Path(__file__).resolve().parent.parent / "scripts" / "init_slice.py").resolve()),
).load_module()


class FindRepoRootTests(unittest.TestCase):
    def test_finds_marker_in_current_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            result = MODULE.find_repo_root(root, ["pyproject.toml"])
            self.assertEqual(result, root.resolve())

    def test_finds_marker_in_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child = root / "src" / "nested"
            child.mkdir(parents=True)
            result = MODULE.find_repo_root(child, [".git"])
            self.assertEqual(result, root.resolve())

    def test_returns_none_when_no_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = MODULE.find_repo_root(Path(tmpdir), ["nonexistent-marker"])
            self.assertIsNone(result)


class FindSiblingRepoTests(unittest.TestCase):
    def test_finds_sibling_with_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            repo_a = parent / "repo-a"
            repo_b = parent / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            (repo_b / ".git").mkdir()
            result = MODULE.find_sibling_repo(repo_a, "repo-b")
            self.assertEqual(result, repo_b)

    def test_returns_none_for_missing_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo-a"
            repo.mkdir()
            result = MODULE.find_sibling_repo(repo, "repo-b")
            self.assertIsNone(result)

    def test_returns_none_for_sibling_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            repo_a = parent / "repo-a"
            repo_b = parent / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            result = MODULE.find_sibling_repo(repo_a, "repo-b")
            self.assertIsNone(result)


class ParseModeMarkdownTests(unittest.TestCase):
    def test_extracts_key_value_from_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text(
                "# Mode\n\n```\nplan_root: ~/repos/project/plans\nrepos_root: ~/repos\n```\n",
                encoding="utf-8",
            )
            config = MODULE.parse_mode_markdown(md)
            self.assertIn("repos/project/plans", config.get("plan_root", ""))
            self.assertIn("repos", config.get("repos_root", ""))

    def test_extracts_json_from_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text(
                '# Mode\n\n```json\n{"plan_root": "/tmp/plans"}\n```\n',
                encoding="utf-8",
            )
            config = MODULE.parse_mode_markdown(md)
            self.assertEqual(config.get("plan_root"), "/tmp/plans")

    def test_returns_empty_for_no_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text("# Mode\n\nNo code blocks here.\n", encoding="utf-8")
            config = MODULE.parse_mode_markdown(md)
            self.assertEqual(config, {})


class NormalizeConfigTests(unittest.TestCase):
    def test_expands_tilde(self) -> None:
        result = MODULE._normalize_config({"plan_root": "~/plans"})
        self.assertNotIn("~", result["plan_root"])

    def test_preserves_contexts(self) -> None:
        result = MODULE._normalize_config({"contexts": {"default": {"key": "val"}}})
        self.assertEqual(result["contexts"]["default"]["key"], "val")

    def test_preserves_non_string(self) -> None:
        result = MODULE._normalize_config({"count": 5})
        self.assertEqual(result["count"], 5)


class LoadJsonConfigTests(unittest.TestCase):
    def test_loads_and_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "config.json"
            cfg.write_text(json.dumps({"plan_root": "/tmp/plans"}), encoding="utf-8")
            result = MODULE.load_json_config(cfg)
            self.assertEqual(result["plan_root"], "/tmp/plans")


class ResolveContextTests(unittest.TestCase):
    def test_returns_empty_when_no_contexts(self) -> None:
        result = MODULE.resolve_context({"plan_root": "/tmp"}, None)
        self.assertEqual(result, {})

    def test_returns_named_context(self) -> None:
        config = {"contexts": {"myapp": {"backend_repo": "api"}}}
        result = MODULE.resolve_context(config, "myapp")
        self.assertEqual(result["backend_repo"], "api")

    def test_raises_for_unknown_context(self) -> None:
        config = {"contexts": {"myapp": {}}}
        with self.assertRaises(ValueError):
            MODULE.resolve_context(config, "unknown")

    def test_auto_selects_single_context(self) -> None:
        config = {"contexts": {"only": {"key": "val"}}}
        result = MODULE.resolve_context(config, None)
        self.assertEqual(result["key"], "val")

    def test_prefers_default_context(self) -> None:
        config = {"contexts": {"default": {"key": "d"}, "other": {"key": "o"}}}
        result = MODULE.resolve_context(config, None)
        self.assertEqual(result["key"], "d")

    def test_raises_for_ambiguous_contexts(self) -> None:
        config = {"contexts": {"a": {}, "b": {}}}
        with self.assertRaises(ValueError):
            MODULE.resolve_context(config, None)


class LoadConfigTests(unittest.TestCase):
    def test_loads_json_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "config.json"
            cfg.write_text(json.dumps({"plan_root": "/tmp/plans"}), encoding="utf-8")
            result = MODULE.load_config(str(cfg))
            self.assertEqual(result["plan_root"], "/tmp/plans")

    def test_loads_markdown_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "mode.md"
            md.write_text("```\nplan_root: /tmp/plans\n```\n", encoding="utf-8")
            result = MODULE.load_config(str(md))
            self.assertEqual(result["plan_root"], "/tmp/plans")
            self.assertEqual(result["_mode_name"], "mode")

    def test_raises_for_missing_config(self) -> None:
        with self.assertRaises(FileNotFoundError):
            MODULE.load_config("/nonexistent/config.json")

    def test_falls_back_to_env_config_json(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "config.json"
            cfg.write_text(json.dumps({"plan_root": "/tmp/plans"}), encoding="utf-8")
            with unittest.mock.patch.dict(os.environ, {"DOMAIN_PLAN_CONFIG": str(cfg)}), \
                 unittest.mock.patch.object(MODULE, "_try_overlay_context", return_value=None):
                result = MODULE.load_config(None)
                self.assertEqual(result["plan_root"], "/tmp/plans")

    def test_falls_back_to_env_plan_root(self) -> None:
        import os
        with unittest.mock.patch.dict(os.environ, {"DOMAIN_PLAN_ROOT": "/tmp/plans"}, clear=False), \
             unittest.mock.patch.object(MODULE, "_try_overlay_context", return_value=None):
            env_bak = os.environ.pop("DOMAIN_PLAN_CONFIG", None)
            try:
                result = MODULE.load_config(None)
                self.assertEqual(result["plan_root"], "/tmp/plans")
            finally:
                if env_bak:
                    os.environ["DOMAIN_PLAN_CONFIG"] = env_bak

    def test_raises_when_nothing_found(self) -> None:
        import os
        with unittest.mock.patch.object(MODULE, "_try_overlay_context", return_value=None), \
             unittest.mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                MODULE.load_config(None)

    def test_prefers_overlay_context(self) -> None:
        overlay = {"plan_root": "/overlay/plans"}
        with unittest.mock.patch.object(MODULE, "_try_overlay_context", return_value=overlay):
            result = MODULE.load_config(None)
            self.assertEqual(result["plan_root"], "/overlay/plans")


class TryOverlayContextTests(unittest.TestCase):
    def test_resolves_sibling_shared_before_home_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sibling = root / "_shared" / "scripts"
            home_fallback = root / "home" / ".claude" / "skills" / "_shared" / "scripts"
            sibling.mkdir(parents=True)
            home_fallback.mkdir(parents=True)

            with unittest.mock.patch.object(
                MODULE,
                "_shared_scripts_candidates",
                return_value=[sibling, home_fallback],
            ):
                self.assertEqual(MODULE._resolve_shared_scripts(), sibling)

    def test_resolves_home_shared_when_sibling_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sibling = root / "_shared" / "scripts"
            home_fallback = root / "home" / ".claude" / "skills" / "_shared" / "scripts"
            home_fallback.mkdir(parents=True)

            with unittest.mock.patch.object(
                MODULE,
                "_shared_scripts_candidates",
                return_value=[sibling, home_fallback],
            ):
                self.assertEqual(MODULE._resolve_shared_scripts(), home_fallback)

    def test_returns_none_when_shared_missing(self) -> None:
        with unittest.mock.patch.object(Path, "exists", return_value=False):
            result = MODULE._try_overlay_context()
            self.assertIsNone(result)

    def test_missing_config_guidance_names_shared_install_contract(self) -> None:
        import os
        with unittest.mock.patch.object(MODULE, "_try_overlay_context", return_value=None), \
             unittest.mock.patch.object(
                 MODULE,
                 "_shared_scripts_candidates",
                 return_value=[
                     Path("/skills/_shared/scripts"),
                     Path("/home/user/.claude/skills/_shared/scripts"),
                 ],
             ), \
             unittest.mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as raised:
                MODULE.load_config(None)
            message = str(raised.exception)
            self.assertIn("/skills/_shared/scripts", message)
            self.assertIn("/home/user/.claude/skills/_shared/scripts", message)
            self.assertIn("filtered skill installs that include domain-planner", message)


class InitSliceTests(unittest.TestCase):
    def test_rejects_invalid_name(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.init_slice("bad-name!", {"plan_root": "/tmp"})

    def test_creates_slice_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"plan_root": str(Path(tmpdir) / "plans")}
            MODULE.init_slice("test_slice", config)
            self.assertTrue((Path(tmpdir) / "plans" / "test_slice").exists())

    def test_existing_slice_skips(self) -> None:
        import io
        import sys
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "plans" / "existing"
            target.mkdir(parents=True)
            (target / "plan.md").write_text("existing", encoding="utf-8")
            config = {"plan_root": str(Path(tmpdir) / "plans")}
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                MODULE.init_slice("existing", config)
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            self.assertIn("already exists", output)

    def test_draft_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"plan_root": str(Path(tmpdir) / "released"), "plan_draft": str(Path(tmpdir) / "planned")}
            MODULE.init_slice("draft_slice", config, draft=True)
            self.assertTrue((Path(tmpdir) / "planned" / "draft_slice").exists())

    def test_draft_fallback_to_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"plan_root": str(Path(tmpdir) / "released")}
            MODULE.init_slice("draft_slice", config, draft=True)
            self.assertTrue((Path(tmpdir) / "planned" / "draft_slice").exists())

    def test_raises_when_no_plan_root(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.init_slice("test_slice", {})

    def test_migration_created_with_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plans = Path(tmpdir) / "project" / "plans"
            plans.mkdir(parents=True)
            (Path(tmpdir) / "project" / ".git").mkdir()
            backend = Path(tmpdir) / "backend"
            backend.mkdir()
            (backend / ".git").mkdir()
            migrations = backend / "migrations"
            migrations.mkdir()
            config = {
                "plan_root": str(plans),
                "contexts": {"default": {"backend_repo": "backend"}},
            }
            MODULE.init_slice("auth_flow", config)
            migration_files = list(migrations.glob("*_auth_flow_initial*"))
            self.assertEqual(len(migration_files), 1)

    def test_skips_migration_without_backend(self) -> None:
        import io
        import sys
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"plan_root": str(Path(tmpdir) / "plans")}
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                MODULE.init_slice("no_backend", config)
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            self.assertIn("Skipped migration", output)


class MainTests(unittest.TestCase):
    def test_main_creates_slice(self) -> None:
        import sys
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "config.json"
            cfg.write_text(json.dumps({"plan_root": str(Path(tmpdir) / "plans")}), encoding="utf-8")
            old_argv = sys.argv
            sys.argv = ["init_slice.py", "main_test", "--config", str(cfg)]
            try:
                MODULE.main()
            finally:
                sys.argv = old_argv
            self.assertTrue((Path(tmpdir) / "plans" / "main_test").exists())


if __name__ == "__main__":
    unittest.main()
