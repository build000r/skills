import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = SourceFileLoader(
    "delta_audit",
    str(ROOT / "scripts" / "delta_audit.py"),
).load_module()


def _make_snapshot(
    target: str = "/tmp/repo",
    scope_path: str = "/tmp/repo",
    functions: list | None = None,
    file_hashes: dict | None = None,
    test_assertions: dict | None = None,
) -> MODULE.Snapshot:
    return MODULE.Snapshot(
        target=target,
        scope_path=scope_path,
        functions=functions or [],
        file_hashes=file_hashes or {},
        test_file_assertion_counts=test_assertions or {},
    )


def _func(
    file: str = "src/main.py",
    symbol: str = "do_stuff",
    language: str = "python",
    start_line: int = 1,
    end_line: int = 10,
    cc: int = 5,
) -> MODULE.FunctionRecord:
    return MODULE.FunctionRecord(
        file=file,
        symbol=symbol,
        language=language,
        start_line=start_line,
        end_line=end_line,
        cc=cc,
        line_count=end_line - start_line + 1,
    )


class TestAuditClean(unittest.TestCase):
    def test_identical_snapshots_are_clean(self) -> None:
        funcs = [_func()]
        baseline = _make_snapshot(functions=funcs)
        current = _make_snapshot(functions=funcs)
        result = MODULE.audit_delta(baseline, current)
        self.assertEqual(result.verdict, "clean")
        self.assertEqual(result.flag_count, 0)

    def test_added_function_is_clean(self) -> None:
        baseline = _make_snapshot(functions=[_func()])
        current = _make_snapshot(functions=[
            _func(),
            _func(symbol="new_helper", start_line=12, end_line=15, cc=2),
        ])
        result = MODULE.audit_delta(baseline, current)
        self.assertEqual(result.verdict, "clean")

    def test_cc_reduction_same_function_is_clean(self) -> None:
        baseline = _make_snapshot(functions=[_func(cc=10)])
        current = _make_snapshot(functions=[_func(cc=5)])
        result = MODULE.audit_delta(baseline, current)
        self.assertEqual(result.verdict, "clean")


class TestSplitDetection(unittest.TestCase):
    def test_split_preserving_complexity_is_suspicious(self) -> None:
        baseline = _make_snapshot(functions=[
            _func(symbol="big_handler", cc=20),
        ])
        current = _make_snapshot(functions=[
            _func(symbol="part_a", start_line=1, end_line=5, cc=7),
            _func(symbol="part_b", start_line=6, end_line=10, cc=7),
            _func(symbol="part_c", start_line=11, end_line=15, cc=7),
        ])
        result = MODULE.audit_delta(baseline, current)
        self.assertEqual(result.verdict, "suspicious")
        categories = [f.category for f in result.flags]
        self.assertIn("split-without-reduction", categories)

    def test_split_reducing_complexity_is_clean(self) -> None:
        baseline = _make_snapshot(functions=[
            _func(symbol="big_handler", cc=20),
        ])
        # Only one new function replaced it — not a split
        current = _make_snapshot(functions=[
            _func(symbol="simplified_handler", cc=5),
        ])
        result = MODULE.audit_delta(baseline, current)
        split_flags = [f for f in result.flags if f.category == "split-without-reduction"]
        self.assertEqual(len(split_flags), 0)


class TestScopeEscape(unittest.TestCase):
    def test_file_disappeared_without_deletion_is_suspicious(self) -> None:
        baseline = _make_snapshot(
            functions=[_func(file="src/core.py", symbol="process", cc=15)],
        )
        current = _make_snapshot(functions=[])
        result = MODULE.audit_delta(baseline, current)
        self.assertEqual(result.verdict, "suspicious")
        categories = [f.category for f in result.flags]
        self.assertIn("scope-escape", categories)

    def test_trivial_cc_disappearance_is_ignored(self) -> None:
        baseline = _make_snapshot(
            functions=[_func(file="src/util.py", symbol="trivial", cc=1)],
        )
        current = _make_snapshot(functions=[])
        result = MODULE.audit_delta(baseline, current)
        escape_flags = [f for f in result.flags if f.category == "scope-escape"]
        self.assertEqual(len(escape_flags), 0)


