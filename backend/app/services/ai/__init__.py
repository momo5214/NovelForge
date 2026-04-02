"""AI服务模块

统一的LLM调用、结构化生成、续写和助手服务。
"""

def build_chat_model(*args, **kwargs):
    from .core.chat_model_factory import build_chat_model as _build_chat_model

    return _build_chat_model(*args, **kwargs)


def generate_structured(*args, **kwargs):
    from .core.llm_service import generate_structured as _generate_structured

    return _generate_structured(*args, **kwargs)


def generate_continuation_streaming(*args, **kwargs):
    from .core.llm_service import (
        generate_continuation_streaming as _generate_continuation_streaming,
    )

    return _generate_continuation_streaming(*args, **kwargs)


def generate_assistant_chat_streaming(*args, **kwargs):
    from .assistant.assistant_service import (
        generate_assistant_chat_streaming as _generate_assistant_chat_streaming,
    )

    return _generate_assistant_chat_streaming(*args, **kwargs)

__all__ = [
    'build_chat_model',
    'generate_structured',
    'generate_continuation_streaming',
    'generate_assistant_chat_streaming',
]
