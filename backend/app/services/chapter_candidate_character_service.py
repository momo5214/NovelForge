from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card
from app.services.character_roster_service import sync_character_roster as sync_official_character_roster
from app.schemas.wizard import (
    ChapterCharacterDiscoveryResult,
    ChapterCharacterPlanningResult,
    DiscoveredCharacterCard,
)


def _normalize_name(text: Any) -> str:
    return str(text or "").strip().lower()


def _dedupe_names(names: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for item in names:
        text = str(item or "").strip()
        normalized = _normalize_name(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
    return result


def _build_official_name_map(official_character_cards: Any) -> tuple[Dict[str, str], List[Dict[str, Any]]]:
    alias_map: Dict[str, str] = {}
    normalized_cards: List[Dict[str, Any]] = []
    if not isinstance(official_character_cards, list):
        return alias_map, normalized_cards

    for card in official_character_cards:
        if not isinstance(card, dict):
            continue
        content = card.get("content") or {}
        if not isinstance(content, dict):
            content = {}
        standard_name = str(content.get("name") or card.get("title") or "").strip()
        if not standard_name:
            continue
        normalized_cards.append({"title": card.get("title"), "content": content})
        alias_map[_normalize_name(standard_name)] = standard_name
        alias_map[_normalize_name(card.get("title") or "")] = standard_name
        for alias in content.get("aliases") or []:
            normalized = _normalize_name(alias)
            if normalized:
                alias_map[normalized] = standard_name

    return alias_map, normalized_cards


def _normalize_existing_names(names: Any, alias_map: Dict[str, str]) -> List[str]:
    resolved: List[str] = []
    seen: set[str] = set()
    for item in names or []:
        standard_name = alias_map.get(_normalize_name(item))
        if not standard_name:
            continue
        normalized = _normalize_name(standard_name)
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(standard_name)
    return resolved


def _filter_candidate_characters(
    planning_data: ChapterCharacterPlanningResult,
    alias_map: Dict[str, str],
) -> tuple[List[DiscoveredCharacterCard], List[str]]:
    filtered: List[DiscoveredCharacterCard] = []
    matched_existing_names: List[str] = []
    seen: set[str] = set()

    for raw_item in planning_data.new_characters or []:
        item = raw_item if isinstance(raw_item, DiscoveredCharacterCard) else DiscoveredCharacterCard.model_validate(raw_item)
        candidate_keys = [_normalize_name(item.name), *[_normalize_name(alias) for alias in (item.aliases or [])]]
        matched_standard_names = [alias_map[key] for key in candidate_keys if key and key in alias_map]
        if matched_standard_names:
            matched_existing_names.extend(matched_standard_names)
            continue
        normalized_name = _normalize_name(item.name)
        if not normalized_name or normalized_name in seen:
            continue
        seen.add(normalized_name)
        filtered.append(item)

    return filtered, _dedupe_names(matched_existing_names)


def _build_candidate_summary(candidate_characters: List[DiscoveredCharacterCard]) -> str:
    blocks: List[str] = []
    for item in candidate_characters:
        parts = [
            f"角色名：{item.name}",
            f"角色类型：{item.role_type}",
            f"生命周期：{item.life_span}",
            f"角色权重：{item.role_weight or ''}",
            f"其他称谓：{'、'.join(item.aliases or [])}",
            f"身份：{item.identity or ''}",
            f"首次出场场景：{item.born_scene or ''}",
            f"首次登场事件：{item.first_event or ''}",
            f"角色功能：{item.story_function or ''}",
            f"角色概述：{item.description or ''}",
            f"核心驱动力：{item.core_drive or ''}",
            f"角色弧光：{item.character_arc or ''}",
        ]
        blocks.append("\n".join(parts))
    return "\n\n".join([block for block in blocks if block.strip()])


def build_candidate_character_content_update(
    *,
    content: Any = None,
    planning_result: Any = None,
    planning_data: Any = None,
    official_character_cards: Any,
    base_entity_list: Any = None,
    updated_at: Any = None,
) -> Dict[str, Any]:
    raw_planning = planning_data if planning_data is not None else planning_result
    planning = (
        raw_planning
        if isinstance(raw_planning, ChapterCharacterPlanningResult)
        else ChapterCharacterPlanningResult.model_validate(raw_planning or {})
    )
    if base_entity_list is None and isinstance(content, dict):
        base_entity_list = content.get("entity_list") or []
    alias_map, _ = _build_official_name_map(official_character_cards)
    selected_existing_names = _normalize_existing_names(planning.selected_existing_names, alias_map)
    candidate_characters, matched_existing_names = _filter_candidate_characters(planning, alias_map)
    selected_existing_names = _dedupe_names([*selected_existing_names, *matched_existing_names])

    candidate_names = [item.name for item in candidate_characters]
    final_character_names = _normalize_existing_names(planning.final_character_names, alias_map)
    final_character_names.extend(candidate_names)

    if not final_character_names:
        final_character_names = [*selected_existing_names, *candidate_names]
    final_character_names = _dedupe_names(final_character_names)

    entity_list = _dedupe_names([*(base_entity_list or []), *candidate_names])
    prepared_at = str(updated_at).strip() if str(updated_at or "").strip() else datetime.now().isoformat()
    summary_text = _build_candidate_summary(candidate_characters)

    return {
        "candidate_existing_names": selected_existing_names,
        "candidate_characters": [item.model_dump(mode="python") for item in candidate_characters],
        "candidate_final_character_names": final_character_names,
        "candidate_character_summary": summary_text,
        "candidate_character_status": "pending",
        "candidate_character_prepared_at": prepared_at,
        "entity_list": entity_list,
    }
def _resolve_asset_hub_parent_id(session: Session, project_id: int) -> Optional[int]:
    hub = session.exec(
        select(Card).where(Card.project_id == project_id, Card.title == "世界与资产").order_by(Card.id)
    ).first()
    return hub.id if hub else None


def confirm_chapter_candidate_characters(session: Session, chapter_card_id: int) -> Dict[str, Any]:
    chapter = session.get(Card, chapter_card_id)
    if chapter is None:
        raise ValueError("章节卡不存在")

    content = dict(chapter.content or {})
    candidate_characters = content.get("candidate_characters") or []
    project_id = int(chapter.project_id)
    parent_id = _resolve_asset_hub_parent_id(session, project_id)

    result = sync_official_character_roster(
        session,
        project_id=project_id,
        parent_id=parent_id,
        data=ChapterCharacterDiscoveryResult(
            existing_matches=[],
            new_characters=candidate_characters,
        ),
    )

    content["candidate_characters"] = []
    content["candidate_existing_names"] = []
    content["candidate_final_character_names"] = []
    content["candidate_character_summary"] = ""
    content["candidate_character_status"] = "confirmed"
    content["candidate_character_confirmed_at"] = datetime.now().isoformat()
    chapter.content = content
    flag_modified(chapter, "content")
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    confirmed_names = [
        str((item or {}).get("name") or "").strip()
        for item in candidate_characters
        if str((item or {}).get("name") or "").strip()
    ]
    return {
        "success": result.success,
        "assigned_code_count": result.assigned_code_count,
        "updated_card_count": result.updated_card_count,
        "created_card_count": result.created_card_count,
        "chapter_card_id": chapter.id,
        "confirmed_names": _dedupe_names(confirmed_names),
    }
