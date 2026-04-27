from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.ai import ContinuationRequest, ContinuationResponse, GeneralAIRequest
from app.schemas.response import ApiResponse
from app.services import prompt_service, llm_config_service

from app.services.schema_service import compose_full_schema
from app.utils.stream_utils import wrap_sse_stream
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from typing import Type, Dict, Any, List
import json
import re

from app.db.models import Card, CardType
from app.utils.schema_utils import filter_schema_for_ai

# 引入知识库
from app.services.knowledge_service import KnowledgeService
from app.schemas.entity import DYNAMIC_INFO_TYPES
from app.schemas import entity as entity_schemas
from app.core import emit_event
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.generation.continuation_context_service import enrich_continuation_context_info
from app.services.ai.generation.instruction_validator import validate_instruction, apply_instruction
from app.services.ai.generation.instruction_generator import generate_instruction_stream
from app.services.ai.generation.prompt_builder import build_instruction_system_prompt
from app.schemas.instruction import InstructionGenerateRequest
from app.schemas.wizard import Tags as _Tags
from loguru import logger

router = APIRouter()


def _get_llm_service():
    # 延迟导入，避免应用启动阶段就拉起重型模型依赖链。
    from app.services.ai.core import llm_service

    return llm_service

# 响应模型映射表（内置）
from app.schemas.response_registry import RESPONSE_MODEL_MAP

_ARCH_LOCAL_PROMPT_NAMES = {
    "步骤一-分卷使命宣言",
    "步骤二-世界观与冲突发生器",
    "步骤三-情节线与推进机制",
    "步骤四-核心角色规划",
    "步骤五-叙事风格与文本策略",
}
_ARCH_STEP_TEMPLATE_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_GENERIC_TEMPLATE_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FACTS_SECTION_PATTERN = re.compile(r"【事实子图】\n(?P<content>.*?)(?=(?:\n\n【)|\Z)", flags=re.S)
_REFERENCE_CONTEXT_SECTION_PATTERN = re.compile(r"【引用上下文】\n(?P<content>.*?)(?=(?:\n\n【)|\Z)", flags=re.S)
_EXISTING_CHAPTER_SECTION_PATTERN = re.compile(r"【已有章节内容】\n(?P<content>.*?)(?=(?:\n\n【)|\Z)", flags=re.S)
_INSTRUCTION_SECTION_PATTERN = re.compile(r"【指令】(?P<content>.*)$", flags=re.S)

_ARCH_THEME_JSON_PATTERN = re.compile(r'"theme"\s*:\s*"([^\"]+)"', flags=re.IGNORECASE)
_ARCH_THEME_TEXT_PATTERN = re.compile(r"主题\s*[:：]\s*([^\n,，]+)", flags=re.IGNORECASE)
_ARCH_VOLUME_COUNT_JSON_PATTERN = re.compile(r'"volume_count"\s*:\s*(\d+)', flags=re.IGNORECASE)
_ARCH_VOLUME_COUNT_TEXT_PATTERN = re.compile(r"总卷数\s*[:：]\s*(\d+)", flags=re.IGNORECASE)
_ARCH_TOTAL_CHAPTERS_JSON_PATTERN = re.compile(r'"total_chapters"\s*:\s*(\d+)', flags=re.IGNORECASE)
_ARCH_TOTAL_CHAPTERS_TEXT_PATTERN = re.compile(r"总章数\s*[:：]\s*(\d+)", flags=re.IGNORECASE)
_ARCH_CHAPTER_WORD_COUNT_JSON_PATTERN = re.compile(r'"chapter_word_count"\s*:\s*(\d+)', flags=re.IGNORECASE)
_ARCH_CHAPTER_WORD_COUNT_TEXT_PATTERN = re.compile(r"每章字数\s*[:：]\s*(\d+)", flags=re.IGNORECASE)
_ARCH_OVERVIEW_JSON_PATTERN = re.compile(r'"overview"\s*:\s*"([^\"]+)"', flags=re.IGNORECASE)
_ARCH_OVERVIEW_TEXT_PATTERN = re.compile(r"(?:故事大纲|核心主题|主题)\s*[:：]\s*([^\n]+)", flags=re.IGNORECASE)
_ARCH_TAGS_LINE_PATTERN = re.compile(r"作品标签\s*[:：]\s*(\{[\s\S]*?\})", flags=re.IGNORECASE)
_ARCH_STEP_RESULT_BLOCK_PATTERN = re.compile(
    r"^\s*步骤\s*(?P<step>[1-5一二三四五])\s*结果\s*[:：]\s*(?P<value>[\s\S]*?)(?=^\s*步骤\s*(?:[1-5一二三四五])\s*结果\s*[:：]|\Z)",
    flags=re.IGNORECASE | re.MULTILINE,
)
_ARCH_STEP_NUM_MAP: Dict[str, str] = {
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
}

