import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


MODULE = SourceFileLoader(
    "analyze_mutants",
    str((Path(__file__).resolve().parent.parent / "scripts" / "analyze_mutants.py").resolve()),
).load_module()


class AnalyzeMutantsTests(unittest.TestCase):
    def test_parse_mutmut_meta_and_write_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
            (repo / "mutants" / "src").mkdir(parents=True)
            meta_path = repo / "mutants" / "src" / "sample.py.meta"
            meta_path.write_text(
                json.dumps(
                    {
                        "exit_code_by_key": {
                            "pkg.module.x_alpha__mutmut_1": 0,
                            "pkg.module.x_beta__mutmut_2": 1,
                            "pkg.module.x_gamma__mutmut_3": 36,
                        },
                        "durations_by_key": {},
                        "estimated_durations_by_key": {},
                        "type_check_error_by_key": {},
                    }
                ),
                encoding="utf-8",
            )

            findings, sources = MODULE.collect_findings(repo, ["mutmut"])

            self.assertEqual(len(findings), 3)
            counts, todo_count = MODULE.summarize(findings)
            self.assertEqual(todo_count, 2)
            self.assertEqual(counts["survived"], 1)
            self.assertEqual(counts["killed"], 1)
            self.assertEqual(counts["timeout"], 1)
            self.assertEqual(sources, [meta_path.resolve()])

            ledger_path = repo / ".mutate" / "ledger.json"
            MODULE.write_ledger(ledger_path, repo, findings, sources)
            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["todo"], 2)
            self.assertEqual(payload["mutants"][0]["path"], "src/sample.py")

    def test_existing_ledger_review_status_closes_todo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
            (repo / "mutants" / "src").mkdir(parents=True)
            meta_path = repo / "mutants" / "src" / "sample.py.meta"
            key = "pkg.module.x_alpha__mutmut_1"
            meta_path.write_text(
                json.dumps(
                    {
                        "exit_code_by_key": {key: 0},
                        "durations_by_key": {},
                        "estimated_durations_by_key": {},
                        "type_check_error_by_key": {},
                    }
                ),
                encoding="utf-8",
            )

            findings, sources = MODULE.collect_findings(repo, ["mutmut"])
            ledger_path = repo / ".mutate" / "ledger.json"
            ledger_path.parent.mkdir(parents=True)
            ledger_path.write_text(
                json.dumps(
                    {
                        "mutants": [
                            {
                                "key": "mutmut:src/sample.py:pkg.module.x_alpha__mutmut_1",
                                "review_status": "equivalent",
                                "note": "reviewed already",
                                "first_seen": "2026-03-16T00:00:00+00:00",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            MODULE.apply_reviews(findings, MODULE.load_existing_reviews(ledger_path))
            report = MODULE.render_report(
                repo,
                findings,
                top=None,
                ledger_path=ledger_path,
                sources=sources,
            )

            self.assertIn("done equivalent", report)
            self.assertIn("FINAL_TODO: 0", report)

    def test_parse_stryker_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "package.json").write_text("{}\n", encoding="utf-8")
            (repo / "reports" / "mutation").mkdir(parents=True)
            report_path = repo / "reports" / "mutation" / "mutation.json"
            report_path.write_text(
                json.dumps(
                    {
                        "files": {
                            "src/example.ts": {
                                "mutants": [
                                    {
                                        "id": "1",
                                        "mutatorName": "ConditionalExpression",
                                        "replacement": "false",
                                        "status": "Survived",
                                        "location": {"start": {"line": 7}},
                                    },
                                    {
                                        "id": "2",
                                        "mutatorName": "BooleanLiteral",
                                        "replacement": "true",
                                        "status": "NoCoverage",
                                        "location": {"start": {"line": 11}},
                                    },
                                    {
                                        "id": "3",
                                        "mutatorName": "StringLiteral",
                                        "replacement": "\"x\"",
                                        "status": "Killed",
                                        "location": {"start": {"line": 14}},
                                    },
                                ]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            findings = MODULE.parse_stryker_report(repo, report_path)
            counts, todo_count = MODULE.summarize(findings)

            self.assertEqual(len(findings), 3)
            self.assertEqual(todo_count, 2)
            self.assertEqual(counts["survived"], 1)
            self.assertEqual(counts["no_coverage"], 1)
            self.assertEqual(counts["killed"], 1)
            self.assertEqual(findings[0].path, Path("src/example.ts"))
            self.assertEqual(findings[0].line, 7)

    def test_parse_cargo_text_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Cargo.toml").write_text("[package]\nname='sample'\n", encoding="utf-8")
            mutants_out = repo / "mutants.out"
            mutants_out.mkdir()
            (mutants_out / "missed.txt").write_text(
                "src/lib.rs:12 changed return value\n",
                encoding="utf-8",
            )
            (mutants_out / "caught.txt").write_text(
                "src/lib.rs:40 removed panic\n",
                encoding="utf-8",
            )

            findings, _sources = MODULE.collect_findings(repo, ["cargo-mutants"])
            counts, todo_count = MODULE.summarize(findings)

            self.assertEqual(len(findings), 2)
            self.assertEqual(todo_count, 1)
            self.assertEqual(counts["survived"], 1)
            self.assertEqual(counts["killed"], 1)
            self.assertEqual(findings[0].path, Path("src/lib.rs"))

    def test_parse_cargo_outcomes_uses_current_summary_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Cargo.toml").write_text("[package]\nname='sample'\n", encoding="utf-8")
            mutants_out = repo / "mutants.out"
            mutants_out.mkdir()
            outcomes_path = mutants_out / "outcomes.json"
            outcomes_path.write_text(
                json.dumps(
                    {
                        "outcomes": [
                            {
                                "scenario": "Baseline",
                                "summary": "Success",
                                "log_path": "log/baseline.log",
                            },
                            {
                                "scenario": {
                                    "Mutant": {
                                        "name": "src/lib.rs:12:5: replace answer -> bool with false",
                                        "file": "src/lib.rs",
                                        "function": {
                                            "function_name": "answer",
                                            "span": {"start": {"line": 11, "column": 1}},
                                        },
                                        "span": {
                                            "start": {"line": 12, "column": 5},
                                            "end": {"line": 12, "column": 20},
                                        },
                                        "replacement": "false",
                                        "genre": "FnValue",
                                    }
                                },
                                "summary": "CaughtMutant",
                                "log_path": "log/src__lib.rs_line_12_col_5.log",
                            },
                            {
                                "scenario": {
                                    "Mutant": {
                                        "name": "src/lib.rs:18:5: replace parse -> Result<()> with Ok(Default::default())",
                                        "file": "src/lib.rs",
                                        "function": {
                                            "function_name": "parse",
                                            "span": {"start": {"line": 17, "column": 1}},
                                        },
                                        "span": {
                                            "start": {"line": 18, "column": 5},
                                            "end": {"line": 18, "column": 40},
                                        },
                                        "replacement": "Ok(Default::default())",
                                        "genre": "FnValue",
                                    }
                                },
                                "summary": "Unviable",
                                "log_path": "log/src__lib.rs_line_18_col_5.log",
                            },
                        ],
                        "total_mutants": 2,
                        "caught": 1,
                        "missed": 0,
                        "timeout": 0,
                        "unviable": 1,
                        "success": 0,
                    }
                ),
                encoding="utf-8",
            )

            findings = MODULE.parse_cargo_outcomes(repo, outcomes_path)
            counts, todo_count = MODULE.summarize(findings)

            self.assertEqual(len(findings), 2)
            self.assertEqual(todo_count, 0)
            self.assertEqual(counts["killed"], 1)
            self.assertEqual(counts["ignored"], 1)
            self.assertEqual(findings[0].path, Path("src/lib.rs"))
            self.assertEqual(findings[0].line, 12)
            self.assertEqual(findings[0].symbol, "answer")

    def test_muter_is_supported_adapter(self) -> None:
        self.assertIn("muter", MODULE.SUPPORTED_ADAPTERS)
        self.assertIn("muterReport.json", MODULE.MUTER_REPORT_NAMES)

    def test_detect_language_maps_swift(self) -> None:
        self.assertEqual(MODULE.detect_language(Path("x.swift")), "swift")

    def test_canonicalize_muter_status_mappings(self) -> None:
        cases = {
            "passed": "survived",
            "failed": "killed",
            "buildError": "compile_error",
            "runtimeError": "killed",
            "noCoverage": "no_coverage",
            "timeout": "timeout",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(MODULE.canonicalize_muter_status(raw), expected)
        self.assertEqual(MODULE.canonicalize_muter_status("totally unknown"), "suspicious")

    def test_parse_muter_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Package.swift").write_text("// swift-tools-version:5.9\n", encoding="utf-8")
            report_path = repo / "muterReport.json"
            report_path.write_text(
                json.dumps(
                    {
                        "globalMutationScore": 66,
                        "totalAppliedMutationOperators": 3,
                        "numberOfKilledMutants": 2,
                        "projectCodeCoverage": 80,
                        "timeElapsed": "00:02:11",
                        "fileReports": [
                            {
                                "fileName": "SessionStore.swift",
                                "mutationScore": 50,
                                "appliedOperators": [
                                    {
                                        "mutationPoint": {
                                            "filePath": "Sources/Auth/SessionStore.swift",
                                            "position": {"line": 42, "column": 5},
                                            "mutationOperatorId": "RelationalOperatorReplacement",
                                        },
                                        "mutationSnapshot": {"before": ">", "after": "<"},
                                        "testSuiteOutcome": "passed",
                                    },
                                    {
                                        "mutationPoint": {
                                            "filePath": "Sources/Auth/SessionStore.swift",
                                            "position": {"line": 58, "column": 9},
                                            "mutationOperatorId": "RemoveSideEffects",
                                        },
                                        "mutationSnapshot": {"before": "log()", "after": ""},
                                        "testSuiteOutcome": "failed",
                                    },
                                    {
                                        "mutationPoint": {
                                            "filePath": "Sources/Auth/SessionStore.swift",
                                            "position": {"line": 71, "column": 3},
                                            "mutationOperatorId": "ChangeLogicalConnector",
                                        },
                                        "testSuiteOutcome": "noCoverage",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            findings = MODULE.parse_muter_report(repo, report_path)

            self.assertEqual(len(findings), 3)
            counts, todo_count = MODULE.summarize(findings)
            self.assertEqual(todo_count, 2)
            self.assertEqual(counts["survived"], 1)
            self.assertEqual(counts["killed"], 1)
            self.assertEqual(counts["no_coverage"], 1)
            survived = [f for f in findings if f.status == "survived"][0]
            self.assertEqual(survived.path, Path("Sources/Auth/SessionStore.swift"))
            self.assertEqual(survived.line, 42)
            self.assertEqual(survived.raw_id, "RelationalOperatorReplacement")
            self.assertIn(">", survived.detail or "")

    def test_collect_findings_dispatches_muter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "Package.swift").write_text("// swift-tools-version:5.9\n", encoding="utf-8")
            report_path = repo / "muterReport.json"
            report_path.write_text(
                json.dumps(
                    {
                        "fileReports": [
                            {
                                "fileName": "A.swift",
                                "appliedOperators": [
                                    {
                                        "mutationPoint": {
                                            "filePath": "Sources/A.swift",
                                            "position": {"line": 10},
                                            "mutationOperatorId": "SwapTernary",
                                        },
                                        "testSuiteOutcome": "passed",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            findings, sources = MODULE.collect_findings(repo, ["muter"])

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].adapter, "muter")
            self.assertEqual(sources, [report_path.resolve()])


if __name__ == "__main__":
    unittest.main()
