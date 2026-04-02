"""Agent 构建器

提取 Agent 创建逻辑，供灵感助手和工作流节点复用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from loguru import logger

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool


def build_agent(
    model: BaseChatModel,
    tools: List[BaseTool],
    system_prompt: str,
    enable_summarization: bool = False,
    max_tokens_before_summary: int = 8192,
):
    """构建 LangChain Agent
    
    Args:
        model: LangChain ChatModel 实例
        tools: 工具列表
        system_prompt: 系统提示词
        enable_summarization: 是否启用上下文摘要
        max_tokens_before_summary: 摘要触发的 token 阈值
        
    Returns:
        LangChain Agent 实例
    """
    middleware = []

    if enable_summarization:
        try:
            from langchain.agents.middleware import SummarizationMiddleware
            middleware.append(
                SummarizationMiddleware(
                    model=model,
                    max_tokens_before_summary=max_tokens_before_summary,
                )
            )
        except Exception as e:
            logger.warning(f"初始化 SummarizationMiddleware 失败，将忽略上下文摘要: {e}")

    # 使用 LangChain 1.x 的 create_agent 创建带工具的智能体
    from langchain.agents import create_agent
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
    )
    
    return agent
