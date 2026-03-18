"""
Stdio Transport Implementation
stdio 传输协议 - 用于 Claude Desktop 集成
"""

import asyncio
import sys
from typing import Optional, Dict, Any

from backend.protocol.json_rpc import JSONRPCHandler
from backend.core.logging import get_logger
from backend.config import settings

logger = get_logger(__name__)


class StdioTransport:
    """
    stdio 传输协议

    通过标准输入输出与 Claude Desktop 通信
    实现 MCP 协议的 stdio 传输方式
    """

    def __init__(self):
        self.handler: Optional[JSONRPCHandler] = None
        self._running = False
        self._reader_task: Optional[asyncio.Task] = None

    async def run(self, handler: JSONRPCHandler) -> None:
        """
        运行 stdio 服务器

        Args:
            handler: JSON-RPC 处理器
        """
        self.handler = handler
        self._running = True

        logger.info("Starting stdio transport for MCP")

        # 创建读取任务
        self._reader_task = asyncio.create_task(self._read_messages())

        try:
            # 等待任务完成或被取消
            await self._reader_task
        except asyncio.CancelledError:
            logger.info("Stdio transport cancelled")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """停止 stdio 服务器"""
        if not self._running:
            return

        logger.info("Stopping stdio transport")
        self._running = False

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def _read_messages(self) -> None:
        """
        从 stdin 读取消息并处理

        消息格式：每行一个 JSON 对象（Content-Length 头可选）
        """
        while self._running:
            try:
                # 读取一行
                line = await self._read_line()

                if not line:
                    # EOF
                    logger.debug("Received EOF, shutting down")
                    break

                line = line.strip()

                if not line:
                    # 空行，跳过
                    continue

                # 解析 Content-Length（如果有）
                if line.lower().startswith("content-length:"):
                    # 读取空行
                    await self._read_line()
                    # 读取指定长度的内容
                    content_length = int(line.split(":")[1].strip())
                    message = await self._read_bytes(content_length)
                else:
                    # 直接解析 JSON
                    message = line

                logger.debug(f"Received message: {message[:200]}...")

                # 处理消息
                response = await self.handler.handle(message)

                # 发送响应（通知不返回响应）
                if response:
                    await self._send_message(response)

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # 发送错误响应
                if self.handler:
                    error_response = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "Internal error",
                            "data": {"detail": str(e)},
                        },
                        "id": None,
                    }
                    await self._send_message(error_response)

    async def _read_line(self) -> str:
        """
        从 stdin 读取一行

        Returns:
            读取的行（不含换行符）
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sys.stdin.readline)

    async def _read_bytes(self, count: int) -> str:
        """
        从 stdin 读取指定字节数

        Args:
            count: 字节数

        Returns:
            读取的字符串
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: sys.stdin.read(count))

    async def _send_message(self, message: str) -> None:
        """
        发送消息到 stdout

        Args:
            message: JSON 消息字符串
        """
        try:
            # 添加 Content-Length 头（推荐格式）
            content_length = len(message.encode("utf-8"))
            output = f"Content-Length: {content_length}\r\n\r\n{message}"

            # 写入 stdout
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: sys.stdout.write(output + "\n"))
            await loop.run_in_executor(None, sys.stdout.flush)

            logger.debug(f"Sent message: {message[:200]}...")

        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        发送通知（无响应的请求）

        Args:
            method: 方法名
            params: 参数
        """
        import json

        message = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            message["params"] = params

        await self._send_message(json.dumps(message, ensure_ascii=False))

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = None) -> None:
        """
        发送请求（但 stdio 模式下通常不会主动发送请求）

        Args:
            method: 方法名
            params: 参数
            request_id: 请求 ID
        """
        import json

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id or 1,
        }
        if params:
            message["params"] = params

        await self._send_message(json.dumps(message, ensure_ascii=False))


__all__ = ["StdioTransport"]
