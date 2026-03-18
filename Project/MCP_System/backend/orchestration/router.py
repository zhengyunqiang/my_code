"""
Request Router Module
请求路由器 - 将请求分发到相应处理器
"""

import asyncio
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

from backend.core.logging import get_logger
from backend.core.exceptions import InvalidRequestError, MethodNotFoundError
from backend.protocol.lifecycle import MCPLifecycleManager
from backend.gateway.auth import AuthContext
from backend.services.tools import tool_executor
from backend.services.resources import resource_manager
from backend.services.prompts import prompt_manager

logger = get_logger(__name__)


class RequestType(str, Enum):
    """请求类型"""
    INITIALIZE = "initialize"
    LIST_TOOLS = "list_tools"
    CALL_TOOL = "call_tool"
    LIST_RESOURCES = "list_resources"
    READ_RESOURCE = "read_resource"
    LIST_PROMPTS = "list_prompts"
    GET_PROMPT = "get_prompt"
    NOTIFICATION = "notification"


@dataclass
class RequestContext:
    """请求上下文"""
    request_id: str
    request_type: RequestType
    method: str
    params: Dict[str, Any]
    auth_context: Optional[AuthContext] = None
    lifecycle: Optional[MCPLifecycleManager] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """检查权限"""
        if self.auth_context is None:
            return False
        return permission in (self.auth_context.permissions or [])


@dataclass
class ResponseContext:
    """响应上下文"""
    request_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        if self.success:
            return {
                "result": self.result,
                "request_id": self.request_id,
            }
        else:
            return {
                "error": self.error,
                "request_id": self.request_id,
            }


class RequestRouter:
    """
    请求路由器

    将 MCP 请求路由到相应的处理器
    """

    def __init__(self):
        self._handlers: Dict[RequestType, Callable] = {}
        self._middleware: List[Callable] = []
        self._setup_default_handlers()

    def _setup_default_handlers(self) -> None:
        """设置默认处理器"""
        self._handlers = {
            RequestType.INITIALIZE: self._handle_initialize,
            RequestType.LIST_TOOLS: self._handle_list_tools,
            RequestType.CALL_TOOL: self._handle_call_tool,
            RequestType.LIST_RESOURCES: self._handle_list_resources,
            RequestType.READ_RESOURCE: self._handle_read_resource,
            RequestType.LIST_PROMPTS: self._handle_list_prompts,
            RequestType.GET_PROMPT: self._handle_get_prompt,
        }

    def register_handler(
        self,
        request_type: RequestType,
        handler: Callable,
    ) -> None:
        """
        注册处理器

        Args:
            request_type: 请求类型
            handler: 处理函数
        """
        self._handlers[request_type] = handler
        logger.info(f"Registered handler for: {request_type.value}")

    def add_middleware(self, middleware: Callable) -> None:
        """
        添加中间件

        Args:
            middleware: 中间件函数
        """
        self._middleware.append(middleware)

    async def route(
        self,
        request: RequestContext,
    ) -> ResponseContext:
        """
        路由请求

        Args:
            request: 请求上下文

        Returns:
            ResponseContext
        """
        try:
            # 执行前置中间件
            for middleware in self._middleware:
                await middleware(request, None)

            # 查找处理器
            handler = self._handlers.get(request.request_type)
            if handler is None:
                raise MethodNotFoundError(request.method)

            # 执行处理器
            result = await handler(request)

            # 执行后置中间件
            for middleware in reversed(self._middleware):
                await middleware(request, result)

            return ResponseContext(
                request_id=request.request_id,
                success=True,
                result=result,
            )

        except Exception as e:
            logger.error(
                f"Error routing request {request.request_id}: {e}",
                extra={"request_id": request.request_id},
            )

            # 执行错误中间件
            for middleware in reversed(self._middleware):
                try:
                    await middleware(request, e)
                except Exception as me:
                    logger.error(f"Middleware error: {me}")

            return ResponseContext(
                request_id=request.request_id,
                success=False,
                error={
                    "message": str(e),
                    "type": type(e).__name__,
                },
            )

    async def _handle_initialize(self, request: RequestContext) -> Dict[str, Any]:
        """处理初始化请求"""
        from backend.config import settings

        logger.info(f"Initialize request from client")

        # 更新生命周期
        if request.lifecycle:
            await request.lifecycle.initialize(
                client_info=request.params.get("clientInfo", {}),
                client_capabilities=request.params.get("capabilities", {}),
                protocol_version=request.params.get("protocolVersion", "2024-11-05"),
            )

        return {
            "protocolVersion": settings.MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": settings.MCP_SERVER_NAME,
                "version": settings.MCP_SERVER_VERSION,
            },
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
            },
        }

    async def _handle_list_tools(self, request: RequestContext) -> Dict[str, Any]:
        """处理列出工具请求"""
        from backend.services.tools import tool_registry

        tools = tool_registry.list_tools()
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
                for tool in tools
                if tool.status.value == "enabled"
            ]
        }

    async def _handle_call_tool(self, request: RequestContext) -> Dict[str, Any]:
        """处理调用工具请求"""
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if not tool_name:
            raise InvalidRequestError("Missing tool name")

        # 执行工具
        from backend.services.tools import ExecutionContext

        exec_context = ExecutionContext(
            request_id=request.request_id,
            user_id=request.auth_context.user_id if request.auth_context else None,
            session_id=request.metadata.get("session_id"),
        )

        result = await tool_executor.execute(tool_name, arguments, exec_context)

        return {
            "content": result.content,
            "isError": not result.success,
        }

    async def _handle_list_resources(self, request: RequestContext) -> Dict[str, Any]:
        """处理列出资源请求"""
        resources = resource_manager.list_resources()
        return {
            "resources": [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mime_type,
                }
                for r in resources
            ]
        }

    async def _handle_read_resource(self, request: RequestContext) -> Dict[str, Any]:
        """处理读取资源请求"""
        uri = request.params.get("uri")

        if not uri:
            raise InvalidRequestError("Missing resource URI")

        # 读取资源
        content = await resource_manager.read(
            uri,
            user_id=request.auth_context.user_id if request.auth_context else None,
        )

        return {
            "contents": [
                {
                    "uri": content.uri,
                    "mimeType": content.mime_type,
                    "text": content.text,
                }
            ]
        }

    async def _handle_list_prompts(self, request: RequestContext) -> Dict[str, Any]:
        """处理列出提示词请求"""
        prompts = prompt_manager.list_prompts()
        return {
            "prompts": [
                {
                    "name": p.name,
                    "description": p.description,
                    "arguments": [
                        {
                            "name": v.name,
                            "description": v.description,
                            "required": v.required,
                        }
                        for v in p.variables
                    ],
                }
                for p in prompts
            ]
        }

    async def _handle_get_prompt(self, request: RequestContext) -> Dict[str, Any]:
        """处理获取提示词请求"""
        name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if not name:
            raise InvalidRequestError("Missing prompt name")

        # 渲染提示词
        rendered = prompt_manager.render(name, arguments)

        return {
            "messages": [
                {
                    "role": msg.role,
                    "content": {
                        "type": "text",
                        "text": msg.content,
                    },
                }
                for msg in rendered.messages
            ]
        }


# 全局请求路由器
request_router = RequestRouter()


__all__ = [
    "RequestType",
    "RequestContext",
    "ResponseContext",
    "RequestRouter",
    "request_router",
]
