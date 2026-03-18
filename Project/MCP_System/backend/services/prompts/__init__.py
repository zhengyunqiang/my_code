"""
Prompts System Package
提示词系统 - 提示词模板管理器
"""

# 兼容旧的 templates 模块
from backend.services.prompts.templates import (
    PromptFormat,
    PromptVariable as OldPromptVariable,
    PromptDefinition,
    PromptMessage,
    RenderedPrompt,
    PromptRenderer,
    PromptManager as OldPromptManager,
    prompt_manager as old_prompt_manager,
    prompt,
)

# 新的统一提示词管理系统
from backend.services.prompts.prompt_manager import (
    PromptCategory,
    PromptLanguage,
    PromptVariable,
    PromptTemplate,
    PromptManager,
    prompt_manager,
    # 内置模板
    NL_DATABASE_PARSE_SYSTEM,
    NL_DATABASE_PARSE_USER,
    SQL_GENERATION_SYSTEM,
    ERROR_RECOVERY_GUIDANCE,
)

__all__ = [
    # 旧系统（兼容性）
    "PromptFormat",
    "PromptDefinition",
    "PromptMessage",
    "RenderedPrompt",
    "PromptRenderer",
    "prompt",
    # 新系统（推荐使用）
    "PromptCategory",
    "PromptLanguage",
    "PromptVariable",
    "PromptTemplate",
    "PromptManager",
    "prompt_manager",
    # 内置模板
    "NL_DATABASE_PARSE_SYSTEM",
    "NL_DATABASE_PARSE_USER",
    "SQL_GENERATION_SYSTEM",
    "ERROR_RECOVERY_GUIDANCE",
]
