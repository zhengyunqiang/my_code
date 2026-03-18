"""
Context Manager Module
上下文管理器 - 管理请求上下文和会话状态
"""

import uuid
import time
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import asyncio

from backend.core.logging import get_logger

logger = get_logger(__name__)


class SessionState(str, Enum):
    """会话状态"""
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


@dataclass
class MessageContext:
    """消息上下文"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    role: str = "user"  # user, assistant, system
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class SessionContext:
    """会话上下文"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[int] = None
    state: SessionState = SessionState.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0
    capabilities: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_history: List[MessageContext] = field(default_factory=list)

    def update_activity(self) -> None:
        """更新活动时间"""
        self.last_activity = datetime.now(timezone.utc)
        self.message_count += 1

    def add_message(self, role: str, content: str, **metadata) -> MessageContext:
        """添加消息到历史"""
        msg = MessageContext(role=role, content=content, metadata=metadata)
        self.message_history.append(msg)
        self.update_activity()
        return msg

    def get_idle_time(self) -> float:
        """获取空闲时间（秒）"""
        return (datetime.now(timezone.utc) - self.last_activity).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "message_count": self.message_count,
            "capabilities": list(self.capabilities),
            "metadata": self.metadata,
        }


@dataclass
class RequestContext:
    """请求上下文"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    transport: str = "unknown"  # stdio, http
    client_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "method": self.method,
            "params": self.params,
            "timestamp": self.timestamp.isoformat(),
            "transport": self.transport,
            "client_info": self.client_info,
            "metadata": self.metadata,
        }


class ContextManager:
    """
    上下文管理器

    管理请求上下文和会话状态
    """

    def __init__(self, session_timeout: int = 3600, max_messages: int = 1000):
        """
        初始化上下文管理器

        Args:
            session_timeout: 会话超时时间（秒）
            max_messages: 最大消息历史数量
        """
        self._sessions: Dict[str, SessionContext] = {}
        self._session_timeout = session_timeout
        self._max_messages = max_messages

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动上下文管理器"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Context manager started")

    async def stop(self) -> None:
        """停止上下文管理器"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Context manager stopped")

    def create_session(
        self,
        user_id: Optional[int] = None,
        capabilities: Optional[Set[str]] = None,
        **metadata,
    ) -> SessionContext:
        """
        创建会话

        Args:
            user_id: 用户 ID
            capabilities: 能力集合
            **metadata: 额外元数据

        Returns:
            SessionContext
        """
        session = SessionContext(
            user_id=user_id,
            capabilities=capabilities or set(),
            metadata=metadata,
        )

        self._sessions[session.session_id] = session
        logger.info(f"Created session: {session.session_id}")

        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """
        获取会话

        Args:
            session_id: 会话 ID

        Returns:
            SessionContext 或 None
        """
        return self._sessions.get(session_id)

    def update_session(
        self,
        session_id: str,
        **updates,
    ) -> Optional[SessionContext]:
        """
        更新会话

        Args:
            session_id: 会话 ID
            **updates: 更新字段

        Returns:
            更新后的 SessionContext 或 None
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)

        session.update_activity()
        return session

    def close_session(self, session_id: str) -> bool:
        """
        关闭会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        session.state = SessionState.CLOSED
        del self._sessions[session_id]

        logger.info(f"Closed session: {session_id}")
        return True

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        **metadata,
    ) -> Optional[MessageContext]:
        """
        添加消息到会话

        Args:
            session_id: 会话 ID
            role: 角色
            content: 内容
            **metadata: 额外元数据

        Returns:
            MessageContext 或 None
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        msg = session.add_message(role, content, **metadata)

        # 限制消息历史
        if len(session.message_history) > self._max_messages:
            session.message_history = session.message_history[-self._max_messages:]

        return msg

    def get_message_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[MessageContext]:
        """
        获取消息历史

        Args:
            session_id: 会话 ID
            limit: 限制数量

        Returns:
            消息上下文列表
        """
        session = self._sessions.get(session_id)
        if session is None:
            return []

        history = session.message_history
        if limit:
            return history[-limit:]
        return history

    def get_active_sessions(self) -> List[SessionContext]:
        """
        获取活跃会话

        Returns:
            会话上下文列表
        """
        return [
            session for session in self._sessions.values()
            if session.state == SessionState.ACTIVE
        ]

    def get_session_count(self) -> int:
        """
        获取会话数量

        Returns:
            会话数量
        """
        return len(self._sessions)

    async def _cleanup_loop(self) -> None:
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                now = datetime.now(timezone.utc)
                expired_sessions = []

                for session_id, session in self._sessions.items():
                    idle_time = session.get_idle_time()
                    if idle_time > self._session_timeout:
                        expired_sessions.append(session_id)

                for session_id in expired_sessions:
                    logger.info(f"Session expired: {session_id}")
                    self.close_session(session_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计字典
        """
        active_sessions = self.get_active_sessions()

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len(active_sessions),
            "session_timeout": self._session_timeout,
            "max_messages": self._max_messages,
        }


# 全局上下文管理器
context_manager = ContextManager()


__all__ = [
    "SessionState",
    "MessageContext",
    "SessionContext",
    "RequestContext",
    "ContextManager",
    "context_manager",
]
