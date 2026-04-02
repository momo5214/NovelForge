from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import Session
from sqlalchemy.orm.attributes import flag_modified

from loguru import logger

from app.schemas.relation_extract import RelationExtraction, CN_TO_EN_KIND
from app.schemas.entity import Entity
from pydantic import BaseModel
# 引入动态信息模型
from app.schemas.entity import (
    UpdateDynamicInfo,
    DynamicInfoType,
    DynamicInfoItem,
    DeletionInfo,
    CharacterCard,
    UpdateCharacterState,
)
from app.db.models import Card, CardType
from sqlmodel import select

# 引入带类型的参与者模型
from app.schemas.memory import ParticipantTyped

# 从数据库加载提示词
from app.services import prompt_service

# 使用可切换的知识图谱 Provider
from app.services.kg_provider import get_provider, KnowledgeGraphUnavailableError

# 主宾类型约束（建议表）
_ALLOWED_PAIRS: Dict[str, List[Tuple[str, str]]] = {
    '同盟': [('character','character')],
    '队友': [('character','character')],
    '同门': [('character','character')],
    '敌对': [('character','character')],
    '亲属': [('character','character')],
    '师徒': [('character','character')],
    '对手': [('character','character')],
    '伙伴': [('character','character')],
    '上级': [('character','character')],
    '下属': [('character','character')],

    '隶属': [('character','organization')],
    '成员': [('character','organization')],
    '领导': [('character','organization'), ('organization','organization')],
    '创立': [('character','organization') , ('organization','organization')],

    # '拥有': [('character','item'), ('organization','item')],
    # '使用': [('character','item'), ('organization','item')],
    # '修炼': [('character','concept')],
    # '领悟': [('character','concept')],

    '控制': [('organization','scene')],
    '位于': [('scene','organization')],

    
    '关于': [('character','character'), ('organization','organization'), ('character','organization'), ('organization','character'),
        #    ('item','item'), ('concept','concept'), ('character','concept'), ('character','item')
           ],
    '其他': [('character','character'), ('organization','organization'), ('character','organization'), ('organization','character'), ('item','item'), ('concept','concept'), ('character','concept'), ('character','item')],
    # '影响': [('character','character'), ('organization','organization'), ('character','organization'), ('organization','character'), ('item','item'), ('concept','concept'), ('character','concept'), ('character','item'), ('scene','organization'), ('organization','scene')],
    # '克制': [('item','item'), ('concept','concept'), ('character','character')],
}

# # 简化：从卡片类型名称推断实体类型
# _CARDTYPE_TO_ENTITYTYPE: Dict[str, str] = {
#     '角色卡': 'character',
#     '场景卡': 'scene',
#     '组织卡': 'organization',
#     # '物品卡': 'item',
#     # '概念卡': 'concept',
# }

def _guess_entity_type(session: Session, project_id: int, name: str) -> Optional[str]:
    try:
        # 在该项目下查找 title == name 的卡片，并读取其类型名称
        st = select(Card).where(Card.project_id == project_id, Card.title == name)
        card = session.exec(st).first()
        if not card:
            return None
        ct = card.card_type
        if not ct:
            return None
        
        # 修正：card.content 已经是 dict，应使用 model_validate 而不是 model_validate_json
        entity=Entity.model_validate(card.content)
        return str(entity.entity_type)
        # return _CARDTYPE_TO_ENTITYTYPE.get(ct.name or '', None)
    except Exception as e:
        logger.error(f"Error guessing entity type: {e}")
        return None


# 动态信息每类别数量上限（可根据需要调整）
DYNAMIC_INFO_LIMITS: Dict[str, int] = {
    "系统/模拟器/金手指信息": 3,
    "等级/修为境界": 3,
    "装备/法宝": 3,
    "知识/情报": 3,
    "资产/领地": 3,
    "功法/技能": 3,
    "血脉/体质": 3,
    "心理想法/目标快照": 3,
}

ROLE_WEIGHT_DEFAULTS: Dict[str, int] = {
    "主角": 98,
    "主角团配角": 75,
    "反派": 70,
    "普通NPC": 35,
}

ROLE_WEIGHT_SINGLE_CHAPTER_DELTA_LIMIT = 6


def _derive_role_tier(weight: int) -> str:
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