_ARCH_CURRENT_DATA_ALIASES: Dict[str, tuple[str, ...]] = {
    "genre": ("genre", "theme"),
    "topic": ("topic", "theme", "overview"),
    "Total_volume_number": ("Total_volume_number", "volume_count"),
    "number_of_chapters": ("number_of_chapters", "total_chapters"),
    "word_number": ("word_number", "chapter_word_count"),
    "user_guidance": ("user_guidance", "guide", "writing_guide", "instruction"),
    "step1_result": ("step1_result",),
    "step2_result": ("step2_result",),
    "step3_result": ("step3_result",),
    "step4_result": ("step4_result",),
}


_ARCH_VAR_SOURCE_LABELS: Dict[str, Dict[str, str]] = {
    "genre": {
        "context_info_json": "context_info.theme",
        "context_info_text": "context_info(主题)",
        "current_data": "current_data.genre/theme",
    },
    "Total_volume_number": {
        "context_info_json": "context_info.volume_count",
        "context_info_text": "context_info(总卷数)",
        "current_data": "current_data.Total_volume_number/volume_count",
    },
    "number_of_chapters": {
        "context_info_json": "context_info.total_chapters",
        "context_info_text": "context_info(总章数)",
        "current_data": "current_data.number_of_chapters/total_chapters",
    },
    "word_number": {
        "context_info_json": "context_info.chapter_word_count",
        "context_info_text": "context_info(每章字数)",
        "current_data": "current_data.word_number/chapter_word_count",
    },
    "topic": {
        "context_info_json": "context_info.theme/context_info.overview",
        "context_info_text": "context_info(主题/故事大纲)",
        "current_data": "current_data.topic/theme/overview",
    },
    "user_guidance": {
        "user_prompt": "request.user_prompt",
        "current_data": "current_data.user_guidance/guide/writing_guide/instruction",
    },
    "step1_result": {
        "context_info_text": "context_info(步骤1结果)",
        "current_data": "current_data.step1_result",
    },
    "step2_result": {
        "context_info_text": "context_info(步骤2结果)",
        "current_data": "current_data.step2_result",
    },
    "step3_result": {
        "context_info_text": "context_info(步骤3结果)",
        "current_data": "current_data.step3_result",
    },
    "step4_result": {
        "context_info_text": "context_info(步骤4结果)",
        "current_data": "current_data.step4_result",
    },
}


def _build_arch_missing_detail(missing: List[str], sources: Dict[str, str], required_vars: set[str]) -> str:
    lines: List[str] = []
    for var in sorted(missing):
        source_meta = _ARCH_VAR_SOURCE_LABELS.get(var, {})
        parts: List[str] = []
        for src_key in ("context_info_json", "context_info_text", "user_prompt", "current_data"):
            label = source_meta.get(src_key)
            if not label:
                continue
            state = "命中" if sources.get(f"{var}:{src_key}") else "未命中"
            parts.append(f"{label}={state}")
        if not parts:
            parts.append("无可用提取规则")
        lines.append(f"- {var}: " + "；".join(parts))

    diagnostic = [
        f"架构提示词变量缺失: {', '.join(sorted(missing))}",
        f"required_vars={sorted(required_vars)}",
        "missing_breakdown:",
        *lines,
        "请检查变量传递链路：前端resolvedContext -> request.context_info/current_data -> 后端提取规则。",
    ]
    return "\n".join(diagnostic)


def _extract_first(compiled_pattern: re.Pattern[str], text: str) -> str | None:
    match = compiled_pattern.search(text)
    if not match:
        return None
    value = (match.group(1) or "").strip()
    return value or None


