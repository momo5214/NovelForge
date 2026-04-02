import unittest
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Card, CardType, LLMConfig, NodeExecutionState, Project


class ChapterPostprocessServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)

    def test_postprocess_run_uses_current_card_effective_llm_config(self):
        from app.services.chapter_postprocess_service import (
            resolve_manual_params_for_workflow_run,
        )

        with Session(self.engine) as session:
            project = Project(name="测试项目")
            card_type = CardType(
                name="增强章节正文",
                ai_params={"llm_config_id": 18, "prompt_name": "增强章节正文草稿-续写版"},
            )
            llm16 = LLMConfig(provider="openai_compatible", display_name="旧模型", model_name="old", api_key="x")
            llm18 = LLMConfig(provider="openai_compatible", display_name="新模型", model_name="new", api_key="x")
            session.add(project)
            session.add(card_type)
            session.add(llm16)
            session.add(llm18)
            session.commit()
            session.refresh(project)
            session.refresh(card_type)

            card = Card(
                title="第1章 测试",
                project_id=project.id,
                card_type_id=card_type.id,
                content={"content": "正文"},
                ai_params=None,
            )
            session.add(card)
            session.commit()
            session.refresh(card)

            params = resolve_manual_params_for_workflow_run(
                session=session,
                workflow_name="增强章节后处理闭环",
                manual_params={"project_id": project.id, "target_card_id": card.id, "llm_config_id": 16},
            )

            self.assertEqual(params["llm_config_id"], 18)
            self.assertEqual(params["resolved_llm_config_id"], 18)
            self.assertEqual(params["resolved_llm_config_source"], "card_effective_ai_params")

    def test_postprocess_resume_uses_current_card_effective_llm_config(self):
        from app.services.chapter_postprocess_service import (
            resolve_manual_params_for_workflow_run,
        )

        with Session(self.engine) as session:
            project = Project(name="测试项目")
            card_type = CardType(
                name="增强章节正文",
                ai_params={"llm_config_id": 18, "prompt_name": "增强章节正文草稿-续写版"},
            )
            llm16 = LLMConfig(provider="openai_compatible", display_name="旧模型", model_name="old", api_key="x")
            llm18 = LLMConfig(provider="openai_compatible", display_name="新模型", model_name="new", api_key="x")
            session.add(project)
            session.add(card_type)
            session.add(llm16)
            session.add(llm18)
            session.commit()
            session.refresh(project)
            session.refresh(card_type)

            card = Card(
                title="第1章 测试",
                project_id=project.id,
                card_type_id=card_type.id,
                content={"content": "正文"},
                ai_params=None,
            )
            session.add(card)
            session.commit()
            session.refresh(card)

            params = resolve_manual_params_for_workflow_run(
                session=session,
                workflow_name="增强章节后处理闭环",
                manual_params={"project_id": project.id, "target_card_id": card.id, "llm_config_id": 16},
                resume=True,
            )

            self.assertEqual(params["llm_config_id"], 18)
            self.assertEqual(params["resolved_llm_config_id"], 18)
            self.assertEqual(params["resolved_llm_config_source"], "card_effective_ai_params_resume")

    def test_state_summary_maps_to_update_character_state_payload(self):
        from app.services.chapter_postprocess_service import (
            build_character_state_update_from_summary,
        )

        payload = build_character_state_update_from_summary(
            {
                "summary_list": [
                    {
                        "name": "林澈",
                        "aliases": ["阿澈"],
                        "role_weight": 88,
                        "latest_position": {
                            "location": "故城三中操场",
                            "event": "与陆恒渊正面对峙",
                            "companions": ["沈清禾"],
                            "purpose": "试探对方底牌",
                        },
                        "latest_event": {
                            "event_type": "对峙",
                            "summary": "林澈确认陆恒渊与异常尖啸有关",
                        },
                        "life_state": {
                            "physical_state": "轻伤",
                            "psychological_state": "高度警惕",
                            "long_term_impact": "开始主动追查异常来源",
                        },
                    }
                ]
            },
            volume_number=2,
            chapter_number=7,
        )

        self.assertEqual(len(payload["state_list"]), 1)
        item = payload["state_list"][0]
        self.assertEqual(item["name"], "林澈")
        self.assertEqual(item["aliases"], ["阿澈"])
        self.assertEqual(item["role_weight"], 88)
        self.assertEqual(item["position_tracks"][0]["volume_number"], 2)
        self.assertEqual(item["position_tracks"][0]["chapter_number"], 7)
        self.assertEqual(item["key_event_records"][0]["event_type"], "对峙")
        self.assertEqual(item["life_state"]["physical_state"], "轻伤")

    def test_postprocess_workflow_keeps_run_history(self):
        from app.bootstrap.workflows import _parse_code_workflow

        workflow_file = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "bootstrap"
            / "workflows"
            / "增强章节后处理闭环.wf"
        )

        data = _parse_code_workflow(str(workflow_file))

        self.assertTrue(data["keep_run_history"])

    def test_postprocess_resume_invalidates_llm_selection_nodes_only(self):
        from app.services.chapter_postprocess_service import (
            invalidate_resume_node_states_for_workflow,
        )

        with Session(self.engine) as session:
            session.add_all([
                NodeExecutionState(
                    run_id=22,
                    node_id="selected_llm_config_id",
                    node_type="Logic.Expression",
                    status="success",
                    outputs_json={"result": 16},
                ),
                NodeExecutionState(
                    run_id=22,
                    node_id="llm",
                    node_type="Logic.SelectLLM",
                    status="success",
                    outputs_json={"llm_config_id": 16},
                ),
                NodeExecutionState(
                    run_id=22,
                    node_id="plot_points_card",
                    node_type="Card.BatchUpsert",
                    status="success",
                    outputs_json={"id": 1},
                ),
            ])
            session.commit()

            invalidated = invalidate_resume_node_states_for_workflow(
                session=session,
                workflow_name="增强章节后处理闭环",
                run_id=22,
            )

            self.assertEqual(invalidated, ["selected_llm_config_id", "llm"])
            remaining = session.exec(
                select(NodeExecutionState).where(NodeExecutionState.run_id == 22)
            ).all()
            remaining_ids = sorted(item.node_id for item in remaining)
            self.assertEqual(remaining_ids, ["plot_points_card"])

    def test_resume_context_keeps_initial_params_while_preserving_completed_outputs(self):
        from app.services.workflow.engine.async_executor import merge_resume_context

        merged = merge_resume_context(
            loaded_context={
                "selected_project_id": {"result": 12},
                "plot_points_card": {"id": 1},
            },
            initial_context={
                "project_id": 12,
                "target_card_id": 359,
                "llm_config_id": 18,
            },
        )

        self.assertEqual(merged["project_id"], 12)
        self.assertEqual(merged["target_card_id"], 359)
        self.assertEqual(merged["llm_config_id"], 18)
        self.assertEqual(merged["plot_points_card"], {"id": 1})
        self.assertEqual(merged["selected_project_id"], {"result": 12})


if __name__ == "__main__":
    unittest.main()
