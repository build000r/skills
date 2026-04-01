import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = SourceFileLoader(
    "analyze_crap",
    str(ROOT / "scripts" / "analyze_crap.py"),
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

    def test_iter_supported_files_ignores_dot_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "src").mkdir()
            wanted = repo / "src" / "wanted.py"
            wanted.write_text("def wanted():\n    return 1\n", encoding="utf-8")
            ignored = repo / ".cache"
            ignored.mkdir()
            (ignored / "leak.rs").write_text("fn leak() {}\n", encoding="utf-8")

            files = MODULE.iter_supported_files(repo, ["python", "rust"])

            self.assertEqual(files, [wanted.resolve()])

    def test_analyze_rust_does_not_treat_lifetimes_as_single_quoted_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.rs"
            source.write_text(
                "\n".join(
                    [
                        "fn frame() -> &'static str {",
                        '    "ok"',
                        "}",
                        "",
                        "fn small() {",
                        "    let value = 1;",
                        "}",
                        "",
                        "fn with_char() {",
                        "    let marker = ':';",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            findings = {
                symbol: (start_line, end_line, cc)
                for symbol, start_line, end_line, cc in MODULE.analyze_rust(source)
            }

            self.assertEqual(findings["frame"], (1, 3, 1))
            self.assertEqual(findings["small"], (5, 7, 1))
            self.assertEqual(findings["with_char"], (9, 11, 1))

    def test_analyze_typescript_keeps_single_quoted_strings_as_literals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "sample.ts"
            source.write_text(
                "\n".join(
                    [
                        "export function sample() {",
                        "  const label = '{not a block}';",
                        "  if (label) {",
                        "    return label;",
                        "  }",
                        "  return 'fallback';",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            findings = MODULE.analyze_typescript(source)

            self.assertEqual(findings, [("sample", 1, 7, 2)])

    def test_render_report_mentions_mutation_hand_off_below_threshold(self) -> None:
        repo = Path("/tmp/repo")
        report = MODULE.render_report(
            repo,
            [
                MODULE.Finding(
                    language="python",
                    path=repo / "src" / "sample.py",
                    symbol="sample",
                    start_line=1,
                    end_line=3,
                    cc=2,
                    coverage=1.0,
                    crap=10.0,
                )
            ],
        )

        self.assertIn(
            "- mutation-hardening: /mutate the top hotspot groups once the baseline test path is green; use survivors to drive stronger tests, then rerun CRAP toward < 8",
            report,
        )

    def test_render_report_defers_mutation_hand_off_above_threshold(self) -> None:
        repo = Path("/tmp/repo")
        report = MODULE.render_report(
            repo,
            [
                MODULE.Finding(
                    language="python",
                    path=repo / "src" / "sample.py",
                    symbol="sample",
                    start_line=1,
                    end_line=3,
                    cc=6,
                    coverage=0.2,
                    crap=72.0,
                )
            ],
        )

        self.assertIn(
            "- mutation-hardening: defer /mutate until the scoped FINAL_SCORE is below 30 or the hotspot is otherwise stable enough to mutate economically",
            report,
        )


if __name__ == "__main__":
    unittest.main()
