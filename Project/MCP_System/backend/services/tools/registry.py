"""
Tools Registry Module
工具注册表 - 管理所有可用的工具
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from backend.core.logging import get_logger
from backend.core.exceptions import ToolNotFoundError, ToolExecutionError, ToolTimeoutError

logger = get_logger(__name__)


class ToolStatus(str, Enum):
    """工具状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable
    status: ToolStatus = ToolStatus.ENABLED
    category: str = "general"
    timeout: int = 30
    is_async: bool = True
    is_idempotent: bool = True
    rate_limit: Optional[int] = None
    required_permissions: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "status": self.status.value,
            "category": self.category,
            "timeout": self.timeout,
            "isAsync": self.is_async,
            "isIdempotent": self.is_idempotent,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "examples": self.examples,
        }


class ToolRegistry:
    """
    工具注册表

    管理所有可用的工具，提供注册、查找、执行等功能
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._executors: Dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable,
        **kwargs,
    ) -> None:
        """
        注册工具

        Args:
            name: 工具名称（唯一）
            description: 工具描述
            input_schema: 输入 JSON Schema
            handler: 处理函数
            **kwargs: 额外参数
        """
        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered, overwriting")

        tool_def = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            **kwargs,
        )

        self._tools[name] = tool_def
        logger.info(f"Registered tool: {name} (category: {tool_def.category})")

    def unregister(self, name: str) -> None:
        """
        注销工具

        Args:
            name: 工具名称
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")

    def get(self, name: str) -> Optional[ToolDefinition]:
        """
        获取工具定义

        Args:
            name: 工具名称

        Returns:
            工具定义，不存在返回 None
        """
        return self._tools.get(name)

    def list_tools(
        self,
        category: Optional[str] = None,
        status: Optional[ToolStatus] = None,
    ) -> List[ToolDefinition]:
        """
        列出工具

        Args:
            category: 分类过滤
            status: 状态过滤

        Returns:
            工具定义列表
        """
        tools = list(self._tools.values())

        if category:
            tools = [t for t in tools if t.category == category]

        if status:
            tools = [t for t in tools if t.status == status]

        return tools

    def list_by_category(self) -> Dict[str, List[str]]:
        """
        按分类列出工具

        Returns:
            分类到工具名称列表的映射
        """
        result: Dict[str, List[str]] = {}
        for tool in self._tools.values():
            if tool.category not in result:
                result[tool.category] = []
            result[tool.category].append(tool.name)
        return result

    def exists(self, name: str) -> bool:
        """
        检查工具是否存在

        Args:
            name: 工具名称

        Returns:
            是否存在
        """
        return name in self._tools

    def is_enabled(self, name: str) -> bool:
        """
        检查工具是否启用

        Args:
            name: 工具名称

        Returns:
            是否启用
        """
        tool = self._tools.get(name)
        return tool is not None and tool.status == ToolStatus.ENABLED

    def enable(self, name: str) -> None:
        """
        启用工具

        Args:
            name: 工具名称
        """
        if name in self._tools:
            self._tools[name].status = ToolStatus.ENABLED
            logger.info(f"Enabled tool: {name}")

    def disable(self, name: str) -> None:
        """
        禁用工具

        Args:
            name: 工具名称
        """
        if name in self._tools:
            self._tools[name].status = ToolStatus.DISABLED
            logger.info(f"Disabled tool: {name}")

    def get_count(self) -> int:
        """
        获取工具数量

        Returns:
            工具总数
        """
        return len(self._tools)


# 全局工具注册表
tool_registry = ToolRegistry()


# ========================================
# 工具装饰器
# ========================================

def tool(
    name: str,
    description: str = "",
    category: str = "general",
    timeout: int = 30,
    is_idempotent: bool = True,
    **kwargs,
):
    """
    工具装饰器

    用于将函数注册为工具

    Args:
        name: 工具名称
        description: 工具描述
        category: 工具分类
        timeout: 超时时间（秒）
        is_idempotent: 是否幂等
        **kwargs: 额外参数
    """
    def decorator(func: Callable) -> Callable:
        # 提取输入 Schema（从函数签名或 docstring）
        input_schema = extract_input_schema(func)

        tool_registry.register(
            name=name,
            description=description or func.__doc__ or "",
            input_schema=input_schema,
            handler=func,
            category=category,
            timeout=timeout,
            is_idempotent=is_idempotent,
            is_async=asyncio.iscoroutinefunction(func),
            **kwargs,
        )

        return func

    return decorator


def extract_input_schema(func: Callable) -> Dict[str, Any]:
    """
    从函数提取输入 Schema

    Args:
        func: 函数对象

    Returns:
        JSON Schema
    """
    # 简化实现：返回基本的 object schema
    # 实际应该解析函数签名和类型注解
    import inspect

    schema = {
        "type": "object",
        "properties": {},
    }

    sig = inspect.signature(func)
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ["self", "cls", "kwargs"]:
            continue

        param_type = "string"

        # 简单的类型推断
        if param.annotation != inspect.Parameter.empty:
            annotation_str = str(param.annotation)
            if "int" in annotation_str:
                param_type = "integer"
            elif "float" in annotation_str or "double" in annotation_str:
                param_type = "number"
            elif "bool" in annotation_str:
                param_type = "boolean"
            elif "list" in annotation_str or "List" in annotation_str:
                param_type = "array"
            elif "dict" in annotation_str or "Dict" in annotation_str:
                param_type = "object"

        schema["properties"][param_name] = {"type": param_type}

        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    if required:
        schema["required"] = required

    return schema


__all__ = [
    "ToolStatus",
    "ToolDefinition",
    "ToolRegistry",
    "tool_registry",
    "tool",
]
