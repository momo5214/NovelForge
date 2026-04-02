from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.entity import CharacterCard
from app.schemas.wizard import ChapterCharacterDiscoveryResult


_CODE_RE = re.compile(r"^ID(\d{4,})$")


def _normalize_name(text: str) -> str:
    return str(text or "").strip().lower()


def _derive_role_tier(weight: Optional[int]) -> Optional[str]:
    if weight is None:
        return None
    if weight <= 20:
        return "背景角色"
    if weight <= 40:
        return "单元角色"
    if weight <= 60:
        return "次要配角"
    if weight <= 80:
        return "关键角色"
    if weight <= 95:
        return "核心配角"
    return "主角级"


@dataclass
class CharacterRosterSyncResult:
    success: bool
    assigned_code_count: int = 0
    updated_card_count: int = 0
    created_card_count: int = 0
    created_card_ids: List[int] = field(default_factory=list)


def sync_character_roster(
    session: Session,
    *,
    project_id: int,
    parent_id: Optional[int],
    data: ChapterCharacterDiscoveryResult,
) -> CharacterRosterSyncResult:
    stmt = (
        select(Card)
        .where(Card.project_id == project_id)
        .order_by(Card.created_at, Card.id)
    )
    cards = session.exec(stmt).all()
    role_cards = [c for c in cards if c.card_type and c.card_type.name == "角色卡"]
    role_card_type = next((c.card_type for c in role_cards if c.card_type and c.card_type.name == "角色卡"), None)
    if role_card_type is None:
        ct_stmt = select(CardType).where(CardType.name == "角色卡")
        role_card_type = session.exec(ct_stmt).first()
    if role_card_type is None:
        return CharacterRosterSyncResult(success=False)

    used_codes: set[int] = set()
    assigned_code_count = 0
    updated_card_count = 0
    created_card_count = 0
    touched: Dict[int, Card] = {}
    created_card_ids: List[int] = []

    def _parse_existing_code(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        match = _CODE_RE.match(str(value).strip().upper())
        if not match:
            return None
        return int(match.group(1))

    for card in role_cards:
        raw_content = card.content or {}
        code_num = _parse_existing_code((raw_content or {}).get("character_code"))
        if code_num is not None:
            used_codes.add(code_num)

    next_code_num = max(used_codes) + 1 if used_codes else 1

    def _next_code() -> str:
        nonlocal next_code_num
        while next_code_num in used_codes:
            next_code_num += 1
        used_codes.add(next_code_num)
        code = f"ID{next_code_num:04d}"
        next_code_num += 1
        return code

    existing_titles = {_normalize_name(c.title): c for c in role_cards}
    alias_map: Dict[str, Card] = {}

    def _merge_aliases(model: CharacterCard, aliases: List[str]) -> bool:
        merged = list(model.aliases or [])
        changed = False
        seen = {_normalize_name(model.name), *[_normalize_name(x) for x in merged]}
        for alias in aliases:
            normalized = _normalize_name(alias)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(str(alias).strip())
            changed = True
        if changed:
            model.aliases = merged[:12]
        return changed

    def _touch_card(card: Card, model: CharacterCard) -> None:
        card.content = model.model_dump(exclude_unset=True)
        flag_modified(card, "content")
        touched[card.id] = card

    validated_models: Dict[int, CharacterCard] = {}
    for card in role_cards:
        raw = card.content or {}
        try:
            model = CharacterCard.model_validate(raw)
        except Exception:
            data = dict(raw)
            if not data.get("character_code"):
                data["character_code"] = _next_code()
                assigned_code_count += 1
            card.content = data
            flag_modified(card, "content")
            touched[card.id] = card
            name = str(data.get("name") or card.title or "").strip()
            if name:
                existing_titles[_normalize_name(name)] = card
            for alias in data.get("aliases") or []:
                alias_map[_normalize_name(alias)] = card
            continue

        if not model.character_code:
            model.character_code = _next_code()
            assigned_code_count += 1
            _touch_card(card, model)
        if model.role_weight is not None and not model.role_tier:
            model.role_tier = _derive_role_tier(model.role_weight)
            _touch_card(card, model)

        validated_models[card.id] = model
        if model.name:
            existing_titles[_normalize_name(model.name)] = card
        existing_titles[_normalize_name(card.title)] = card
        for alias in model.aliases or []:
            alias_map[_normalize_name(alias)] = card

    def _find_card(name: str) -> Optional[Card]:
        normalized = _normalize_name(name)
        return existing_titles.get(normalized) or alias_map.get(normalized)

    for item in data.existing_matches or []:
        card = _find_card(item.matched_name) or _find_card(item.observed_name)
        if card is None:
            continue
        model = validated_models.get(card.id)
        if model is None:
            try:
                model = CharacterCard.model_validate(card.content or {})
            except Exception:
                continue
        alias_candidates = [item.observed_name, *(item.aliases or [])]
        changed = _merge_aliases(model, alias_candidates)
        if changed:
            _touch_card(card, model)
            validated_models[card.id] = model
            updated_card_count += 1
            for alias in model.aliases or []:
                alias_map[_normalize_name(alias)] = card

    sibling_count = len([c for c in cards if c.parent_id == parent_id])
    for item in data.new_characters or []:
        existing = _find_card(item.name)
        if existing is not None:
            model = validated_models.get(existing.id)
            if model is None:
                try:
                    model = CharacterCard.model_validate(existing.content or {})
                except Exception:
                    continue
            if _merge_aliases(model, item.aliases or []):
                _touch_card(existing, model)
                validated_models[existing.id] = model
                updated_card_count += 1
            continue

        code = _next_code()
        role_tier = _derive_role_tier(item.role_weight)
        content = {
            "name": item.name,
            "entity_type": item.entity_type,
            "life_span": item.life_span,
            "role_type": item.role_type,
            "character_code": code,
            "aliases": item.aliases or [],
            "role_weight": item.role_weight,
            "role_tier": role_tier,
            "gender": item.gender,
            "age": item.age,
            "appearance": item.appearance,
            "identity": item.identity,
            "born_scene": item.born_scene,
            "first_volume": item.first_volume,
            "first_event": item.first_event,
            "story_function": item.story_function,
            "description": item.description,
            "background": item.background,
            "personality": item.personality,
            "core_drive": item.core_drive,
            "inner_conflict": item.inner_conflict,
            "relationship_summary": item.relationship_summary,
            "character_arc": item.character_arc,
            "dynamic_info": item.dynamic_info or {},
        }
        new_card = Card(
            title=item.name,
            content=content,
            parent_id=parent_id,
            project_id=project_id,
            card_type_id=role_card_type.id,
            display_order=sibling_count,
            ai_context_template=role_card_type.default_ai_context_template,
        )
        sibling_count += 1
        session.add(new_card)
        session.flush()
        created_card_count += 1
        created_card_ids.append(int(new_card.id))

    for card in touched.values():
        session.add(card)

    session.commit()

    return CharacterRosterSyncResult(
        success=True,
        assigned_code_count=assigned_code_count,
        updated_card_count=updated_card_count,
        created_card_count=created_card_count,
        created_card_ids=created_card_ids,
    )
