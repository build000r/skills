#!/usr/bin/env python3
"""
Initialize a new domain slice with template files.

Usage:
    python scripts/init_slice.py recipe_recommendations
    python scripts/init_slice.py depreciation_sync --context myapp --config config.json
    python scripts/init_slice.py user_auth --config modes/planning.md

Config resolution order:
    1. --config flag (JSON file or mode markdown file)
    2. DOMAIN_PLAN_CONFIG env var (path to config file)
    3. DOMAIN_PLAN_ROOT + REPOS_ROOT env vars (minimal setup)

Creates:
    {plan_root}/{slice}/
        plan.md, shared.md, backend.md, frontend.md, flows.md, schema.mmd,
        WORKGRAPH.md

    Migration file (if backend_repo configured):
        {repos_root}/{backend_repo}/{migrations_path}/{timestamp}_{slice}_initial{migration_ext}
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Generic repo helpers (no hardcoded names)
# ---------------------------------------------------------------------------

def find_repo_root(start_path: Path, marker_files: list[str]) -> Path | None:
    """Walk up from start_path to find a directory containing any marker file."""
    current = start_path.resolve()
    while current != current.parent:
        for marker in marker_files:
            if (current / marker).exists():
                return current
        current = current.parent
    return None


def find_sibling_repo(repo_root: Path, sibling_name: str) -> Path | None:
    """Find a sibling repository (same parent directory)."""
    sibling = repo_root.parent / sibling_name
    if sibling.exists() and (sibling / ".git").exists():
        return sibling
    return None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def parse_mode_markdown(path: Path) -> dict:
    """Extract key-value config from fenced code blocks in a mode markdown file.

    Scans for lines like `plan_root: ~/repos/project/plans/released` inside
    ``` blocks.  Returns a flat dict of string values plus a nested
    ``contexts`` dict if context blocks are found.
    """
    text = path.read_text()
    config: dict = {}
    contexts: dict = {}

    # Pull all fenced code block contents
    code_blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    block_text = "\n".join(code_blocks)

    # Try JSON first -- a code block might contain full JSON config
    for block in code_blocks:
        stripped = block.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return _normalize_config(parsed)
            except json.JSONDecodeError:
                pass

    # Fallback: parse simple key: value lines
    current_context: str | None = None
    for line in block_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Detect context headers like [myapp] or [default]
        ctx_match = re.match(r"^\[(\w+)]$", line)
        if ctx_match:
            current_context = ctx_match.group(1)
            contexts.setdefault(current_context, {})
            continue

        kv_match = re.match(r"^(\w+)\s*:\s*(.+)$", line)
        if kv_match:
            key, value = kv_match.group(1), kv_match.group(2).strip()
            if current_context:
                contexts[current_context][key] = value
            else:
                config[key] = value

    if contexts:
        config["contexts"] = contexts
    return _normalize_config(config)


def load_json_config(path: Path) -> dict:
    """Load and normalize a JSON config file."""
    with open(path) as f:
        raw = json.load(f)
    return _normalize_config(raw)


def _normalize_config(raw: dict) -> dict:
    """Expand ~ in path values and ensure consistent structure."""
    config = {}
    for key, value in raw.items():
        if key == "contexts" and isinstance(value, dict):
            config["contexts"] = value
        elif isinstance(value, str):
            config[key] = str(Path(value).expanduser()) if "~" in value else value
        else:
            config[key] = value
    return config


def _try_overlay_context() -> dict | None:
    """Try loading config from skillbox client context.yaml."""
    shared_scripts = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"
    if not shared_scripts.exists():
        return None
    import sys as _sys
    _sys.path.insert(0, str(shared_scripts))
    try:
        from resolve_context import resolve  # type: ignore[import-untyped]
    except ImportError:
        return None
    finally:
        _sys.path.pop(0)

    cwd = os.path.realpath(os.getcwd())
    plans = resolve(cwd, section="plans")
    if plans is None:
        return None

    # Build config dict from overlay sections
    config: dict = {}
    for key in ("plan_root", "plan_draft", "plan_index", "session_plans"):
        if key in plans:
            config[key] = plans[key]

    backend = resolve(cwd, section="backend")
    frontend = resolve(cwd, section="frontend")
    auth = resolve(cwd, section="auth")

    if backend or frontend:
        contexts: dict = {"default": {}}
        if backend:
            for k, v in backend.items():
                if k == "repo":
                    contexts["default"]["backend_repo"] = v
                else:
                    contexts["default"][k] = v
        if frontend:
            for k, v in frontend.items():
                if k == "repo":
                    contexts["default"]["frontend_repo"] = v
                else:
                    contexts["default"][k] = v
        if auth:
            contexts["default"]["auth_packages_root"] = auth.get("packages_root", "")
            if auth.get("python_packages"):
                contexts["default"]["auth_python_packages"] = auth["python_packages"]
            if auth.get("npm_packages"):
                contexts["default"]["auth_npm_packages"] = auth["npm_packages"]
        config["contexts"] = contexts

    return _normalize_config(config) if config else None


def load_config(config_path: str | None) -> dict:
    """Load config from file, env vars, or fail with guidance."""

    # 0. Skillbox client overlay context
    overlay_config = _try_overlay_context()
    if overlay_config and not config_path:
        return overlay_config

    # 1. Explicit --config flag
    if config_path:
        p = Path(config_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        if p.suffix == ".json":
            return load_json_config(p)
        else:
            config = parse_mode_markdown(p)
            # Extract mode name from filename (e.g., "cca.md" → "cca")
            config["_mode_name"] = p.stem
            return config

    # 2. DOMAIN_PLAN_CONFIG env var
    env_config = os.environ.get("DOMAIN_PLAN_CONFIG")
    if env_config:
        p = Path(env_config).expanduser().resolve()
        if p.exists():
            if p.suffix == ".json":
                return load_json_config(p)
            else:
                return parse_mode_markdown(p)

    # 3. Individual env vars
    plan_root = os.environ.get("DOMAIN_PLAN_ROOT")
    if plan_root:
        config: dict = {"plan_root": str(Path(plan_root).expanduser())}
        repos_root = os.environ.get("REPOS_ROOT")
        if repos_root:
            config["repos_root"] = str(Path(repos_root).expanduser())
        plan_draft = os.environ.get("DOMAIN_PLAN_DRAFT")
        if plan_draft:
            config["plan_draft"] = str(Path(plan_draft).expanduser())
        return config

    # Nothing found -- give helpful guidance
    raise SystemExit(
        "No configuration found. Provide one of:\n"
        "\n"
        "  1. --config path/to/config.json\n"
        "  2. --config path/to/mode.md  (with config in code blocks)\n"
        "  3. Set environment variables:\n"
        "       DOMAIN_PLAN_ROOT  - directory for released slice plans\n"
        "       REPOS_ROOT        - parent directory for sibling repos\n"
        "       DOMAIN_PLAN_DRAFT - (optional) directory for draft plans\n"
        "\n"
        "JSON config example:\n"
        '  {\n'
        '    "plan_root": "~/repos/project/plans/released",\n'
        '    "plan_draft": "~/repos/project/plans/planned",\n'
        '    "contexts": {\n'
        '      "default": {\n'
        '        "backend_repo": "my-backend",\n'
        '        "migrations_path": "alembic/versions",\n'
        '        "migration_ext": ".sql.planning"\n'
        '      }\n'
        '    }\n'
        '  }\n'
    )


# ---------------------------------------------------------------------------
# Resolve context within a loaded config
# ---------------------------------------------------------------------------

def resolve_context(config: dict, context_name: str | None) -> dict:
    """Return the context dict for the given name, or the default context."""
    contexts = config.get("contexts", {})
    if not contexts:
        # No contexts defined -- return an empty context (plan-only mode)
        return {}

    if context_name:
        if context_name not in contexts:
            available = ", ".join(sorted(contexts.keys()))
            raise ValueError(
                f"Unknown context '{context_name}'. Available: {available}"
            )
        return contexts[context_name]

    # Auto-select if only one context defined
    if len(contexts) == 1:
        return next(iter(contexts.values()))

    # Check for "default"
    if "default" in contexts:
        return contexts["default"]

    available = ", ".join(sorted(contexts.keys()))
    raise ValueError(
        f"Multiple contexts available ({available}). "
        f"Specify one with --context."
    )


# ---------------------------------------------------------------------------
# Paths relative to this script (for template discovery)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATES_DIR = SKILL_DIR / "assets" / "templates"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def init_slice(
    name: str,
    config: dict,
    context_name: str | None = None,
    draft: bool = False,
) -> None:
    """Create slice folder with templates and optional migration planning file."""

    # Validate name
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Slice name must be snake_case alphanumeric: {name}")

    ctx = resolve_context(config, context_name)
    ctx_label = context_name or "default"
    if ctx.get("backend_repo"):
        print(f"Context: {ctx_label} (backend: {ctx['backend_repo']})")
    else:
        print(f"Context: {ctx_label}")

    # Determine target directory
    if draft:
        plan_draft = config.get("plan_draft")
        if not plan_draft:
            plan_root = config.get("plan_root")
            if not plan_root:
                raise ValueError("No plan_root or plan_draft configured")
            # Default draft location: sibling 'planned' directory
            plan_draft = str(Path(plan_root).parent / "planned")
        target_dir = Path(plan_draft) / name
    else:
        plan_root = config.get("plan_root")
        if not plan_root:
            raise ValueError("No plan_root configured")
        target_dir = Path(plan_root) / name

    # Check if already exists
    if target_dir.exists():
        print(f"Slice already exists: {target_dir}")
        print("Files in slice:")
        for f in target_dir.iterdir():
            print(f"  - {f.name}")
        return

    # Create slice directory
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created: {target_dir}")

    # Copy template files
    # Check for mode-specific frontend template (e.g., frontend-cca.md → frontend.md)
    template_files = [
        "plan.md", "shared.md", "backend.md",
        "frontend.md", "flows.md", "schema.mmd", "WORKGRAPH.md",
    ]
    backend_repo = ctx.get("backend_repo", "")

    # Detect mode name from config file path for template selection
    mode_name = config.get("_mode_name", "")

    for template_name in template_files:
        # For frontend.md, prefer mode-specific variant if available
        if template_name == "frontend.md" and mode_name:
            mode_template = TEMPLATES_DIR / f"frontend-{mode_name}.md"
            if mode_template.exists():
                template_path = mode_template
                print(f"  Using mode-specific template: frontend-{mode_name}.md")
            else:
                template_path = TEMPLATES_DIR / template_name
        else:
            template_path = TEMPLATES_DIR / template_name

        if template_path.exists():
            dest_path = target_dir / template_name
            shutil.copy(template_path, dest_path)

            # Replace placeholders in copied file
            content = dest_path.read_text()
            content = content.replace("{slice_name}", name)
            content = content.replace("{SLICE_NAME}", name.upper())
            content = content.replace("{context}", ctx_label)
            content = content.replace("{backend_repo}", backend_repo)
            dest_path.write_text(content)

            print(f"  Created: {template_name}")
        else:
            print(f"  Warning: Template not found: {template_name}")

    # Create migration planning file (only if backend_repo is configured)
    if not backend_repo:
        print("  Skipped migration file (no backend_repo in context)")
    else:
        repos_root = config.get("repos_root")
        backend_path: Path | None = None

        # Try sibling repo discovery from plan_root
        plan_root_path = Path(config.get("plan_root", ""))
        repo_root = find_repo_root(plan_root_path, [".git"])
        if repo_root:
            backend_path = find_sibling_repo(repo_root, backend_repo)

        # Fallback to repos_root
        if backend_path is None and repos_root:
            candidate = Path(repos_root) / backend_repo
            if candidate.exists():
                backend_path = candidate

        if backend_path is None:
            print(f"  Warning: Could not locate backend repo '{backend_repo}'")
        else:
            migrations_rel = ctx.get("migrations_path", "migrations")
            migration_ext = ctx.get("migration_ext", ".sql.planning")
            migrations_dir = backend_path / migrations_rel

            if migrations_dir.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                migration_name = f"{timestamp}_{name}_initial{migration_ext}"
                migration_path = migrations_dir / migration_name

                migration_content = (
                    f"-- Migration: {name} initial tables\n"
                    f"-- Context: {ctx_label} (backend: {backend_repo})\n"
                    f"-- Status: PLANNING\n"
                    f"--\n"
                    f"-- This file is a planning draft. Review before applying.\n"
                    f"\n"
                    f"-- Tables for {name} domain\n"
                    f"\n"
                    f"-- TODO: Add CREATE TABLE statements from planning docs\n"
                    f"\n"
                )

                migration_path.write_text(migration_content)
                print(f"  Created migration draft: {migration_name}")
                print(f"    Location: {migrations_dir}")
            else:
                print(
                    f"  Warning: migrations dir not found: {migrations_dir}"
                )

    print()
    print("Next steps:")
    print(f"  1. Fill in templates in {target_dir}")
    print("  2. Use domain-planner skill to refine and lock the 6 plan files")
    print("  3. Populate WORKGRAPH.md after plan sign-off for execution waves")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a new domain slice with templates"
    )
    parser.add_argument(
        "name",
        help="Slice name in snake_case (e.g., recipe_recommendations)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=(
            "Path to config file (JSON or mode markdown). "
            "Falls back to DOMAIN_PLAN_CONFIG, then DOMAIN_PLAN_ROOT env vars."
        ),
    )
    parser.add_argument(
        "--context",
        metavar="NAME",
        help="Context name from config (auto-selected when only one exists)",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create in draft/planned directory instead of released",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    init_slice(args.name, config, context_name=args.context, draft=args.draft)


if __name__ == "__main__":
    main()