def _normalize_role_weight(weight: int, role_type: Optional[str]) -> int:
    normalized = max(1, min(100, int(weight)))
    if role_type == "主角":
        normalized = max(90, normalized)
    return normalized


def _apply_role_weight_change(
    current_weight: int,
    suggested_weight: Optional[int],
    role_type: Optional[str],
) -> int:
    base_weight = _normalize_role_weight(current_weight, role_type)
    if suggested_weight is None:
        return base_weight

    target_weight = _normalize_role_weight(suggested_weight, role_type)
    delta = target_weight - base_weight
    if delta > ROLE_WEIGHT_SINGLE_CHAPTER_DELTA_LIMIT:
        target_weight = base_weight + ROLE_WEIGHT_SINGLE_CHAPTER_DELTA_LIMIT
    elif delta < -ROLE_WEIGHT_SINGLE_CHAPTER_DELTA_LIMIT:
        target_weight = base_weight - ROLE_WEIGHT_SINGLE_CHAPTER_DELTA_LIMIT

    return _normalize_role_weight(target_weight, role_type)


def _role_state_limits(weight: int) -> Dict[str, int]:
    high_weight = weight > 90
    return {
        "position_tracks": 3 if high_weight else 1,
        "key_event_records": 5 if high_weight else 2,
        "inventory_items": 5 if high_weight else 2,
        "techniques": 5 if high_weight else 2,
        "relationship_network": 5 if high_weight else 2,
    }


def _dedupe_keep_last(items: List[Any], key_func) -> List[Any]:
    seen: Dict[Any, Any] = {}
    order: List[Any] = []
    for item in items:
        key = key_func(item)
        if key in seen:
            try:
                order.remove(key)
            except ValueError:
                pass
        seen[key] = item
        order.append(key)
    return [seen[key] for key in order]


def _latest_appearance_from_model(model: CharacterCard) -> Optional[Tuple[int, int]]:
    candidates: List[Tuple[int, int]] = []
    if model.last_appearance:
        try:
            candidates.append((int(model.last_appearance[0]), int(model.last_appearance[1])))
        except Exception:
            pass
    for item in model.position_tracks or []:
        try:
            candidates.append((int(item.volume_number or 0), int(item.chapter_number)))
        except Exception:
            continue
    for item in model.key_event_records or []:
        try:
            candidates.append((int(item.volume_number or 0), int(item.chapter_number)))
        except Exception:
            continue
    if not candidates:
        return None
    return max(candidates)


_TEXT_NORMALIZE_PATTERN = re.compile(r"[\s,，。；;：:、\-—_（）()\[\]【】\"'“”‘’]+")


def _normalize_compare_text(text: str) -> str:
    normalized = _TEXT_NORMALIZE_PATTERN.sub("", str(text or "").strip().lower())
    return normalized


def _collect_state_reference_texts(model: CharacterCard) -> List[str]:
    texts: List[str] = []

    for item in model.position_tracks or []:
        texts.extend(
            [
                str(item.location or ""),
                str(item.event or ""),
                str(item.purpose or ""),
                " ".join([str(name or "").strip() for name in (item.companions or []) if str(name or "").strip()]),
            ]
        )

    for item in model.key_event_records or []:
        texts.extend([str(item.event_type or ""), str(item.summary or "")])

    if model.life_state:
        texts.extend(
            [
                str(model.life_state.physical_state or ""),
                str(model.life_state.psychological_state or ""),
                str(model.life_state.long_term_impact or ""),
            ]
        )

    for item in model.inventory_items or []:
        texts.extend([str(item.name or ""), str(item.description or "")])

    for item in model.techniques or []:
        texts.extend([str(item.name or ""), str(item.description or "")])

    for item in model.relationship_network or []:
        texts.extend([str(item.target_name or ""), str(item.relation_type or "")])

    if model.behavior_decision_pattern:
        texts.extend(
            [
                str(model.behavior_decision_pattern.behavior_pattern or ""),
                str(model.behavior_decision_pattern.decision_preference or ""),
            ]
        )

    if model.dialogue_style_keywords:
        texts.append(" ".join([str(x or "").strip() for x in (model.dialogue_style_keywords.style_tags or []) if str(x or "").strip()]))
        texts.append(" ".join([str(x or "").strip() for x in (model.dialogue_style_keywords.keywords or []) if str(x or "").strip()]))

    if model.romance_state:
        texts.append(str(model.romance_state.state_description or ""))

    return [text for text in texts if str(text or "").strip()]