def _extract_architecture_prompt_variables(
    context_info: str | None,
    user_prompt: str | None,
    current_data: Dict[str, Any] | None = None,
) -> tuple[Dict[str, str], Dict[str, str]]:
    text = context_info if isinstance(context_info, str) else ""

    variables: Dict[str, str] = {}
    sources: Dict[str, str] = {}

    theme_by_json = _extract_first(_ARCH_THEME_JSON_PATTERN, text)
    theme_by_text = _extract_first(_ARCH_THEME_TEXT_PATTERN, text)
    theme = theme_by_json or theme_by_text
    if theme:
        variables["genre"] = theme
        variables["topic"] = theme
        if theme_by_json:
            sources["genre:context_info_json"] = theme_by_json
            sources["topic:context_info_json"] = theme_by_json
        if theme_by_text:
            sources["genre:context_info_text"] = theme_by_text
            sources["topic:context_info_text"] = theme_by_text

    volume_count_by_json = _extract_first(_ARCH_VOLUME_COUNT_JSON_PATTERN, text)
    volume_count_by_text = _extract_first(_ARCH_VOLUME_COUNT_TEXT_PATTERN, text)
    volume_count = volume_count_by_json or volume_count_by_text
    if volume_count:
        variables["Total_volume_number"] = volume_count
        if volume_count_by_json:
            sources["Total_volume_number:context_info_json"] = volume_count_by_json
        if volume_count_by_text:
            sources["Total_volume_number:context_info_text"] = volume_count_by_text

    total_chapters_by_json = _extract_first(_ARCH_TOTAL_CHAPTERS_JSON_PATTERN, text)
    total_chapters_by_text = _extract_first(_ARCH_TOTAL_CHAPTERS_TEXT_PATTERN, text)
    total_chapters = total_chapters_by_json or total_chapters_by_text
    if total_chapters:
        variables["number_of_chapters"] = total_chapters
        if total_chapters_by_json:
            sources["number_of_chapters:context_info_json"] = total_chapters_by_json
        if total_chapters_by_text:
            sources["number_of_chapters:context_info_text"] = total_chapters_by_text

    chapter_word_count_by_json = _extract_first(_ARCH_CHAPTER_WORD_COUNT_JSON_PATTERN, text)
    chapter_word_count_by_text = _extract_first(_ARCH_CHAPTER_WORD_COUNT_TEXT_PATTERN, text)
    chapter_word_count = chapter_word_count_by_json or chapter_word_count_by_text
    if chapter_word_count:
        variables["word_number"] = chapter_word_count
        if chapter_word_count_by_json:
            sources["word_number:context_info_json"] = chapter_word_count_by_json
        if chapter_word_count_by_text:
            sources["word_number:context_info_text"] = chapter_word_count_by_text

    overview_by_json = _extract_first(_ARCH_OVERVIEW_JSON_PATTERN, text)
    overview_by_text = _extract_first(_ARCH_OVERVIEW_TEXT_PATTERN, text)
    overview = overview_by_json or overview_by_text
    if overview and "topic" not in variables:
        variables["topic"] = overview
        if overview_by_json:
            sources["topic:context_info_json"] = overview_by_json
        if overview_by_text:
            sources["topic:context_info_text"] = overview_by_text

    tags_json_text = _extract_first(_ARCH_TAGS_LINE_PATTERN, text)
    if tags_json_text:
        try:
            tags_payload = json.loads(tags_json_text)
            if not str(variables.get("genre", "")).strip():
                genre_from_tags = str(tags_payload.get("theme") or "").strip()
                if genre_from_tags:
                    variables["genre"] = genre_from_tags
                    sources["genre:context_info_json"] = genre_from_tags
            if not str(variables.get("topic", "")).strip():
                topic_from_tags = str(tags_payload.get("theme") or tags_payload.get("overview") or "").strip()
                if topic_from_tags:
                    variables["topic"] = topic_from_tags
                    sources["topic:context_info_json"] = topic_from_tags
            if not str(variables.get("Total_volume_number", "")).strip():
                volume_from_tags = str(tags_payload.get("volume_count") or tags_payload.get("Total_volume_number") or "").strip()
                if volume_from_tags:
                    variables["Total_volume_number"] = volume_from_tags
                    sources["Total_volume_number:context_info_json"] = volume_from_tags
            if not str(variables.get("number_of_chapters", "")).strip():
                chapters_from_tags = str(tags_payload.get("total_chapters") or tags_payload.get("number_of_chapters") or "").strip()
                if chapters_from_tags:
                    variables["number_of_chapters"] = chapters_from_tags
                    sources["number_of_chapters:context_info_json"] = chapters_from_tags
            if not str(variables.get("word_number", "")).strip():
                words_from_tags = str(tags_payload.get("chapter_word_count") or tags_payload.get("word_number") or "").strip()
                if words_from_tags:
                    variables["word_number"] = words_from_tags
                    sources["word_number:context_info_json"] = words_from_tags
        except Exception:
            pass

    for match in _ARCH_STEP_RESULT_BLOCK_PATTERN.finditer(text):
        raw_step = (match.group("step") or "").strip()
        step_num = _ARCH_STEP_NUM_MAP.get(raw_step)
        if step_num not in {"1", "2", "3", "4"}:
            continue

        step_value = (match.group("value") or "").strip()
        if not step_value:
            continue

        var_name = f"step{step_num}_result"
        variables[var_name] = step_value
        sources[f"{var_name}:context_info_text"] = step_value

    guidance = (user_prompt or "").strip()
    if guidance:
        variables["user_guidance"] = guidance
        sources["user_guidance:user_prompt"] = guidance

    if isinstance(current_data, dict):
        for canonical_key, alias_keys in _ARCH_CURRENT_DATA_ALIASES.items():
            for alias_key in alias_keys:
                val = current_data.get(alias_key)
                if val is None:
                    continue
                val_str = str(val).strip()
                if not val_str:
                    continue
                variables[canonical_key] = val_str
                sources[f"{canonical_key}:current_data"] = val_str
                break

    return variables, sources


