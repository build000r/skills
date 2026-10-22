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
        cls.documents = {
            document: document.read_text(encoding="utf-8") for document in DOCUMENTS
        }
        cls.text = "\n".join(cls.documents.values())

    def test_stale_authority_guidance_is_absent(self) -> None:
        for pattern in (
            r"\bSOL\s+`?(?:medium|max)\b",
            r"gpt-5\.6-sol[^\n]*(?:medium|max)",
            r"gpt-5\.6-terra",
            r"Terra ultra",
            r"Standing Grok-to-Codex Fallback",
            r"(?:use|to) the SOL lane",
            r"Prefer the Grok controller",
        ):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.text, re.IGNORECASE))

    def test_routing_documents_do_not_pin_effort(self) -> None:
        for document, text in self.documents.items():
            with self.subTest(document=document.name):
                self.assertIsNone(
                    re.search(
                        r"\b(?:SOL|Grok) route-v2 at\s+`(?:low|medium|high|xhigh|max)`",
                        text,
                    )
                )

    def test_returned_route_is_authoritative_in_each_document(self) -> None:
        # Check separately: a correct reference must not hide a stale SKILL.md.
        for document, text in self.documents.items():
            for required in (
                "runnable: true",
                "complete decision",
                "returned effort",
                "Do not block or ask for approval",
            ):
                with self.subTest(document=document.name, required=required):
                    self.assertTrue(required in text, f"Missing {required!r}")

    def test_route_commands_and_real_no_route_boundary_remain(self) -> None:
        self.assertIn("sbp route <low|med|high> --refresh --json", self.text)
        self.assertNotIn("sbp route pick sol --refresh --json", self.text)
        for document, text in self.documents.items():
            for required in ("tier no-route stops", "MODEL_CHANGE", "fresh-eyes"):
                with self.subTest(document=document.name, required=required):
                    self.assertTrue(required in text, f"Missing {required!r}")

    def test_native_selection_preserves_safe_handoff(self) -> None:
        skill = self.documents[ROOT / "SKILL.md"]
        fallback = skill.split("### Native Selection And Safe Continuation", 1)[1].split(
            "`smart` chooses the next move", 1
        )[0]
        compact = " ".join(fallback.split())
        for required in (
            "without asking for permission",
            "current Codex session and native Codex subagents",
            "account binding",
            "stop or fence the original writer",
            "transfer only the remaining work",
            "independent fresh-eyes reviewer who did not implement",
            "stop the affected work",
            "Preserve user provider limits",
            "Do not manufacture an external route prerequisite",
        ):
            with self.subTest(required=required):
                self.assertIn(required, compact)

    def test_combo_cannot_restore_permission_loop(self) -> None:
        reference = self.documents[ROOT / "references" / "combo-routing.md"]
        self.assertIn("../SKILL.md#native-selection-and-safe-continuation", reference)
        self.assertIn("without asking for permission", reference)
        self.assertIn("who did not implement the change", reference)
        self.assertNotIn("no-route stops that dispatch unless", self.text)


if __name__ == "__main__":
    unittest.main()
