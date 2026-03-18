"""
MCP Protocol Handlers
MCP 协议方法处理器
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.core.logging import get_logger
from backend.core.exceptions import InvalidParamsError, ToolNotFoundError, ResourceNotFoundError
from backend.config import settings

logger = get_logger(__name__)


class MCPProtocolHandler:
    """
    MCP 协议处理器

    实现 MCP 协议的核心方法：
    - initialize: 初始化连接
    - list_tools: 列出可用工具
    - call_tool: 调用工具
    - list_resources: 列出可用资源
    - read_resource: 读取资源
    - list_prompts: 列出可用提示词
    - get_prompt: 获取提示词
    """

    def __init__(self):
        self.initialized = False
        self.server_info = {
            "name": settings.MCP_SERVER_NAME,
            "version": settings.MCP_SERVER_VERSION,
        }
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {},
        }

        # 注册的组件
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._resources: Dict[str, Dict[str, Any]] = {}
        self._prompts: Dict[str, Dict[str, Any]] = {}

        # 请求日志
        self._request_log: List[Dict[str, Any]] = []

    async def initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        初始化 MCP 连接

        Args:
            params: 初始化参数
                - protocolVersion: 协议版本
                - capabilities: 客户端能力
                - clientInfo: 客户端信息

        Returns:
            服务器信息
        """
        protocol_version = params.get("protocolVersion")
        client_info = params.get("clientInfo", {})
        client_capabilities = params.get("capabilities", {})

        logger.info(
            f"MCP initialize request from {client_info.get('name', 'unknown')} "
            f"v{client_info.get('version', 'unknown')} "
            f"(protocol: {protocol_version})"
        )

        # 验证协议版本
        if protocol_version != settings.MCP_PROTOCOL_VERSION:
            logger.warning(
                f"Protocol version mismatch: expected {settings.MCP_PROTOCOL_VERSION}, "
                f"got {protocol_version}"
            )

        # 记录客户端能力
        logger.debug(f"Client capabilities: {client_capabilities}")

        # 标记为已初始化
        self.initialized = True

        return {
            "protocolVersion": settings.MCP_PROTOCOL_VERSION,
            "serverInfo": self.server_info,
            "capabilities": self.capabilities,
        }

    async def list_tools(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        列出可用工具

        Args:
            params: 参数（可选）

        Returns:
            工具列表
        """
        logger.debug("list_tools called")

        tools = []
        for tool_name, tool_def in self._tools.items():
            # tool_def 可能是 ToolDefinition 对象或字典
            if isinstance(tool_def, dict):
                description = tool_def.get("description", "")
                input_schema = tool_def.get("input_schema", {"type": "object"})
            else:
                description = tool_def.description
                input_schema = tool_def.input_schema

            tools.append({
                "name": tool_name,
                "description": description,
                "inputSchema": input_schema,
            })

        return {"tools": tools}

    async def call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用工具

        Args:
            params: 参数
                - name: 工具名称
                - arguments: 工具参数

        Returns:
            工具执行结果
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise InvalidParamsError("Missing tool name")

        logger.info(f"call_tool: {tool_name} with args: {arguments}")

        # 查找工具
        if tool_name not in self._tools:
            raise ToolNotFoundError(tool_name)

        tool_def = self._tools[tool_name]
        # tool_def 可能是 ToolDefinition 对象或字典
        if isinstance(tool_def, dict):
            handler = tool_def.get("handler")
        else:
            handler = tool_def.handler

        if not handler:
            raise ToolNotFoundError(tool_name)

        # 执行工具
        try:
            # 检查处理器签名，如果需要 context 参数则传递
            import inspect
            sig = inspect.signature(handler)
            if "context" in sig.parameters and len(sig.parameters) >= 2:
                # 处理器需要 context 参数
                result = await handler(arguments, {})
            else:
                # 处理器只需要 arguments
                result = await handler(arguments)
            logger.info(f"call_tool {tool_name} completed successfully")
            return {
                "content": result,
                "isError": False,
            }
        except Exception as e:
            logger.error(f"call_tool {tool_name} failed: {e}")
            return {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            }

    async def list_resources(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        列出可用资源

        Args:
            params: 参数（可选）

        Returns:
            资源列表
        """
        logger.debug("list_resources called")

        resources = []
        for resource_uri, resource_def in self._resources.items():
            resources.append({
                "uri": resource_uri,
                "name": resource_def.name if hasattr(resource_def, "name") else resource_uri,
                "description": resource_def.description if hasattr(resource_def, "description") else "",
                "mimeType": resource_def.mime_type if hasattr(resource_def, "mime_type") else "text/plain",
            })

        return {"resources": resources}

    async def read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        读取资源

        Args:
            params: 参数
                - uri: 资源 URI

        Returns:
            资源内容
        """
        uri = params.get("uri")

        if not uri:
            raise InvalidParamsError("Missing resource URI")

        logger.info(f"read_resource: {uri}")

        # 查找资源
        if uri not in self._resources:
            raise ResourceNotFoundError(uri)

        resource_def = self._resources[uri]
        handler = resource_def.handler

        if not handler:
            raise ResourceNotFoundError(uri)

        # 读取资源
        try:
            content = await handler(uri)
            logger.info(f"read_resource {uri} completed successfully")
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": resource_def.get("mime_type", "text/plain"),
                    "text": content,
                }],
            }
        except Exception as e:
            logger.error(f"read_resource {uri} failed: {e}")
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": f"Error reading resource: {e}",
                }],
            }

    async def list_prompts(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        列出可用提示词

        Args:
            params: 参数（可选）

        Returns:
            提示词列表
        """
        logger.debug("list_prompts called")

        prompts = []
        for prompt_name, prompt_def in self._prompts.items():
            prompts.append({
                "name": prompt_name,
                "description": prompt_def.get("description", ""),
                "arguments": prompt_def.get("arguments", []),
            })

        return {"prompts": prompts}

    async def get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取提示词

        Args:
            params: 参数
                - name: 提示词名称
                - arguments: 提示词参数

        Returns:
            渲染后的提示词
        """
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if not prompt_name:
            raise InvalidParamsError("Missing prompt name")

        logger.info(f"get_prompt: {prompt_name} with args: {arguments}")

        # 查找提示词
        if prompt_name not in self._prompts:
            raise InvalidParamsError(f"Prompt '{prompt_name}' not found")

        prompt_def = self._prompts[prompt_name]
        template = prompt_def.get("template", "")

        # 渲染提示词
        rendered = template
        for key, value in arguments.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))

        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": rendered,
                    },
                }
            ]
        }

    # ========================================
    # 工具注册方法
    # ========================================

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: callable,
    ) -> None:
        """
        注册工具

        Args:
            name: 工具名称
            description: 工具描述
            input_schema: 输入 JSON Schema
            handler: 处理函数
        """
        self._tools[name] = {
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }
        logger.info(f"Registered tool: {name}")

    def unregister_tool(self, name: str) -> None:
        """
        注销工具

        Args:
            name: 工具名称
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str,
        handler: callable,
    ) -> None:
        """
        注册资源

        Args:
            uri: 资源 URI
            name: 资源名称
            description: 资源描述
            mime_type: MIME 类型
            handler: 处理函数
        """
        self._resources[uri] = {
            "name": name,
            "description": description,
            "mime_type": mime_type,
            "handler": handler,
        }
        logger.info(f"Registered resource: {uri}")

    def register_prompt(
        self,
        name: str,
        description: str,
        template: str,
        arguments: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        注册提示词

        Args:
            name: 提示词名称
            description: 提示词描述
            template: 提示词模板
            arguments: 参数定义
        """
        self._prompts[name] = {
            "description": description,
            "template": template,
            "arguments": arguments or [],
        }
        logger.info(f"Registered prompt: {name}")

    # ========================================
    # 状态方法
    # ========================================

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "initialized": self.initialized,
            "tools_count": len(self._tools),
            "resources_count": len(self._resources),
            "prompts_count": len(self._prompts),
            "request_count": len(self._request_log),
        }

    def get_registered_tools(self) -> List[str]:
        """获取已注册的工具列表"""
        return list(self._tools.keys())

    def get_registered_resources(self) -> List[str]:
        """获取已注册的资源列表"""
        return list(self._resources.keys())

    def get_registered_prompts(self) -> List[str]:
        """获取已注册的提示词列表"""
        return list(self._prompts.keys())


# ========================================
# 默认处理器实例和工具注册
# ========================================

def create_default_handler() -> MCPProtocolHandler:
    """
    创建默认的 MCP 协议处理器

    Returns:
        MCPProtocolHandler 实例
    """
    handler = MCPProtocolHandler()

    # 注册示例工具
    async def echo_tool(args: Dict[str, Any]) -> List[Dict[str, Any]]:
        """回显工具"""
        message = args.get("message", "")
        return [{"type": "text", "text": f"Echo: {message}"}]

    handler.register_tool(
        name="echo",
        description="Echoes back the input message",
        input_schema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to echo back",
                },
            },
            "required": ["message"],
        },
        handler=echo_tool,
    )

    # 注册示例资源
    async def readme_resource(uri: str) -> str:
        """README 资源"""
        return f"# MCP System\n\nThis is a production-grade MCP system.\n\nVersion: {settings.MCP_SERVER_VERSION}"

    handler.register_resource(
        uri="file:///README.md",
        name="README",
        description="MCP System README",
        mime_type="text/markdown",
        handler=readme_resource,
    )

    # 注册示例提示词
    handler.register_prompt(
        name="summarize",
        description="Summarize the given text",
        template="Please summarize the following text:\n\n{text}",
        arguments=[
            {
                "name": "text",
                "description": "Text to summarize",
                "required": True,
            }
        ],
    )

    # 从全局工具注册表同步工具
    from backend.services.tools.registry import tool_registry
    for tool_name, tool_def in tool_registry._tools.items():
        # 将 ToolDefinition 对象转换为字典
        handler._tools[tool_name] = {
            "description": tool_def.description,
            "input_schema": tool_def.input_schema,
            "handler": tool_def.handler,
        }
        logger.debug(f"Synced tool '{tool_name}' to handler")

    return handler


__all__ = [
    "MCPProtocolHandler",
    "create_default_handler",
]