def _render_architecture_prompt_or_raise(
    prompt_text: str,
    context_info: str | None,
    user_prompt: str | None,
    current_data: Dict[str, Any] | None = None,
) -> str:
    required_vars = set(_ARCH_STEP_TEMPLATE_VAR_PATTERN.findall(prompt_text or ""))
    if not required_vars:
        return prompt_text

    variables, sources = _extract_architecture_prompt_variables(context_info, user_prompt, current_data)

    missing = [name for name in sorted(required_vars) if not str(variables.get(name, "")).strip()]
    if missing:
        detail = _build_arch_missing_detail(missing, sources, required_vars)
        logger.error(f"[卡片生成][变量缺失诊断] {detail}")
        raise ValueError(detail)

    return prompt_service.render_prompt(prompt_text, variables)


def is_architecture_prompt_template(prompt_template: str | None) -> bool:
    prompt_name = str(prompt_template or "").strip()
    if not prompt_name:
        return False
    return prompt_name in _ARCH_LOCAL_PROMPT_NAMES


def _build_generic_prompt_variables(
    context_info: str | None,
    user_prompt: str | None,
    current_data: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    context_text = (context_info or "").strip()
    current = current_data if isinstance(current_data, dict) else {}
    reference_match = _REFERENCE_CONTEXT_SECTION_PATTERN.search(context_text)
    reference_text = (reference_match.group("content") or "").strip() if reference_match else context_text

    existing_match = _EXISTING_CHAPTER_SECTION_PATTERN.search(context_text)
    existing_text = (existing_match.group("content") or "").strip() if existing_match else str(current.get("content") or "").strip()

    facts_match = _FACTS_SECTION_PATTERN.search(context_text)
    facts_text = (facts_match.group("content") or "").strip() if facts_match else ""
    if not facts_text:
        facts_text = "关键事实：暂无（尚未收集）。"

    instruction_match = _INSTRUCTION_SECTION_PATTERN.search(context_text)
    instruction_text = (instruction_match.group("content") or "").strip() if instruction_match else ""
    if not instruction_text:
        instruction_text = (user_prompt or "").strip() or "请开始创作。直接输出结果。"

    variables: Dict[str, str] = {
        "context_info": context_text,
        "reference_context": reference_text,
        "existing_chapter_text": existing_text,
        "facts_subgraph": facts_text,
        "instruction": instruction_text,
        "user_prompt": instruction_text,
        "current_data_json": json.dumps(current, ensure_ascii=False, indent=2),
    }

    for key, value in current.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            variables[key] = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            variables[key] = str(value)

    return variables


def _render_generic_prompt_if_needed(
    prompt_text: str,
    context_info: str | None,
    user_prompt: str | None,
    current_data: Dict[str, Any] | None = None,
) -> str:
    required_vars = set(_GENERIC_TEMPLATE_VAR_PATTERN.findall(prompt_text or ""))
    if not required_vars:
        return prompt_text

    variables = _build_generic_prompt_variables(context_info, user_prompt, current_data)
    missing = [name for name in sorted(required_vars) if name not in variables]
    if missing:
        raise ValueError(f"渲染提示词失败：缺少变量 {', '.join(missing)}")

    return prompt_service.render_prompt(prompt_text, variables)


def _assert_no_unresolved_template_vars(prompt_text: str, scene: str) -> None:
    unresolved = sorted(set(_GENERIC_TEMPLATE_VAR_PATTERN.findall(prompt_text or "")))
    if unresolved:
        detail = f"{scene} 仍存在未替换占位符: {', '.join(unresolved)}"
        logger.error(detail)
        raise ValueError(detail)


@router.get("/schemas", response_model=Dict[str, Any], summary="获取所有输出模型的JSON Schema（仅内置）")
def get_all_schemas(session: Session = Depends(get_session)):
    """返回内置 pydantic 模型的 schema 聚合，键为模型名称。"""
    all_definitions: Dict[str, Any] = {}

    # 1) 内置 pydantic 模型
    for name, model_class in RESPONSE_MODEL_MAP.items():
        schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
        if '$defs' in schema:
            all_definitions.update(schema['$defs'])
            del schema['$defs']
        all_definitions[name] = schema

    # 动态修复 CharacterCard.dynamic_info 的属性
    try:
        cc = all_definitions.get('CharacterCard')
        if isinstance(cc, dict):
            props = (cc.get('properties') or {})
            if 'dynamic_info' in props:
                item_schema = {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "info": {"type": "string"},
                        "weight": {"type": "number"}
                    },
                    "required": ["id", "info", "weight"]
                }
                enum_values = DYNAMIC_INFO_TYPES
                props['dynamic_info'] = {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        ev: {"type": "array", "items": item_schema} for ev in enum_values
                    },
                    "description": "角色动态信息，按类别分组的数组（键为中文枚举值）"
                }
                cc['properties'] = props
                all_definitions['CharacterCard'] = cc
    except Exception:
        pass

    # 2) 注入 entity 动态信息相关模型（用于前端解析 $ref: DynamicInfo 等）
    try:
        entity_models = [
            entity_schemas.DynamicInfoItem,
            entity_schemas.DynamicInfo,
            entity_schemas.UpdateDynamicInfo,
        ]
        for mdl in entity_models:
            sch = mdl.model_json_schema(ref_template="#/$defs/{model}")
            if '$defs' in sch:
                all_definitions.update(sch['$defs'])
                del sch['$defs']
            all_definitions[mdl.__name__] = sch
    except Exception:
        pass

    return all_definitions

