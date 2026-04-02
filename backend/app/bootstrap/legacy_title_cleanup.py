"""历史系统卡标题清理。

将早期增强链路遗留的内部实现标题迁移到当前统一中文命名。
"""

import re

from loguru import logger
from sqlmodel import Session, select

from app.db.models import Card
from .registry import initializer


EXACT_TITLE_MAP = {
    "ANG.M0/步骤二组织卡自动生成开关": "系统开关/步骤二自动生成组织卡",
    "ANG.M2/伏笔总台账": "伏笔管理/总台账",
    "ANG.M2/伏笔台账-未回收": "伏笔管理/未回收台账",
}

REPORT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^ANG\.M2/一致性审校报告-第(\d+)章-(.+)$"), "一致性审校"),
    (re.compile(r"^一致性审校-第(\d+)章-(.+)$"), "一致性审校"),
    (re.compile(r"^ANG\.M2/伏笔治理报告-第(\d+)章-(.+)$"), "伏笔治理"),
    (re.compile(r"^伏笔治理-第(\d+)章-(.+)$"), "伏笔治理"),
    (re.compile(r"^ANG\.M1/剧情要点-第(\d+)章-(.+)$"), "剧情要点"),
    (re.compile(r"^剧情要点-第(\d+)章-(.+)$"), "剧情要点"),
]


def _normalize_chapter_scoped_title(prefix: str, chapter: str, raw_title: str) -> str:
    title = str(raw_title or "").strip()
    if not title:
        return f"{prefix}-第{chapter}章"
    duplicated_prefix = re.compile(rf"^第{re.escape(chapter)}章(?:[\s\-:：、.．]*)")
    normalized_title = duplicated_prefix.sub("", title, count=1).strip() or title
    return f"{prefix}-第{chapter}章-{normalized_title}"


def _normalize_card_title(title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        return raw

    exact = EXACT_TITLE_MAP.get(raw)
    if exact:
        return exact

    for pattern, prefix in REPORT_PATTERNS:
        match = pattern.match(raw)
        if match:
            return _normalize_chapter_scoped_title(prefix, match.group(1), match.group(2))

    return raw


@initializer(name="历史系统卡标题清理", order=60)
def cleanup_legacy_system_card_titles(session: Session) -> None:
    cards = session.exec(select(Card)).all()
    updated_count = 0

    for card in cards:
        normalized_title = _normalize_card_title(card.title)
        if normalized_title == card.title:
            continue
        card.title = normalized_title
        session.add(card)
        updated_count += 1

    if updated_count:
        session.commit()
        logger.info(f"历史系统卡标题清理完成: 更新 {updated_count} 张卡片")
    else:
        logger.info("历史系统卡标题清理完成: 无需更新")
