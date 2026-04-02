from __future__ import annotations

import re
from typing import Dict, List, Any

from pydantic import BaseModel, Field

from ...registry import register_node
from ..base import BaseNode
from app.schemas.wizard import Step4CharacterExtractCard


class ParseStep4CharactersInput(BaseModel):
    text: str = Field(..., description="步骤四：核心角色规划正文")


class ParseStep4CharactersOutput(BaseModel):
    character_cards: List[Step4CharacterExtractCard] = Field(
        default_factory=list,
        description="从步骤四正文中解析得到的核心角色卡列表",
    )


FIELD_ALIASES = {
    "基础信息": "base_info",
    "角色定位": "role_position",
    "背景经历": "background",
    "核心动机": "core_drive",
    "角色关系": "relationship_summary",
    "关键矛盾": "inner_conflict",
    "首次登场规划": "first_event",
    "成长/堕落弧线": "character_arc",
    "分卷作用": "volume_role_plan",
}

PERSONALITY_KEYWORDS = [
    "谨慎", "冷静", "克制", "果断", "务实", "狠辣", "强势", "温和", "隐忍", "狡诈",
    "忠诚", "执拗", "野心", "勇敢", "敏锐", "理性", "冷硬", "沉稳", "可靠", "狠厉",
]

CHINESE_NUM_MAP = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _to_plain_text(value: str) -> str:
    return re.sub(r"\s+\n", "\n", (value or "").strip())


def _split_role_blocks(text: str) -> List[tuple[str, str]]:
    pattern = re.compile(r"(?m)^●\s*核心角色\d+[：:]\s*(.+?)\s*$")
    matches = list(pattern.finditer(text))
    blocks: List[tuple[str, str]] = []
    for i, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else text.find("● 角色驱动总览", start)
        if end == -1:
            end = len(text)
        blocks.append((name, text[start:end].strip()))
    return blocks


def _parse_sections(block: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_label: str | None = None
    buffer: List[str] = []

    def flush() -> None:
        nonlocal current_label, buffer
        if current_label:
            sections[current_label] = _to_plain_text("\n".join(buffer))
        current_label = None
        buffer = []

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^-\s*([^：:]+)[：:]\s*(.*)$", stripped)
        if match and match.group(1) in FIELD_ALIASES:
            flush()
            current_label = FIELD_ALIASES[match.group(1)]
            if match.group(2):
                buffer.append(match.group(2).strip())
            continue
        if current_label:
            buffer.append(stripped)

    flush()
    return sections


def _split_base_info(base_info: str) -> tuple[str, str, str, str]:
    parts = [p.strip() for p in re.split(r"\s*/\s*", base_info or "", maxsplit=3)]
    while len(parts) < 4:
        parts.append("")
    return parts[0], parts[1], parts[2], parts[3]


def _infer_role_type(text: str) -> str:
    if "主角" in text:
        return "主角"
    if any(word in text for word in ["反派", "对手", "追索者", "爪牙", "匪首", "帮主", "执事"]):
        return "反派"
    if any(word in text for word in ["盟友", "伙伴", "女主", "合伙人", "队友", "配角"]):
        return "主角团配角"
    return "普通NPC"


def _extract_personality(text: str, role_type: str) -> str:
    found: List[str] = []
    for word in PERSONALITY_KEYWORDS:
        if word in text and word not in found:
            found.append(word)
        if len(found) >= 4:
            break
    if found:
        return "、".join(found)
    defaults = {
        "主角": "谨慎、成长型、执行力强",
        "主角团配角": "可靠、互补、协作型",
        "反派": "强势、功利、压迫性强",
        "普通NPC": "务实、执行力强、立场明确",
    }
    return defaults.get(role_type, "性格待补充")


def _parse_first_volume(text: str) -> int:
    if not text:
        return 1
    digit = re.search(r"第\s*(\d+)\s*卷", text)
    if digit:
        return max(1, int(digit.group(1)))
    cn = re.search(r"第\s*([一二三四五六七八九十]+)\s*卷", text)
    if cn:
        chars = cn.group(1)
        if chars == "十":
            return 10
        if len(chars) == 2 and chars[0] == "十":
            return 10 + CHINESE_NUM_MAP.get(chars[1], 0)
        if len(chars) == 2 and chars[1] == "十":
            return CHINESE_NUM_MAP.get(chars[0], 1) * 10
        return CHINESE_NUM_MAP.get(chars, 1)
    return 1


def _extract_born_scene(first_event: str) -> str:
    if not first_event:
        return "待补充"
    parts = re.split(r"\s*/\s*", first_event, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[1].strip().split("，")[0].split("。")[0].strip()
    return first_event.split("，")[0].split("。")[0].strip()


def _shorten(text: str, limit: int = 120) -> str:
    value = _to_plain_text(text)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


@register_node
class ParseStep4CharactersNode(BaseNode[ParseStep4CharactersInput, ParseStep4CharactersOutput]):
    node_type = "Logic.ParseStep4Characters"
    category = "logic"
    label = "解析步骤四角色"
    description = "按固定文本格式解析步骤四正文，提取核心角色卡"

    input_model = ParseStep4CharactersInput
    output_model = ParseStep4CharactersOutput

    async def execute(self, inputs: ParseStep4CharactersInput):
        text = inputs.text or ""
        blocks = _split_role_blocks(text)
        cards: List[Step4CharacterExtractCard] = []

        for name, block in blocks:
            sections = _parse_sections(block)
            base_info = sections.get("base_info", "")
            gender, age, appearance, identity = _split_base_info(base_info)
            role_position = sections.get("role_position", "")
            role_type = _infer_role_type(role_position)
            first_event = sections.get("first_event", "")
            born_scene = _extract_born_scene(first_event)

            card = Step4CharacterExtractCard(
                name=name.strip(),
                entity_type="character",
                life_span="长期",
                role_type=role_type,
                gender=gender or "待补充",
                age=age or "待补充",
                appearance=appearance or "待补充",
                identity=identity or _shorten(role_position, 60) or "待补充",
                born_scene=born_scene or "待补充",
                first_volume=_parse_first_volume(first_event),
                first_event=first_event or "待补充",
                story_function=_shorten(f"{role_position}\n{sections.get('volume_role_plan', '')}", 140),
                description=_shorten(role_position or sections.get("background", ""), 140),
                background=sections.get("background", "") or "待补充",
                personality=_extract_personality(f"{role_position}\n{sections.get('background', '')}\n{sections.get('inner_conflict', '')}", role_type),
                core_drive=sections.get("core_drive", "") or "待补充",
                inner_conflict=sections.get("inner_conflict", "") or "待补充",
                relationship_summary=sections.get("relationship_summary", "") or "待补充",
                character_arc=sections.get("character_arc", "") or "待补充",
                dynamic_info={},
            )
            cards.append(card)

        yield ParseStep4CharactersOutput(character_cards=cards)
