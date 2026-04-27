"""卡片参数服务

负责卡片 AI 参数的合并、验证等业务逻辑。
"""

from typing import Dict, Any
from sqlmodel import Session
from app.db.models import Card, LLMConfig
from app.services.card_service import ARCHITECTURE_STEP_PROMPTS
from loguru import logger


def merge_effective_ai_params(session: Session, card: Card) -> Dict[str, Any]:
    """合并卡片的有效 AI 参数

    合并逻辑：
    1. 基础参数来自 CardType.ai_params
    2. 覆盖参数来自 Card.ai_params
    3. 小说架构步骤卡：根据 content.step 修正 prompt_name
    4. 补齐缺失的 llm_config_id（选择 ID 最小的 LLM）
    5. 规范化类型

    Args:
        session: 数据库会话
        card: 卡片对象

    Returns:
        合并后的有效参数字典
    """
    # 获取基础参数（来自类型）
    base = (card.card_type.ai_params if card.card_type and card.card_type.ai_params else {}) or {}

    # 获取覆盖参数（来自实例）
    override = (card.ai_params or {})

    # 合并参数
    effective = {**base, **override}

    # 小说架构步骤卡：根据 content.step 修正 prompt_name
    if card.card_type and card.card_type.name == "小说架构步骤" and isinstance(card.content, dict):
        step_num = card.content.get("step")
        if step_num is not None:
            try:
                correct_prompt = ARCHITECTURE_STEP_PROMPTS.get(int(step_num))
                if correct_prompt:
                    effective["prompt_name"] = correct_prompt
            except (ValueError, TypeError):
                pass
    
    # 补齐 llm_config_id（如果缺失）
    if effective.get("llm_config_id") in (None, 0, "0", ""):
        try:
            # 选用 ID 最小的 LLM 作为默认值
            llm = session.query(LLMConfig).order_by(LLMConfig.id.asc()).first()  # type: ignore
            if llm:
                effective["llm_config_id"] = int(getattr(llm, "id", 0))
        except Exception as e:
            logger.warning(f"获取默认 LLM 配置失败: {e}")
    
    # 规范化 llm_config_id 类型
    if effective.get("llm_config_id") is not None:
        try:
            effective["llm_config_id"] = int(effective.get("llm_config_id"))
        except (ValueError, TypeError):
            pass
    
    return effective
