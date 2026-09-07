from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "SKILL.md",
    ROOT / "references" / "combo-routing.md",
)


class SmartRouteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = "\n".join(
            document.read_text(encoding="utf-8") for document in DOCUMENTS
        )

    def test_stale_authority_guidance_is_absent(self) -> None:
        for pattern in (
            r"\bSOL\s+`?(?:medium|max)\b",
            r"gpt-5\.6-sol[^\n]*(?:medium|max)",
            r"gpt-5\.6-terra",
            r"Terra ultra",
        ):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.text, re.IGNORECASE))

    def test_model_preserving_route_authority_is_explicit(self) -> None:
        self.assertIn("SOL route-v2 at `xhigh`", self.text)
        self.assertIn("Grok route-v2 at `high`", self.text)
        self.assertIn("sbp route pick sol --refresh --json", self.text)
        self.assertIn("sbp route pick <lane> --refresh --json", self.text)
        self.assertIn("same-family Cursor", self.text)
        self.assertIn("MODEL_CHANGE", self.text)


if __name__ == "__main__":
    unittest.main()
