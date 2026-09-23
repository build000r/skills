from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = (
    ROOT / "references" / "workgraph-synthesis.md",
    ROOT / "references" / "mode-template.md",
    ROOT / "references" / "grok-sidecar-selection.md",
    ROOT / "references" / "model-economics.md",
)
HISTORICAL_MARKER = "HISTORICAL ONLY:"


class RouteReferenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lines = [
            (path.name, number, line)
            for path in REFERENCES
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            )
        ]

    def assert_no_normative_pattern(self, pattern: str) -> None:
        compiled = re.compile(pattern, re.IGNORECASE)
        findings = [
            f"{name}:{number}: {line}"
            for name, number, line in self.lines
            if HISTORICAL_MARKER not in line and compiled.search(line)
        ]
        self.assertEqual([], findings)

    def test_no_stale_sol_or_availability_fallback_guidance(self) -> None:
        for pattern in (
            r"gpt-5\.6-sol\s*(?:at|:)\s*`?(?:medium|max)\b",
            r"\bSOL\s+`?(?:medium|max)\b",
            r"gpt-5\.6-terra",
            r"availability alone selects",
        ):
            with self.subTest(pattern=pattern):
                self.assert_no_normative_pattern(pattern)

    def test_current_guidance_uses_exact_route_v2_authority(self) -> None:
        synthesis = REFERENCES[0].read_text(encoding="utf-8")
        mode = REFERENCES[1].read_text(encoding="utf-8")
        self.assertIn("sbp route high --refresh --json", synthesis)
        self.assertIn("route_ntm_spawn.sh --decision-json", synthesis)
        self.assertIn("high work tier", synthesis)
        self.assertIn("MODEL_CHANGE", synthesis)
        self.assertIn("sbp route <low|med|high> --refresh --json", mode)
        self.assertIn("`high` for no-ragrets composition", mode)
        self.assertIn("`med` for ordinary implementation", mode)
        self.assertIn("`low` for runtime orchestration", mode)

    def test_candidate_models_require_route_and_acceptance_proof(self) -> None:
        policy = REFERENCES[3].read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("GPT-6 Luna", policy)
        self.assertIn("Claude Opus 5.5", policy)
        self.assertIn("Grok 4.7", policy)
        self.assertIn("cost per accepted node", policy)
        self.assertIn("no new blocker/severe review", policy)
        self.assertIn("New benchmark releases nominate routes for a", skill)
        self.assertIn("`med` for ordinary implementation", skill)

    def test_grok_45_mentions_are_explicitly_historical(self) -> None:
        findings = [
            f"{name}:{number}: {line}"
            for name, number, line in self.lines
            if re.search(r"Grok 4\.5", line, re.IGNORECASE)
            and HISTORICAL_MARKER not in line
        ]
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
