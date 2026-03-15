import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "analyze_crap",
    "/Users/b/repos/opensource/skills/crap/scripts/analyze_crap.py",
).load_module()


class AnalyzeCrapCoverageTests(unittest.TestCase):
    def test_find_coverage_files_includes_standard_coverage_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "package.json").write_text("{}\n", encoding="utf-8")
            (repo / "coverage").mkdir()
            artifact = repo / "coverage" / "lcov.info"
            artifact.write_text("TN:\n", encoding="utf-8")

            matches = MODULE.find_coverage_files(repo)

            self.assertIn(artifact.resolve(), matches)

    def test_load_coverage_reads_lcov_from_coverage_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "package.json").write_text("{}\n", encoding="utf-8")
            (repo / "src").mkdir()
            source_file = repo / "src" / "sample.ts"
            source_file.write_text("export function sample() {\n  return 1\n}\n", encoding="utf-8")
            (repo / "coverage").mkdir()
            (repo / "coverage" / "lcov.info").write_text(
                "TN:\n"
                "SF:src/sample.ts\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "DA:3,1\n"
                "LF:3\n"
                "LH:3\n"
                "end_of_record\n",
                encoding="utf-8",
            )

            coverage = MODULE.load_coverage(repo)

            self.assertEqual(coverage.coverage_for(source_file, 1, 3), 1.0)

    def test_iter_supported_files_ignores_dot_venv_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "src").mkdir()
            wanted = repo / "src" / "wanted.ts"
            wanted.write_text("export function wanted() { return 1 }\n", encoding="utf-8")
            ignored = repo / ".venv.old.20260304135400"
            ignored.mkdir()
            (ignored / "leak.py").write_text("def leak():\n    return 1\n", encoding="utf-8")

            files = MODULE.iter_supported_files(repo, ["python", "typescript"])

            self.assertEqual(files, [wanted.resolve()])


if __name__ == "__main__":
    unittest.main()
