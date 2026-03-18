"""
JSON-RPC 2.0 Handler
JSON-RPC 2.0 协议处理器
"""

import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

from backend.core.logging import get_logger
from backend.core.exceptions import (
    InvalidRequestError,
    MethodNotFoundError,
    InvalidParamsError,
    MCPError,
    handle_exception,
)

logger = get_logger(__name__)


class JSONRPCErrorCode(int, Enum):
    """JSON-RPC 2.0 错误码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class JSONRPCRequest:
    """JSON-RPC 请求"""
    jsonrpc: str = "2.0"
    method: str = ""
    params: Optional[Union[Dict[str, Any], List[Any]]] = None
    id: Optional[Union[str, int]] = None

    def is_notification(self) -> bool:
        """是否是通知（无 id 的请求）"""
        return self.id is None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.params is not None:
            result["params"] = self.params
        if self.id is not None:
            result["id"] = self.id
        return result


@dataclass
class JSONRPCResponse:
    """JSON-RPC 响应"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

    def is_error(self) -> bool:
        """是否是错误响应"""
        return self.error is not None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "jsonrpc": self.jsonrpc,
        }
        if self.result is not None:
            result["result"] = self.result
        if self.error is not None:
            result["error"] = self.error
        if self.id is not None:
            result["id"] = self.id
        return result


