"""步骤四迁移

将历史测试项目中的旧版步骤四卡统一迁移到“核心角色规划”。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update
from sqlmodel import Session, select

from app.db.models import Card, CardType
from .registry import initializer


STEP4_CONTEXT_TEMPLATE = (
    "作品标签: @作品标签.content\n"
    "故事大纲: @故事大纲.content.overview\n"
    "步骤1结果: @type:小说架构步骤[index=1].content.content\n"
    "步骤2结果: @type:小说架构步骤[index=2].content.content\n"
    "步骤3结果: @type:小说架构步骤[index=3].content.content"
)

OLD_STEP4_TITLES = {
    "步骤4：角色驱动系统",
}

OLD_STEP4_PROMPT_NAMES = {
    "步骤四-核心角色规划",
    "role_driven_system",
    "core_character_cards",
    "",
    None,
}

OLD_STEP4_STEP_NAMES = {
    "角色驱动系统",
    "模块四：角色驱动系统",
    "核心角色卡",
    "",
    None,
}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


@initializer(name="步骤四迁移", order=62)
def migrate_step4_cards(session: Session) -> None:
    card_type = session.exec(select(CardType).where(CardType.name == "小说架构步骤")).first()
    if card_type is None:
        return

    cards = session.exec(select(Card).where(Card.card_type_id == card_type.id)).all()
    updated_count = 0

    for card in cards:
        content = dict(_as_dict(card.content))
        ai_params = dict(_as_dict(card.ai_params))

        title = str(card.title or "").strip()
        step = content.get("step")
        prompt_name = content.get("prompt_name")
        step_name = content.get("step_name")

        is_old_step4 = (
            title in OLD_STEP4_TITLES
            or step == 4
            or str(step).strip() == "4"
            or prompt_name in OLD_STEP4_PROMPT_NAMES
            or step_name in OLD_STEP4_STEP_NAMES
        ) and title.startswith("步骤4")

        if not is_old_step4:
            continue

        content["step"] = 4
        content["step_name"] = "核心角色规划"
        content["prompt_name"] = "步骤四-核心角色规划"
        content["ai_context_template"] = STEP4_CONTEXT_TEMPLATE

        if ai_params:
            ai_params["prompt_name"] = "步骤四-核心角色规划"
        else:
            ai_params = {"prompt_name": "步骤四-核心角色规划"}

        session.exec(
            sql_update(Card)
            .where(Card.id == card.id)
            .values(
                title="步骤4：核心角色规划",
                content=content,
                ai_params=ai_params,
            )
        )
        updated_count += 1

    old_switch_cards = session.exec(select(Card).where(Card.title == "ANG.M0/步骤四角色卡自动生成开关")).all()
    if old_switch_cards:
        session.exec(
            sql_delete(Card).where(Card.title == "ANG.M0/步骤四角色卡自动生成开关")
        )

    if updated_count or old_switch_cards:
        session.commit()
        logger.info(
            f"步骤四迁移完成: 更新步骤四卡 {updated_count} 张, 删除旧开关 {len(old_switch_cards)} 张"
        )
    else:
        logger.info("步骤四迁移完成: 无需处理")
