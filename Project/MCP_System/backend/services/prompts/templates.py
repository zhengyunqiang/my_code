"""
Prompts Templates Module
提示词模板系统 - 管理和渲染提示词
"""

import re
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.core.logging import get_logger
from backend.core.exceptions import ValidationError

logger = get_logger(__name__)


class PromptFormat(str, Enum):
    """提示词格式"""
    TEXT = "text"
    CHAT = "chat"
    JSON = "json"


@dataclass
class PromptVariable:
    """提示词变量定义"""
    name: str
    description: str = ""
    type: str = "string"
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None


@dataclass
class PromptDefinition:
    """提示词定义"""
    name: str
    template: str
    description: str = ""
    variables: List[PromptVariable] = field(default_factory=list)
    format: PromptFormat = PromptFormat.TEXT
    language: str = "zh-CN"
    category: str = "general"
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [
                {
                    "name": v.name,
                    "description": v.description,
                    "required": v.required,
                }
                for v in self.variables
            ],
        }


@dataclass
class PromptMessage:
    """提示词消息（聊天格式）"""
    role: str  # system, user, assistant
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderedPrompt:
    """渲染后的提示词"""
    messages: List[PromptMessage]
    format: PromptFormat
    metadata: Dict[str, Any] = field(default_factory=dict)