@router.get("/content-models", response_model=List[str], summary="获取所有可用输出模型名称")
def get_content_models(session: Session = Depends(get_session)):
    # 仅返回内置模型名称
    return list(RESPONSE_MODEL_MAP.keys())


@router.get("/config-options", summary="获取AI生成配置选项")
async def get_ai_config_options(session: Session = Depends(get_session)):
    """获取AI生成时可用的配置选项"""
    try:
        # 获取所有LLM配置
        llm_configs = llm_config_service.get_llm_configs(session)
        # 获取所有提示词
        prompts = prompt_service.get_prompts(session)
        # 响应模型仅内置
        response_models = get_content_models(session)
        return ApiResponse(data={
            "llm_configs": [{"id": config.id, "display_name": config.display_name or config.model_name} for config in llm_configs],
            "prompts": [{"id": prompt.id, "name": prompt.name, "description": prompt.description, "built_in": getattr(prompt, 'built_in', False)} for prompt in prompts],
            "available_tasks": [],
            "response_models": response_models
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置选项失败: {str(e)}")

@router.get("/prompts/render", summary="渲染并注入知识库的提示词模板")
async def render_prompt_with_knowledge(name: str, session: Session = Depends(get_session)):
    p = prompt_service.get_prompt_by_name(session, name)
    if not p or not p.template:
        raise HTTPException(status_code=404, detail=f"未找到提示词: {name}")
    try:
        text = prompt_service.inject_knowledge(session, str(p.template))
        return ApiResponse(data={"text": text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"渲染失败: {e}")

@router.post("/generate", summary="通用AI生成接口")
async def generate_ai_content(
    request: GeneralAIRequest = Body(...),
    session: Session = Depends(get_session),
):
    """
    通用的AI内容生成端点：前端必须提供 response_model_schema。
    """
    # 基本参数校验：input/llm_config_id/prompt_name/response_model_schema 必填
    if not request.input or not request.llm_config_id or not request.prompt_name:
        raise HTTPException(status_code=400, detail="缺少必要的生成参数: input, llm_config_id 或 prompt_name")
    if request.response_model_schema is None:
        raise HTTPException(status_code=400, detail="请提供 response_model_schema")

    # 解析响应模型（仅动态 schema）
    try:
        # 完整 Schema 组装：内置 defs + CardType defs
        composed = compose_full_schema(session, request.response_model_schema)
        # 基于 x-ai-exclude 过滤字段
        schema_for_prompt = filter_schema_for_ai(composed) if request.exclude_ai_fields else composed
        # 动态构建 Pydantic 模型
        resp_model = build_model_from_json_schema('DynamicResponseModel', schema_for_prompt or composed)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"动态创建模型失败: {e}")

    # 获取提示词
    prompt = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not prompt:
        raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")

    # 注入知识库
    prompt_template = prompt_service.inject_knowledge(session, prompt.template or '')
    input_text = str((request.input or {}).get('input_text') or '')
    prompt_template = _render_generic_prompt_if_needed(
        prompt_template,
        input_text,
        input_text,
        request.input,
    )
    _assert_no_unresolved_template_vars(prompt_template, f"/api/ai/generate prompt={request.prompt_name}")

    # System Prompt：携带 JSON Schema
    schema_json = json.dumps(schema_for_prompt if schema_for_prompt is not None else resp_model.model_json_schema(), indent=2, ensure_ascii=False)
    system_prompt = (
        f"{prompt_template}\n\n"
        f"```json\n{schema_json}\n```"
    )

    user_prompt = input_text
    deps_str = request.deps or ""

    try:
        result = await _get_llm_service().generate_structured(
            session=session,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            output_type=resp_model,
            llm_config_id=request.llm_config_id, 
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            timeout=request.timeout,
            deps=deps_str,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 触发 OnGenerateFinish（若能定位 card）
    card: Card | None = None
    try:
        card_id = None
        if isinstance(request.input, dict):
            card_id = request.input.get('card_id')
        if card_id:
            card = session.get(Card, int(card_id))
        project_id = None
        if isinstance(request.input, dict):
            project_id = request.input.get('project_id') or (card.project_id if card else None)
        emit_event("generate.finished", {
            "session": session,
            "card": card,
            "project_id": int(project_id) if project_id else (card.project_id if card else None)
        })
    except Exception:
        pass
    return ApiResponse(data=result)

@router.post("/generate/continuation", 
             response_model=ApiResponse[ContinuationResponse], 
             summary="续写正文",
             responses={
                 200: {
                     "content": {
                         "application/json": {},
                         "text/event-stream": {}
                     },
                     "description": "成功返回续写结果或事件流"
                 }
             })
async def generate_continuation(
    request: ContinuationRequest,
    session: Session = Depends(get_session),
):
    try:
        # 强制从 prompt_name 读取模板作为 system prompt
        if not request.prompt_name:
            raise HTTPException(status_code=400, detail="续写必须指定 prompt_name")
        p = prompt_service.get_prompt_by_name(session, request.prompt_name)
        if not p or not p.template:
            raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")
        # 注入知识库
        system_prompt = prompt_service.inject_knowledge(session, str(p.template))


        request.context_info = enrich_continuation_context_info(session, request)
        system_prompt = _render_generic_prompt_if_needed(
            system_prompt,
            request.context_info,
            "",
            {
                "content": request.previous_content or "",
                "existing_word_count": request.existing_word_count,
                "chapter_number": request.chapter_number,
                "volume_number": request.volume_number,
                "project_id": request.project_id,
                "participants": request.participants or [],
            },
        )
        _assert_no_unresolved_template_vars(
            system_prompt,
            f"/api/ai/generate/continuation prompt={request.prompt_name}",
        )
        

        if request.stream:
            # 先做一次配额预检，避免流式过程中才抛错
            ok, reason = llm_config_service.can_consume(session, request.llm_config_id, 0, 0, 1)
            if not ok:
                raise HTTPException(status_code=400, detail=f"LLM 配额不足：{reason}")
            async def _stream_and_trigger():
                async for chunk in _get_llm_service().generate_continuation_streaming(session, request, system_prompt):
                    yield chunk
                try:
                    # 续写结束后触发
                    emit_event("generate.finished", {
                        "session": session,
                        "card": None,
                        "project_id": request.project_id
                    })
                except Exception:
                    pass
            return StreamingResponse(wrap_sse_stream(_stream_and_trigger()), media_type="text/event-stream")
        else:
            # 非流式模式：收集所有内容
            content_parts = []
            async for chunk in _get_llm_service().generate_continuation_streaming(session, request, system_prompt):
                content_parts.append(chunk)
            result = "".join(content_parts)
            try:
                emit_event("generate.finished", {
                    "session": session,
                    "card": None,
                    "project_id": request.project_id
                })
            except Exception:
                pass
            return ApiResponse(data=ContinuationResponse(content=result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/models/tags", response_model=_Tags, summary="导出 Tags 模型（用于类型生成）")
def export_tags_model():
    return _Tags()


# ==================== 指令流生成端点 ====================


@router.post("/generate/stream", summary="指令流式生成端点")
async def generate_with_instruction_stream(
    request: InstructionGenerateRequest,
    session: Session = Depends(get_session),
):
    """
    指令流式生成端点
    
    实时返回 LLM 生成的指令流，前端逐条执行并更新 UI。
    支持自动校验和修复，用户可以在生成过程中与 AI 交互。
    """
    async def event_generator():
        try:
            # 1. 组装完整 Schema（注入 $defs）
            full_schema = compose_full_schema(session, request.response_model_schema)
            
            # 为小说架构步骤自动补齐用户提示，避免触发提示词里的“请补充基础输入”兜底文案
            effective_user_prompt = (request.user_prompt or "").strip()
            if is_architecture_prompt_template(request.prompt_template):
                if not effective_user_prompt:
                    effective_user_prompt = "请基于已有上下文直接生成当前架构步骤，不要输出‘请补充基础输入’或提问，直接给出可保存结果。"
                    logger.info(f"[卡片生成] 已为 {request.prompt_template} 自动注入默认用户提示")

            # 2. 加载卡片任务提示词（如果提供了名称）
            card_prompt_content = None
            if request.prompt_template:
                prompt = prompt_service.get_prompt_by_name(session, request.prompt_template)
                if prompt and prompt.template:
                    card_prompt_content = prompt_service.inject_knowledge(session, str(prompt.template))
                    if is_architecture_prompt_template(request.prompt_template):
                        card_prompt_content = _render_architecture_prompt_or_raise(
                            card_prompt_content,
                            request.context_info,
                            effective_user_prompt,
                            request.current_data,
                        )
                    else:
                        card_prompt_content = _render_generic_prompt_if_needed(
                            card_prompt_content,
                            request.context_info,
                            effective_user_prompt,
                            request.current_data,
                        )
                        _assert_no_unresolved_template_vars(
                            card_prompt_content,
                            f"/api/ai/generate/stream prompt={request.prompt_template}",
                        )
                    logger.info(f"[卡片生成] 加载提示词模板: {request.prompt_template}, 长度: {len(card_prompt_content)}")
                else:
                    logger.warning(f"[卡片生成] 未找到提示词模板: {request.prompt_template}")

            # 3. 构建 System Prompt（卡片任务 + 指令规范 + Schema）
            system_prompt = build_instruction_system_prompt(
                session=session,
                schema=full_schema,
                card_prompt=card_prompt_content
            )
            
            # 4. 调用指令流生成服务
            async for event in generate_instruction_stream(
                session=session,
                llm_config_id=request.llm_config_id,
                user_prompt=effective_user_prompt,
                system_prompt=system_prompt,
                schema=full_schema,
                current_data=request.current_data,
                conversation_context=request.conversation_context,
                context_info=request.context_info,
                temperature=request.temperature or 0.7,
                max_tokens=request.max_tokens,
                timeout=request.timeout or 150
            ):
                # 5. 发送 SSE 事件（格式：data: {json}\n\n）
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            logger.error(f"指令流生成失败: {e}", exc_info=True)
            error_event = {
                "type": "error",
                "text": f"生成失败: {str(e)}"
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    ) 
