"""提示词初始化

从文件系统加载提示词模板并初始化到数据库。
"""

import ast
import os
import re
from pathlib import Path
from typing import Dict, TypedDict

from loguru import logger
from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Prompt
from .registry import initializer


class ExternalPromptMeta(TypedDict):
    short_name: str
    description: str
    skills: str
    placeholder_aliases: Dict[str, str]


_FORMAT_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

M0_EXTERNAL_PROMPT_META: Dict[str, ExternalPromptMeta] = {
    "architecture_step1_mission_prompt": {
        "short_name": "architecture_step1_mission",
        "description": "ANG M0 架构步骤1：分卷使命宣言",
        "skills": "分卷战略设计、主题拆解、篇幅规划",
        "placeholder_aliases": {},
    },
    "architecture_step2_worldview_prompt": {
        "short_name": "architecture_step2_worldview",
        "description": "ANG M0 架构步骤2：世界观与冲突发生器",
        "skills": "世界观建模、核心矛盾构建、冲突驱动设计",
        "placeholder_aliases": {},
    },
    "architecture_step3_plot_prompt": {
        "short_name": "architecture_step3_plot",
        "description": "ANG M0 架构步骤3：情节线与推进机制",
        "skills": "主线/支线编排、因果推进、阶段节奏控制",
        "placeholder_aliases": {},
    },
    "architecture_step4_character_prompt": {
        "short_name": "architecture_step4_character",
        "description": "ANG M0 架构步骤4：核心角色规划",
        "skills": "角色功能拆解、关系网络设计、人物弧线规划、登场策略编排",
        "placeholder_aliases": {},
    },
    "architecture_step5_style_prompt": {
        "short_name": "architecture_step5_style",
        "description": "ANG M0 架构步骤5：叙事风格与文本策略",
        "skills": "叙事视角规划、语言风格约束、文本一致性控制",
        "placeholder_aliases": {},
    },
    "volume_design_format": {
        "short_name": "volume_design_format",
        "description": "ANG M0 分卷格式模板",
        "skills": "模板约束设计、结构化格式规范",
        "placeholder_aliases": {},
    },
    "volume_outline_prompt": {
        "short_name": "volume_outline",
        "description": "ANG M0 首卷分卷大纲生成",
        "skills": "分卷剧情规划、卷级目标拆分、章节节奏设计",
        "placeholder_aliases": {},
    },
    "subsequent_volume_prompt": {
        "short_name": "subsequent_volume",
        "description": "ANG M0 中间卷分卷大纲生成",
        "skills": "多卷衔接、剧情递进、伏线延展",
        "placeholder_aliases": {},
    },
    "final_volume_prompt": {
        "short_name": "final_volume",
        "description": "ANG M0 终卷收束大纲生成",
        "skills": "终局收束、主线回收、情感高潮设计",
        "placeholder_aliases": {},
    },
    "chapter_blueprint_prompt": {
        "short_name": "chapter_blueprint",
        "description": "ANG M0 章节目录蓝图生成",
        "skills": "章节拆解、情节点编排、章节级目标控制",
        "placeholder_aliases": {},
    },
    "chapter_draft_prompt": {
        "short_name": "chapter_draft",
        "description": "ANG M0 章节正文草稿生成",
        "skills": "正文写作、场景铺陈、角色行动与对白生成",
        "placeholder_aliases": {
            "历史章节正文": "history_chapter_text",
            "字数下限": "word_count_min",
            "字数上限": "word_count_max",
        },
    },
    "Chapter_Review_prompt": {
        "short_name": "chapter_review",
        "description": "ANG M2 一致性审校",
        "skills": "逻辑一致性审查、情节冲突识别、文本质量评估",
        "placeholder_aliases": {
            "章节字数": "chapter_word_count",
            "字数下限": "word_count_min",
            "字数上限": "word_count_max",
        },
    },
    "foreshadowing_history_processing_prompt": {
        "short_name": "foreshadow_history_processing",
        "description": "ANG M2 伏笔历史内容预处理",
        "skills": "伏笔历史抽取、编号识别、上下文整理",
        "placeholder_aliases": {},
    },
    "foreshadowing_content_processing_prompt": {
        "short_name": "foreshadow_content_processing",
        "description": "ANG M2 本章伏笔内容提取",
        "skills": "正文伏笔提取、伏笔进展归纳、章节线索整理",
        "placeholder_aliases": {},
    },
    "foreshadowing_processing_prompt": {
        "short_name": "foreshadow_processing",
        "description": "ANG M2 伏笔整合与台账生成",
        "skills": "伏笔合并、状态整合、伏笔知识沉淀",
        "placeholder_aliases": {},
    },
}

M0_EXTERNAL_PROMPT_KEYS = tuple(M0_EXTERNAL_PROMPT_META.keys())

