from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
from sqlmodel import Session, select
from datetime import datetime

from app.db.models import ForeshadowItem as ForeshadowItemModel
from app.services.foreshadow_parser import (
    infer_foreshadow_label,
    infer_foreshadow_type,
    parse_foreshadow_entry,
)


class ForeshadowService:
    def __init__(self, session: Session):
        self.session = session

    def suggest(self, text: str) -> Dict[str, Any]:
        """
        极简启发式：
        - 捕捉“将要/准备/打算/誓要/必须”等后接短语作为待完成目标
        - 捕捉以『剑/刀/戒/符/印/丹/阵/甲/鼎/珠/镜』为后缀的名词作为可疑道具
        - 粗略抽取2-4字的人名候选（排除常见功能词）
        """
        if not isinstance(text, str):
            text = str(text or "")
        goals: List[str] = []
        items: List[str] = []
        persons: List[str] = []

        # 目标
        for m in re.findall(r"(将要|准备|打算|誓要|必须)([^。？！\n]{2,20})", text):
            frag = (m[0] + m[1]).strip()
            if frag and frag not in goals:
                goals.append(frag)

        # 道具
        for m in re.findall(r"([\u4e00-\u9fa5]{1,8})(剑|刀|戒|符|印|丹|阵|甲|鼎|珠|镜)", text):
            frag = (m[0] + m[1]).strip()
            if frag and frag not in items:
                items.append(frag)

        # 人名（粗略）
        stopwords = {"什么", "但是", "因为", "然后", "虽然", "可是", "不会", "看看", "我们", "你们", "他们", "以及"}
        for m in re.findall(r"([\u4e00-\u9fa5]{2,4})", text):
            if m and 2 <= len(m) <= 4 and m not in stopwords:
                if m not in persons:
                    persons.append(m)
        persons = persons[:10]

        return {
            "goals": goals[:8],
            "items": items[:8],
            "persons": persons,
        }

    # --- CRUD via DB ---
    def list(self, project_id: int, status: Optional[str] = None) -> List[ForeshadowItemModel]:
        stmt = select(ForeshadowItemModel).where(ForeshadowItemModel.project_id == project_id)
        if status:
            stmt = stmt.where(ForeshadowItemModel.status == status)
        items = self.session.exec(stmt.order_by(ForeshadowItemModel.status.desc(), ForeshadowItemModel.created_at.desc())).all()
        return items

    def register(self, project_id: int, entries: List[Dict[str, Any]]) -> List[ForeshadowItemModel]:
        out: List[ForeshadowItemModel] = []
        for it in entries:
            title = str(it.get('title') or '').strip()
            parsed = parse_foreshadow_entry(it.get('note') or title)
            foreshadow_id = str(it.get('foreshadow_id') or parsed.get('foreshadow_id') or '').strip() or None
            display_title = str(it.get('display_title') or parsed.get('display_title') or '').strip() or None
            if not title and foreshadow_id:
                title = f"{foreshadow_id} {display_title or infer_foreshadow_label(foreshadow_id)}".strip()
            if not title:
                continue
            desired_status = str(it.get('status') or 'open').strip().lower()
            desired_status = 'resolved' if desired_status == 'resolved' else 'open'
            type_value = str(it.get('type') or parsed.get('foreshadow_type') or infer_foreshadow_type(foreshadow_id) or 'other') or 'other'
            note = it.get('note') or parsed.get('raw_text') or parsed.get('description')

            item = None
            if foreshadow_id:
                stmt = select(ForeshadowItemModel).where(
                    ForeshadowItemModel.project_id == project_id,
                    ForeshadowItemModel.foreshadow_id == foreshadow_id,
                )
                item = self.session.exec(stmt).first()
            if item is None:
                stmt = select(ForeshadowItemModel).where(
                    ForeshadowItemModel.project_id == project_id,
                    ForeshadowItemModel.title == title,
                )
                item = self.session.exec(stmt).first()

            due_chapter_number = it.get('due_chapter_number')
            if due_chapter_number in (None, ''):
                due_chapter_number = parsed.get('due_chapter_number')
            try:
                due_chapter_number = int(due_chapter_number) if due_chapter_number not in (None, '') else None
            except Exception:
                due_chapter_number = None

            try:
                first_chapter_number = int(it.get('first_chapter_number')) if it.get('first_chapter_number') not in (None, '') else None
            except Exception:
                first_chapter_number = None
            try:
                last_chapter_number = int(it.get('last_chapter_number')) if it.get('last_chapter_number') not in (None, '') else None
            except Exception:
                last_chapter_number = None

            if item is None:
                item = ForeshadowItemModel(
                    project_id=project_id,
                    chapter_id=it.get('chapter_id'),
                    foreshadow_id=foreshadow_id,
                    title=title,
                    display_title=display_title or (infer_foreshadow_label(foreshadow_id) if foreshadow_id else title),
                    type=type_value,
                    note=note,
                    status=desired_status,
                    due_chapter_number=due_chapter_number,
                    first_chapter_number=first_chapter_number,
                    last_chapter_number=last_chapter_number,
                    resolved_at=datetime.utcnow() if desired_status == 'resolved' else None,
                )
            else:
                item.chapter_id = it.get('chapter_id') or item.chapter_id
                item.foreshadow_id = foreshadow_id or item.foreshadow_id
                item.title = title or item.title
                item.display_title = display_title or item.display_title or item.title
                item.type = type_value or item.type or 'other'
                item.note = note
                item.status = desired_status
                item.due_chapter_number = due_chapter_number or item.due_chapter_number
                item.first_chapter_number = item.first_chapter_number or first_chapter_number or last_chapter_number
                if last_chapter_number:
                    item.last_chapter_number = max(int(item.last_chapter_number or last_chapter_number), last_chapter_number)
                item.resolved_at = datetime.utcnow() if desired_status == 'resolved' else None
                if desired_status != 'resolved':
                    item.resolved_at = None

            self.session.add(item)
            out.append(item)
        if out:
            self.session.commit()
            for i in out:
                self.session.refresh(i)
        return out

    def resolve(self, project_id: int, item_id: str | int) -> Optional[ForeshadowItemModel]:
        item = self.session.get(ForeshadowItemModel, item_id)
        if not item or item.project_id != project_id:
            return None
        if item.status != 'resolved':
            item.status = 'resolved'
            item.resolved_at = datetime.utcnow()
            self.session.add(item)
            self.session.commit()
            self.session.refresh(item)
        return item

    def delete(self, project_id: int, item_id: str | int) -> bool:
        item = self.session.get(ForeshadowItemModel, item_id)
        if not item or item.project_id != project_id:
            return False
        self.session.delete(item)
        self.session.commit()
        return True 
