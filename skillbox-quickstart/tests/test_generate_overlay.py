from __future__ import annotations

import importlib.util
import shlex
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_overlay.py"
SPEC = importlib.util.spec_from_file_location("generate_overlay", SCRIPT)
assert SPEC and SPEC.loader
generate_overlay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_overlay)


class FirstBoxCommandTests(unittest.TestCase):
    def test_shell_quotes_set_values_with_spaces(self) -> None:
        command = generate_overlay.build_first_box_cmd(
            "demo-client",
            {
                "blueprint": "git-repo-http-service",
                "set_args": {
                    "PRIMARY_REPO_ID": "demo",
                    "SERVICE_COMMAND": "npm run dev",
                },
            },
        )

        argv = shlex.split(command)

        self.assertIn("SERVICE_COMMAND=npm run dev", argv)
        self.assertEqual(argv.count("--set"), 2)
        self.assertNotIn("run", argv)
        self.assertNotIn("dev", argv)


if __name__ == "__main__":
    unittest.main()
