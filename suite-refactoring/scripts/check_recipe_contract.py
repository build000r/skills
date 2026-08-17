#!/usr/bin/env python3
"""Prove the recipe reference and a suite-readiness registry are in bijection.

The finding code is this skill's API: the scorer emits a code, an agent opens
the recipe with that heading. Drift in either direction breaks it, and the two
directions fail differently, so both are checked:

  * a live code with no recipe strands an agent mid-loop with a finding it
    cannot act on;
  * a recipe with no live code teaches a fix for something the scorer will
    never emit, which is how a guide rots without anyone noticing.

The registry is read from an explicit ``--registry`` path. There is no default
and no discovery: a checker that guesses a location is a checker that silently
validates the wrong file, and one that hardcodes a path is not portable to the
next machine.

Usage:
  check_recipe_contract.py --registry <registry.json> [--recipes <recipes.md>] [--json]

Exit codes:
  0  contract holds
  1  drift (missing recipe, orphan recipe, mismatched field, malformed recipe)
  2  usage — the registry or recipe file could not be read or parsed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# The reference lives beside this script, in the same skill. Resolved from this
# file rather than from the working directory so the checker behaves the same
# wherever it is invoked from.
DEFAULT_RECIPES = Path(__file__).resolve().parent.parent / "references" / "recipes.md"

SCHEMA = "suite-readiness/v1"

# A recipe heading is a finding code: upper snake case, nothing else. Anything
# that is not a code is prose and is skipped, so the reference can carry
# sections without confusing them for recipes.
RECIPE_HEADING_RE = re.compile(r"^###\s+([A-Z][A-Z0-9_]*)\s*$", re.MULTILINE)
FIELD_RE = "^-\\s+{field}:\\s+`([^`]+)`\\s*$"

# Every recipe must carry all five. A recipe missing "Prove" is the failure mode
# this catches: a plausible instruction with no evidence gate, which reads as
# complete and closes nothing.
REQUIRED_LABELS = ("Detect", "Invariant", "Do", "Prove", "Stop")
REQUIRED_FIELDS = ("recipe_id", "axis", "blocks")


class ContractError(Exception):
    """Input could not be read or parsed. Distinct from a drift finding."""


def load_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(f"registry unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"registry is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("registry must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise ContractError(
            f"registry schema is {data.get('schema')!r}, expected {SCHEMA!r}"
        )
    codes = data.get("codes")
    if not isinstance(codes, list) or not codes:
        raise ContractError("registry has no codes array")
    return data


def registry_codes(registry: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Map live code -> its declared recipe_id, axis and blocks."""
    live: dict[str, dict[str, str]] = {}
    for entry in registry["codes"]:
        if not isinstance(entry, dict):
            raise ContractError("registry codes must be objects")
        code = entry.get("code")
        if not isinstance(code, str) or not code:
            raise ContractError("registry code entry has no code")
        if code in live:
            raise ContractError(f"registry declares {code} twice")
        missing = [f for f in REQUIRED_FIELDS if not isinstance(entry.get(f), str)]
        if missing:
            raise ContractError(f"registry entry {code} is missing {', '.join(missing)}")
        live[code] = {field: entry[field] for field in REQUIRED_FIELDS}
    return live


def parse_recipes(text: str) -> dict[str, dict[str, Any]]:
    """Map recipe heading -> declared fields and which required labels are present."""
    headings = list(RECIPE_HEADING_RE.finditer(text))
    recipes: dict[str, dict[str, Any]] = {}
    for index, match in enumerate(headings):
        code = match.group(1)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[match.end():end]
        if code in recipes:
            raise ContractError(f"recipes declare {code} twice")
        fields: dict[str, str] = {}
        for field in REQUIRED_FIELDS:
            found = re.search(FIELD_RE.format(field=field), block, re.MULTILINE)
            if found:
                fields[field] = found.group(1)
        labels = [
            label
            for label in REQUIRED_LABELS
            # The label must introduce actual text, so a bare bold heading with
            # an empty body does not satisfy the contract.
            if re.search(rf"\*\*{label}\.\*\*\s*\S", block)
        ]
        recipes[code] = {"fields": fields, "labels": labels}
    return recipes