class JSONRPCParser:
    """JSON-RPC 消息解析器"""

    @staticmethod
    def parse(message: str) -> Union[JSONRPCRequest, List[JSONRPCRequest]]:
        """
        解析 JSON-RPC 消息

        Args:
            message: JSON 消息字符串

        Returns:
            JSONRPCRequest 或 List[JSONRPCRequest]

        Raises:
            InvalidRequestError: 无效请求
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise InvalidRequestError(
                message="Parse error",
                details={"original_message": message[:200]},
            )

        # 批量请求
        if isinstance(data, list):
            if not data:
                raise InvalidRequestError("Empty batch request")
            return [JSONRPCParser._parse_single_request(item) for item in data]

        # 单个请求
        return JSONRPCParser._parse_single_request(data)

    @staticmethod
    def _parse_single_request(data: Dict[str, Any]) -> JSONRPCRequest:
        """
        解析单个请求

        Args:
            data: 请求数据字典

        Returns:
            JSONRPCRequest

        Raises:
            InvalidRequestError: 无效请求
        """
        if not isinstance(data, dict):
            raise InvalidRequestError("Request must be an object")

        # 检查 jsonrpc 版本
        jsonrpc = data.get("jsonrpc", "2.0")
        if jsonrpc != "2.0":
            raise InvalidRequestError(
                message='Unsupported jsonrpc version',
                details={"version": jsonrpc, "expected": "2.0"},
            )

        # 检查 method
        method = data.get("method")
        if not method or not isinstance(method, str):
            raise InvalidRequestError(
                message="Missing or invalid method",
                details={"method": method},
            )

        # 创建请求对象
        request = JSONRPCRequest(
            jsonrpc=jsonrpc,
            method=method,
            params=data.get("params"),
            id=data.get("id"),
        )

        # 验证 params
        if request.params is not None:
            if not isinstance(request.params, (dict, list)):
                raise InvalidRequestError(
                    message="Invalid params type",
                    details={"params_type": type(request.params).__name__},
                )

        return request

    @staticmethod
    def serialize(response: Union[JSONRPCResponse, List[JSONRPCResponse]]) -> str:
        """
        序列化响应

        Args:
            response: JSONRPCResponse 或 List[JSONRPCResponse]

        Returns:
            JSON 字符串
        """
        if isinstance(response, list):
            data = [r.to_dict() for r in response]
        else:
            data = response.to_dict()
        return json.dumps(data, ensure_ascii=False)


class JSONRPCHandler:
    """
    JSON-RPC 请求处理器

    处理 JSON-RPC 请求并返回响应
    """

    def __init__(self):
        self.method_handlers: Dict[str, callable] = {}
        self.parser = JSONRPCParser()

    def register_method(self, name: str, handler: callable) -> None:
        """
        注册方法处理器

        Args:
            name: 方法名
            handler: 处理函数
        """
        self.method_handlers[name] = handler
        logger.debug(f"Registered JSON-RPC method: {name}")

    def unregister_method(self, name: str) -> None:
        """
        注销方法处理器

        Args:
            name: 方法名
        """
        if name in self.method_handlers:
            del self.method_handlers[name]
            logger.debug(f"Unregistered JSON-RPC method: {name}")

    def get_registered_methods(self) -> List[str]:
        """
        获取已注册的方法列表

        Returns:
            方法名列表
        """
        return list(self.method_handlers.keys())

    async def handle(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        处理 JSON-RPC 消息

        Args:
            message: JSON 消息字符串
            context: 请求上下文

        Returns:
            JSON 响应字符串（通知返回 None）
        """
        context = context or {}

        try:
            # 解析请求
            request = self.parser.parse(message)

            # 批量请求
            if isinstance(request, list):
                responses = []
                for req in request:
                    response = await self._handle_single_request(req, context)
                    if response is not None:  # 跳过通知的响应
                        responses.append(response)

                if responses:
                    return self.parser.serialize(responses)
                return None

            # 单个请求
            response = await self._handle_single_request(request, context)
            if response is not None:
                return self.parser.serialize(response)
            return None

        except MCPError as e:
            # MCP 错误
            error_response = JSONRPCResponse(
                error={
                    "code": e.code.value,
                    "message": e.message,
                    "data": e.details,
                },
                id=None,  # 解析阶段无 id
            )
            return self.parser.serialize(error_response)

        except Exception as e:
            # 未预期错误
            logger.exception(f"Unexpected error: {e}")
            error_response = JSONRPCResponse(
                error={
                    "code": JSONRPCErrorCode.INTERNAL_ERROR,
                    "message": "Internal error",
                    "data": {"detail": str(e)},
                },
                id=None,
            )
            return self.parser.serialize(error_response)

    async def _handle_single_request(
        self,
        request: JSONRPCRequest,
        context: Dict[str, Any],
    ) -> Optional[JSONRPCResponse]:
        """
        处理单个请求

        Args:
            request: JSONRPCRequest
            context: 请求上下文

        Returns:
            JSONRPCResponse 或 None（通知）
        """
        # 通知不需要响应
        if request.is_notification():
            await self._execute_method(request, context)
            return None

        try:
            # 执行方法
            result = await self._execute_method(request, context)
            return JSONRPCResponse(result=result, id=request.id)

        except MCPError as e:
            # MCP 错误
            return JSONRPCResponse(
                error={
                    "code": e.code.value,
                    "message": e.message,
                    "data": e.details,
                },
                id=request.id,
            )

        except Exception as e:
            # 未预期错误
            logger.exception(f"Error executing method {request.method}: {e}")
            return JSONRPCResponse(
                error={
                    "code": JSONRPCErrorCode.INTERNAL_ERROR,
                    "message": "Internal error",
                    "data": {"detail": str(e)},
                },
                id=request.id,
            )

    async def _execute_method(
        self,
        request: JSONRPCRequest,
        context: Dict[str, Any],
    ) -> Any:
        """
        执行方法

        Args:
            request: JSONRPCRequest
            context: 请求上下文

        Returns:
            方法执行结果

        Raises:
            MethodNotFoundError: 方法未找到
            InvalidParamsError: 参数无效
        """
        # 检查方法是否存在
        if request.method not in self.method_handlers:
            raise MethodNotFoundError(request.method)

        handler = self.method_handlers[request.method]

        # 准备参数
        if isinstance(request.params, dict):
            # 命名参数
            params = {**context, **request.params}
        elif isinstance(request.params, list):
            # 位置参数
            params = request.params
        else:
            # 无参数
            params = {}

        # 调用处理器
        if isinstance(request.params, dict):
            # 命名参数调用
            return await handler(**params)
        elif isinstance(request.params, list):
            # 位置参数调用
            return await handler(*request.params)
        else:
            # 无参数调用
            return await handler()


__all__ = [
    "JSONRPCErrorCode",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCParser",
    "JSONRPCHandler",
]
