#!/usr/bin/env python3
"""Launch the sibling Skillbox MCP server with repo-relative defaults."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    skills_repo = Path(__file__).resolve().parents[1]
    opensource_root = skills_repo.parent
    monorepo_root = opensource_root.parent
    default_server = opensource_root / "skillbox" / ".env-manager" / "mcp_server.py"
    server = Path(os.environ.get("SKILLBOX_MCP_SERVER", str(default_server))).expanduser()

    if not server.exists():
        sys.stderr.write(
            "Skillbox MCP server was not found at "
            f"{server}. Clone skillbox next to this skills repo or set "
            "SKILLBOX_MCP_SERVER to the server script path.\n"
        )
        return 127

    os.environ.setdefault("SKILLBOX_MONOSERVER_ROOT", str(monorepo_root))
    os.environ.setdefault("SKILLBOX_MONOSERVER_HOST_ROOT", str(monorepo_root))
    os.environ.setdefault(
        "SKILLBOX_CLIENTS_HOST_ROOT",
        str(monorepo_root / "skillbox-config" / "clients"),
    )

    os.execv(sys.executable, [sys.executable, str(server), *sys.argv[1:]])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
