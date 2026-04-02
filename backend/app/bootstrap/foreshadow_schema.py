"""伏笔结构化字段兼容迁移。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlmodel import Session, select

from app.db.models import ForeshadowItem
from app.services.foreshadow_parser import (
    infer_foreshadow_label,
    infer_foreshadow_type,
    parse_foreshadow_entry,
)
from app.db.session import engine
from .registry import initializer


REQUIRED_COLUMNS: dict[str, str] = {
    "foreshadow_id": "TEXT",
    "display_title": "TEXT",
    "due_chapter_number": "INTEGER",
    "first_chapter_number": "INTEGER",
    "last_chapter_number": "INTEGER",
}


def _ensure_columns() -> None:
    with engine.begin() as connection:
        result = connection.execute(text("PRAGMA table_info(foreshadowitem)"))
        existing_columns = {row[1] for row in result.fetchall()}
        for column_name, sql_type in REQUIRED_COLUMNS.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE foreshadowitem ADD COLUMN {column_name} {sql_type}"))
            logger.info(f"伏笔表结构迁移: 新增字段 {column_name}")


@initializer(name="伏笔结构化迁移", order=61)
def migrate_foreshadow_schema(session: Session) -> None:
    _ensure_columns()

    items = session.exec(select(ForeshadowItem)).all()
    updated_count = 0

    for item in items:
        parsed = parse_foreshadow_entry(item.note or item.title)
        changed = False

        if not item.foreshadow_id and parsed.get("foreshadow_id"):
            item.foreshadow_id = parsed["foreshadow_id"]
            changed = True
        if not item.display_title:
            item.display_title = (
                parsed.get("display_title")
                or (infer_foreshadow_label(item.foreshadow_id) if item.foreshadow_id else item.title)
            )
            changed = True
        if (not item.type or item.type == "other") and item.foreshadow_id:
            item.type = infer_foreshadow_type(item.foreshadow_id)
            changed = True
        if item.due_chapter_number is None and parsed.get("due_chapter_number") is not None:
            item.due_chapter_number = parsed["due_chapter_number"]
            changed = True

        if changed:
            session.add(item)
            updated_count += 1

    if updated_count:
        session.commit()
        logger.info(f"伏笔结构化迁移完成: 更新 {updated_count} 条伏笔记录")
    else:
        logger.info("伏笔结构化迁移完成: 无需更新")
