import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "scripts").resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCORE_MODULE = SourceFileLoader(
    "score_skill_contract",
    str((SCRIPTS_DIR / "score_skill_contract.py").resolve()),
).load_module()


class ScoreSkillContractTests(unittest.TestCase):
    def write_skill(self, root: Path, name: str, body: str) -> Path:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    f"name: {name}",
                    f'description: "Use when testing optimization readiness scoring for {name}."',
                    "---",
                    "",
                    body.strip(),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return skill_dir

    def test_skill_without_scoring_contract_is_inadequate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "plain-skill",
                "# Plain Skill\n\nRun the requested workflow and validate the result.",
            )

            payload = SCORE_MODULE.score_skill(skill_dir)

        self.assertEqual(payload["verdict"], "inadequate")
        self.assertLess(payload["optimization_readiness_score"], 600)
        self.assertIn("weights_and_formula", payload["mandatory_gaps"])
        self.assertIn("loss_framing", payload["mandatory_gaps"])

    def test_scoring_contract_in_reference_counts_toward_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = self.write_skill(
                Path(tmpdir),
                "scored-skill",
                "# Scored Skill\n\nRead references/score.md before reviewing output quality.",
            )
            references = skill_dir / "references"
            references.mkdir()
            (references / "score.md").write_text(
                "\n".join(
                    [
                        "# Optimization score",
                        "",
                        "- Objective: optimize output quality for the operator outcome.",
                        "- Dimensions: clarity, elegance, robustness, utility, and risk.",
                        "- Scale anchors: 0, 500, 1000. 0 means unusable, 500 means mixed, 1000 means excellent.",
                        "- Weights: w_i values are defined per dimension.",
                        "- Formula: overall_score = sum(w_i * score_i).",
                        "- Loss: loss = sum(w_i * (1000 - score_i)); report top loss contributors and thresholds.",
                        "- Decision: if a score is low, the next patch targets that loss before prose polish.",
                        "- Evidence calibration: validate with tests, transcript evidence, and watch metrics.",
                        "- Anti-gaming: avoid Goodhart gaming, boilerplate scoring, and false precision.",
                    ]
                ),
                encoding="utf-8",
            )

            payload = SCORE_MODULE.score_skill(skill_dir)

        self.assertEqual(payload["verdict"], "strong")
        self.assertGreaterEqual(payload["optimization_readiness_score"], 800)
        self.assertEqual(payload["mandatory_gaps"], [])

    def test_catalog_mode_ranks_scored_skills_and_lists_exemptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_skill(
                root,
                "plain-skill",
                "# Plain Skill\n\nRun the workflow and validate the result.",
            )
            self.write_skill(
                root,
                "mechanical-skill",
                "# Mechanical Skill\n\nRun the fixed validator and return pass or fail.",
            )
            exemptions_path = root / "exemptions.json"
            exemptions_path.write_text(
                """{
  "mechanical-skill": {
    "reason": "Deterministic pass/fail validator.",
    "validator": "mechanical-skill/scripts/check.sh"
  }
}""",
                encoding="utf-8",
            )

            payload = SCORE_MODULE.score_catalog(root, exemptions_path=exemptions_path)

        self.assertEqual(payload["summary"]["scored_count"], 1)
        self.assertEqual(payload["summary"]["exempt_count"], 1)
        self.assertEqual(payload["ranked"][0]["skill"], "plain-skill")
        self.assertEqual(payload["exemptions"][0]["skill"], "mechanical-skill")
        self.assertEqual(payload["exemptions"][0]["verdict"], "exempt_mechanical")


if __name__ == "__main__":
    unittest.main()
