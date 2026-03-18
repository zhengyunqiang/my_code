"""
MCP Protocol Lifecycle Management
生命周期管理 - 连接握手、能力协商、心跳检测
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum

from backend.core.logging import get_logger
from backend.config import settings

logger = get_logger(__name__)


class ConnectionState(str, Enum):
    """连接状态"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    INITIALIZED = "initialized"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ClientInfo:
    """客户端信息"""
    name: str = "unknown"
    version: str = "0.0.0"
    protocol_version: str = "2024-11-05"


@dataclass
class ClientCapabilities:
    """客户端能力"""
    roots: bool = False
    sampling: bool = False
    resources: bool = False
    tools: bool = False
    prompts: bool = False


@dataclass
class ConnectionMetrics:
    """连接指标"""
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requests_sent: int = 0
    requests_received: int = 0
    errors: int = 0


class MCPLifecycleManager:
    """
    MCP 生命周期管理器

    管理 MCP 连接的完整生命周期：
    1. 连接建立
    2. 握手初始化
    3. 能力协商
    4. 消息交换
    5. 心跳维持
    6. 连接关闭
    """

    def __init__(
        self,
        heartbeat_interval: int = 30,
        heartbeat_timeout: int = 90,
        max_retries: int = 3,
    ):
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_retries = max_retries

        # 连接状态
        self.state = ConnectionState.DISCONNECTED
        self.connection_id: Optional[str] = None

        # 客户端信息
        self.client_info = ClientInfo()
        self.client_capabilities = ClientCapabilities()

        # 服务器能力
        self.server_capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {},
        }

        # 指标
        self.metrics = ConnectionMetrics()

        # 心跳任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        # 回调函数
        self._on_message_callbacks: list = []
        self._on_error_callbacks: list = []
        self._on_disconnect_callbacks: list = []

    async def connect(self, connection_id: str) -> None:
        """
        建立连接

        Args:
            connection_id: 连接 ID
        """
        logger.info(f"Connecting: {connection_id}")

        self.connection_id = connection_id
        self.state = ConnectionState.CONNECTING
        self.metrics.connected_at = datetime.now(timezone.utc)

        # 启动心跳
        await self._start_heartbeat()

    async def initialize(
        self,
        client_info: Dict[str, Any],
        client_capabilities: Dict[str, Any],
        protocol_version: str,
    ) -> Dict[str, Any]:
        """
        初始化连接（握手）

        Args:
            client_info: 客户端信息
            client_capabilities: 客户端能力
            protocol_version: 协议版本

        Returns:
            服务器响应
        """
        logger.info(
            f"Initializing connection from {client_info.get('name', 'unknown')} "
            f"v{client_info.get('version', 'unknown')}"
        )

        # 更新客户端信息
        self.client_info = ClientInfo(
            name=client_info.get("name", "unknown"),
            version=client_info.get("version", "0.0.0"),
            protocol_version=protocol_version,
        )

        # 更新客户端能力
        self.client_capabilities = ClientCapabilities(
            roots=client_capabilities.get("roots", False),
            sampling=client_capabilities.get("sampling", False),
            resources=client_capabilities.get("resources", False),
            tools=client_capabilities.get("tools", False),
            prompts=client_capabilities.get("prompts", False),
        )

        # 更新状态
        self.state = ConnectionState.INITIALIZED

        logger.info(
            f"Connection initialized - Client: {self.client_info.name} "
            f"v{self.client_info.version}, "
            f"Capabilities: {self.client_capabilities}"
        )

        # 返回服务器信息
        return {
            "protocolVersion": settings.MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": settings.MCP_SERVER_NAME,
                "version": settings.MCP_SERVER_VERSION,
            },
            "capabilities": self.server_capabilities,
        }

    async def disconnect(self, reason: Optional[str] = None) -> None:
        """
        断开连接

        Args:
            reason: 断开原因
        """
        logger.info(f"Disconnecting: {self.connection_id}, reason: {reason}")

        self.state = ConnectionState.DISCONNECTING

        # 停止心跳
        await self._stop_heartbeat()

        # 触发断开回调
        await self._trigger_disconnect_callbacks(reason)

        self.state = ConnectionState.DISCONNECTED

    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        发送消息

        Args:
            message: 消息字典
        """
        if self.state == ConnectionState.DISCONNECTED:
            raise RuntimeError("Connection is not established")

        self.metrics.requests_sent += 1
        self.metrics.last_activity = datetime.now(timezone.utc)

        logger.debug(f"Sending message: {message.get('method', 'response')}")

        # 触发消息回调
        await self._trigger_message_callbacks(message)

    async def receive_message(self, message: Dict[str, Any]) -> None:
        """
        接收消息

        Args:
            message: 消息字典
        """
        self.metrics.requests_received += 1
        self.metrics.last_activity = datetime.now(timezone.utc)

        logger.debug(f"Received message: {message.get('method', 'request')}")

    def record_error(self, error: Exception) -> None:
        """
        记录错误

        Args:
            error: 异常对象
        """
        self.metrics.errors += 1
        logger.error(f"Connection error: {error}")

        # 触发错误回调
        asyncio.create_task(self._trigger_error_callbacks(error))

    async def _start_heartbeat(self) -> None:
        """启动心跳"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.debug(f"Heartbeat started (interval: {self.heartbeat_interval}s)")

    async def _stop_heartbeat(self) -> None:
        """停止心跳"""
        self._running = False

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        logger.debug("Heartbeat stopped")

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        try:
            while self._running:
                await asyncio.sleep(self.heartbeat_interval)

                if not self._running:
                    break

                # 检查超时
                idle_time = (
                    datetime.now(timezone.utc) - self.metrics.last_activity
                ).total_seconds()

                if idle_time > self.heartbeat_timeout:
                    logger.warning(
                        f"Heartbeat timeout: {idle_time}s > {self.heartbeat_timeout}s"
                    )
                    await self.disconnect("heartbeat timeout")
                    break

                # 发送心跳
                await self._send_heartbeat()

        except asyncio.CancelledError:
            pass

    async def _send_heartbeat(self) -> None:
        """发送心跳"""
        logger.debug("Sending heartbeat")

        heartbeat_message = {
            "jsonrpc": "2.0",
            "method": "notifications/heartbeat",
            "params": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        await self.send_message(heartbeat_message)

    def register_message_callback(self, callback: Callable) -> None:
        """
        注册消息回调

        Args:
            callback: 回调函数
        """
        self._on_message_callbacks.append(callback)

    def register_error_callback(self, callback: Callable) -> None:
        """
        注册错误回调

        Args:
            callback: 回调函数
        """
        self._on_error_callbacks.append(callback)

    def register_disconnect_callback(self, callback: Callable) -> None:
        """
        注册断开回调

        Args:
            callback: 回调函数
        """
        self._on_disconnect_callbacks.append(callback)

    async def _trigger_message_callbacks(self, message: Dict[str, Any]) -> None:
        """触发消息回调"""
        for callback in self._on_message_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

    async def _trigger_error_callbacks(self, error: Exception) -> None:
        """触发错误回调"""
        for callback in self._on_error_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error)
                else:
                    callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    async def _trigger_disconnect_callbacks(self, reason: Optional[str]) -> None:
        """触发断开回调"""
        for callback in self._on_disconnect_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason)
                else:
                    callback(reason)
            except Exception as e:
                logger.error(f"Error in disconnect callback: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        获取连接状态

        Returns:
            状态字典
        """
        idle_time = (
            datetime.now(timezone.utc) - self.metrics.last_activity
        ).total_seconds()

        return {
            "connection_id": self.connection_id,
            "state": self.state.value,
            "client": {
                "name": self.client_info.name,
                "version": self.client_info.version,
                "protocol_version": self.client_info.protocol_version,
            },
            "capabilities": {
                "client": self.client_capabilities.__dict__,
                "server": self.server_capabilities,
            },
            "metrics": {
                "connected_at": self.metrics.connected_at.isoformat(),
                "last_activity": self.metrics.last_activity.isoformat(),
                "idle_time_seconds": idle_time,
                "requests_sent": self.metrics.requests_sent,
                "requests_received": self.metrics.requests_received,
                "errors": self.metrics.errors,
            },
            "heartbeat": {
                "interval": self.heartbeat_interval,
                "timeout": self.heartbeat_timeout,
                "running": self._running,
            },
        }

    def is_connected(self) -> bool:
        """
        检查是否已连接

        Returns:
            是否连接
        """
        return self.state in (
            ConnectionState.CONNECTED,
            ConnectionState.INITIALIZED,
        )

    def is_initialized(self) -> bool:
        """
        检查是否已初始化

        Returns:
            是否初始化
        """
        return self.state == ConnectionState.INITIALIZED


__all__ = [
    "ConnectionState",
    "ClientInfo",
    "ClientCapabilities",
    "ConnectionMetrics",
    "MCPLifecycleManager",
]
