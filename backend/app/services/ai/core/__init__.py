"""AI核心工具模块

纯函数工具和配额管理，无外部依赖。
"""

from .token_utils import estimate_tokens, calc_input_tokens
from .quota_manager import precheck_quota, record_usage


def build_chat_model(*args, **kwargs):
    from .chat_model_factory import build_chat_model as _build_chat_model

    return _build_chat_model(*args, **kwargs)

__all__ = [
    'build_chat_model',
    'estimate_tokens',
    'calc_input_tokens',
    'precheck_quota',
    'record_usage',
]
