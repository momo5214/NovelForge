import unittest
from pathlib import Path


class ArchitectureStep4PromptRoutingTests(unittest.TestCase):
    def test_architecture_prompt_detection_accepts_step4_legacy_and_canonical_names(self):
        from app.api.endpoints.ai import is_architecture_prompt_template

        self.assertTrue(is_architecture_prompt_template("ANG.M0.architecture_step1_mission"))
        self.assertTrue(is_architecture_prompt_template("ANG.M0.architecture_step4_character"))
        self.assertTrue(is_architecture_prompt_template("步骤四-核心角色规划"))
        self.assertFalse(is_architecture_prompt_template("增强章节角色规划"))

    def test_card_service_uses_canonical_step4_prompt_name(self):
        from app.services.card_service import ARCHITECTURE_STEP_PROMPTS

        self.assertEqual(ARCHITECTURE_STEP_PROMPTS[4], "ANG.M0.architecture_step4_character")

    def test_project_creation_workflow_uses_canonical_step4_prompt_name(self):
        workflow_file = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "bootstrap"
            / "workflows"
            / "项目创建·增强创作链路.wf"
        )

        content = workflow_file.read_text(encoding="utf-8")

        self.assertIn('"prompt_name": "ANG.M0.architecture_step4_character"', content)
        self.assertNotIn('"prompt_name": "步骤四-核心角色规划"', content)


if __name__ == "__main__":
    unittest.main()
