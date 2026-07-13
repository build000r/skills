import unittest
from pathlib import Path

import yaml


DEPLOY_ROOT = Path(__file__).resolve().parent.parent
SKILL = (DEPLOY_ROOT / "SKILL.md").read_text(encoding="utf-8")
STANDARD = (DEPLOY_ROOT / "references" / "self-release.md").read_text(
    encoding="utf-8"
)
MODE_TEMPLATE = (DEPLOY_ROOT / "references" / "mode-template.md").read_text(
    encoding="utf-8"
)


class SelfReleaseContractTests(unittest.TestCase):
    def test_skill_triggers_for_actions_cost_and_self_release(self) -> None:
        frontmatter = " ".join(SKILL.split("---", 2)[1].split())
        for phrase in (
            "local self-test",
            "self-release paths",
            "paid GitHub Actions",
            "reducing Actions spend",
            "self-deploy",
        ):
            self.assertIn(phrase, frontmatter)

    def test_cold_invocation_selects_self_release_as_the_default(self) -> None:
        self.assertIn("## Local Self-Release Is The Default", SKILL)
        self.assertIn("references/self-release.md", SKILL)
        self.assertIn("run the canonical full gate for that exact SHA", SKILL)
        self.assertIn("build once and deploy the exact gated artifact", SKILL)
        self.assertIn("never rebuild on the production host", SKILL)
        self.assertIn("optional break-glass auth, never local release authority", SKILL)
        self.assertNotIn("gh run watch", SKILL)

    def test_standard_covers_each_supported_release_surface(self) -> None:
        for heading in (
            "### Server Or Container",
            "### Pages, Edge, Or Static Hosting",
            "### Package Registry Or App Store",
        ):
            self.assertIn(heading, STANDARD)

    def test_standard_preserves_cutover_and_recovery_invariants(self) -> None:
        standard = " ".join(STANDARD.split())
        for phrase in (
            "complete one real local deploy",
            "leave the existing deploy trigger intact",
            "behavior proof",
            "state proof",
            "Rollback is code-only only when",
            "workflow_dispatch",
            "untrusted contributor",
            "target-side timer",
        ):
            self.assertIn(phrase, standard)

    def test_overlay_exposes_the_release_contract(self) -> None:
        for key in (
            "release.command",
            "release.gate",
            "release.ref_policy",
            "release.transport",
            "release.credential_probe",
            "release.manifest_dir",
            "release.break_glass_workflow",
        ):
            self.assertIn(key, MODE_TEMPLATE)

        example = yaml.safe_load(MODE_TEMPLATE.split("# Deploy Overlay Key Reference", 1)[0])
        deploy = example["client"]["context"]["deploy"]
        for target in (
            deploy["services"]["api"],
            deploy["services"]["frontend"],
            deploy["packages"]["cli"],
        ):
            self.assertEqual(target["release"]["command"], "make release")
            self.assertIn("gate", target["release"])
            self.assertIn("transport", target["release"])
            self.assertIn("credential_probe", target["release"])

    def test_main_skill_stays_within_progressive_disclosure_limit(self) -> None:
        self.assertLessEqual(len(SKILL.splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