def check(registry: dict[str, Any], recipes_text: str) -> dict[str, Any]:
    live = registry_codes(registry)
    parsed = parse_recipes(recipes_text)

    live_codes = set(live)
    recipe_codes = set(parsed)

    findings: list[dict[str, str]] = []

    for code in sorted(live_codes - recipe_codes):
        findings.append({
            "kind": "missing_recipe",
            "code": code,
            "detail": f"live code {code} has no recipe; an agent scoring it has nothing to open",
        })

    for code in sorted(recipe_codes - live_codes):
        findings.append({
            "kind": "orphan_recipe",
            "code": code,
            "detail": f"recipe {code} matches no live code in the registry",
        })

    for code in sorted(live_codes & recipe_codes):
        entry = parsed[code]
        for field in REQUIRED_FIELDS:
            declared = entry["fields"].get(field)
            if declared is None:
                findings.append({
                    "kind": "missing_field",
                    "code": code,
                    "detail": f"recipe {code} does not declare {field}",
                })
            elif declared != live[code][field]:
                findings.append({
                    "kind": "field_mismatch",
                    "code": code,
                    "detail": (
                        f"recipe {code} declares {field}={declared!r}, "
                        f"registry says {live[code][field]!r}"
                    ),
                })
        absent = [label for label in REQUIRED_LABELS if label not in entry["labels"]]
        if absent:
            findings.append({
                "kind": "incomplete_recipe",
                "code": code,
                "detail": f"recipe {code} is missing section(s): {', '.join(absent)}",
            })

    # The registry's own recipe_ids list must agree with the ids on its codes.
    # Checked here because this skill consumes both, and a registry that
    # disagrees with itself would make either direction of the bijection
    # unfalsifiable.
    declared_ids = registry.get("recipe_ids")
    if isinstance(declared_ids, list):
        from_codes = {value["recipe_id"] for value in live.values()}
        for recipe_id in sorted(set(declared_ids) - from_codes):
            findings.append({
                "kind": "registry_self_inconsistent",
                "code": recipe_id,
                "detail": f"registry lists recipe_id {recipe_id} that no code claims",
            })
        for recipe_id in sorted(from_codes - set(declared_ids)):
            findings.append({
                "kind": "registry_self_inconsistent",
                "code": recipe_id,
                "detail": f"code declares recipe_id {recipe_id} absent from recipe_ids",
            })

    duplicate_ids = sorted(
        {
            entry["fields"]["recipe_id"]
            for code, entry in parsed.items()
            if "recipe_id" in entry["fields"]
            and sum(
                1
                for other in parsed.values()
                if other["fields"].get("recipe_id") == entry["fields"]["recipe_id"]
            )
            > 1
        }
    )
    for recipe_id in duplicate_ids:
        findings.append({
            "kind": "duplicate_recipe_id",
            "code": recipe_id,
            "detail": f"recipe_id {recipe_id} is claimed by more than one recipe",
        })

    return {
        "schema": SCHEMA,
        "live_codes": sorted(live_codes),
        "recipes": sorted(recipe_codes),
        "counts": {"live_codes": len(live_codes), "recipes": len(recipe_codes)},
        "findings": findings,
        "ok": not findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check recipe/registry bijection for suite-readiness findings."
    )
    parser.add_argument(
        "--registry",
        required=True,
        help="path to a suite-readiness/v1 finding registry JSON file",
    )
    parser.add_argument(
        "--recipes",
        default=str(DEFAULT_RECIPES),
        help="path to references/recipes.md (defaults to the copy beside this script)",
    )
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(Path(args.registry))
        recipes_path = Path(args.recipes)
        try:
            recipes_text = recipes_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContractError(f"recipes unreadable: {exc}") from exc
        report = check(registry, recipes_text)
    except ContractError as exc:
        if args.json:
            print(json.dumps({"schema": SCHEMA, "ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"contract check could not run: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    elif report["ok"]:
        print(
            f"contract holds: {report['counts']['live_codes']} live codes, "
            f"{report['counts']['recipes']} recipes, bijection proven"
        )
    else:
        print(f"contract drift: {len(report['findings'])} finding(s)", file=sys.stderr)
        for finding in report["findings"]:
            print(f"  {finding['kind']}: {finding['detail']}", file=sys.stderr)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