def _has_state_level_overlap(model: CharacterCard, info_text: str) -> bool:
    candidate = _normalize_compare_text(info_text)
    if len(candidate) < 4:
        return False

    for state_text in _collect_state_reference_texts(model):
        normalized_state = _normalize_compare_text(state_text)
        if len(normalized_state) < 4:
            continue
        if candidate == normalized_state:
            return True
        if len(candidate) >= 6 and candidate in normalized_state:
            return True
        if len(normalized_state) >= 6 and normalized_state in candidate:
            return True

    return False

class MemoryService:
    def __init__(self, session: Session):
        self.session = session
        self.graph = get_provider()

    @staticmethod
    def _get_llm_service():
        # 延迟导入，避免模块导入阶段强依赖 langchain/transformers。
        from app.services.ai.core import llm_service

        return llm_service

    async def extract_relations_llm(self, text: str, participants: Optional[List[ParticipantTyped]] = None, llm_config_id: int = 1, timeout: Optional[float] = None, prompt_name: Optional[str] = "关系提取") -> RelationExtraction:
        # 优先使用默认提示词，如果不存在则回退到硬编码版本
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        system_prompt = prompt.template
        
        # 将输出模型的 JSON Schema 附加到系统提示词中
        schema_json = RelationExtraction.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 格式进行输出:\n{schema_json}"

        participant_names = [p.name for p in participants] if participants else []
        user_prompt = (
            f"参与者: {', '.join(participant_names)}\n\n"
            "请从以下正文中抽取：\n"
            f"{text}"
        )
        res = await self._get_llm_service().generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=RelationExtraction,
            system_prompt=system_prompt,
            timeout=timeout,
        )
        if not isinstance(res, RelationExtraction):
            raise ValueError("LLM 关系抽取失败：输出格式不符合 RelationExtraction")
        return res

    async def extract_dynamic_info_from_text(self, text: str, participants: Optional[List[ParticipantTyped]] = None, llm_config_id: int = 1, timeout: Optional[float] = None, prompt_name: Optional[str] = "角色动态信息提取", project_id: Optional[int] = None, extra_context: Optional[str] = None) -> UpdateDynamicInfo:
        """从文本中为指定参与者抽取动态信息。extra_context 由前端拼装（可包含分卷主线/支线、阶段概述等任意文本）。"""
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {prompt_name}")
        system_prompt = prompt.template

        # 附加 JSON Schema 以强化输出结构
        schema_json = UpdateDynamicInfo.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 格式进行输出:\n{schema_json}"

        # 参考上下文（完全由前端决定）+ 现有角色动态信息
        ref_blocks: List[str] = []
        if extra_context:
            ref_blocks.append(f"【大纲参考信息，不允许从中提取信息】\n{extra_context}")

        # 使用带类型的参与者，仅处理 character 类型
        character_participants = [p for p in (participants or []) if p.type == 'character']
        if project_id and character_participants:
            try:
                lines: List[str] = []
                for p in character_participants:
                    st = select(Card).where(Card.project_id == project_id, Card.title == p.name)
                    card = self.session.exec(st).first()
                    if not card or not card.card_type or card.card_type.name != '角色卡':
                        continue
                    try:
                        from app.schemas.entity import CharacterCard
                     
                        model = CharacterCard.model_validate(card.content or {})
    
                        di = model.dynamic_info or {}
                        if not di:
                            continue
                        lines.append(f"- {p.name}:")
                        for cat_enum, items in di.items():
                            if len(items)==0:
                                continue

                            # 增加数量/上限的上下文（去掉权重）
                            preview = "; ".join([f"[{it.id}] {it.info}" for it in items[:5]])
                            limit = DYNAMIC_INFO_LIMITS.get(cat_enum, 3)
                            info_line = f"  • {cat_enum} ({len(items)}/{limit}): {preview}"
                            lines.append(info_line)
                    except Exception as e:
                        logger.error(f"Error preparing dynamic info context: {e}")
                        continue
                if lines:
                    ref_blocks.append("【现有角色动态信息（只读参考）】\n" + "\n".join(lines))
            except Exception as e:
                logger.error(f"Error preparing dynamic info context: {e}")

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""

        user_prompt = (
            f"{ref_text}"
            f"章节正文：\n"
            f"{text}"
            f"请为以下参与者抽取动态信息：\n"
            f"{', '.join([p.name for p in character_participants])}\n\n"
        )

        res = await self._get_llm_service().generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=UpdateDynamicInfo,
            system_prompt=system_prompt,
            timeout=timeout,
        )

        if not isinstance(res, UpdateDynamicInfo):
            raise ValueError("LLM 动态信息抽取失败：输出格式不符合 UpdateDynamicInfo")
        
        # 后处理：仅保留 character_participants 中的角色
        if character_participants:
            name_set = {p.name for p in character_participants}
            if isinstance(res.info_list, list):
                res.info_list = [it for it in res.info_list if (it.name or '').strip() in name_set]
        
        return res

    async def extract_character_state_from_text(
        self,
        text: str,
        participants: Optional[List[ParticipantTyped]] = None,
        llm_config_id: int = 1,
        timeout: Optional[float] = None,
        prompt_name: Optional[str] = "角色状态更新",
        project_id: Optional[int] = None,
        extra_context: Optional[str] = None,
    ) -> UpdateCharacterState:
        """从正文中提取角色状态更新，按权重限制字段范围。"""
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {prompt_name}")
        system_prompt = prompt.template

        schema_json = UpdateCharacterState.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 格式进行输出:\n{schema_json}"

        ref_blocks: List[str] = []
        if extra_context:
            ref_blocks.append(f"【大纲参考信息，不允许直接抄写】\n{extra_context}")

        character_participants = [p for p in (participants or []) if p.type == 'character']
        if project_id and character_participants:
            lines: List[str] = []
            for p in character_participants:
                st = select(Card).where(Card.project_id == project_id, Card.title == p.name)
                card = self.session.exec(st).first()
                if not card or not card.card_type or card.card_type.name != '角色卡':
                    continue
                try:
                    model = CharacterCard.model_validate(card.content or {})
                    weight = _normalize_role_weight(
                        int(model.role_weight or ROLE_WEIGHT_DEFAULTS.get(model.role_type, 50)),
                        model.role_type,
                    )
                    tier = model.role_tier or _derive_role_tier(weight)
                    lines.append(f"- {p.name}（权重={weight}，层级={tier}）")
                    if model.last_appearance:
                        lines.append(f"  最后出场：卷{model.last_appearance[0]} 章{model.last_appearance[1]}")
                    if model.key_event_records:
                        lines.append(
                            "  关键事件：" + "；".join(
                                [f"第{item.chapter_number}章[{item.event_type}] {item.summary}" for item in model.key_event_records[:3]]
                            )
                        )
                    if model.position_tracks:
                        lines.append(
                            "  位置轨迹：" + "；".join(
                                [f"第{item.chapter_number}章 {item.location}" for item in model.position_tracks[:2]]
                            )
                        )
                    if model.life_state:
                        lines.append(
                            f"  生命状态：身体={model.life_state.physical_state}；心理={model.life_state.psychological_state}"
                        )
                    if model.dynamic_info:
                        lines.append(f"  动态信息类别：{', '.join(model.dynamic_info.keys())}")
                except Exception as e:
                    logger.warning(f"Failed to prepare character state context for {p.name}: {e}")
            if lines:
                ref_blocks.append("【现有角色状态（只读参考）】\n" + "\n".join(lines))

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        user_prompt = (
            f"{ref_text}"
            f"章节正文：\n{text}\n\n"
            f"请仅为这些角色输出状态更新：{', '.join([p.name for p in character_participants])}\n"
        )

        res = await self._get_llm_service().generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=UpdateCharacterState,
            system_prompt=system_prompt,
            timeout=timeout,
        )
        if not isinstance(res, UpdateCharacterState):
            raise ValueError("LLM 角色状态提取失败：输出格式不符合 UpdateCharacterState")

        if character_participants:
            name_set = {p.name for p in character_participants}
            if isinstance(res.state_list, list):
                res.state_list = [it for it in res.state_list if (it.name or "").strip() in name_set]

        return res

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.graph.query_subgraph(
            project_id=project_id,
            participants=participants,
            radius=radius,
            edge_type_whitelist=edge_type_whitelist,
            top_k=top_k,
            max_chapter_id=max_chapter_id,
        )

    def ingest_relations_from_llm(self, project_id: int, data: RelationExtraction, *, volume_number: Optional[int] = None, chapter_number: Optional[int] = None, participants_with_type: Optional[List[ParticipantTyped]] = None) -> Dict[str, Any]:
        # 写入关系三元组；同时最小持久化称呼/事件摘要/立场（作为可检索证据）
        # tuples: (主体, 关系, 客体, 属性字典)
        triples_with_attrs: List[tuple[str, str, str, Dict[str, Any]]] = []

        DIALOGUES_QUEUE_SIZE = 2
        EVENTS_QUEUE_SIZE = 10

        # 创建参与者类型映射以便快速查找
        participant_type_map = {p.name: p.type for p in participants_with_type} if participants_with_type else {}

        def _merge_queue(existing: List[Any], incoming: List[Any], key_fn=lambda x: x, max_size: int = 3) -> List[Any]:
            seen = set()
            merged: List[Any] = []
            # 先旧后新，保持“新在队尾”，之后裁剪保留队尾（最近）
            for it in (existing or []) + (incoming or []):
                k = key_fn(it)
                if k in seen:
                    continue
                seen.add(k)
                merged.append(it)
            if len(merged) <= max_size:
                return merged
            return merged[-max_size:]

        # 按队列策略合并对话/事件摘要（size=3），并序列化为字典
        merged_evidence_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        # 预取：将本批所有 (a, b, kind_cn) 收集，做一次子图查询后在内存中过滤，避免多次往返
        pairs: List[Tuple[str, str, str]] = []  # (a, b, kind_en)
        for r in (data.relations or []):
            pred = CN_TO_EN_KIND.get(r.kind or '', '')
            if pred:
                pairs.append((r.a, r.b, pred))

        # 构建现存数据索引：key=(a,b,kind_en) -> {recent_dialogues, recent_event_summaries}
        existing_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        try:
            # 参与者全集（去重）
            all_parts = list({p for t in pairs for p in (t[0], t[1])})
            if all_parts:
                sub = self.graph.query_subgraph(project_id=project_id, participants=all_parts, top_k=200)
                from app.schemas.relation_extract import EN_TO_CN_KIND
                for item in (sub.get("relation_summaries") or []):
                    try:
                        a0 = item.get("a"); b0 = item.get("b"); kind_cn = item.get("kind")
                        kind_en = CN_TO_EN_KIND.get(kind_cn or '', '')
                        if not (a0 and b0 and kind_en):
                            continue
                        key = (a0, b0, kind_en)
                        existing_index[key] = {
                            "recent_dialogues": item.get("recent_dialogues") or [],
                            "recent_event_summaries": item.get("recent_event_summaries") or [],
                        }
                    except Exception:
                        continue
        except Exception:
            existing_index = {}

        def _coerce_kind_by_types(kind_cn: str, type_a: Optional[str], type_b: Optional[str]) -> str:
            if not type_a or not type_b:
                return kind_cn
            allowed = _ALLOWED_PAIRS.get(kind_cn)
            if not allowed:
                return kind_cn
            if (type_a, type_b) in allowed:
                return kind_cn
            # 不合法：降级为“关于”
            return '关于'

        for r in (data.relations or []):
            pred = CN_TO_EN_KIND.get(r.kind or '', '')
            if not pred:
                continue
            
            # 使用传入的类型信息，如果缺失则回退到猜测
            type_a = participant_type_map.get(r.a) or _guess_entity_type(self.session, project_id, r.a)
            type_b = participant_type_map.get(r.b) or _guess_entity_type(self.session, project_id, r.b)

            # 约束：依据实体类型矫正关系 kind（中文）
            kind_cn_fixed = _coerce_kind_by_types(r.kind, type_a, type_b)
            pred = CN_TO_EN_KIND.get(kind_cn_fixed, pred)
            
            # 准备属性字典
            attributes = r.model_dump(exclude={"a", "b", "kind"}, exclude_none=True)

            # 后端强制过滤：如果 A 或 B 不是 character，则移除称呼和对话
            if type_a != 'character' or type_b != 'character':
                attributes.pop('a_to_b_addressing', None)
                attributes.pop('b_to_a_addressing', None)
                attributes.pop('recent_dialogues', None)

            # 对话（过滤长度）
            new_dialogues = [d.strip() for d in (attributes.get("recent_dialogues") or []) if isinstance(d, str) and len(d.strip()) >= 20]
            if new_dialogues:
                attributes["recent_dialogues"] = new_dialogues
            elif "recent_dialogues" in attributes:
                attributes.pop("recent_dialogues")


            # 事件摘要（补全卷章）
            new_summaries: List[Dict[str, Any]] = []
            old_summaries_by_summary: Dict[str, Dict[str, Any]] = {}
            key = (r.a, r.b, pred)
            prev = existing_index.get(key, {})
            old_summaries: List[Dict[str, Any]] = list(prev.get("recent_event_summaries") or [])
            for old_item in old_summaries:
                summary_key = str(old_item.get("summary") or "").strip()
                if summary_key and summary_key not in old_summaries_by_summary:
                    old_summaries_by_summary[summary_key] = old_item

            for s in (r.recent_event_summaries or []):
                try:
                    item = s.model_dump()
                    summary_text = str(item.get("summary") or "").strip()
                    if not summary_text:
                        continue

                    matched_old = old_summaries_by_summary.get(summary_text)
                    if matched_old:
                        if item.get("volume_number") is None and matched_old.get("volume_number") is not None:
                            item["volume_number"] = matched_old.get("volume_number")
                        if item.get("chapter_number") is None and matched_old.get("chapter_number") is not None:
                            item["chapter_number"] = matched_old.get("chapter_number")

                    if volume_number is not None and item.get("volume_number") is None:
                        item["volume_number"] = int(volume_number)
                    if chapter_number is not None and item.get("chapter_number") is None:
                        item["chapter_number"] = int(chapter_number)

                    if summary_text:
                        new_summaries.append(item)
                except Exception:
                    continue

            # 读取现存并合并为队列
            old_dialogues: List[str] = list(prev.get("recent_dialogues") or [])

            merged_dialogues = _merge_queue(old_dialogues, new_dialogues, key_fn=lambda x: x, max_size=DIALOGUES_QUEUE_SIZE)
            merged_summaries = _merge_queue(
                old_summaries,
                new_summaries,
                key_fn=lambda x: (
                    str((x or {}).get("summary") or "").strip(),
                    (x or {}).get("volume_number"),
                    (x or {}).get("chapter_number"),
                ),
                max_size=EVENTS_QUEUE_SIZE,
            )

            if merged_dialogues:
                attributes["recent_dialogues"] = merged_dialogues
            if merged_summaries:
                attributes["recent_event_summaries"] = merged_summaries

            # 清理空字段
            if not attributes.get("recent_dialogues") and "recent_dialogues" in attributes:
                attributes.pop("recent_dialogues", None)
            if not attributes.get("recent_event_summaries") and "recent_event_summaries" in attributes:
                attributes.pop("recent_event_summaries", None)
            
            triples_with_attrs.append((r.a, pred, r.b, attributes))
            
            # 返回值（仅摘要）
            merged_evidence_map[key] = {
                "recent_dialogues": attributes.get("recent_dialogues", []),
                "recent_event_summaries": [s.get('summary') for s in attributes.get("recent_event_summaries", [])]
            }

        if triples_with_attrs:
            try:
                self.graph.ingest_triples_with_attributes(project_id, triples_with_attrs)
            except Exception as e:
                raise ValueError(f"知识图谱写入失败: {e}")
        
        return {"written": len(triples_with_attrs), "merged_evidence": merged_evidence_map} 

    def update_dynamic_character_info(self, project_id: int, data: UpdateDynamicInfo, queue_size: int = 3) -> Dict[str, Any]:
        """
        更新角色卡的动态信息，支持新增、删除。
        每个类别的最大数量使用 DYNAMIC_INFO_LIMITS 中的配置；若未配置，则回退到 queue_size（默认3）。
        """
        from app.schemas.entity import CharacterCard

        # 1. 先处理删除
        if data.delete_info_list:
            for del_item in data.delete_info_list:
                # 心理想法/目标快照：忽略来自 LLM 的删除指令，交由系统按 FIFO 处理
                if str(del_item.dynamic_type) == '心理想法/目标快照':
                    continue
                st = select(Card).where(Card.project_id == project_id, Card.title == del_item.name)
                card = self.session.exec(st).first()
                if not card or card.card_type.name != '角色卡':
                    continue
                
                try:
                    model = CharacterCard.model_validate(card.content or {})
                    if model.dynamic_info and del_item.dynamic_type in model.dynamic_info:
                        model.dynamic_info[del_item.dynamic_type] = [
                            item for item in model.dynamic_info[del_item.dynamic_type] if item.id != del_item.id
                        ]
                        card.content = model.model_dump(exclude_unset=True)
                        flag_modified(card, "content")
                        self.session.add(card)
                except Exception as e:
                    logger.warning(f"Failed to process deletion for {del_item.name}: {e}")
            self.session.commit()

        # 2. 再处理新增与修改
        updated_cards: Dict[str, Card] = {}
        # 预加载所有相关的角色卡
        all_names = list(set([i.name for i in data.info_list]))
        if not all_names:
            return {"success": False, "updated_card_count": 0}

        stmt = select(Card).where(Card.project_id == project_id, Card.title.in_(all_names))
        cards = self.session.exec(stmt).all()
        card_map = {c.title: c for c in cards if c.card_type and c.card_type.name == '角色卡'}


        # 处理新增
        # (和之前类似，但要确保在已更新的 card 对象上操作)
        for info_group in data.info_list:
            card = updated_cards.get(info_group.name) or card_map.get(info_group.name)
            if not card:
                continue

            try:
                model = CharacterCard.model_validate(card.content or {})
                if not model.dynamic_info:
                    model.dynamic_info = {}

                for cat, items in info_group.dynamic_info.items():
                    if not items:
                        continue
                    
                    if cat not in model.dynamic_info:
                        model.dynamic_info[cat] = []
                    
                    existing_items = model.dynamic_info[cat]
                    existing_normalized = {
                        _normalize_compare_text(str(item.info or ""))
                        for item in existing_items
                        if _normalize_compare_text(str(item.info or ""))
                    }
                    
                    # 合并（新项追加在队尾，便于 FIFO）
                    for new_item in items:
                        normalized_info = _normalize_compare_text(str(new_item.info or ""))
                        if not normalized_info:
                            continue
                        if normalized_info in existing_normalized:
                            continue
                        if _has_state_level_overlap(model, new_item.info):
                            logger.info(
                                f"[DynamicInfo] 跳过与当前状态层重复的动态信息: role={info_group.name}, "
                                f"category={cat}, info={new_item.info}"
                            )
                            continue
                        # 将占位或缺失ID暂记为 0，稍后统一分配正数ID
                        if not isinstance(new_item.id, int) or new_item.id <= 0:
                            new_item.id = 0
                        existing_items.append(new_item)
                        existing_normalized.add(normalized_info)
                    
                    # 统一ID规范化：为所有 <=0 的条目分配连续正数ID（不改变已有正数ID）
                    existing_positive = [it.id for it in existing_items if isinstance(it.id, int) and it.id > 0]
                    next_id = (max(existing_positive) + 1) if existing_positive else 1
                    for it in existing_items:
                        if not isinstance(it.id, int) or it.id <= 0:
                            it.id = next_id
                            next_id += 1
                    
                    # 按配置上限裁剪
                    limit = DYNAMIC_INFO_LIMITS.get(cat, queue_size)
                    if str(cat) == '心理想法/目标快照':
                        # 保留最新 limit 条（先进先出，淘汰最旧）
                        model.dynamic_info[cat] = existing_items[-limit:]
                    else:
                        # 其他类别沿用当前策略（若需改为保留最新，可改为 existing_items[-limit:]）
                        model.dynamic_info[cat] = existing_items[:limit]

                card.content = model.model_dump(exclude_unset=True)
                flag_modified(card, "content")
                updated_cards[card.title] = card
            except Exception as e:
                logger.warning(f"Failed to process addition for {info_group.name}: {e}")

        # 统一提交
        for card in updated_cards.values():
            self.session.add(card)
        
        if updated_cards:
            self.session.commit()
            for card in updated_cards.values():
                self.session.refresh(card)

        return {"success": True, "updated_card_count": len(updated_cards)} 

    def update_character_state(self, project_id: int, data: UpdateCharacterState) -> Dict[str, Any]:
        """按角色权重将最新角色状态合并回角色卡，只保留最近有效记录。"""
        state_list = data.state_list or []
        if not state_list:
            return {"success": False, "updated_card_count": 0}

        all_names = list(set([item.name for item in state_list if (item.name or "").strip()]))
        if not all_names:
            return {"success": False, "updated_card_count": 0}

        stmt = select(Card).where(Card.project_id == project_id, Card.title.in_(all_names))
        cards = self.session.exec(stmt).all()
        card_map = {c.title: c for c in cards if c.card_type and c.card_type.name == '角色卡'}

        updated_cards: Dict[str, Card] = {}

        for patch in state_list:
            card = updated_cards.get(patch.name) or card_map.get(patch.name)
            if not card:
                continue

            try:
                model = CharacterCard.model_validate(card.content or {})

                weight = _apply_role_weight_change(
                    current_weight=int(model.role_weight or ROLE_WEIGHT_DEFAULTS.get(model.role_type, 50)),
                    suggested_weight=patch.role_weight,
                    role_type=model.role_type,
                )
                model.role_weight = weight
                model.role_tier = _derive_role_tier(weight)
                limits = _role_state_limits(weight)

                if patch.aliases:
                    merged_aliases = [*(model.aliases or []), *patch.aliases]
                    deduped: List[str] = []
                    seen = set()
                    for alias in merged_aliases:
                        normalized = str(alias or "").strip()
                        if not normalized or normalized in seen:
                            continue
                        seen.add(normalized)
                        deduped.append(normalized)
                    model.aliases = deduped[:8]

                if patch.position_tracks:
                    merged_tracks = [*(model.position_tracks or []), *patch.position_tracks]
                    merged_tracks = _dedupe_keep_last(
                        merged_tracks,
                        lambda item: (
                            int(item.volume_number or 0),
                            int(item.chapter_number),
                            str(item.location or "").strip(),
                            str(item.event or "").strip(),
                            str(item.purpose or "").strip(),
                        ),
                    )
                    merged_tracks.sort(key=lambda item: (int(item.volume_number or 0), int(item.chapter_number)))
                    model.position_tracks = merged_tracks[-limits["position_tracks"]:]

                if patch.key_event_records and weight >= 21:
                    merged_events = [*(model.key_event_records or []), *patch.key_event_records]
                    merged_events = _dedupe_keep_last(
                        merged_events,
                        lambda item: (
                            int(item.volume_number or 0),
                            int(item.chapter_number),
                            str(item.event_type or "").strip(),
                            str(item.summary or "").strip(),
                        ),
                    )
                    merged_events.sort(key=lambda item: (int(item.volume_number or 0), int(item.chapter_number)))
                    model.key_event_records = merged_events[-limits["key_event_records"]:]

                if patch.life_state and weight >= 41:
                    model.life_state = patch.life_state

                if patch.inventory_items and weight >= 41:
                    merged_inventory = [*(model.inventory_items or []), *patch.inventory_items]
                    merged_inventory = _dedupe_keep_last(merged_inventory, lambda item: str(item.name or "").strip())
                    model.inventory_items = merged_inventory[-limits["inventory_items"]:]

                if patch.techniques and weight >= 41:
                    merged_techniques = [*(model.techniques or []), *patch.techniques]
                    merged_techniques = _dedupe_keep_last(merged_techniques, lambda item: str(item.name or "").strip())
                    model.techniques = merged_techniques[-limits["techniques"]:]

                if patch.relationship_network and weight >= 61:
                    merged_relationships = [*(model.relationship_network or []), *patch.relationship_network]
                    merged_relationships = _dedupe_keep_last(
                        merged_relationships,
                        lambda item: (
                            str(item.target_name or "").strip(),
                            str(item.relation_type or "").strip(),
                        ),
                    )
                    model.relationship_network = merged_relationships[-limits["relationship_network"]:]

                if patch.behavior_decision_pattern and weight >= 81:
                    model.behavior_decision_pattern = patch.behavior_decision_pattern

                if patch.dialogue_style_keywords and weight >= 81:
                    model.dialogue_style_keywords = patch.dialogue_style_keywords

                if patch.romance_state and weight >= 96:
                    model.romance_state = patch.romance_state

                latest_appearance = _latest_appearance_from_model(model)
                if latest_appearance:
                    model.last_appearance = latest_appearance

                card.content = model.model_dump(exclude_unset=True)
                flag_modified(card, "content")
                updated_cards[card.title] = card
            except Exception as e:
                logger.warning(f"Failed to update character state for {patch.name}: {e}")

        for card in updated_cards.values():
            self.session.add(card)

        if updated_cards:
            self.session.commit()
            for card in updated_cards.values():
                self.session.refresh(card)

        return {"success": True, "updated_card_count": len(updated_cards)}
