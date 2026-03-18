"""
HTTP/SSE Transport Implementation
HTTP/SSE 传输协议 - 用于生产环境
"""

import asyncio
import json
from typing import Optional, Dict, Any, AsyncIterator

from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from backend.protocol.json_rpc import JSONRPCHandler
from backend.core.logging import get_logger
from backend.config import settings

logger = get_logger(__name__)


class HTTPSseTransport:
    """
    HTTP/SSE 传输协议

    通过 HTTP 和 Server-Sent Events 与客户端通信
    实现 MCP 协议的 HTTP 传输方式
    """

    def __init__(self):
        self.handler: Optional[JSONRPCHandler] = None
        self._active_connections: Dict[str, Any] = {}

    async def handle_request(
        self,
        request: Request,
        handler: JSONRPCHandler,
    ) -> StreamingResponse:
        """
        处理 HTTP 请求

        Args:
            request: FastAPI Request 对象
            handler: JSON-RPC 处理器

        Returns:
            StreamingResponse
        """
        self.handler = handler

        # 读取请求体
        body = await request.body()
        message = body.decode("utf-8")

        logger.info(f"Received HTTP request: {message[:200]}...")

        # 提取请求上下文
        context = await self._extract_context(request)

        # 处理消息
        response = await handler.handle(message, context)

        if response is None:
            # 通知，返回 202
            return StreamingResponse(
                self._empty_stream(),
                media_type="text/plain",
                status_code=202,
            )

        # 返回 JSON 响应
        return StreamingResponse(
            self._response_stream(response),
            media_type="application/json",
        )

    async def handle_sse(
        self,
        request: Request,
        handler: JSONRPCHandler,
    ) -> EventSourceResponse:
        """
        处理 SSE 连接

        Args:
            request: FastAPI Request 对象
            handler: JSON-RPC 处理器

        Returns:
            EventSourceResponse
        """
        self.handler = handler

        # 生成连接 ID
        connection_id = f"conn_{id(request)}"
        self._active_connections[connection_id] = {
            "request": request,
            "queue": asyncio.Queue(),
        }

        logger.info(f"SSE connection established: {connection_id}")

        async def event_generator():
            """SSE 事件生成器"""
            try:
                # 发送连接成功事件
                yield {
                    "event": "connected",
                    "data": json.dumps({"connection_id": connection_id}),
                }

                # 持续监听消息
                while True:
                    try:
                        # 等待消息（带超时）
                        message = await asyncio.wait_for(
                            self._active_connections[connection_id]["queue"].get(),
                            timeout=30.0,
                        )

                        yield {
                            "event": "message",
                            "data": message,
                        }

                    except asyncio.TimeoutError:
                        # 发送心跳
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps({"timestamp": asyncio.get_event_loop().time()}),
                        }

            except asyncio.CancelledError:
                logger.info(f"SSE connection cancelled: {connection_id}")
            finally:
                # 清理连接
                if connection_id in self._active_connections:
                    del self._active_connections[connection_id]
                logger.info(f"SSE connection closed: {connection_id}")

        return EventSourceResponse(event_generator())

    async def _extract_context(self, request: Request) -> Dict[str, Any]:
        """
        提取请求上下文

        Args:
            request: FastAPI Request 对象

        Returns:
            上下文字典
        """
        context = {
            "transport_type": "http",
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "request_id": request.headers.get("x-request-id"),
        }

        # 从请求头提取认证信息
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            context["token"] = auth_header[7:]

        api_key = request.headers.get(settings.API_KEY_HEADER)
        if api_key:
            context["api_key"] = api_key

        return context

    async def _response_stream(self, response: str) -> AsyncIterator[str]:
        """
        响应流生成器

        Args:
            response: JSON 响应字符串

        Yields:
            响应块
        """
        yield response

    async def _empty_stream(self) -> AsyncIterator[str]:
        """
        空响应流

        Yields:
            空字符串
        """
        return
        yield  # pylint: disable=unreachable

    async def broadcast(self, message: str) -> None:
        """
        向所有 SSE 连接广播消息

        Args:
            message: 消息字符串
        """
        for connection_id, connection in self._active_connections.items():
            try:
                await connection["queue"].put(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {connection_id}: {e}")

    def get_active_connections(self) -> Dict[str, Any]:
        """
        获取活跃连接

        Returns:
            连接字典
        """
        return self._active_connections.copy()

    def get_connection_count(self) -> int:
        """
        获取连接数

        Returns:
            连接数量
        """
        return len(self._active_connections)


__all__ = ["HTTPSseTransport"]
