#!/usr/bin/env python3
"""Score a skill's optimization-readiness contract.

This helper is intentionally heuristic. It answers one narrow review question:
does the skill text contain a usable scoring/loss model for subjective quality?
Final `skill_quality_score` still comes from transcript evidence and reviewer
judgment.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from lib.skill_bundle_filter import iter_included_skill_files
except ImportError:  # pragma: no cover - only used when copied outside the skill.
    iter_included_skill_files = None


@dataclass(frozen=True)
class Dimension:
    name: str
    weight: int
    min_hits: int
    patterns: tuple[str, ...]
    rationale: str


DIMENSIONS = (
    Dimension(
        "objective_named",
        120,
        2,
        (
            r"\bobjective\b",
            r"\boptimi[sz](?:e|ing|ation)\b",
            r"\bsuccess criteria\b",
            r"\bquality target\b",
            r"\bgoal\b",
            r"\boutcome\b",
        ),
        "Names the outcome or quality target the score optimizes.",
    ),
    Dimension(
        "soft_dimensions_defined",
        170,
        4,
        (
            r"\bdimensions?\b",
            r"\bfactors?\b",
            r"\bcriteria\b",
            r"\brubric\b",
            r"\bscorecard\b",
            r"\belegance\b",
            r"\bclarity\b",
            r"\brobustness\b",
            r"\butility\b",
            r"\brisk\b",
            r"\breliability\b",
        ),
        "Defines multiple soft factors that can be scored.",
    ),
    Dimension(
        "scale_anchors",
        140,
        3,
        (
            r"\b0\s*(?:/|-|to)\s*1000\b",
            r"\b0\s*,\s*500\s*,\s*1000\b",
            r"\blow\b.*\bmid\b.*\bhigh\b",
            r"\banchors?\b",
            r"\bscale\b",
            r"\b1000 means\b",
            r"\b500 means\b",
            r"\b0 means\b",
        ),
        "Provides anchors so scores can be applied consistently.",
    ),
    Dimension(
        "weights_and_formula",
        150,
        3,
        (
            r"\bweights?\b",
            r"\bweighted\b",
            r"\bformula\b",
            r"\boverall_score\b",
            r"\breview_score\b",
            r"\bscore_i\b",
            r"\bw_i\b",
            r"\bsum\s*\(",
        ),
        "Defines weights and an aggregation formula.",
    ),
    Dimension(
        "loss_framing",
        150,
        3,
        (
            r"\bloss\b",
            r"\bpenalt(?:y|ies)\b",
            r"\bthresholds?\b",
            r"\bcap\b",
            r"\btop_loss\b",
            r"\btop loss\b",
            r"\b1000\s*-\s*score\b",
            r"\bmax\s*\(\s*0\b",
        ),
        "Turns scores into loss, penalties, thresholds, or caps.",
    ),
    Dimension(
        "decision_linkage",
        140,
        3,
        (
            r"\bdecision\b",
            r"\bnext patch\b",
            r"\bnext fix\b",
            r"\bgate\b",
            r"\bif\b.{0,40}\bscore\b",
            r"\bwhen\b.{0,40}\blow\b",
            r"\bdo next\b",
            r"\bpass\b",
            r"\bfail\b",
            r"\bblock\b",
        ),
        "Explains how scores change the agent's next action.",
    ),
    Dimension(
        "evidence_calibration",
        80,
        3,
        (
            r"\bevidence\b",
            r"\btranscript\b",
            r"\bvalidation\b",
            r"\bverify\b",
            r"\bmetrics?\b",
            r"\btests?\b",
            r"\bobservations?\b",
            r"\bcalibrat(?:e|ion)\b",
            r"\bwatch metric\b",
        ),
        "Ties scoring to evidence, tests, metrics, or observations.",
    ),
    Dimension(
        "anti_gaming_guardrails",
        70,
        2,
        (
            r"\bgoodhart\b",
            r"\bgaming\b",
            r"\bfalse precision\b",
            r"\bfake precision\b",
            r"\bdecorative\b",
            r"\bboilerplate\b",
            r"\banti-gaming\b",
            r"\boverfit(?:ting)?\b",
            r"\bnumerology\b",
        ),
        "Warns against score gaming, boilerplate compliance, or false precision.",
    ),
)

DEFAULT_EXEMPTIONS_PATH = (
    Path(__file__).resolve().parent.parent / "references" / "soft-score-exemptions.json"
)


def skill_markdown_path(path: Path) -> Path:
    if path.is_dir():
        return path / "SKILL.md"
    return path


def read_text(path: Path) -> str:
    skill_md = skill_markdown_path(path)
    if not skill_md.exists():
        raise SystemExit(f"SKILL.md not found: {skill_md}")
    return skill_md.read_text(encoding="utf-8", errors="ignore")


def read_score_corpus(path: Path) -> str:
    if not path.is_dir():
        return read_text(path)

    if iter_included_skill_files is None:
        files = sorted(path.rglob("*.md"))
    else:
        files = [
            file_path
            for file_path in iter_included_skill_files(path)
            if file_path.suffix.lower() == ".md"
        ]

    chunks: list[str] = []
    for file_path in files:
        try:
            rel = file_path.relative_to(path)
        except ValueError:
            rel = file_path
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        chunks.append(f"\n\n## FILE: {rel}\n\n{text}")
    return "\n".join(chunks)


def skill_name(path: Path, text: str) -> str:
    match = re.search(r"^name:\s*([A-Za-z0-9_-]+)\s*$", text, re.MULTILINE)
    return match.group(1) if match else skill_markdown_path(path).parent.name


def count_hits(patterns: tuple[str, ...], text: str) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE | re.DOTALL))


def evidence_lines(patterns: tuple[str, ...], text: str, limit: int = 3) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        if len(found) >= limit:
            break
        stripped = line.strip()
        if not stripped:
            continue
        if any(re.search(pattern, stripped, re.IGNORECASE) for pattern in patterns):
            found.append(stripped[:180])
    return found


def dimension_score(dimension: Dimension, text: str) -> dict:
    hits = count_hits(dimension.patterns, text)
    score = round(min(1.0, hits / dimension.min_hits) * 1000)
    weighted_loss = round(dimension.weight * (1000 - score) / 1000, 2)
    return {
        "name": dimension.name,
        "score": score,
        "weight": dimension.weight,
        "hits": hits,
        "min_hits": dimension.min_hits,
        "weighted_loss": weighted_loss,
        "rationale": dimension.rationale,
        "evidence": evidence_lines(dimension.patterns, text),
    }


def score_skill(path: Path) -> dict:
    skill_text = read_text(path)
    corpus_text = read_score_corpus(path)
    dimensions = [dimension_score(dimension, corpus_text) for dimension in DIMENSIONS]
    total_weight = sum(item["weight"] for item in dimensions)
    total_loss = sum(item["weight"] * (1000 - item["score"]) for item in dimensions) / total_weight
    raw_score = round(1000 - total_loss)

    mandatory_gaps: list[str] = []
    scores = {item["name"]: item["score"] for item in dimensions}
    for name in ("weights_and_formula", "loss_framing"):
        if scores.get(name, 0) < 500:
            mandatory_gaps.append(name)
    if scores.get("soft_dimensions_defined", 0) < 500:
        mandatory_gaps.append("soft_dimensions_defined")

    cap = 700 if any(name in mandatory_gaps for name in ("weights_and_formula", "loss_framing")) else 1000
    if "soft_dimensions_defined" in mandatory_gaps:
        cap = min(cap, 750)
    final_score = min(raw_score, cap)
    final_loss = 1000 - final_score

    verdict = "strong"
    if final_score < 600:
        verdict = "inadequate"
    elif final_score < 800:
        verdict = "usable_but_incomplete"

    top_loss_contributors = sorted(
        dimensions,
        key=lambda item: (item["weighted_loss"], item["weight"]),
        reverse=True,
    )[:3]

    return {
        "skill": skill_name(path, skill_text),
        "path": str(skill_markdown_path(path)),
        "optimization_readiness_score": final_score,
        "optimization_readiness_loss": final_loss,
        "raw_score": raw_score,
        "score_cap": cap,
        "verdict": verdict,
        "mandatory_gaps": mandatory_gaps,
        "top_loss_contributors": [
            {
                "name": item["name"],
                "score": item["score"],
                "weighted_loss": item["weighted_loss"],
            }
            for item in top_loss_contributors
        ],
        "dimensions": dimensions,
    }


def load_exemptions(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"exemptions file must contain a JSON object: {path}")
    exemptions: dict[str, dict[str, str]] = {}
    for skill_name_value, payload in data.items():
        if not isinstance(skill_name_value, str) or not isinstance(payload, dict):
            raise SystemExit(f"invalid exemption entry in {path}: {skill_name_value!r}")
        reason = payload.get("reason")
        validator = payload.get("validator")
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit(f"exemption for {skill_name_value} is missing reason")
        if validator is not None and not isinstance(validator, str):
            raise SystemExit(f"exemption validator for {skill_name_value} must be a string")
        exemptions[skill_name_value] = {
            "reason": reason.strip(),
            "validator": validator.strip() if isinstance(validator, str) else "",
        }
    return exemptions


def catalog_skill_dirs(root: Path) -> list[Path]:
    if (root / "SKILL.md").exists():
        return [root]
    return sorted(path.parent for path in root.glob("*/SKILL.md"))


def score_catalog(root: Path, *, exemptions_path: Path | None = DEFAULT_EXEMPTIONS_PATH) -> dict:
    exemptions = load_exemptions(exemptions_path)
    ranked: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for skill_dir in catalog_skill_dirs(root):
        skill_text = read_text(skill_dir)
        name = skill_name(skill_dir, skill_text)
        seen_names.add(name)
        if name in exemptions:
            exemption = exemptions[name]
            exempted.append(
                {
                    "skill": name,
                    "path": str(skill_dir / "SKILL.md"),
                    "verdict": "exempt_mechanical",
                    "reason": exemption["reason"],
                    "validator": exemption["validator"],
                }
            )
            continue

        payload = score_skill(skill_dir)
        ranked.append(
            {
                "skill": payload["skill"],
                "path": payload["path"],
                "optimization_readiness_score": payload["optimization_readiness_score"],
                "optimization_readiness_loss": payload["optimization_readiness_loss"],
                "verdict": payload["verdict"],
                "mandatory_gaps": payload["mandatory_gaps"],
                "top_loss_contributors": payload["top_loss_contributors"],
            }
        )

    ranked.sort(key=lambda item: (item["optimization_readiness_score"], item["skill"]))
    exempted.sort(key=lambda item: item["skill"])
    verdict_counts: dict[str, int] = {}
    for item in ranked:
        verdict_counts[item["verdict"]] = verdict_counts.get(item["verdict"], 0) + 1

    unused_exemptions = sorted(set(exemptions) - seen_names)
    return {
        "catalog_root": str(root),
        "exemptions_path": str(exemptions_path) if exemptions_path else None,
        "summary": {
            "scored_count": len(ranked),
            "exempt_count": len(exempted),
            "verdict_counts": verdict_counts,
            "unused_exemptions": unused_exemptions,
        },
        "ranked": ranked,
        "exemptions": exempted,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        f"# Optimization Readiness Score: {payload['skill']}",
        "",
        f"- Score: {payload['optimization_readiness_score']}/1000",
        f"- Loss: {payload['optimization_readiness_loss']}",
        f"- Verdict: {payload['verdict']}",
        f"- Score cap: {payload['score_cap']}",
    ]
    if payload["mandatory_gaps"]:
        lines.append(f"- Mandatory gaps: {', '.join(payload['mandatory_gaps'])}")
    lines.extend(
        [
            "",
            "| Dimension | Score | Weight | Weighted loss | Evidence |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for item in payload["dimensions"]:
        evidence = "; ".join(item["evidence"]) if item["evidence"] else ""
        lines.append(
            f"| {item['name']} | {item['score']} | {item['weight']} | "
            f"{item['weighted_loss']} | {evidence} |"
        )
    lines.extend(["", "Top loss contributors:"])
    for item in payload["top_loss_contributors"]:
        lines.append(f"- {item['name']}: score {item['score']}, weighted loss {item['weighted_loss']}")
    return "\n".join(lines) + "\n"


def render_catalog_markdown(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# Skill Optimization Readiness Catalog",
        "",
        f"- Catalog root: {payload['catalog_root']}",
        f"- Scored skills: {summary['scored_count']}",
        f"- Mechanical exemptions: {summary['exempt_count']}",
        f"- Verdict counts: {json.dumps(summary['verdict_counts'], sort_keys=True)}",
    ]
    if summary["unused_exemptions"]:
        lines.append(f"- Unused exemptions: {', '.join(summary['unused_exemptions'])}")

    lines.extend(
        [
            "",
            "## Ranked Scored Skills",
            "",
            "| Skill | Score | Verdict | Mandatory gaps | Top loss contributors |",
            "|---|---:|---|---|---|",
        ]
    )
    for item in payload["ranked"]:
        losses = ", ".join(
            f"{loss['name']}={loss['weighted_loss']}"
            for loss in item["top_loss_contributors"]
        )
        gaps = ", ".join(item["mandatory_gaps"])
        lines.append(
            f"| {item['skill']} | {item['optimization_readiness_score']} | "
            f"{item['verdict']} | {gaps} | {losses} |"
        )

    lines.extend(
        [
            "",
            "## Explicit Mechanical Exemptions",
            "",
            "| Skill | Reason | Validator |",
            "|---|---|---|",
        ]
    )
    for item in payload["exemptions"]:
        lines.append(f"| {item['skill']} | {item['reason']} | {item['validator']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", help="Skill directory, SKILL.md file, or catalog root")
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="Score every top-level skill under skill_path and apply explicit exemptions",
    )
    parser.add_argument(
        "--exemptions",
        type=Path,
        default=DEFAULT_EXEMPTIONS_PATH,
        help="JSON file of mechanical/deterministic skill exemptions for catalog mode",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = parser.parse_args()

    if args.catalog:
        payload = score_catalog(Path(args.skill_path), exemptions_path=args.exemptions)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(render_catalog_markdown(payload), end="")
        return

    payload = score_skill(Path(args.skill_path))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_markdown(payload), end="")


if __name__ == "__main__":
    main()