class TestScopeNarrowing(unittest.TestCase):
    def test_narrowed_target_is_suspicious(self) -> None:
        baseline = _make_snapshot(target="/tmp/repo")
        current = _make_snapshot(target="/tmp/repo/src/subpackage")
        result = MODULE.audit_delta(baseline, current)
        categories = [f.category for f in result.flags]
        self.assertIn("scope-narrowing", categories)

    def test_same_target_is_clean(self) -> None:
        baseline = _make_snapshot(target="/tmp/repo")
        current = _make_snapshot(target="/tmp/repo")
        result = MODULE.audit_delta(baseline, current)
        narrowing_flags = [f for f in result.flags if f.category == "scope-narrowing"]
        self.assertEqual(len(narrowing_flags), 0)


class TestHollowCoverage(unittest.TestCase):
    def test_new_test_file_with_no_assertions_is_suspicious(self) -> None:
        baseline = _make_snapshot(test_assertions={})
        current = _make_snapshot(test_assertions={"tests/test_new.py": 0})
        result = MODULE.audit_delta(baseline, current)
        categories = [f.category for f in result.flags]
        self.assertIn("hollow-coverage", categories)

    def test_new_test_file_with_assertions_is_clean(self) -> None:
        baseline = _make_snapshot(test_assertions={})
        current = _make_snapshot(test_assertions={"tests/test_new.py": 5})
        result = MODULE.audit_delta(baseline, current)
        hollow_flags = [f for f in result.flags if f.category == "hollow-coverage"]
        self.assertEqual(len(hollow_flags), 0)

    def test_gutted_test_file_is_warning(self) -> None:
        baseline = _make_snapshot(test_assertions={"tests/test_old.py": 10})
        current = _make_snapshot(test_assertions={"tests/test_old.py": 0})
        result = MODULE.audit_delta(baseline, current)
        self.assertIn(result.verdict, ("warning", "suspicious"))
        categories = [f.category for f in result.flags]
        self.assertIn("hollow-coverage", categories)


class TestSnapshotRoundtrip(unittest.TestCase):
    def test_snapshot_serialization(self) -> None:
        snap = _make_snapshot(
            functions=[_func()],
            file_hashes={"src/main.py": "abc123"},
            test_assertions={"tests/test_main.py": 3},
        )
        data = MODULE.snapshot_to_dict(snap)
        restored = MODULE.snapshot_from_dict(data)
        self.assertEqual(len(restored.functions), 1)
        self.assertEqual(restored.functions[0].symbol, "do_stuff")
        self.assertEqual(restored.file_hashes, {"src/main.py": "abc123"})
        self.assertEqual(restored.test_file_assertion_counts, {"tests/test_main.py": 3})


class TestRenderOutput(unittest.TestCase):
    def test_text_output_includes_verdict_line(self) -> None:
        baseline = _make_snapshot(functions=[_func()])
        current = _make_snapshot(functions=[_func()])
        result = MODULE.audit_delta(baseline, current)
        text = MODULE.render_text(result)
        self.assertIn("DELTA_INTEGRITY: clean", text)

    def test_json_output_is_valid(self) -> None:
        baseline = _make_snapshot(functions=[_func()])
        current = _make_snapshot(functions=[_func()])
        result = MODULE.audit_delta(baseline, current)
        data = json.loads(MODULE.render_json(result))
        self.assertEqual(data["verdict"], "clean")


class TestCollectInventory(unittest.TestCase):
    def test_collects_python_functions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
            src = repo / "src"
            src.mkdir()
            (src / "app.py").write_text(
                "def handler(request):\n"
                "    if request.method == 'GET':\n"
                "        return 200\n"
                "    return 400\n",
                encoding="utf-8",
            )
            snap = MODULE.collect_inventory(repo, ["python"])
            self.assertEqual(len(snap.functions), 1)
            self.assertEqual(snap.functions[0].symbol, "handler")
            self.assertEqual(snap.functions[0].cc, 2)

    def test_counts_assertions_in_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
            tests = repo / "tests"
            tests.mkdir()
            (tests / "test_app.py").write_text(
                "def test_handler():\n"
                "    assert handler() == 200\n"
                "    assert handler() != 500\n",
                encoding="utf-8",
            )
            snap = MODULE.collect_inventory(repo, ["python"])
            test_key = [k for k in snap.test_file_assertion_counts if "test_app" in k]
            self.assertTrue(test_key)
            self.assertGreaterEqual(snap.test_file_assertion_counts[test_key[0]], 2)


if __name__ == "__main__":
    unittest.main()
