"""表达式 helper 函数库（精简版）

说明：
- 仅保留非 Python 内置、且在工作流中有明确价值的 helper。
- 与内置同名的能力（如 len/str/int/range/sum 等）统一由 `builtins.py` 提供。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from app.services.foreshadow_parser import (
    build_foreshadow_register_payload,
    build_foreshadow_processing_vars,
    build_open_foreshadow_ledger,
    extract_foreshadow_ids,
    foreshadow_lifecycle_gate,
    normalize_foreshadow_plan,
)
from app.services.chapter_candidate_character_service import (
    build_candidate_character_content_update,
)
from app.services.chapter_postprocess_service import build_character_state_update_from_summary


_HELPER_REGISTRY: Dict[str, Callable[..., Any]] = {}
_HELPER_META_REGISTRY: Dict[str, "HelperMeta"] = {}


@dataclass(frozen=True)
class HelperMeta:
    """helper 元信息（用于自动生成 AI 说明）"""

    summary: str
    scenario: str
    priority: int = 50
    example: str = ""


def register_function(
    name: str,
    *,
    summary: str = "",
    scenario: str = "",
    priority: int = 50,
    example: str = "",
):
    """注册 helper 的装饰器（保留扩展能力）"""

    def decorator(func: Callable[..., Any]):
        _HELPER_REGISTRY[name] = func
        _HELPER_META_REGISTRY[name] = HelperMeta(
            summary=summary or ((func.__doc__ or "").strip()),
            scenario=scenario or "通用",
            priority=priority,
            example=example,
        )
        return func

    return decorator


def get_builtin_functions() -> Dict[str, Callable[..., Any]]:
    """获取所有 helper（返回副本）"""
    return _HELPER_REGISTRY.copy()


def get_helper_metadata() -> Dict[str, HelperMeta]:
    """获取 helper 元信息（返回副本）"""
    return _HELPER_META_REGISTRY.copy()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _get_card_content(card: Any) -> Dict[str, Any]:
    if isinstance(card, dict):
        content = card.get("content") or {}
        if isinstance(content, dict):
            return content
    return {}


def _get_character_standard_name(card: Any) -> str:
    content = _get_card_content(card)
    return str(content.get("name") or (card.get("title") if isinstance(card, dict) else "") or "").strip()


def _find_last_position_text(content: Dict[str, Any]) -> str:
    tracks = content.get("position_tracks") or []
    if not isinstance(tracks, list) or not tracks:
        return ""
    item = tracks[-1] or {}
    location = str(item.get("location") or "").strip()
    chapter_number = str(item.get("chapter_number") or "").strip()
    if location and chapter_number:
        return f"第{chapter_number}章位于{location}"
    return location


def _find_last_event_text(content: Dict[str, Any]) -> str:
    events = content.get("key_event_records") or []
    if not isinstance(events, list) or not events:
        return ""
    item = events[-1] or {}
    chapter_number = str(item.get("chapter_number") or "").strip()
    event_type = str(item.get("event_type") or "").strip()
    summary = str(item.get("summary") or "").strip()
    prefix = ""
    if chapter_number:
        prefix += f"第{chapter_number}章"
    if event_type:
        prefix += f"[{event_type}]"
    return (prefix + summary).strip()


@register_function(
    "default",
    summary="当 value 为 None 时返回默认值",
    scenario="空值兜底",
    priority=75,
    example="default(card.content.title, '未命名')",
)
def fn_default(value: Any, default_value: Any) -> Any:
    """当 value 为 None 时返回默认值"""
    return value if value is not None else default_value


@register_function(
    "resolve_character_targets",
    summary="基于章节实体名单和正文内容，解析本章应处理的已有角色标准名",
    scenario="章节生成/后处理角色状态更新前的目标角色收口",
    priority=96,
    example="resolve_character_targets(card.content.entity_list, chapter_text, character_cards.cards)",
)
def fn_resolve_character_targets(
    entity_list: Any,
    chapter_text: Any,
    character_cards: Any,
    *,
    limit: int = 8,
) -> List[str]:
    """从章节实体名单与正文内容中收口本章已有角色标准名。"""
    if not isinstance(character_cards, list):
        return []

    alias_map: Dict[str, str] = {}
    ordered_cards: List[Dict[str, Any]] = []
    for card in character_cards:
        if not isinstance(card, dict):
            continue
        content = _get_card_content(card)
        standard_name = _get_character_standard_name(card)
        if not standard_name:
            continue
        ordered_cards.append(card)
        alias_map[_normalize_text(standard_name)] = standard_name
        for alias in content.get("aliases") or []:
            normalized = _normalize_text(alias)
            if normalized:
                alias_map[normalized] = standard_name

    resolved: List[str] = []
    seen: set[str] = set()

    def _append(name: str) -> None:
        normalized = _normalize_text(name)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        resolved.append(name)

    for item in entity_list or []:
        standard_name = alias_map.get(_normalize_text(item))
        if standard_name:
            _append(standard_name)
        if len(resolved) >= limit:
            return resolved[:limit]

    chapter_text_str = str(chapter_text or "")
    if chapter_text_str and len(resolved) < limit:
        for card in ordered_cards:
            standard_name = _get_character_standard_name(card)
            content = _get_card_content(card)
            candidate_tokens = [standard_name, *(content.get("aliases") or [])]
            if any(str(token or "").strip() and str(token).strip() in chapter_text_str for token in candidate_tokens):
                _append(standard_name)
            if len(resolved) >= limit:
                break

    return resolved[:limit]


@register_function(
    "build_character_match_payload",
    summary="把角色标准名列表转换为角色库同步节点可直接使用的匹配载荷",
    scenario="在无需新角色识别时驱动角色库同步",
    priority=90,
    example="build_character_match_payload(['林澈', '沈清禾'])",
)
def fn_build_character_match_payload(target_names: Any) -> Dict[str, Any]:
    """将目标角色名列表包装成角色库同步节点输入。"""
    names = [str(name or "").strip() for name in (target_names or []) if str(name or "").strip()]
    return {
        "existing_matches": [
            {
                "observed_name": name,
                "matched_name": name,
                "aliases": [],
            }
            for name in names
        ],
        "new_characters": [],
    }


@register_function(
    "build_character_state_reference",
    summary="为目标角色生成紧凑的当前状态参考摘要",
    scenario="角色状态结构化提取前缩小上下文",
    priority=94,
    example="build_character_state_reference(character_cards.cards, ['林澈'])",
)
def fn_build_character_state_reference(character_cards: Any, target_names: Any) -> str:
    """按角色标准名生成轻量状态参考文本。"""
    if not isinstance(character_cards, list):
        return ""

    target_name_set = {
        _normalize_text(name) for name in (target_names or [])
        if _normalize_text(name)
    }
    if not target_name_set:
        return ""

    lines: List[str] = []
    for card in character_cards:
        if not isinstance(card, dict):
            continue
        content = _get_card_content(card)
        standard_name = _get_character_standard_name(card)
        if _normalize_text(standard_name) not in target_name_set:
            continue

        aliases = [str(alias or "").strip() for alias in (content.get("aliases") or []) if str(alias or "").strip()]
        line_parts = [
            f"角色名：{standard_name}",
            f"角色编号：{str(content.get('character_code') or '未编号')}",
            f"角色类型：{str(content.get('role_type') or '')}",
            f"角色权重：{str(content.get('role_weight') or '')}",
            f"角色层级：{str(content.get('role_tier') or '')}",
            f"身份：{str(content.get('identity') or '')}",
            f"角色概述：{str(content.get('description') or '')}",
        ]
        if aliases:
            line_parts.append("其他称谓：" + "、".join(aliases))

        last_position = _find_last_position_text(content)
        if last_position:
            line_parts.append("最近位置：" + last_position)

        last_event = _find_last_event_text(content)
        if last_event:
            line_parts.append("最近事件：" + last_event)

        life_state = content.get("life_state") or {}
        if isinstance(life_state, dict):
            physical = str(life_state.get("physical_state") or "").strip()
            psychological = str(life_state.get("psychological_state") or "").strip()
            if physical or psychological:
                line_parts.append(f"生命状态：身体={physical or '无'}；心理={psychological or '无'}")

        lines.append("\n".join([part for part in line_parts if str(part).strip()]))

    return "\n\n".join(lines)


@register_function(
    "build_character_state_update_from_summary",
    summary="把角色状态摘要转换成角色卡写回载荷",
    scenario="章节后处理的角色状态摘要提取完成后，本地映射为 UpdateCharacterState",
    priority=93,
    example="build_character_state_update_from_summary(summary_extract.data, volume_number=1, chapter_number=3)",
)
def fn_build_character_state_update_from_summary(
    summary_data: Any,
    *,
    volume_number: int,
    chapter_number: int,
) -> Dict[str, Any]:
    return build_character_state_update_from_summary(
        summary_data,
        volume_number=int(volume_number),
        chapter_number=int(chapter_number),
    )


@register_function(
    "build_candidate_character_content_update",
    summary="把章节角色规划结果整理成章节候选角色字段和 entity_list 写回内容",
    scenario="章节草稿前候选角色准备",
    priority=92,
    example="build_candidate_character_content_update(target.content, character_planning.data, character_cards.cards)",
)
def fn_build_candidate_character_content_update(
    content: Any,
    planning_result: Any,
    official_character_cards: Any,
    *,
    updated_at: Any = None,
) -> Dict[str, Any]:
    return build_candidate_character_content_update(
        content=content if isinstance(content, dict) else {},
        planning_result=planning_result or {},
        official_character_cards=official_character_cards or [],
        updated_at=str(updated_at) if updated_at is not None else None,
    )


@register_function(
    "coalesce",
    summary="返回第一个非 None 的值",
    scenario="多候选字段回退",
    priority=85,
    example="coalesce(a.title, a.name, '未命名')",
)
def fn_coalesce(*values: Any) -> Any:
    """返回第一个非 None 的值"""
    for value in values:
        if value is not None:
            return value
    return None


@register_function(
    "merge",
    summary="合并多个字典，忽略非字典参数",
    scenario="数据拼装",
    priority=80,
    example="merge(base, {'project_id': project.id})",
)
def fn_merge(*dicts: Any) -> Dict[str, Any]:
    """合并多个字典，忽略非字典参数"""
    result: Dict[str, Any] = {}
    for item in dicts:
        if isinstance(item, dict):
            result.update(item)
    return result


@register_function(
    "json_parse",
    summary="JSON 字符串转对象",
    scenario="解析外部返回 JSON",
    priority=60,
    example="json_parse(raw_json).get('items', [])",
)
def fn_json_parse(json_str: str) -> Any:
    """JSON 字符串转对象"""
    return json.loads(json_str)


@register_function(
    "json_stringify",
    summary="对象转 JSON 字符串",
    scenario="调试输出与存档",
    priority=55,
    example="json_stringify(result, indent=2)",
)
def fn_json_stringify(obj: Any, indent: int | None = None) -> str:
    """对象转 JSON 字符串"""
    return json.dumps(obj, indent=indent, ensure_ascii=False)


@register_function(
    "read_file",
    summary="读取文件内容（失败时返回错误文本）",
    scenario="把外部文件内容注入工作流",
    priority=95,
    example="read_file(item.meta.path)",
)
def fn_read_file(path: str, encoding: str = "utf-8") -> str:
    """读取文件内容（失败时返回错误文本）"""
    try:
        with open(path, "r", encoding=encoding) as file:
            return file.read()
    except Exception as exc:
        return f"[读取失败: {exc}]"


@register_function(
    "normalize_ranges",
    summary="修复范围列表的缺口/重叠，保证连续覆盖",
    scenario="阶段范围/章节归属兜底",
    priority=92,
    example="normalize_ranges(stages, start=1, end=total_chapters)",
)
def fn_normalize_ranges(
    ranges: Any,
    *,
    start: int = 1,
    end: int | None = None,
    start_key: str = "chapter_start",
    end_key: str = "chapter_end",
) -> list[dict[str, Any]]:
    """规范化范围列表，修复缺口与重叠。

    - 输入：list[dict]，每项至少包含 start_key/end_key。
    - 输出：按 start_key 排序后的新 list[dict]（不修改原对象）。
    - 规则：
      1) 按 start_key 排序
      2) 若出现缺口（cur_start > prev_end + 1），则把缺口并入上一段（扩展 prev_end）
      3) 若出现重叠（cur_start <= prev_end），则将 cur_start 调整为 prev_end + 1
      4) 若 end 指定，则最后一段补齐到 end（若不足），并且所有段 end 不超过 end
    """

    if not isinstance(ranges, list) or not ranges:
        return []

    normalized: list[dict[str, Any]] = []

    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    # 过滤并复制
    cleaned: list[dict[str, Any]] = []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        s = _to_int(item.get(start_key))
        e = _to_int(item.get(end_key))
        if s is None or e is None:
            continue
        copied = dict(item)
        copied[start_key] = s
        copied[end_key] = e
        cleaned.append(copied)

    if not cleaned:
        return []

    cleaned.sort(key=lambda x: (x[start_key], x[end_key]))

    for idx, item in enumerate(cleaned):
        cur = dict(item)
        cur_start = cur[start_key]
        cur_end = cur[end_key]

        if idx == 0:
            if cur_start > start:
                cur_start = start
            if cur_end < cur_start:
                cur_end = cur_start
            if end is not None and cur_end > end:
                cur_end = end
            cur[start_key] = cur_start
            cur[end_key] = cur_end
            normalized.append(cur)
            continue

        prev = normalized[-1]
        prev_end = int(prev[end_key])
        expected = prev_end + 1

        if cur_start > expected:
            # 缺口并入上一段：把上一段 end 扩展到缺口末尾（expected..cur_start-1）
            prev[end_key] = cur_start - 1
            prev_end = int(prev[end_key])
            expected = prev_end + 1

        if cur_start < expected:
            cur_start = expected

        if cur_end < cur_start:
            cur_end = cur_start

        if end is not None and cur_start > end:
            break

        if end is not None and cur_end > end:
            cur_end = end

        cur[start_key] = cur_start
        cur[end_key] = cur_end
        normalized.append(cur)

    if end is not None and normalized:
        last = normalized[-1]
        if int(last[end_key]) < end:
            last[end_key] = end

    return normalized


@register_function(
    "squash_adjacent_stages",
    summary="合并相邻重复阶段，抑制单章重复阶段",
    scenario="阶段规划去重",
    priority=90,
    example="squash_adjacent_stages(stages)",
)
def fn_squash_adjacent_stages(
    stages: Any,
    *,
    name_key: str = "stage_name",
    start_key: str = "chapter_start",
    end_key: str = "chapter_end",
    outline_key: str = "stage_outline",
    summary_key: str = "stage_summary",
    tiny_threshold: int = 1,
) -> list[dict[str, Any]]:
    """合并相邻重复阶段，避免“同名+近似内容+单章”碎片。

    规则：
    1) 仅处理相邻阶段。
    2) 若相邻阶段同名，直接合并章节范围，保留信息更丰富的一侧文本。
    3) 若当前阶段仅 1 章且与前一阶段文本高度相似，也合并到前一阶段。
    """

    if not isinstance(stages, list) or not stages:
        return []

    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    def _clean_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return re.sub(r"\s+", "", text)

    def _is_similar_text(a: Any, b: Any) -> bool:
        ta = _clean_text(a)
        tb = _clean_text(b)
        if not ta or not tb:
            return False
        if ta == tb:
            return True
        short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        return len(short) >= 24 and short in long

    cleaned: list[dict[str, Any]] = []
    for item in stages:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        s = _to_int(copied.get(start_key))
        e = _to_int(copied.get(end_key))
        if s is None or e is None:
            continue
        if e < s:
            e = s
        copied[start_key] = s
        copied[end_key] = e
        cleaned.append(copied)

    if not cleaned:
        return []

    cleaned.sort(key=lambda x: (x[start_key], x[end_key]))

    squashed: list[dict[str, Any]] = []
    for cur in cleaned:
        if not squashed:
            squashed.append(cur)
            continue

        prev = squashed[-1]

        prev_name = str(prev.get(name_key) or "").strip()
        cur_name = str(cur.get(name_key) or "").strip()
        same_name = bool(prev_name and cur_name and prev_name == cur_name)

        cur_len = int(cur[end_key]) - int(cur[start_key]) + 1
        tiny_and_similar = cur_len <= tiny_threshold and (
            _is_similar_text(prev.get(outline_key), cur.get(outline_key))
            or _is_similar_text(prev.get(summary_key), cur.get(summary_key))
        )

        if same_name or tiny_and_similar:
            prev[end_key] = max(int(prev[end_key]), int(cur[end_key]))

            prev_outline = str(prev.get(outline_key) or "")
            cur_outline = str(cur.get(outline_key) or "")
            if len(cur_outline) > len(prev_outline):
                prev[outline_key] = cur_outline

            prev_summary = str(prev.get(summary_key) or "")
            cur_summary = str(cur.get(summary_key) or "")
            if len(cur_summary) > len(prev_summary):
                prev[summary_key] = cur_summary
            continue

        squashed.append(cur)

    return squashed


@register_function(
    "normalize_foreshadow_plan",
    summary="把旧版伏笔条目或结构化条目统一整理成稳定对象列表",
    scenario="增强章节大纲/伏笔治理前预处理",
    priority=98,
    example="normalize_foreshadow_plan(outline.content.foreshadow_plan_items or outline.content.foreshadow_items)",
)
def fn_normalize_foreshadow_plan(items: Any) -> list[dict[str, Any]]:
    return normalize_foreshadow_plan(items)


@register_function(
    "extract_foreshadow_ids",
    summary="从伏笔条目列表中提取稳定伏笔编号",
    scenario="伏笔历史检索与同步",
    priority=94,
    example="extract_foreshadow_ids(outline.content.foreshadow_items)",
)
def fn_extract_foreshadow_ids(items: Any) -> list[str]:
    return extract_foreshadow_ids(items)


@register_function(
    "foreshadow_lifecycle_gate",
    summary="检查当前章节是否响应了所有到期未回收伏笔",
    scenario="章节生成/后处理前的伏笔门禁",
    priority=99,
    example="foreshadow_lifecycle_gate(chapter_no, ledger_text, planned_items).get('allow')",
)
def fn_foreshadow_lifecycle_gate(chapter_number: Any, ledger_text: Any, planned_items: Any) -> dict[str, Any]:
    return foreshadow_lifecycle_gate(chapter_number, ledger_text, planned_items)


@register_function(
    "build_foreshadow_register_payload",
    summary="根据伏笔治理报告生成伏笔登记载荷",
    scenario="ForeshadowItem 同步",
    priority=96,
    example="build_foreshadow_register_payload(ids_text, report_text, chapter_id, chapter_no)",
)
def fn_build_foreshadow_register_payload(
    foreshadow_ids_text: Any,
    report_text: Any,
    chapter_id: Any = None,
    current_chapter_number: Any = None,
) -> list[dict[str, Any]]:
    return build_foreshadow_register_payload(
        foreshadow_ids_text=foreshadow_ids_text,
        report_text=report_text,
        chapter_id=chapter_id,
        current_chapter_number=current_chapter_number,
    )


@register_function(
    "build_foreshadow_processing_vars",
    summary="构建伏笔治理所需的标准变量字典",
    scenario="增强章节闭环/后处理闭环",
    priority=97,
    example="build_foreshadow_processing_vars(chapter_no, chapter_id, title, blueprint, chapter_text, ledger, planned_items)",
)
def fn_build_foreshadow_processing_vars(
    chapter_number: Any,
    chapter_id: Any,
    chapter_title: Any,
    chapter_blueprint: Any,
    chapter_text: Any,
    existing_ledger: Any,
    planned_items: Any,
) -> dict[str, Any]:
    return build_foreshadow_processing_vars(
        chapter_number=chapter_number,
        chapter_id=chapter_id,
        chapter_title=chapter_title,
        chapter_blueprint=chapter_blueprint,
        chapter_text=chapter_text,
        existing_ledger=existing_ledger,
        planned_items=planned_items,
    )


@register_function(
    "build_open_foreshadow_ledger",
    summary="从伏笔治理报告中过滤出未回收台账文本",
    scenario="更新伏笔管理/未回收台账",
    priority=93,
    example="build_open_foreshadow_ledger(report_text)",
)
def fn_build_open_foreshadow_ledger(report_text: Any) -> str:
    return build_open_foreshadow_ledger(report_text)
