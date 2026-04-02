from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union, Tuple
from pydantic import BaseModel, Field, field_validator

# 以 Literal 表达可选集合，并提供常量数组供遍历/Schema 构造
DynamicInfoType = Literal[
    "系统/模拟器/金手指信息",
    "等级/修为境界",
    "装备/法宝",
    "知识/情报",
    "资产/领地",
    "功法/技能",
    "血脉/体质",
    "心理想法/目标快照",
]
DYNAMIC_INFO_TYPES: List[str] = [
    "系统/模拟器/金手指信息",
    "等级/修为境界",
    "装备/法宝",
    "知识/情报",
    "资产/领地",
    "功法/技能",
    "血脉/体质",
    "心理想法/目标快照",
]

# 实体类型标识（统一主类型）
EntityType = Literal['character', 'scene', 'organization']
RoleTier = Literal['背景角色', '单元角色', '次要配角', '关键角色', '核心配角', '主角级']


class DynamicInfoItem(BaseModel):
    id:int=Field(-1,description="手动设置，无需生成；并入时若为-1将自动赋值为该类别的顺序序号（从1开始）")
    info:str=Field(description="简要描述具体动态信息。")
    # weight:float=Field(description="权重，0-1之间")
    
class DynamicInfo(BaseModel):
    name: str = Field(description="角色名称。")
    # 键直接使用中文字面量类型，前后端一致
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(default_factory=dict, description="动态信息字典，键为中文类别；值为信息项列表。")

    @field_validator('dynamic_info', mode='before')
    @classmethod
    def _normalize_keys(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        normalized: Dict[str, Any] = {}
        allowed = set(DYNAMIC_INFO_TYPES)
        for k, arr in v.items():
            key = k if isinstance(k, str) else str(k)
            # 仅保留允许的中文键，其它忽略
            if key in allowed:
                normalized[key] = arr
        return normalized

class DeletionInfo(BaseModel):
    name: str = Field(description="角色名称。")
    dynamic_type: DynamicInfoType = Field(description="动态信息类型。")
    id: int = Field(gt=0, description="要删除的动态信息的ID (不能为-1)")

class UpdateDynamicInfo(BaseModel):
    info_list:List[DynamicInfo]=Field(description="需要更新的动态信息列表，尽量只提取足够重要的信息")
    delete_info_list: Optional[List[DeletionInfo]] = Field(default=None, description="（可选）为新增信息腾出空间而要删除的旧信息列表")


class Entity(BaseModel):
    name: str = Field(..., min_length=1, description="实体名称（唯一标识），不包含任何别称、外号、称号等信息，单纯的名称。")
    entity_type: EntityType = Field(..., description="实体类型标记。")
    life_span: Literal['长期','短期'] = Field(description="实体在故事中的生命周期。长期表示跨卷存在，短期表示仅在单卷内产生影响")
    # 最后出场时间（二维：卷号、章节号）
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最后出场时间：[卷号, 章节号]")



class CharacterCardCore(Entity):
    role_type: Literal['主角','主角团配角','普通NPC','反派'] = Field("主角团配角", description="角色定位。")
    born_scene: str = Field(description="出场/常驻场景。")
    description: str = Field(description="一句话简介/背景与关系概述。")


class CharacterCard(CharacterCardCore):
    """完整角色卡。"""
    # 固定实体类型标记
    entity_type: EntityType = Field(description="实体类型标记。")
    character_code: Optional[str] = Field(default=None, description="角色稳定编号，例如 ID0001。")
    gender: Optional[str] = Field(default=None, description="角色性别。")
    age: Optional[str] = Field(default=None, description="角色年龄或年龄段。")
    appearance: Optional[str] = Field(default=None, description="外貌特征与识别点。")
    identity: Optional[str] = Field(default=None, description="职业、身份或社会定位。")
    first_volume: Optional[int] = Field(default=None, description="首次登场的分卷。")
    first_event: Optional[str] = Field(default=None, description="首次登场事件或情境。")
    story_function: Optional[str] = Field(default=None, description="该角色在故事中的叙事功能。")
    background: Optional[str] = Field(default=None, description="角色背景、成长经历或出身概述。")
    personality: str = Field(description="性格关键词，如'谨慎'、'幽默'。")
    core_drive: str = Field(description="核心驱动力/目标。")
    inner_conflict: Optional[str] = Field(default=None, description="角色内在矛盾或心理拉扯。")
    relationship_summary: Optional[str] = Field(default=None, description="与关键角色的关系摘要。")
    character_arc: str = Field(description="一段话简要描述角色在全书的弧光/阶段变化。")
    aliases: List[str] = Field(default_factory=list, description="角色其他称谓列表，如别称、小名、尊称、化名等。")
    role_weight: Optional[int] = Field(default=None, ge=1, le=100, description="角色权重，1-100。")
    role_tier: Optional[RoleTier] = Field(default=None, description="根据角色权重自动映射出的角色层级。")
    position_tracks: List["PositionTrackItem"] = Field(default_factory=list, description="最近若干条位置轨迹，仅保留当前有效记录。")
    key_event_records: List["KeyEventItem"] = Field(default_factory=list, description="最近若干条关键事件记录。")
    life_state: Optional["LifeState"] = Field(default=None, description="角色当前生命状态。")
    inventory_items: List["InventoryItem"] = Field(default_factory=list, description="角色当前持有物品。")
    techniques: List["TechniqueItem"] = Field(default_factory=list, description="角色当前技术能力或可稳定调用的能力。")
    relationship_network: List["RelationshipNetworkItem"] = Field(default_factory=list, description="角色当前主要关系网。")
    behavior_decision_pattern: Optional["BehaviorDecisionPattern"] = Field(default=None, description="角色当前的行为模式与决策偏好。")
    dialogue_style_keywords: Optional["DialogueStyleKeywords"] = Field(default=None, description="角色当前的语言风格与常用对话关键词。")
    romance_state: Optional["RomanceState"] = Field(default=None, description="角色当前情感线状态。")

    # 动态信息（新设计方案：集中作为真相源）
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(default_factory=dict, description="动态信息字典，留空，勿生成信息，系统会自动维护。")

    @field_validator('dynamic_info', mode='before')
    @classmethod
    def _normalize_dynamic_info(cls, v: Any) -> Dict[str, Any]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            return {}
        return v


class PositionTrackItem(BaseModel):
    volume_number: Optional[int] = Field(default=None, ge=1, description="所在卷号。")
    chapter_number: int = Field(ge=1, description="所在章节号。")
    location: str = Field(description="位置或行动路径。")
    event: str = Field(description="该位置对应的事件摘要。")
    companions: List[str] = Field(default_factory=list, description="同行人物列表。")
    purpose: str = Field(default="", description="行动目的。")


class KeyEventItem(BaseModel):
    volume_number: Optional[int] = Field(default=None, ge=1, description="所在卷号。")
    chapter_number: int = Field(ge=1, description="所在章节号。")
    event_type: str = Field(description="事件类型，如战斗、突破、对峙、情报等。")
    summary: str = Field(description="事件摘要。")


class LifeState(BaseModel):
    physical_state: str = Field(default="", description="身体状态。")
    psychological_state: str = Field(default="", description="心理状态。")
    long_term_impact: str = Field(default="", description="长期影响。")


class InventoryItem(BaseModel):
    name: str = Field(description="物品名称。")
    description: str = Field(description="物品功能、状态或来源说明。")


class TechniqueItem(BaseModel):
    name: str = Field(description="能力或技术名称。")
    description: str = Field(description="能力或技术说明。")


class RelationshipNetworkItem(BaseModel):
    target_name: str = Field(description="关系对象名称。")
    relation_type: str = Field(description="关系类型。")
    relation_strength: Literal['低', '中', '高'] = Field(default='中', description="关系强度。")
    interaction_frequency: Literal['稀少', '普通', '频繁'] = Field(default='普通', description="互动频率。")


class BehaviorDecisionPattern(BaseModel):
    behavior_pattern: str = Field(default="", description="行为模式。")
    decision_preference: str = Field(default="", description="决策偏好。")


class DialogueStyleKeywords(BaseModel):
    style_tags: List[str] = Field(default_factory=list, description="语言风格标签。")
    keywords: List[str] = Field(default_factory=list, description="常用短句或关键词。")


class RomanceState(BaseModel):
    state_description: str = Field(default="", description="情感线状态说明。")
    favorability: Optional[int] = Field(default=None, ge=0, le=100, description="好感度。")
    bond_level: Optional[int] = Field(default=None, ge=0, description="羁绊等级。")


class PositionTrackSummary(BaseModel):
    location: str = Field(description="本章结束时最关键的位置。")
    event: str = Field(default="", description="该位置对应的关键事件。")
    companions: List[str] = Field(default_factory=list, description="同行角色。")
    purpose: str = Field(default="", description="行动目的。")


class KeyEventSummary(BaseModel):
    event_type: str = Field(description="本章关键事件类型。")
    summary: str = Field(description="本章关键事件摘要。")


class CharacterStateSummaryItem(BaseModel):
    name: str = Field(description="角色名称，必须匹配现有角色卡标题。")
    aliases: List[str] = Field(default_factory=list, description="本章确认的别称。")
    role_weight: Optional[int] = Field(default=None, ge=1, le=100, description="建议角色权重。")
    latest_position: Optional[PositionTrackSummary] = Field(default=None, description="本章结束时的关键位置摘要。")
    latest_event: Optional[KeyEventSummary] = Field(default=None, description="本章最关键的事件摘要。")
    life_state: Optional[LifeState] = Field(default=None, description="本章结束时的生命状态。")
    inventory_items: List[InventoryItem] = Field(default_factory=list, description="本章确认的持有物品变化。")
    techniques: List[TechniqueItem] = Field(default_factory=list, description="本章确认的能力变化。")
    relationship_network: List[RelationshipNetworkItem] = Field(default_factory=list, description="本章确认的主要关系变化。")
    behavior_decision_pattern: Optional[BehaviorDecisionPattern] = Field(default=None, description="本章体现出的行为与决策倾向。")
    dialogue_style_keywords: Optional[DialogueStyleKeywords] = Field(default=None, description="本章体现出的语言风格。")
    romance_state: Optional[RomanceState] = Field(default=None, description="本章结束时的情感线状态。")


class CharacterStateSummaryResult(BaseModel):
    summary_list: List[CharacterStateSummaryItem] = Field(default_factory=list, description="角色状态摘要列表。")


class CharacterStateUpdate(BaseModel):
    name: str = Field(description="角色名称，必须匹配现有角色卡标题。")
    aliases: Optional[List[str]] = Field(default=None, description="新增或确认的其他称谓。")
    role_weight: Optional[int] = Field(default=None, ge=1, le=100, description="角色权重，允许在确有必要时更新。")
    position_tracks: Optional[List[PositionTrackItem]] = Field(default=None, description="最新位置轨迹。")
    key_event_records: Optional[List[KeyEventItem]] = Field(default=None, description="最新关键事件记录。")
    life_state: Optional[LifeState] = Field(default=None, description="当前生命状态。")
    inventory_items: Optional[List[InventoryItem]] = Field(default=None, description="当前持有物品。")
    techniques: Optional[List[TechniqueItem]] = Field(default=None, description="当前技术能力。")
    relationship_network: Optional[List[RelationshipNetworkItem]] = Field(default=None, description="当前主要关系网。")
    behavior_decision_pattern: Optional[BehaviorDecisionPattern] = Field(default=None, description="行为模式与决策偏好。")
    dialogue_style_keywords: Optional[DialogueStyleKeywords] = Field(default=None, description="语言风格与对话关键词。")
    romance_state: Optional[RomanceState] = Field(default=None, description="情感线状态。")


class UpdateCharacterState(BaseModel):
    state_list: List[CharacterStateUpdate] = Field(description="本次需要写回角色卡的角色状态更新列表。")


class SceneCard(Entity):
    # 固定实体类型标记
    entity_type: EntityType = Field('scene', description="实体类型标记。")
    description: str = Field(description="场景/地图一句话简介")
    function_in_story: str = Field(description="在剧情中的作用") 

# 组织实体
class OrganizationCard(Entity):
    entity_type: EntityType = Field('organization', description="实体类型标记。")
    description: str = Field(description="该组织/势力阵营的信息描述")
    influence: Optional[str] = Field(default=None, description="该组织对小说世界的影响范围/影响力")
    relationship:Optional[List[str]]=Field(description="该组织与其他组织的关系，例如敌对、合作、中立等") 
