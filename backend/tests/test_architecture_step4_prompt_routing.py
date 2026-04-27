import unittest
from pathlib import Path


class ArchitectureStep4PromptRoutingTests(unittest.TestCase):
    def test_architecture_prompt_detection_accepts_step4_legacy_and_canonical_names(self):
        from app.api.endpoints.ai import is_architecture_prompt_template

        # 旧版 ANG.M0 前缀仍应识别
        self.assertTrue(is_architecture_prompt_template("ANG.M0.architecture_step1_mission"))
        self.assertTrue(is_architecture_prompt_template("ANG.M0.architecture_step4_character"))
        # 新版本地名称
        self.assertTrue(is_architecture_prompt_template("步骤一-分卷使命宣言"))
        self.assertTrue(is_architecture_prompt_template("步骤四-核心角色规划"))
        self.assertTrue(is_architecture_prompt_template("步骤五-叙事风格与文本策略"))
        # 非架构提示词
        self.assertFalse(is_architecture_prompt_template("增强章节角色规划"))

    def test_card_service_uses_local_prompt_names(self):
        from app.services.card_service import ARCHITECTURE_STEP_PROMPTS

        self.assertEqual(ARCHITECTURE_STEP_PROMPTS[1], "步骤一-分卷使命宣言")
        self.assertEqual(ARCHITECTURE_STEP_PROMPTS[2], "步骤二-世界观与冲突发生器")
        self.assertEqual(ARCHITECTURE_STEP_PROMPTS[3], "步骤三-情节线与推进机制")
        self.assertEqual(ARCHITECTURE_STEP_PROMPTS[4], "步骤四-核心角色规划")
        self.assertEqual(ARCHITECTURE_STEP_PROMPTS[5], "步骤五-叙事风格与文本策略")

    def test_project_creation_workflow_uses_local_prompt_names(self):
        workflow_file = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "bootstrap"
            / "workflows"
            / "项目创建·增强创作链路.wf"
        )

        content = workflow_file.read_text(encoding="utf-8")

        self.assertIn('"prompt_name": "步骤四-核心角色规划"', content)
        self.assertNotIn('"prompt_name": "ANG.M0.architecture_step4_character"', content)

    def test_local_prompt_files_exist(self):
        prompts_dir = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "bootstrap"
            / "prompts"
        )

        expected_files = [
            "步骤一-分卷使命宣言.txt",
            "步骤二-世界观与冲突发生器.txt",
            "步骤三-情节线与推进机制.txt",
            "步骤四-核心角色规划.txt",
            "步骤五-叙事风格与文本策略.txt",
        ]

        for filename in expected_files:
            filepath = prompts_dir / filename
            self.assertTrue(filepath.exists(), f"缺少提示词文件: {filename}")
            content = filepath.read_text(encoding="utf-8")
            self.assertIn("- Role:", content, f"{filename} 缺少 Role 字段")
            self.assertIn("${genre}", content, f"{filename} 缺少 ${{genre}} 变量")


if __name__ == "__main__":
    unittest.main()
