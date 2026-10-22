import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "init_slice.py"
spec = importlib.util.spec_from_file_location("optional_workgraph_init", SCRIPT)
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class OptionalWorkgraphTests(unittest.TestCase):
    def test_plan_initialization_does_not_seed_unused_execution_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            templates = root / "templates"
            templates.mkdir()
            (templates / "plan.md").write_text("Plan")
            (templates / "WORKGRAPH.md").write_text("Unused execution view")
            with mock.patch.object(MODULE, "TEMPLATES_DIR", templates):
                MODULE.init_slice("slice", {"plan_root": str(root / "plans")})
            self.assertTrue((root / "plans/slice/plan.md").exists())
            self.assertFalse((root / "plans/slice/WORKGRAPH.md").exists())


if __name__ == "__main__":
    unittest.main()
