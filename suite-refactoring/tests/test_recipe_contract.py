#!/usr/bin/env python3
"""Contract tests for the recipe/registry bijection checker.

Two different things need proving, and conflating them would leave a hole:

  * that the *shipped* reference is well-formed — every recipe carries its
    fields and all five sections, and no two claim the same id;
  * that the *checker* actually detects drift — each failure class is
    constructed synthetically and asserted, because a checker that always
    returns green would pass the live registry too.

The synthetic cases are why this file does not need the Skillbox checkout to
exist. The live registry is checked when it is present and skipped when it is
not, so the suite stays portable.

  python3 suite-refactoring/tests/test_recipe_contract.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "check_recipe_contract.py"
RECIPES = SKILL / "references" / "recipes.md"

# Optional live check. Supplied by the caller, never guessed from a sibling
# directory: this skill ships publicly and must not assume the layout of the
# tree it was written in.
LIVE_REGISTRY_ENV = "SUITE_READINESS_REGISTRY"
_live = os.environ.get(LIVE_REGISTRY_ENV, "").strip()
LIVE_REGISTRY = Path(_live) if _live else None


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_recipe_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def make_registry(codes, recipe_ids=None):
    """A minimal but schema-valid registry over the given (code, recipe_id, axis, blocks)."""
    entries = [
        {"code": code, "recipe_id": recipe_id, "axis": axis, "blocks": blocks}
        for code, recipe_id, axis, blocks in codes
    ]
    return {
        "schema": "suite-readiness/v1",
        "schema_version": 1,
        "codes": entries,
        "recipe_ids": sorted(entry["recipe_id"] for entry in entries)
        if recipe_ids is None
        else recipe_ids,
    }


def make_recipes(codes, labels=checker.REQUIRED_LABELS, omit_fields=()):
    """Render a recipes document for the given codes."""
    blocks = ["# Synthetic recipes\n"]
    for code, recipe_id, axis, blocks_value in codes:
        lines = [f"### {code}\n"]
        for field, value in (
            ("recipe_id", recipe_id),
            ("axis", axis),
            ("blocks", blocks_value),
        ):
            if field not in omit_fields:
                lines.append(f"- {field}: `{value}`")
        lines.append("")
        for label in labels:
            lines.append(f"**{label}.** Text for {label}.")
            lines.append("")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


BASE = [
    ("ALPHA_MISSING", "suite-refactor/alpha", "selection_completeness", "parallel"),
    ("BETA_STATIC", "suite-refactor/beta", "concurrency_safety", "parallel"),
]


class ShippedReferenceTests(unittest.TestCase):
    """The reference this skill actually ships."""

    def setUp(self) -> None:
        self.parsed = checker.parse_recipes(RECIPES.read_text(encoding="utf-8"))

    def test_every_recipe_is_complete(self) -> None:
        self.assertTrue(self.parsed, "no recipes parsed from the shipped reference")
        for code, entry in sorted(self.parsed.items()):
            for field in checker.REQUIRED_FIELDS:
                self.assertIn(field, entry["fields"], f"{code} does not declare {field}")
            missing = [
                label for label in checker.REQUIRED_LABELS if label not in entry["labels"]
            ]
            self.assertEqual(missing, [], f"{code} is missing section(s) {missing}")

    def test_recipe_ids_are_unique(self) -> None:
        ids = [entry["fields"]["recipe_id"] for entry in self.parsed.values()]
        self.assertEqual(len(ids), len(set(ids)), "a recipe_id is claimed twice")

    def test_headings_are_finding_codes(self) -> None:
        for code in self.parsed:
            self.assertRegex(code, r"^[A-Z][A-Z0-9_]*$")


class BijectionTests(unittest.TestCase):
    """Each drift class, constructed on purpose."""

    def report(self, registry_codes, recipe_codes, **kwargs):
        return checker.check(
            make_registry(registry_codes), make_recipes(recipe_codes, **kwargs)
        )

    def kinds(self, report):
        return sorted({finding["kind"] for finding in report["findings"]})

    def test_exact_match_holds(self) -> None:
        report = self.report(BASE, BASE)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(report["counts"], {"live_codes": 2, "recipes": 2})

    def test_live_code_without_a_recipe_is_drift(self) -> None:
        # An agent scoring this code has nothing to open.
        report = self.report(BASE, BASE[:1])
        self.assertFalse(report["ok"])
        self.assertEqual(self.kinds(report), ["missing_recipe"])
        self.assertEqual(report["findings"][0]["code"], "BETA_STATIC")

    def test_recipe_without_a_live_code_is_drift(self) -> None:
        # The direction a guide rots in: advice for a code no scorer emits.
        report = self.report(BASE[:1], BASE)
        self.assertFalse(report["ok"])
        self.assertEqual(self.kinds(report), ["orphan_recipe"])
        self.assertEqual(report["findings"][0]["code"], "BETA_STATIC")

    def test_both_directions_at_once(self) -> None:
        extra = [("GAMMA_UNPINNED", "suite-refactor/gamma", "determinism", "caching")]
        report = self.report(BASE, BASE[:1] + extra)
        self.assertEqual(self.kinds(report), ["missing_recipe", "orphan_recipe"])

    def test_recipe_id_mismatch_is_drift(self) -> None:
        drifted = [("ALPHA_MISSING", "suite-refactor/renamed", "selection_completeness", "parallel")]
        report = self.report(BASE[:1], drifted)
        self.assertEqual(self.kinds(report), ["field_mismatch"])
        self.assertIn("renamed", report["findings"][0]["detail"])

    def test_axis_and_blocks_mismatch_is_drift(self) -> None:
        drifted = [("ALPHA_MISSING", "suite-refactor/alpha", "determinism", "caching")]
        report = self.report(BASE[:1], drifted)
        findings = [f for f in report["findings"] if f["kind"] == "field_mismatch"]
        self.assertEqual(len(findings), 2)

    def test_missing_field_is_drift(self) -> None:
        report = self.report(BASE[:1], BASE[:1], omit_fields=("axis",))
        self.assertEqual(self.kinds(report), ["missing_field"])

    def test_recipe_missing_a_section_is_drift(self) -> None:
        # The failure this catches: a plausible instruction with no evidence
        # gate, which reads complete and closes nothing.
        report = self.report(BASE[:1], BASE[:1], labels=("Detect", "Invariant", "Do", "Stop"))
        self.assertEqual(self.kinds(report), ["incomplete_recipe"])
        self.assertIn("Prove", report["findings"][0]["detail"])

    def test_empty_section_body_does_not_satisfy_the_contract(self) -> None:
        text = "### ALPHA_MISSING\n\n- recipe_id: `suite-refactor/alpha`\n" \
            "- axis: `selection_completeness`\n- blocks: `parallel`\n\n" \
            "**Detect.**\n\n**Invariant.**\n\n**Do.**\n\n**Prove.**\n\n**Stop.**\n"
        report = checker.check(make_registry(BASE[:1]), text)
        self.assertEqual(self.kinds(report), ["incomplete_recipe"])

    def test_duplicate_recipe_id_is_drift(self) -> None:
        collided = [
            ("ALPHA_MISSING", "suite-refactor/same", "selection_completeness", "parallel"),
            ("BETA_STATIC", "suite-refactor/same", "concurrency_safety", "parallel"),
        ]
        report = checker.check(make_registry(collided), make_recipes(collided))
        self.assertIn("duplicate_recipe_id", self.kinds(report))

    def test_registry_disagreeing_with_itself_is_drift(self) -> None:
        registry = make_registry(BASE, recipe_ids=["suite-refactor/alpha", "suite-refactor/ghost"])
        report = checker.check(registry, make_recipes(BASE))
        kinds = sorted({f["kind"] for f in report["findings"]})
        self.assertEqual(kinds, ["registry_self_inconsistent"])
        details = " ".join(f["detail"] for f in report["findings"])
        self.assertIn("ghost", details)
        self.assertIn("suite-refactor/beta", details)

    def test_duplicate_recipe_heading_is_a_parse_error(self) -> None:
        with self.assertRaises(checker.ContractError):
            checker.parse_recipes(make_recipes(BASE[:1] + BASE[:1]))

    def test_prose_headings_are_not_mistaken_for_recipes(self) -> None:
        text = "## Selection completeness\n\n### Applying more than one\n\n" + make_recipes(BASE[:1])
        parsed = checker.parse_recipes(text)
        self.assertEqual(sorted(parsed), ["ALPHA_MISSING"])


class RegistryInputTests(unittest.TestCase):
    def load(self, registry):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            return checker.load_registry(path)

    def test_wrong_schema_is_refused(self) -> None:
        # A future schema is not silently treated as v1: the codes and their
        # meanings are exactly what this skill's recipes are pinned against.
        registry = make_registry(BASE)
        registry["schema"] = "suite-readiness/v2"
        with self.assertRaises(checker.ContractError):
            self.load(registry)

    def test_registry_without_codes_is_refused(self) -> None:
        with self.assertRaises(checker.ContractError):
            self.load({"schema": "suite-readiness/v1", "codes": []})

    def test_duplicate_code_in_registry_is_refused(self) -> None:
        registry = make_registry(BASE[:1] + BASE[:1])
        with self.assertRaises(checker.ContractError):
            checker.registry_codes(registry)

    def test_registry_entry_missing_a_field_is_refused(self) -> None:
        registry = make_registry(BASE[:1])
        del registry["codes"][0]["axis"]
        with self.assertRaises(checker.ContractError):
            checker.registry_codes(registry)


class CliTests(unittest.TestCase):
    """Exit codes are the interface a caller scripts against."""

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def write(self, directory, registry, recipes):
        registry_path = Path(directory) / "registry.json"
        recipes_path = Path(directory) / "recipes.md"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        recipes_path.write_text(recipes, encoding="utf-8")
        return registry_path, recipes_path

    def test_holding_contract_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path, recipes_path = self.write(
                tmp, make_registry(BASE), make_recipes(BASE)
            )
            result = self.run_cli(
                "--registry", str(registry_path), "--recipes", str(recipes_path)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("bijection proven", result.stdout)

    def test_drift_exits_one_and_names_the_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path, recipes_path = self.write(
                tmp, make_registry(BASE), make_recipes(BASE[:1])
            )
            result = self.run_cli(
                "--registry", str(registry_path), "--recipes", str(recipes_path)
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("BETA_STATIC", result.stderr)

    def test_unreadable_registry_exits_two(self) -> None:
        # Distinct from drift: "I could not check" must never look like "clean".
        result = self.run_cli("--registry", "/nonexistent/registry.json")
        self.assertEqual(result.returncode, 2)

    def test_malformed_registry_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(self.run_cli("--registry", str(path)).returncode, 2)

    def test_wrong_schema_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = make_registry(BASE)
            registry["schema"] = "suite-readiness/v2"
            registry_path, recipes_path = self.write(tmp, registry, make_recipes(BASE))
            result = self.run_cli(
                "--registry", str(registry_path), "--recipes", str(recipes_path)
            )
            self.assertEqual(result.returncode, 2)

    def test_registry_argument_is_required(self) -> None:
        self.assertEqual(self.run_cli().returncode, 2)

    def test_json_report_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path, recipes_path = self.write(
                tmp, make_registry(BASE), make_recipes(BASE[:1])
            )
            result = self.run_cli(
                "--registry", str(registry_path),
                "--recipes", str(recipes_path),
                "--json",
            )
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["schema"], "suite-readiness/v1")
            self.assertEqual(payload["findings"][0]["kind"], "missing_recipe")

    def test_defaults_to_the_shipped_reference(self) -> None:
        # Invoked from an unrelated working directory: the reference is resolved
        # from the script's own location, not the caller's cwd.
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.json"
            registry_path.write_text(json.dumps(make_registry(BASE)), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--registry", str(registry_path), "--json"],
                capture_output=True, text=True, check=False, cwd=tmp,
            )
            payload = json.loads(result.stdout)
            # BASE is synthetic, so the real reference is all orphans — the point
            # is that it found and parsed the shipped file at all.
            self.assertEqual(payload["counts"]["recipes"], 10)


class PortabilityTests(unittest.TestCase):
    def test_no_machine_specific_path_is_baked_in(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", source)
        self.assertNotIn("/home/", source)
        self.assertNotIn("skillbox/tests/fixtures", source)

    def test_registry_has_no_default(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertIn("--registry", result.stdout)
        self.assertEqual(result.returncode, 0)


class LiveRegistryTests(unittest.TestCase):
    """Run against a real registry when the caller names one; skipped otherwise."""

    @unittest.skipUnless(
        LIVE_REGISTRY is not None and LIVE_REGISTRY.is_file(),
        f"set {LIVE_REGISTRY_ENV} to a registry path to run the live check",
    )
    def test_shipped_recipes_match_the_live_registry(self) -> None:
        registry = checker.load_registry(LIVE_REGISTRY)
        report = checker.check(registry, RECIPES.read_text(encoding="utf-8"))
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual(
            report["counts"]["live_codes"], report["counts"]["recipes"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