class PromptRenderer:
    """
    提示词渲染器

    支持多种模板语法和格式
    """

    def __init__(self):
        self._renderers = {
            PromptFormat.TEXT: self._render_text,
            PromptFormat.CHAT: self._render_chat,
            PromptFormat.JSON: self._render_json,
        }

    def render(
        self,
        prompt_def: PromptDefinition,
        variables: Dict[str, Any],
    ) -> RenderedPrompt:
        """
        渲染提示词

        Args:
            prompt_def: 提示词定义
            variables: 变量值

        Returns:
            RenderedPrompt

        Raises:
            ValidationError: 变量验证失败
        """
        # 验证变量
        self._validate_variables(prompt_def, variables)

        # 设置默认值
        resolved_variables = self._apply_defaults(prompt_def, variables)

        # 根据格式渲染
        renderer = self._renderers.get(prompt_def.format, self._render_text)
        return renderer(prompt_def, resolved_variables)

    def _validate_variables(
        self,
        prompt_def: PromptDefinition,
        variables: Dict[str, Any],
    ) -> None:
        """
        验证变量

        Args:
            prompt_def: 提示词定义
            variables: 变量值

        Raises:
            ValidationError: 验证失败
        """
        errors = []

        for var_def in prompt_def.variables:
            var_name = var_def.name

            # 检查必需变量
            if var_def.required and var_name not in variables:
                if var_def.default is None:
                    errors.append(f"Missing required variable: {var_name}")
                    continue

            # 检查枚举值
            if var_name in variables and var_def.enum:
                value = variables[var_name]
                if value not in var_def.enum:
                    errors.append(
                        f"Variable {var_name} must be one of {var_def.enum}, got: {value}"
                    )

        if errors:
            raise ValidationError(
                message="Prompt variable validation failed",
                field_errors={e: e for e in errors},
            )

    def _apply_defaults(
        self,
        prompt_def: PromptDefinition,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        应用默认值

        Args:
            prompt_def: 提示词定义
            variables: 变量值

        Returns:
            应用默认值后的变量字典
        """
        result = variables.copy()

        for var_def in prompt_def.variables:
            if var_def.name not in result and var_def.default is not None:
                result[var_def.name] = var_def.default

        return result

    def _render_text(
        self,
        prompt_def: PromptDefinition,
        variables: Dict[str, Any],
    ) -> RenderedPrompt:
        """渲染为文本格式"""
        template = prompt_def.template
        rendered = template

        # 简单的变量替换：{variable_name}
        for var_name, var_value in variables.items():
            placeholder = f"{{{var_name}}}"
            rendered = rendered.replace(placeholder, str(var_value))

        return RenderedPrompt(
            messages=[
                PromptMessage(role="user", content=rendered),
            ],
            format=PromptFormat.TEXT,
        )

    def _render_chat(
        self,
        prompt_def: PromptDefinition,
        variables: Dict[str, Any],
    ) -> RenderedPrompt:
        """渲染为聊天格式"""
        template = prompt_def.template
        rendered = template

        # 变量替换
        for var_name, var_value in variables.items():
            placeholder = f"{{{var_name}}}"
            rendered = rendered.replace(placeholder, str(var_value))

        # 解析消息（简单实现）
        # 格式：[role]content[/role]
        messages = []
        pattern = r"\[(system|user|assistant)\](.*?)\[/\1\]"

        for match in re.finditer(pattern, rendered, re.DOTALL):
            role = match.group(1)
            content = match.group(2).strip()
            messages.append(PromptMessage(role=role, content=content))

        # 如果没有找到消息格式，将整个内容作为用户消息
        if not messages:
            messages.append(PromptMessage(role="user", content=rendered))

        return RenderedPrompt(
            messages=messages,
            format=PromptFormat.CHAT,
        )

    def _render_json(
        self,
        prompt_def: PromptDefinition,
        variables: Dict[str, Any],
    ) -> RenderedPrompt:
        """渲染为 JSON 格式"""
        import json

        template = prompt_def.template

        # 尝试解析为 JSON 模板
        try:
            # 变量替换
            template_str = template
            for var_name, var_value in variables.items():
                placeholder = f"{{{var_name}}}"
                template_str = template_str.replace(placeholder, str(var_value))

            # 解析 JSON
            data = json.loads(template_str)

            # 转换为消息格式
            messages = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "role" in item and "content" in item:
                        messages.append(
                            PromptMessage(
                                role=item["role"],
                                content=item["content"],
                            )
                        )
            elif isinstance(data, dict) and "messages" in data:
                for item in data["messages"]:
                    messages.append(
                        PromptMessage(
                            role=item["role"],
                            content=item["content"],
                        )
                    )

            return RenderedPrompt(
                messages=messages,
                format=PromptFormat.JSON,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON template: {e}")
            # 降级为文本格式
            return self._render_text(prompt_def, variables)


class PromptManager:
    """
    提示词管理器

    管理所有提示词模板
    """

    def __init__(self):
        self._prompts: Dict[str, PromptDefinition] = {}
        self._renderer = PromptRenderer()

    def register(
        self,
        name: str,
        template: str,
        description: str = "",
        variables: List[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """
        注册提示词

        Args:
            name: 提示词名称
            template: 提示词模板
            description: 提示词描述
            variables: 变量定义列表
            **kwargs: 额外参数
        """
        if name in self._prompts:
            logger.warning(f"Prompt '{name}' already registered, overwriting")

        # 转换变量定义
        var_objects = []
        for var_def in variables or []:
            var_objects.append(
                PromptVariable(
                    name=var_def["name"],
                    description=var_def.get("description", ""),
                    type=var_def.get("type", "string"),
                    required=var_def.get("required", True),
                    default=var_def.get("default"),
                    enum=var_def.get("enum"),
                )
            )

        prompt_def = PromptDefinition(
            name=name,
            template=template,
            description=description,
            variables=var_objects,
            **kwargs,
        )

        self._prompts[name] = prompt_def
        logger.info(f"Registered prompt: {name}")

    def unregister(self, name: str) -> None:
        """
        注销提示词

        Args:
            name: 提示词名称
        """
        if name in self._prompts:
            del self._prompts[name]
            logger.info(f"Unregistered prompt: {name}")

    def get(self, name: str) -> Optional[PromptDefinition]:
        """
        获取提示词定义

        Args:
            name: 提示词名称

        Returns:
            PromptDefinition 或 None
        """
        return self._prompts.get(name)

    def list_prompts(
        self,
        category: Optional[str] = None,
    ) -> List[PromptDefinition]:
        """
        列出提示词

        Args:
            category: 分类过滤

        Returns:
            提示词定义列表
        """
        prompts = list(self._prompts.values())

        if category:
            prompts = [p for p in prompts if p.category == category]

        return prompts

    def render(
        self,
        name: str,
        variables: Dict[str, Any],
    ) -> RenderedPrompt:
        """
        渲染提示词

        Args:
            name: 提示词名称
            variables: 变量值

        Returns:
            RenderedPrompt

        Raises:
            ValidationError: 提示词不存在或变量无效
        """
        prompt_def = self._prompts.get(name)
        if prompt_def is None:
            raise ValidationError(
                message=f"Prompt not found: {name}",
                field_errors={"name": "Prompt does not exist"},
            )

        return self._renderer.render(prompt_def, variables)

    def exists(self, name: str) -> bool:
        """
        检查提示词是否存在

        Args:
            name: 提示词名称

        Returns:
            是否存在
        """
        return name in self._prompts


# 全局提示词管理器
prompt_manager = PromptManager()


# ========================================
# 提示词装饰器
# ========================================

def prompt(
    name: str,
    description: str = "",
    variables: List[Dict[str, Any]] = None,
    **kwargs,
):
    """
    提示词装饰器

    用于注册提示词模板

    Args:
        name: 提示词名称
        description: 提示词描述
        variables: 变量定义
        **kwargs: 额外参数
    """
    def decorator(func: Callable) -> Callable:
        # 使用函数的文档字符串作为模板
        template = func.__doc__ or ""

        prompt_manager.register(
            name=name,
            template=template,
            description=description,
            variables=variables or [],
            **kwargs,
        )

        return func

    return decorator


__all__ = [
    "PromptFormat",
    "PromptVariable",
    "PromptDefinition",
    "PromptMessage",
    "RenderedPrompt",
    "PromptRenderer",
    "PromptManager",
    "prompt_manager",
    "prompt",
]
