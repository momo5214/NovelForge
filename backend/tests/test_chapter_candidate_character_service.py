import unittest

from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Card, CardType, Project


class ChapterCandidateCharacterServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)

    def _create_role_card_type(self, session: Session) -> CardType:
        card_type = CardType(name="角色卡")
        session.add(card_type)
        session.commit()
        session.refresh(card_type)
        return card_type

    def _create_text_card_type(self, session: Session) -> CardType:
        card_type = CardType(name="通用文本")
        session.add(card_type)
        session.commit()
        session.refresh(card_type)
        return card_type

    def _create_chapter_card_type(self, session: Session) -> CardType:
        card_type = CardType(name="增强章节正文")
        session.add(card_type)
        session.commit()
        session.refresh(card_type)
        return card_type

    def test_build_candidate_update_overwrites_previous_candidates(self):
        from app.services.chapter_candidate_character_service import (
            build_candidate_character_content_update,
        )

        character_cards = [
            {
                "title": "林澈",
                "content": {
                    "name": "林澈",
                    "aliases": ["阿澈"],
                    "role_type": "主角",
                },
            }
        ]
        planning_data = {
            "selected_existing_names": ["林澈"],
            "new_characters": [
                {
                    "name": "陆恒渊",
                    "entity_type": "character",
                    "life_span": "长期",
                    "role_type": "反派",
                    "aliases": ["陆教官"],
                    "role_weight": 82,
                    "first_volume": 1,
                    "description": "教官，盯上林澈。",
                    "story_function": "阶段对手",
                    "core_drive": "核查异常体测结果",
                    "character_arc": "长线对手逐步浮出水面",
                    "dynamic_info": {},
                }
            ],
            "final_character_names": ["林澈", "陆恒渊"],
        }

        payload = build_candidate_character_content_update(
            planning_data=planning_data,
            official_character_cards=character_cards,
            base_entity_list=["林澈", "沈清禾", "故城三中"],
        )

        self.assertEqual(payload["candidate_existing_names"], ["林澈"])
        self.assertEqual([item["name"] for item in payload["candidate_characters"]], ["陆恒渊"])
        self.assertEqual(payload["candidate_final_character_names"], ["林澈", "陆恒渊"])
        self.assertEqual(payload["entity_list"], ["林澈", "沈清禾", "故城三中", "陆恒渊"])
        self.assertIn("角色名：陆恒渊", payload["candidate_character_summary"])

    def test_build_candidate_update_filters_duplicates_by_alias(self):
        from app.services.chapter_candidate_character_service import (
            build_candidate_character_content_update,
        )

        character_cards = [
            {
                "title": "林澈",
                "content": {
                    "name": "林澈",
                    "aliases": ["阿澈", "林同学"],
                    "role_type": "主角",
                },
            }
        ]
        planning_data = {
            "selected_existing_names": [],
            "new_characters": [
                {
                    "name": "阿澈",
                    "entity_type": "character",
                    "life_span": "短期",
                    "role_type": "普通NPC",
                    "aliases": [],
                    "first_volume": 1,
                    "dynamic_info": {},
                }
            ],
            "final_character_names": ["阿澈"],
        }

        payload = build_candidate_character_content_update(
            planning_data=planning_data,
            official_character_cards=character_cards,
            base_entity_list=["林澈"],
        )

        self.assertEqual(payload["candidate_characters"], [])
        self.assertEqual(payload["candidate_existing_names"], ["林澈"])
        self.assertEqual(payload["candidate_final_character_names"], ["林澈"])

    def test_confirm_candidates_creates_official_cards_and_clears_chapter_candidates(self):
        from app.services.chapter_candidate_character_service import (
            confirm_chapter_candidate_characters,
        )

        with Session(self.engine) as session:
            project = Project(name="测试项目")
            role_type = self._create_role_card_type(session)
            text_type = self._create_text_card_type(session)
            chapter_type = self._create_chapter_card_type(session)
            session.add(project)
            session.commit()
            session.refresh(project)

            asset_hub = Card(
                title="世界与资产",
                project_id=project.id,
                card_type_id=text_type.id,
                content={"content": ""},
            )
            chapter = Card(
                title="第1章 红灯尖啸",
                project_id=project.id,
                card_type_id=chapter_type.id,
                content={
                    "chapter_number": 1,
                    "volume_number": 1,
                    "entity_list": ["林澈", "陆恒渊"],
                    "candidate_existing_names": ["林澈"],
                    "candidate_final_character_names": ["林澈", "陆恒渊"],
                    "candidate_character_summary": "角色名：陆恒渊",
                    "candidate_characters": [
                        {
                            "name": "陆恒渊",
                            "entity_type": "character",
                            "life_span": "长期",
                            "role_type": "反派",
                            "aliases": ["陆教官"],
                            "role_weight": 82,
                            "first_volume": 1,
                            "description": "教官，盯上林澈。",
                            "story_function": "阶段对手",
                            "core_drive": "核查异常体测结果",
                            "character_arc": "长线对手逐步浮出水面",
                            "dynamic_info": {},
                        }
                    ],
                },
            )
            official = Card(
                title="林澈",
                project_id=project.id,
                card_type_id=role_type.id,
                content={
                    "name": "林澈",
                    "entity_type": "character",
                    "life_span": "长期",
                    "role_type": "主角",
                    "born_scene": "故城三中",
                    "description": "主角",
                    "personality": "",
                    "core_drive": "",
                    "character_arc": "",
                    "aliases": [],
                    "dynamic_info": {},
                },
            )
            session.add(asset_hub)
            session.add(chapter)
            session.add(official)
            session.commit()
            session.refresh(chapter)

            result = confirm_chapter_candidate_characters(session=session, chapter_card_id=chapter.id)

            self.assertEqual(result["created_card_count"], 1)
            refreshed = session.get(Card, chapter.id)
            self.assertEqual(refreshed.content.get("candidate_characters"), [])
            self.assertEqual(refreshed.content.get("candidate_existing_names"), [])
            self.assertEqual(refreshed.content.get("candidate_character_summary"), "")

            role_cards = session.exec(
                select(Card).where(Card.project_id == project.id, Card.card_type_id == role_type.id)
            ).all()
            role_names = sorted(card.title for card in role_cards)
            self.assertEqual(role_names, ["林澈", "陆恒渊"])

    def test_postprocess_resolution_ignores_unconfirmed_candidate_names(self):
        from app.services.workflow.expressions.functions import fn_resolve_character_targets

        character_cards = [
            {
                "title": "林澈",
                "content": {
                    "name": "林澈",
                    "aliases": ["阿澈"],
                },
            }
        ]

        resolved = fn_resolve_character_targets(
            ["林澈", "陆恒渊"],
            "林澈看见陆恒渊走来。",
            character_cards,
        )

        self.assertEqual(resolved, ["林澈"])


if __name__ == "__main__":
    unittest.main()