_EXTERNAL_ROLE_PATTERN = re.compile(r"(?im)^\s*AI角色\s*[:：]\s*(.+?)\s*$")
_EXTERNAL_TASK_PATTERN = re.compile(r"(?im)^\s*任务\s*[:：]\s*(.+?)\s*$")
_EXTERNAL_OUTPUT_FORMAT_PATTERN = re.compile(r"(?is)\[\s*最终输出格式\s*\]\s*(.*)$")
_DEFAULT_STRUCTURED_SKILLS = "长篇小说策划、结构化生成与写作执行"
_DEFAULT_STRUCTURED_OUTPUT = "请严格遵循 Goals 中的约束与格式要求输出，不要额外解释。"


def _indent_text_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else "" for line in text.splitlines())


def _strip_first_labeled_line(text: str, label: str) -> str:
    pattern = re.compile(rf"(?im)^\s*{re.escape(label)}\s*[:：].*$\n?")
    return pattern.sub("", text, count=1).strip()


def _to_structured_external_prompt_template(key: str, template: str) -> str:
    """将外部提示词包装为 PromptWorkshop 可分区编辑的结构化模板。"""
    role_match = _EXTERNAL_ROLE_PATTERN.search(template)
    task_match = _EXTERNAL_TASK_PATTERN.search(template)
    output_match = _EXTERNAL_OUTPUT_FORMAT_PATTERN.search(template)

    role = (role_match.group(1).strip() if role_match else "") or "长篇小说创作助手"
    task = task_match.group(1).strip() if task_match else ""

    if output_match:
        output_format = output_match.group(1).strip() or _DEFAULT_STRUCTURED_OUTPUT
        body_source = template[: output_match.start()].strip()
    else:
        output_format = _DEFAULT_STRUCTURED_OUTPUT
        body_source = template.strip()

    body_source = _strip_first_labeled_line(_strip_first_labeled_line(body_source, "AI角色"), "任务").strip()

    goals_parts: list[str] = []
    if task:
        goals_parts.append(f"任务：{task}")
    if body_source:
        goals_parts.append(body_source)
    goals = "\n\n".join(goals_parts).strip() or "请根据输入变量完成当前提示词对应任务。"

    skills = (M0_EXTERNAL_PROMPT_META.get(key) or {}).get("skills") or _DEFAULT_STRUCTURED_SKILLS

    return "\n".join(
        [
            f"- Role: {role}",
            f"- Skills: {skills}",
            "- Goals:",
            _indent_text_block(goals, spaces=4),
            f"- OutputFormat: {output_format}",
        ]
    ).strip()


