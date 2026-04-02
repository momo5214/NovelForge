"""卡片类型初始化

初始化默认卡片类型及其Schema定义。
"""

import re
from typing import Any, Dict

from sqlmodel import Session, select
from loguru import logger

from app.db.models import CardType, LLMConfig
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from .registry import initializer


FIELD_TITLE_ZH_MAP: Dict[str, str] = {
    "content": "内容",
    "theme": "主题",
    "audience": "目标读者",
    "narrative_person": "叙事人称",
    "story_tags": "故事标签",
    "affection": "情感关系",
    "total_chapters": "总章数",
    "chapter_word_count": "每章字数",
    "name": "名称",
    "description": "描述",
    "special_abilities_thinking": "金手指设计思考",
    "special_abilities": "金手指",
    "one_sentence_thinking": "一句话梗概思考",
    "one_sentence": "一句话梗概",
    "overview_thinking": "大纲扩展思考",
    "overview": "概述",
    "power_structure": "权力结构",
    "currency_system": "货币体系",
    "background": "背景",
    "major_power_camps": "主要势力阵营",
    "world_view_thinking": "世界观设计思考",
    "world_view": "世界观",
    "volume_count": "总卷数",
    "character_thinking": "角色设计思考",
    "character_cards": "角色卡",
    "scene_thinking": "场景设计思考",
    "scene_cards": "场景卡",
    "organization_thinking": "组织设计思考",
    "organization_cards": "组织卡",
    "volume_number": "卷号",
    "title": "标题",
    "main_target": "主线目标",
    "branch_line": "辅线",
    "new_character_cards": "新增角色卡",
    "new_scene_cards": "新增场景卡",
    "stage_count": "阶段数量",
    "character_action_list": "角色行动列表",
    "entity_snapshot": "实体状态快照",
    "volume_title": "卷名",
    "volume_theme": "分卷主题",
    "plot_milestone": "情节里程碑",
    "worldview_evolution": "世界观演进",
    "ending_hook": "结尾悬念",
    "core_setting_expansion": "核心设定展开",
    "core_conflict": "核心冲突",
    "suspense_clues": "悬念线索",
    "protagonist_progress": "主角进程",
    "protagonist_team_dynamic": "主角团动态",
    "key_character_arcs": "角色弧光",
    "chapter_range": "章节范围",
    "emotional_tone": "情绪基调",
    "narrative_perspective": "叙事视角",
    "signature_scenes": "标志性场景",
    "stage_number": "阶段号",
    "chapter_number": "章节号",
    "entity_list": "实体列表",
    "stage_name": "阶段名称",
    "reference_chapter": "参考章节范围",
    "suspense_curve": "悬念曲线",
    "foreshadow_plan": "伏笔计划",
    "chapter_position": "本章定位",
    "core_function": "核心作用",
    "scene_time": "时间",
    "scene_location": "地点",
    "atmosphere": "氛围",
    "character_motivations": "出场角色与动机",
    "plot_start": "情节脉络-起",
    "plot_develop": "情节脉络-承",
    "plot_twist": "情节脉络-转",
    "plot_end": "情节脉络-合",
    "suspense_type": "悬念类型",
    "emotion_curve": "情绪演变",
    "foreshadow_items": "伏笔条目",
    "reversal_index": "颠覆指数",
    "analysis": "分析",
    "chapter_outline_list": "章节大纲列表",
    "entity_type": "实体类型",
    "life_span": "生命周期",
    "role_type": "角色类型",
    "gender": "性别",
    "age": "年龄",
    "appearance": "外貌特征",
    "identity": "身份/职业",
    "born_scene": "出生场景",
    "first_volume": "首次登场分卷",
    "first_event": "首次登场事件",
    "story_function": "故事功能",
    "background": "背景经历",
    "personality": "性格",
    "core_drive": "核心驱动力",
    "inner_conflict": "内在冲突",
    "relationship_summary": "关键关系摘要",
    "character_arc": "角色弧光",
    "character_code": "角色编号",
    "influence": "影响力",
    "relationship": "关系",
    "dynamic_info": "动态信息",
    "aliases": "其他称谓",
    "role_weight": "角色权重",
    "role_tier": "角色层级",
    "last_appearance": "最后出场时间",
    "position_tracks": "位置轨迹",
    "key_event_records": "关键事件记录",
    "life_state": "生命状态",
    "inventory_items": "持有物品",
    "techniques": "技术能力",
    "relationship_network": "关系网",
    "behavior_decision_pattern": "行为模式与决策偏好",
    "dialogue_style_keywords": "语言风格与对话关键词",
    "romance_state": "情感线状态",
    "volume_number": "卷号",
    "chapter_number": "章节号",
    "location": "位置",
    "event": "事件",
    "companions": "同行人物",
    "purpose": "目的",
    "event_type": "事件类型",
    "summary": "摘要",
    "physical_state": "身体状态",
    "psychological_state": "心理状态",
    "long_term_impact": "长期影响",
    "target_name": "关系对象",
    "relation_type": "关系类型",
    "relation_strength": "关系强度",
    "interaction_frequency": "互动频率",
    "behavior_pattern": "行为模式",
    "decision_preference": "决策偏好",
    "style_tags": "语言风格",
    "keywords": "关键词",
    "state_description": "情感线状态说明",
    "favorability": "好感度",
    "bond_level": "羁绊等级",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _derive_title_from_description(description: Any) -> str | None:
    if not isinstance(description, str):
        return None
    desc = description.strip()
    if not desc or not _contains_cjk(desc):
        return None

    candidate = re.split(r"[，。；;：:（(\n]", desc, maxsplit=1)[0].strip()
    if not candidate:
        return None
    if len(candidate) > 16:
        candidate = candidate[:16].strip()
    return candidate or None


def _localize_schema_titles(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for field_name, field_schema in properties.items():
                    if not isinstance(field_schema, dict):
                        continue
                    current_title = str(field_schema.get("title") or "")
                    if not _contains_cjk(current_title):
                        localized = FIELD_TITLE_ZH_MAP.get(field_name) or _derive_title_from_description(
                            field_schema.get("description")
                        )
                        if localized:
                            field_schema["title"] = localized
                    visit(field_schema)

            defs = node.get("$defs")
            if isinstance(defs, dict):
                for def_schema in defs.values():
                    visit(def_schema)

            items = node.get("items")
            if isinstance(items, dict):
                visit(items)

            for union_key in ("anyOf", "oneOf", "allOf"):
                variants = node.get(union_key)
                if isinstance(variants, list):
                    for variant in variants:
                        visit(variant)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return schema


def _resolve_card_type_schema(name: str, details: Dict[str, Any], type_to_model_key: Dict[str, str]) -> Any:
    explicit_schema = details.get("json_schema")
    if explicit_schema is not None:
        if isinstance(explicit_schema, dict):
            return _localize_schema_titles(explicit_schema)
        return explicit_schema

    try:
        model_class = RESPONSE_MODEL_MAP.get(type_to_model_key.get(name))
        if model_class:
            schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
            return _localize_schema_titles(schema)
    except Exception:
        pass
    return None


@initializer(name="卡片类型", order=20)
def create_default_card_types(session: Session) -> None:
    """初始化默认卡片类型
    
    创建所有内置卡片类型及其Schema、AI参数预设等。
    
    Args:
        session: 数据库会话
    """
    default_types = {
        "通用文本": {
            "editor_component": "MarkdownTextEditor",
            "is_singleton": False,
            "is_ai_enabled": False,
            "default_ai_context_template": None,
            "json_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "title": "内容", "description": "任意文本内容，需使用/转换为 markdown 格式文本"}
                },
                "required": ["content"],
                "additionalProperties": True,
            },
        },
        "作品标签": {"editor_component": "TagsEditor", "is_singleton": True, "is_ai_enabled": False, "default_ai_context_template": None},
        "金手指": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content"},
        "一句话梗概": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities"},
        "故事大纲": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事梗概: @一句话梗概.content.one_sentence"},
        "世界观设定": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大纲: @故事大纲.content.overview"},
        "核心蓝图": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大纲: @故事大纲.content.overview\n世界观设定: @世界观设定.content\n组织/势力设定:@type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}"},
        "增强核心蓝图": {
            "is_singleton": True,
            "json_schema": {
                "type": "object",
                "properties": {
                    "volume_count": {
                        "type": "integer",
                        "minimum": 1,
                        "title": "总卷数",
                        "description": "预期小说的分卷数，通常设置为 3~6 卷"
                    },
                    "scene_thinking": {
                        "type": "string",
                        "title": "场景设计思考",
                        "description": "说明如何从五步结果中收束出长期核心场景"
                    },
                    "scene_cards": {
                        "type": "array",
                        "title": "场景卡",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "title": "名称"},
                                "entity_type": {"type": "string", "enum": ["scene"], "title": "实体类型"},
                                "life_span": {"type": "string", "enum": ["长期"], "title": "生命周期"},
                                "description": {"type": "string", "title": "描述"},
                                "function_in_story": {"type": "string", "title": "在故事中的作用"}
                            },
                            "required": ["name", "entity_type", "life_span", "description", "function_in_story"]
                        },
                        "description": "跨卷长期复用的核心场景/地图/据点列表"
                    }
                },
                "required": ["volume_count", "scene_thinking", "scene_cards"]
            },
            "default_ai_context_template": (
                "作品标签: @作品标签.content\n"
                "金手指/特殊能力: @金手指.content.special_abilities\n"
                "一句话梗概: @一句话梗概.content.one_sentence\n"
                "故事大纲: @故事大纲.content.overview\n"
                "步骤1-分卷使命宣言: @type:小说架构步骤[index=1].content.content\n"
                "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
                "步骤3-情节线与推进机制: @type:小说架构步骤[index=3].content.content\n"
                "步骤4-核心角色规划: @type:小说架构步骤[index=4].content.content\n"
                "步骤5-叙事风格与文本策略: @type:小说架构步骤[index=5].content.content\n"
                "组织/势力设定: @type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}"
            )
        },
        "增强分卷大纲": {"default_ai_context_template": (
            "总卷数: @type:增强核心蓝图[index=1].content.volume_count\n"
            "故事大纲:@故事大纲.content.overview\n"
            "作品标签:@作品标签.content\n"
            "步骤1-分卷使命宣言: @type:小说架构步骤[index=1].content.content\n"
            "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
            "步骤3-情节线与推进机制: @type:小说架构步骤[index=3].content.content\n"
            "步骤4-核心角色规划: @type:小说架构步骤[index=4].content.content\n"
            "步骤5-叙事风格与文本策略: @type:小说架构步骤[index=5].content.content\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}\n"
            "角色卡:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_volume,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc}\n"
            "场景卡:@type:场景卡[previous:global].{content.name,content.description,content.function_in_story}\n"
            "上一卷信息: @type:增强分卷大纲[index=$current.volumeNumber-1].content\n"
            "接下来请你创作第 @self.content.volume_number 卷的细纲\n"
        ),
        "ui_layout": {
            "sections": [
                {
                    "title": "卷定位",
                    "description": "先确定本卷在整书中的位置与阅读体验。",
                    "include": [
                        "volume_number",
                        "volume_title",
                        "volume_theme",
                        "chapter_range",
                        "stage_count",
                        "emotional_tone",
                        "narrative_perspective",
                    ],
                },
                {
                    "title": "卷使命",
                    "description": "定义本卷的战略目标、成长节点与卷末钩子。",
                    "include": [
                        "plot_milestone",
                        "worldview_evolution",
                        "ending_hook",
                    ],
                },
                {
                    "title": "剧情推进",
                    "description": "主线、支线、冲突与节奏骨架。",
                    "include": [
                        "main_target",
                        "branch_line",
                        "core_setting_expansion",
                        "core_conflict",
                        "suspense_clues",
                        "protagonist_progress",
                        "signature_scenes",
                    ],
                },
                {
                    "title": "角色发展",
                    "description": "角色群像推进与卷末状态变化。",
                    "include": [
                        "protagonist_team_dynamic",
                        "key_character_arcs",
                        "character_action_list",
                        "entity_snapshot",
                    ],
                },
                {
                    "title": "增量资产",
                    "description": "仅在本卷确有必要时补充新角色/新场景。",
                    "include": [
                        "new_character_cards",
                        "new_scene_cards",
                    ],
                    "collapsed": True,
                },
                {
                    "title": "内部推演",
                    "description": "给 AI 与工作流使用的思考字段，和正文型字段分开收纳。",
                    "include": [
                        "thinking",
                        "character_thinking",
                    ],
                    "collapsed": True,
                },
            ]
        }},
        "分卷大纲": {"default_ai_context_template": (
            "总卷数(雪花流): @核心蓝图.content.volume_count\n"
            "总卷数(增强流): @type:增强核心蓝图[index=1].content.volume_count\n"
            "故事大纲:@故事大纲.content.overview\n"
            "作品标签:@作品标签.content\n"
            "世界观设定: @世界观设定.content.world_view\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}\n"
            "character_card:@type:角色卡[previous]\n"
            "scene_card:@type:场景卡[previous]\n"
            "上一卷信息: @type:分卷大纲[index=$current.volumeNumber-1].content\n"
            "接下来请你创作第 @self.content.volume_number 卷的细纲\n"
        )},
        "增强写作指南": {
            "is_singleton": False,
            "default_ai_context_template": (
                "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
                "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
                "当前分卷主线:@parent.content.main_target\n"
                "当前分卷辅线:@parent.content.branch_line\n"
                "该卷的阶段数量及卷末实体状态快照:@parent.{content.stage_count,content.entity_snapshot}\n"
                "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_volume,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc}\n"
                "地图/场景卡信息:@type:场景卡[previous:global].{content.name,content.description,content.function_in_story}\n"
                "请为第 @self.content.volume_number 卷生成一份写作指南。"
            )
        },
        "写作指南": {
            "is_singleton": False,
            "default_ai_context_template": (
                "世界观设定: @世界观设定.content.world_view\n"
                "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
                "当前分卷主线:@parent.content.main_target\n"
                "当前分卷辅线:@parent.content.branch_line\n"
                "该卷的阶段数量及卷末实体状态快照:@parent.{content.stage_count,content.entity_snapshot}\n"
                "角色卡信息:@type:角色卡[previous]\n"
                "地图/场景卡信息:@type:场景卡[previous]\n"
                "请为第 @self.content.volume_number 卷生成一份写作指南。"
            )
        },
        "增强阶段大纲": {"default_ai_context_template": (
            "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
            "当前分卷大纲完整结果:@parent.content\n"
            "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_volume,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc}\n"
            "地图/场景卡信息:@type:场景卡[previous:global].{content.name,content.description,content.function_in_story}\n"
            "该卷的角色行动简述:@parent.content.character_action_list\n"
            "之前的阶段故事大纲，确保章节范围、剧情能够衔接:@type:增强阶段大纲[previous:global:1].{content.stage_name,content.reference_chapter,content.analysis,content.overview,content.entity_snapshot}\n"
            "本卷的StageCount总数为：@parent.content.stage_count\n"
            "注意，请务必在@parent.content.stage_count 个阶段内将故事按分卷主线收束，并达到卷末实体快照状态:@parent.content.entity_snapshot\n"
            "该卷的写作注意事项:@type:增强写作指南[sibling].content.content \n"
            "接下来请你创作第 @self.content.stage_number 阶段的故事细纲。"
        )},
        "增强章节拆解": {"default_ai_context_template": (
            "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
            "当前分卷大纲完整结果:@type:增强分卷大纲[index=$current.volumeNumber].content\n"
            "当前阶段任务书:@parent.content\n"
            "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_volume,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc}\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
            "地图/场景卡信息:@type:场景卡[previous:global].{content.name,content.description,content.function_in_story}\n"
            "之前最近3章章节大纲，确保连贯衔接:@type:增强章节大纲[previous:global:3].{content.chapter_number,content.title,content.chapter_position,content.core_function,content.plot_end,content.foreshadow_items,content.overview,content.entity_list}\n"
            "当前未回收伏笔状态:@type:通用文本[index=filter:title = '伏笔管理/未回收台账'].content.content\n"
            "该卷的写作注意事项:@type:增强写作指南[index=filter:content.volume_number = $self.content.volume_number].content.content\n"
            "现在请围绕当前阶段任务书，连续拆解第 @self.content.reference_chapter 章节范围内的章节大纲。"
        )},
        "阶段大纲": {"default_ai_context_template": (
            "世界观设定: @世界观设定.content.world_view\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
            "分卷主线:@parent.content.main_target\n"
            "分卷辅线:@parent.content.branch_line\n"
            "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_volume,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc}\n"
            "地图/场景卡信息:@type:场景卡[previous]\n"
            "该卷的角色行动简述:@parent.content.character_action_list\n"
            "之前的阶段故事大纲，确保章节范围、剧情能够衔接:@type:阶段大纲[previous:global:1].{content.stage_name,content.reference_chapter,content.analysis,content.overview,content.entity_snapshot}\n"
            "上一章节大纲概述，确保能够衔接剧情:@type:章节大纲[previous:global:1].{content.overview}\n"
            "本卷的StageCount总数为：@parent.content.stage_count\n"
            "注意，请务必在@parent.content.stage_count 个阶段内将故事按分卷主线收束，并达到卷末实体快照状态:@parent.content.entity_snapshot\n"
            "该卷的写作注意事项:@type:写作指南[sibling].content.content \n"
            "接下来请你创作第 @self.content.stage_number 阶段的故事细纲。"
        )},
        "增强章节大纲": {"default_ai_context_template": (
            "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
            "volume_number: @self.content.volume_number\n"
            "当前分卷大纲完整结果: @type:增强分卷大纲[index=$current.volumeNumber].content\n"
            "当前阶段故事概述: @stage:current.overview\n"
            "当前阶段覆盖章节范围: @stage:current.reference_chapter\n"
            "之前的章节大纲: @type:增强章节大纲[sibling].{content.chapter_number,content.chapter_position,content.core_function,content.overview,content.foreshadow_items}\n"
            "请开始创作第 @self.content.chapter_number 章的大纲，保证连贯性"
        ),
        "ui_layout": {
            "sections": [
                {
                    "title": "基础信息",
                    "include": ["volume_number", "stage_number", "chapter_number", "title"],
                },
                {
                    "title": "章节功能",
                    "include": ["chapter_position", "core_function", "narrative_perspective"],
                },
                {
                    "title": "场景与角色",
                    "include": ["scene_time", "scene_location", "atmosphere", "character_motivations", "entity_list"],
                },
                {
                    "title": "情节脉络",
                    "include": ["plot_start", "plot_develop", "plot_twist", "plot_end"],
                },
                {
                    "title": "悬念与伏笔",
                    "include": ["suspense_type", "emotion_curve", "foreshadow_items", "reversal_index"],
                },
                {
                    "title": "本章简述",
                    "include": ["overview"],
                },
            ]
        }},
        "章节大纲": {"default_ai_context_template": (
            "word_view: @世界观设定.content\n"
            "volume_number: @self.content.volume_number\n"
            "volume_main_target: @type:分卷大纲[index=$current.volumeNumber].content.main_target\n"
            "volume_branch_line: @type:分卷大纲[index=$current.volumeNumber].content.branch_line\n"
            "本卷的实体action列表: @parent.content.entity_action_list\n"
            "当前阶段故事概述: @stage:current.overview\n"
            "当前阶段覆盖章节范围: @stage:current.reference_chapter\n"
            "之前的章节大纲: @type:章节大纲[sibling].{content.chapter_number,content.overview}\n"
            "请开始创作第 @self.content.chapter_number 章的大纲，保证连贯性"
        )},
        "增强章节正文": {"editor_component": "CodeMirrorEditor", "is_ai_enabled": False, "default_ai_context_template": (
            "步骤2-世界观与冲突发生器: @type:小说架构步骤[index=2].content.content\n"
            "前情摘要:@type:通用文本[index=filter:title = '前情摘要'].content.content\n"
            "组织/势力设定:@type:组织卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.influence,content.relationship}\n"
            "场景卡:@type:场景卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.function_in_story}\n"
            "当前故事阶段大纲: @parent.content.overview\n"
            "角色卡:@type:角色卡[index=filter:content.name in $self.content.entity_list].{content.name,content.character_code,content.aliases,content.role_weight,content.role_tier,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc,content.position_tracks,content.key_event_records,content.life_state,content.inventory_items,content.techniques,content.relationship_network,content.behavior_decision_pattern,content.dialogue_style_keywords,content.romance_state,content.dynamic_info}\n"
            "章节候选角色摘要:@self.content.candidate_character_summary\n"
            "章节候选角色名单:@self.content.candidate_final_character_names\n"
            "最近的章节原文，确保能够衔接剧情:@type:增强章节正文[previous:1].{content.title,content.chapter_number,content.content}\n"
            "参与者实体列表，确保生成内容只会出场这些实体:@self.content.entity_list\n"
            "请根据 @self.content.chapter_number： @self.content.title 的大纲@type:增强章节大纲[index=filter:content.volume_number = $self.content.volume_number&&content.stage_number= $self.content.stage_number&&content.chapter_number= $self.content.chapter_number].{content.chapter_position,content.core_function,content.narrative_perspective,content.scene_time,content.scene_location,content.atmosphere,content.character_motivations,content.plot_start,content.plot_develop,content.plot_twist,content.plot_end,content.suspense_type,content.emotion_curve,content.foreshadow_items,content.reversal_index,content.overview} 来创作章节正文内容，可以适当发散、设计与大纲内容不冲突的剧情来进行扩充，使得最终生成的内容字数3000字达到左右。你无需在正文中重复标题：@self.content.title \n"
            "注意，写作时必须保证结尾剧情与下一章的剧情大纲不会冲突，且不会提前涉及下一章剧情(如果存在的话):@type:增强章节大纲[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number = $self.content.chapter_number+1].{content.title,content.core_function,content.plot_start,content.overview}\n"
            "写作时请结合写作指南要求:@type:增强写作指南[index=filter:content.volume_number = $self.content.volume_number].{content.content}\n"
            )},
        "章节正文": {"editor_component": "CodeMirrorEditor", "is_ai_enabled": False, "default_ai_context_template": (
            "世界观设定: @世界观设定.content\n"
            "组织/势力设定:@type:组织卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.influence,content.relationship}\n"
            "场景卡:@type:场景卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description}\n"
            "当前故事阶段大纲: @parent.content.overview\n"
            "角色卡:@type:角色卡[index=filter:content.name in $self.content.entity_list].{content.name,content.character_code,content.aliases,content.role_weight,content.role_tier,content.role_type,content.gender,content.age,content.appearance,content.identity,content.born_scene,content.first_event,content.story_function,content.description,content.background,content.personality,content.core_drive,content.inner_conflict,content.relationship_summary,content.character_arc,content.position_tracks,content.key_event_records,content.life_state,content.inventory_items,content.techniques,content.relationship_network,content.behavior_decision_pattern,content.dialogue_style_keywords,content.romance_state,content.dynamic_info}\n"
            "最近的章节原文，确保能够衔接剧情:@type:章节正文[previous:1].{content.title,content.chapter_number,content.content}\n"
            "参与者实体列表，确保生成内容只会出场这些实体:@self.content.entity_list\n"
            "请根据 @self.content.chapter_number： @self.content.title 的大纲@type:章节大纲[index=filter:content.volume_number = $self.content.volume_number&&content.stage_number= $self.content.stage_number&&content.chapter_number= $self.content.chapter_number].{content.overview} 来创作章节正文内容，可以适当发散、设计与大纲内容不冲突的剧情来进行扩充，使得最终生成的内容字数3000字达到左右。你无需在正文中重复标题：@self.content.title \n"
            "注意，写作时必须保证结尾剧情与下一章的剧情大纲不会冲突，且不会提前涉及下一章剧情(如果存在的话):@type:章节大纲[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number = $self.content.chapter_number+1].{content.title,content.overview}\n"
            "写作时请结合写作指南要求:@type:写作指南[index=filter:content.volume_number = $self.content.volume_number].{content.content}\n"
            )},
        "小说架构": {
            "editor_component": None,
            "is_singleton": True,
            "is_ai_enabled": True,
            "default_ai_context_template": (
                "作品标签: @作品标签.content\n"
                "金手指/特殊能力: @金手指.content.special_abilities\n"
                "故事大纲: @故事大纲.content.overview"
            ),
        },
        "小说架构步骤": {
            "model_name": "Text",
            "description": "小说架构分步骤卡片",
            "editor_component": None,
            "is_singleton": False,
            "is_ai_enabled": True,
            "json_schema": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "title": "步骤序号"},
                    "step_name": {"type": "string", "title": "步骤名称"},
                    "prompt_name": {"type": "string", "title": "提示词标识"},
                    "ai_context_template": {"type": "string", "title": "AI上下文模板"},
                    "content": {"type": "string", "title": "步骤内容"}
                },
                "required": ["content"]
            },
            "default_ai_context_template": (
                "作品标签: @作品标签.content\n"
                "故事大纲: @故事大纲.content.overview\n"
                "小说架构: @小说架构.content.content"
            ),
        },
        "角色卡": {
            "default_ai_context_template": None,
            "ui_layout": {
                "sections": [
                    {
                        "title": "基础档案",
                        "description": "步骤四现在主要提供角色规划稿；这一部分由后续“步骤四规划转角色卡”工作流落成可维护的基础档案。",
                        "include": [
                            "name",
                            "character_code",
                            "aliases",
                            "role_type",
                            "gender",
                            "age",
                            "appearance",
                            "identity",
                            "first_volume",
                            "first_event",
                            "story_function",
                            "description",
                            "background",
                            "personality",
                            "core_drive",
                            "inner_conflict",
                            "relationship_summary",
                            "character_arc",
                        ],
                    },
                    {
                        "title": "权重控制",
                        "description": "初始权重由步骤四规划转角色卡工作流给出，后续章节再动态升降。",
                        "include": [
                            "role_weight",
                            "role_tier",
                            "last_appearance",
                        ],
                    },
                    {
                        "title": "状态档案",
                        "description": "这一部分主要由章节生成后的状态更新工作流逐步补充，不要求在步骤四阶段一次填满。",
                        "include": [
                            "position_tracks",
                            "key_event_records",
                            "life_state",
                            "inventory_items",
                            "techniques",
                            "relationship_network",
                            "behavior_decision_pattern",
                            "dialogue_style_keywords",
                            "romance_state",
                            "dynamic_info",
                        ],
                        "collapsed": True,
                    },
                ]
            },
        },
        "场景卡": {"default_ai_context_template": None},
        "组织卡": {"default_ai_context_template": None},
    }

    # 类型默认 AI 参数预设（不包含 llm_config_id）
    DEFAULT_AI_PARAMS = {
        "金手指": {"prompt_name": "金手指生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "一句话梗概": {"prompt_name": "一句话梗概", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "故事大纲": {"prompt_name": "一段话大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "世界观设定": {"prompt_name": "世界观设定", "temperature": 0.7, "max_tokens": 4096, "timeout": 150},
        "核心蓝图": {"prompt_name": "核心蓝图", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "增强核心蓝图": {"prompt_name": "增强核心蓝图", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "增强分卷大纲": {"prompt_name": "增强分卷大纲-首卷", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "分卷大纲": {"prompt_name": "分卷大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "增强写作指南": {"prompt_name": "写作指南", "temperature": 0.6, "max_tokens": 8192, "timeout": 120},
        "写作指南": {"prompt_name": "写作指南", "temperature": 0.6, "max_tokens": 8192, "timeout": 120},
        "增强阶段大纲": {"prompt_name": "增强阶段大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "增强章节拆解": {"prompt_name": "增强章节拆解", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "阶段大纲": {"prompt_name": "阶段大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "增强章节大纲": {"prompt_name": "增强章节大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章节大纲": {"prompt_name": "章节大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "增强章节正文": {"prompt_name": "增强章节正文草稿-续写版", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章节正文": {"prompt_name": "内容生成", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "小说架构": {"prompt_name": "一段话大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "小说架构步骤": {"prompt_name": "ANG.M0.architecture_step1_mission", "temperature": 0.7, "max_tokens": 4096, "timeout": 120},
        "角色卡": {"prompt_name": "角色动态信息提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "场景卡": {"prompt_name": "内容生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "组织卡": {"prompt_name": "关系提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
    }

    # 类型名称到内置响应模型的映射（直接用于生成 json_schema）
    TYPE_TO_MODEL_KEY = {
        "通用文本" : "Text",
        "作品标签": "Tags",
        "金手指": "SpecialAbilityResponse",
        "一句话梗概": "OneSentence",
        "故事大纲": "ParagraphOverview",
        "世界观设定": "WorldBuilding",
        "核心蓝图": "Blueprint",
        "增强核心蓝图": "Blueprint",
        "增强分卷大纲": "EnhancedVolumeOutline",
        "分卷大纲": "VolumeOutline",
        "增强写作指南": "WritingGuide",
        "写作指南": "WritingGuide",
        "增强阶段大纲": "EnhancedStageLine",
        "增强章节拆解": "EnhancedChapterBlueprint",
        "阶段大纲": "StageLine",
        "增强章节大纲": "EnhancedChapterOutline",
        "章节大纲": "ChapterOutline",
        "增强章节正文": "Chapter",
        "章节正文": "Chapter",
        "小说架构": "Text",
        "小说架构步骤": "Text",
        "角色卡": "CharacterCard",
        "场景卡": "SceneCard",
        "组织卡": "OrganizationCard",
    }

    existing_types = session.exec(select(CardType)).all()
    existing_type_names = {ct.name for ct in existing_types}
    existing_type_by_name = {ct.name: ct for ct in existing_types}

    # 默认 llm_config_id：取第一个可用 LLM 配置（若存在）
    default_llm = session.exec(select(LLMConfig)).first()

    for name, details in default_types.items():
        if name not in existing_type_names:
            # 直接在卡片类型上存储结构（json_schema）
            schema = _resolve_card_type_schema(name, details, TYPE_TO_MODEL_KEY)
            # AI 参数预设（llm_config_id 由前端选择，不在此指定）
            ai_params = DEFAULT_AI_PARAMS.get(name)
            if ai_params is not None:
                # 若存在可用的默认 LLM，则写入其 ID；避免写 0 导致前端无法识别
                ai_params = {**ai_params, "llm_config_id": (default_llm.id if default_llm else None)}
            card_type = CardType(
                name=name,
                model_name=TYPE_TO_MODEL_KEY.get(name, name),
                description=details.get("description", f"{name}的默认卡片类型"),
                json_schema=schema,
                ai_params=ai_params,
                editor_component=details.get("editor_component"),
                is_ai_enabled=details.get("is_ai_enabled", True),
                is_singleton=details.get("is_singleton", False),
                default_ai_context_template=details.get("default_ai_context_template"),
                ui_layout=details.get("ui_layout"),
                built_in=True,
            )
            session.add(card_type)
            logger.info(f"Created default card type: {name}")
        else:
            # 增量更新：刷新类型结构与元信息
            ct = existing_type_by_name[name]
            schema = _resolve_card_type_schema(name, details, TYPE_TO_MODEL_KEY)
            if schema is not None:
                ct.json_schema = schema
            # 若缺失 ai_params 则按预设填充（不覆盖用户已设置的）
            if getattr(ct, 'ai_params', None) is None:
                preset = DEFAULT_AI_PARAMS.get(name)
                if preset is not None:
                    ct.ai_params = {**preset, "llm_config_id": (default_llm.id if default_llm else None)}
            # 若缺失 model_name 则按映射补齐
            if not getattr(ct, 'model_name', None):
                ct.model_name = TYPE_TO_MODEL_KEY.get(name, name)
            ct.editor_component = details.get("editor_component")
            ct.is_ai_enabled = details.get("is_ai_enabled", True)
            ct.is_singleton = details.get("is_singleton", False)
            ct.description = details.get("description", f"{name}的默认卡片类型")
            ct.default_ai_context_template = details.get("default_ai_context_template")
            ct.ui_layout = details.get("ui_layout")
            ct.built_in = True

    # 自动同步：将未映射到默认卡片类型的内置响应模型写入 CardType
    # 目的：避免新增响应模型后，前端“设置-卡片类型”看不到对应模型定义。
    # mapped_model_keys = set(TYPE_TO_MODEL_KEY.values())
    # for model_key, model_class in RESPONSE_MODEL_MAP.items():
    #     # 已由 default_types 显式管理的模型，不重复创建
    #     if model_key in mapped_model_keys:
    #         continue

    #     existing = next(
    #         (
    #             ct for ct in existing_types
    #             if ct.name == model_key or ct.model_name == model_key
    #         ),
    #         None
    #     )

    #     schema = None
    #     try:
    #         schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
    #     except Exception:
    #         schema = None

    #     if existing:
    #         # 仅对内置类型做增量修复，避免覆盖用户自定义类型
    #         if getattr(existing, "built_in", False):
    #             existing.model_name = model_key
    #             if schema is not None:
    #                 existing.json_schema = schema
    #             if not (existing.description or "").strip():
    #                 existing.description = f"{model_key}（内置响应模型）"
    #         continue

    #     auto_type = CardType(
    #         name=model_key,
    #         model_name=model_key,
    #         description=f"{model_key}（内置响应模型）",
    #         json_schema=schema,
    #         ai_params=None,
    #         editor_component=None,
    #         is_ai_enabled=False,
    #         is_singleton=False,
    #         default_ai_context_template=None,
    #         built_in=True,
    #     )
    #     session.add(auto_type)
    #     existing_types.append(auto_type)
    #     existing_type_names.add(model_key)
    #     existing_type_by_name[model_key] = auto_type
    #     logger.info(f"Created builtin response model card type: {model_key}")

    session.commit()
    logger.info("Default card types committed.")
