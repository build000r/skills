import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "workgraph_ready",
    str((Path(__file__).resolve().parent.parent / "scripts" / "workgraph_ready.py").resolve()),
).load_module()


class WorkgraphReadyTests(unittest.TestCase):
    def test_ready_node_requires_done_when_and_validate_cmds(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "WG-001",
                    "title": "Missing contracts",
                    "depends_on": [],
                    "writes": [],
                    "done_when": [],
                    "validate_cmds": [],
                    "status": "todo",
                }
            ]
        )

        self.assertEqual(ready, [])
        self.assertEqual(len(waiting), 1)
        self.assertIn("WG-001: missing done_when contract", issues)
        self.assertIn("WG-001: missing validate_cmds contract", issues)

    def test_placeholder_contracts_block_readiness(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "WG-001",
                    "title": "Template node",
                    "depends_on": [],
                    "writes": ["src/**"],
                    "done_when": ["Binary completion check"],
                    "validate_cmds": ["Concrete validation command"],
                    "status": "todo",
                }
            ]
        )

        self.assertEqual(ready, [])
        self.assertEqual(len(waiting), 1)
        self.assertIn("WG-001: done_when contains placeholder text", issues)
        self.assertIn("WG-001: validate_cmds contains placeholder text", issues)

    def test_valid_ready_nodes_are_grouped_by_write_overlap(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "WG-001",
                    "title": "Backend",
                    "depends_on": [],
                    "writes": ["src/backend/**"],
                    "done_when": ["API contract implemented"],
                    "validate_cmds": ["pytest tests/test_backend.py"],
                    "status": "todo",
                },
                {
                    "id": "WG-002",
                    "title": "Frontend",
                    "depends_on": [],
                    "writes": ["src/frontend/**"],
                    "done_when": ["UI updated"],
                    "validate_cmds": ["npm test -- frontend"],
                    "status": "todo",
                },
                {
                    "id": "WG-003",
                    "title": "Backend follow-up",
                    "depends_on": [],
                    "writes": ["src/backend/routes/**"],
                    "done_when": ["Routes updated"],
                    "validate_cmds": ["pytest tests/test_routes.py"],
                    "status": "todo",
                },
            ]
        )

        self.assertEqual(len(waiting), 0)
        self.assertEqual(issues, [])
        self.assertEqual([node["id"] for node in ready], ["WG-001", "WG-002", "WG-003"])

        waves = MODULE.group_waves(ready)
        self.assertEqual(len(waves), 2)
        self.assertEqual([node["id"] for node in waves[0]["nodes"]], ["WG-001", "WG-002"])
        self.assertEqual([node["id"] for node in waves[1]["nodes"]], ["WG-003"])

    def test_write_overlap_respects_path_boundaries(self) -> None:
        self.assertFalse(MODULE.writes_overlap(["src/app/**"], ["src/app2/**"]))
        self.assertTrue(MODULE.writes_overlap(["src/app/**"], ["src/app/routes/**"]))

    def test_write_overlap_keeps_same_segment_glob_suffix_conservative(self) -> None:
        self.assertTrue(MODULE.writes_overlap(["src/app*"], ["src/app2/**"]))
        self.assertTrue(MODULE.writes_overlap(["src/app*"], ["src/application/**"]))

    def test_sibling_prefix_paths_can_share_a_wave(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "WG-001",
                    "title": "App",
                    "depends_on": [],
                    "writes": ["src/app/**"],
                    "done_when": ["App updated"],
                    "validate_cmds": ["pytest tests/test_app.py"],
                    "status": "todo",
                },
                {
                    "id": "WG-002",
                    "title": "App 2",
                    "depends_on": [],
                    "writes": ["src/app2/**"],
                    "done_when": ["App 2 updated"],
                    "validate_cmds": ["pytest tests/test_app2.py"],
                    "status": "todo",
                },
            ]
        )

        self.assertEqual(len(waiting), 0)
        self.assertEqual(issues, [])
        waves = MODULE.group_waves(ready)
        self.assertEqual(len(waves), 1)
        self.assertEqual([node["id"] for node in waves[0]["nodes"]], ["WG-001", "WG-002"])

    def test_same_segment_glob_suffix_splits_waves_conservatively(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "WG-001",
                    "title": "App family",
                    "depends_on": [],
                    "writes": ["src/app*"],
                    "done_when": ["App family updated"],
                    "validate_cmds": ["pytest tests/test_app_family.py"],
                    "status": "todo",
                },
                {
                    "id": "WG-002",
                    "title": "App 2",
                    "depends_on": [],
                    "writes": ["src/app2/**"],
                    "done_when": ["App 2 updated"],
                    "validate_cmds": ["pytest tests/test_app2.py"],
                    "status": "todo",
                },
            ]
        )

        self.assertEqual(len(waiting), 0)
        self.assertEqual(issues, [])
        waves = MODULE.group_waves(ready)
        self.assertEqual(len(waves), 2)
        self.assertEqual([node["id"] for node in waves[0]["nodes"]], ["WG-001"])
        self.assertEqual([node["id"] for node in waves[1]["nodes"]], ["WG-002"])

    def test_duplicate_node_ids_block_ambiguous_readiness(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "WG-001",
                    "title": "First copy",
                    "depends_on": [],
                    "writes": ["src/one/**"],
                    "done_when": ["First copy finished"],
                    "validate_cmds": ["pytest tests/test_one.py"],
                    "status": "done",
                },
                {
                    "id": "WG-001",
                    "title": "Second copy",
                    "depends_on": [],
                    "writes": ["src/two/**"],
                    "done_when": ["Second copy finished"],
                    "validate_cmds": ["pytest tests/test_two.py"],
                    "status": "todo",
                },
                {
                    "id": "WG-002",
                    "title": "Depends on ambiguous node",
                    "depends_on": ["WG-001"],
                    "writes": ["src/three/**"],
                    "done_when": ["Dependent finished"],
                    "validate_cmds": ["pytest tests/test_three.py"],
                    "status": "todo",
                },
            ]
        )

        self.assertEqual(ready, [])
        self.assertEqual(len(waiting), 3)
        self.assertIn("WG-001: duplicate node ID", issues)
        self.assertIn("WG-002: ambiguous duplicate dependency IDs: WG-001", issues)

    def test_duplicate_empty_node_ids_are_not_ready(self) -> None:
        ready, waiting, issues = MODULE.classify_nodes(
            [
                {
                    "id": "",
                    "title": "First blank",
                    "depends_on": [],
                    "writes": ["src/one/**"],
                    "done_when": ["First blank finished"],
                    "validate_cmds": ["pytest tests/test_one.py"],
                    "status": "todo",
                },
                {
                    "id": "",
                    "title": "Second blank",
                    "depends_on": [],
                    "writes": ["src/two/**"],
                    "done_when": ["Second blank finished"],
                    "validate_cmds": ["pytest tests/test_two.py"],
                    "status": "todo",
                },
                {
                    "id": "WG-002",
                    "title": "Depends on blank duplicate",
                    "depends_on": [""],
                    "writes": ["src/three/**"],
                    "done_when": ["Dependent finished"],
                    "validate_cmds": ["pytest tests/test_three.py"],
                    "status": "todo",
                },
            ]
        )

        self.assertEqual(ready, [])
        self.assertEqual(len(waiting), 3)
        self.assertIn("<empty>: duplicate node ID", issues)
        self.assertIn("WG-002: ambiguous duplicate dependency IDs: <empty>", issues)


if __name__ == "__main__":
    unittest.main()