def _parse_prompt_file(file_path: str) -> dict:
    """解析单个提示词文件

    Args:
        file_path: 提示词文件路径

    Returns:
        包含name, description, template的字典
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    filename = os.path.basename(file_path)
    name = os.path.splitext(filename)[0]
    description = f"AI任务提示词: {name}"

    return {
        "name": name,
        "description": description,
        "template": content.strip(),
    }


def _default_external_prompt_definitions_path() -> Path:
    """获取默认外部提示词定义路径。"""
    current_file = Path(__file__).resolve()
    candidate_suffixes = [
        Path("AI_NovelGenerator") / "prompt_definitions.py",
        Path("AI_NovelGenerator-main") / "prompt_definitions.py",
        Path("AI_NovelGenerator-main") / "AI_NovelGenerator-main" / "prompt_definitions.py",
    ]
    for parent in current_file.parents:
        for suffix in candidate_suffixes:
            candidate = parent / suffix
            if candidate.exists():
                return candidate

    # 回退到常见仓库布局：.../NovelForge/backend/app/bootstrap/prompts.py -> .../NovelForge
    project_root = current_file.parents[3]
    return project_root.parent / "AI_NovelGenerator-main" / "AI_NovelGenerator-main" / "prompt_definitions.py"


def _resolve_external_prompt_definitions_path() -> Path:
    """解析外部提示词定义路径（优先配置，其次默认路径）。"""
    configured = (settings.bootstrap.external_prompt_definitions_path or "").strip()
    if not configured:
        return _default_external_prompt_definitions_path()

    path = Path(configured).expanduser()
    if not path.is_absolute():
        # 相对路径默认以 backend/ 为基准
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    return path


def _extract_string_assignments(file_path: Path, target_keys: set[str] | None = None) -> Dict[str, str]:
    """从 Python 文件中提取顶层字符串常量赋值。"""
    source = file_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(file_path))

    extracted: Dict[str, str] = {}
    for node in module.body:
        target_name = None
        value_node = None

        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value

        if not target_name or value_node is None:
            continue
        if target_keys is not None and target_name not in target_keys:
            continue

        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            extracted[target_name] = value_node.value

    return extracted


def _apply_placeholder_aliases(template: str, alias_map: Dict[str, str]) -> str:
    """按映射替换占位符名（{old} -> ${new}）。"""
    converted = template
    for source_name, target_name in alias_map.items():
        converted = converted.replace(f"{{{source_name}}}", f"${{{target_name}}}")
    return converted


def _convert_format_placeholders_to_template(template: str) -> str:
    """将 {var} 占位符转换为 Template 兼容的 ${var}。"""

    def replacer(match: re.Match) -> str:
        name = match.group(1)
        return f"${{{name}}}"

    return _FORMAT_PLACEHOLDER_PATTERN.sub(replacer, template)


def _normalize_external_prompt_template(key: str, template: str) -> str:
    """统一处理外部提示词占位符。"""
    converted = _convert_format_placeholders_to_template(template)
    meta = M0_EXTERNAL_PROMPT_META.get(key) or {}
    alias_map = meta.get("placeholder_aliases")
    if isinstance(alias_map, dict) and alias_map:
        converted = _apply_placeholder_aliases(converted, alias_map)
    return _to_structured_external_prompt_template(key, converted)


def _load_external_prompt_files() -> dict:
    """按配置加载外部提示词定义（M0 关键提示词）。"""
    if not settings.bootstrap.enable_external_prompt_import:
        return {}

    strict = bool(settings.bootstrap.external_prompt_strict)
    namespace = (settings.bootstrap.external_prompt_namespace or "ANG.M0").strip().strip(".") or "ANG.M0"
    file_path = _resolve_external_prompt_definitions_path()

    try:
        assignments = _extract_string_assignments(file_path, target_keys=set(M0_EXTERNAL_PROMPT_KEYS))
    except FileNotFoundError:
        message = f"外部提示词定义文件不存在: {file_path}"
        if strict:
            raise FileNotFoundError(message)
        logger.warning(message)
        return {}
    except Exception as e:
        message = f"解析外部提示词定义失败: path={file_path}, err={e}"
        if strict:
            raise RuntimeError(message) from e
        logger.warning(message)
        return {}

    prompt_files: dict = {}
    missing_keys: list[str] = []

    for key, meta in M0_EXTERNAL_PROMPT_META.items():
        raw_template = assignments.get(key)
        if not isinstance(raw_template, str):
            missing_keys.append(key)
            continue

        short_name = str(meta.get("short_name") or (key[:-7] if key.endswith("_prompt") else key))
        prompt_name = f"{namespace}.{short_name}"
        prompt_files[prompt_name] = {
            "name": prompt_name,
            "description": str(meta.get("description") or f"外部导入提示词: {key}"),
            "template": _normalize_external_prompt_template(key, raw_template.strip()),
        }

    if missing_keys:
        logger.warning(
            f"外部提示词缺少 {len(missing_keys)} 个 M0 键，已跳过: {', '.join(missing_keys)}"
        )

    logger.info(
        f"外部提示词加载完成: namespace={namespace}, count={len(prompt_files)}, source={file_path}"
    )
    return prompt_files


def get_all_prompt_files() -> dict:
    """从文件系统加载所有提示词

    Returns:
        提示词字典，key为提示词名称
    """
    prompt_files = {}

    prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
    try:
        prompt_filenames = os.listdir(prompt_dir)
    except FileNotFoundError:
        logger.warning(f"Prompt directory not found at {prompt_dir}. Cannot load built-in prompts.")
        prompt_filenames = []

    for filename in prompt_filenames:
        if filename.endswith((".prompt", ".txt")):
            file_path = os.path.join(prompt_dir, filename)
            name = os.path.splitext(filename)[0]
            prompt_files[name] = _parse_prompt_file(file_path)

    external_prompt_files = _load_external_prompt_files()
    if external_prompt_files:
        prompt_files.update(external_prompt_files)

    return prompt_files


@initializer(name="提示词", order=10)
def init_prompts(session: Session) -> None:
    """初始化默认提示词

    行为受配置项 BOOTSTRAP_OVERWRITE 控制：
    - True: 覆盖更新已存在的提示词
    - False: 跳过已存在的提示词

    Args:
        session: 数据库会话
    """
    overwrite = settings.bootstrap.should_overwrite
    existing_prompts = session.exec(select(Prompt)).all()
    existing_names = {p.name for p in existing_prompts}
    existing_by_name = {p.name: p for p in existing_prompts}

    all_prompts_data = get_all_prompt_files()

    new_count = 0
    updated_count = 0
    skipped_count = 0
    prompts_to_add = []

    for name, prompt_data in all_prompts_data.items():
        if name in existing_names:
            if overwrite:
                existing_prompt = existing_by_name[name]
                existing_prompt.template = prompt_data["template"]
                existing_prompt.description = prompt_data.get("description")
                existing_prompt.built_in = True
                updated_count += 1
            else:
                skipped_count += 1
        else:
            prompts_to_add.append(Prompt(**prompt_data, built_in=True))
            new_count += 1

    if prompts_to_add:
        session.add_all(prompts_to_add)

    if new_count > 0 or updated_count > 0:
        session.commit()
        logger.info(
            f"提示词更新完成: 新增 {new_count} 个，更新 {updated_count} 个（overwrite={overwrite}，跳过 {skipped_count} 个）。"
        )
    else:
        logger.info(f"所有提示词已是最新状态（overwrite={overwrite}，跳过 {skipped_count} 个）。")
