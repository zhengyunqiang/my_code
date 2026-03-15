from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Optional, List
import json
import uuid
from datetime import datetime
import asyncio
from config import settings
from redis_client import redis_manager, RateLimiter, OnlineUserManager, RoomStateManager
from auth import auth_manager
from database import async_session_maker, User, Room, Message
from sqlalchemy import select


class ConnectionManager:
    def __init__(self):
        # 活跃的连接：client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

        # 连接信息：client_id -> connection info
        self.connection_info: Dict[str, dict] = {}

        # 用户到连接的映射：user_id -> set of client_ids
        self.user_connections: Dict[int, Set[str]] = {}

        # 房间到连接的映射：room_id -> set of client_ids
        self.room_connections: Dict[str, Set[str]] = {}

        # 速率限制器
        self.rate_limiter = RateLimiter(redis_manager)

        # 在线用户管理器
        self.online_manager = OnlineUserManager(redis_manager)

        # 房间状态管理器
        self.room_manager = RoomStateManager(redis_manager)

    async def connect(self, websocket: WebSocket) -> str:
        """接受新的 WebSocket 连接"""
        await websocket.accept()
        client_id = str(uuid.uuid4())

        # 保存连接
        self.active_connections[client_id] = websocket
        self.connection_info[client_id] = {
            "client_id": client_id,
            "connected_at": datetime.utcnow(),
            "last_heartbeat": datetime.utcnow(),
            "user_id": None,
            "current_room": None,
            "is_authenticated": False
        }

        return client_id

    async def disconnect(self, client_id: str):
        """断开连接"""
        # 获取连接信息
        conn_info = self.connection_info.get(client_id, {})
        user_id = conn_info.get("user_id")
        current_room = conn_info.get("current_room")

        # 从房间移除
        if current_room:
            await self.leave_room(client_id, current_room)

        # 从在线用户移除
        if user_id:
            await self.online_manager.remove_online_user(user_id)
            await auth_manager.update_user_online_status(user_id, False)

            # 从用户连接映射中移除
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(client_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

        # 移除连接
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.connection_info:
            del self.connection_info[client_id]

    async def send_personal_message(
        self,
        message: dict,
        client_id: str
    ) -> bool:
        """发送消息给特定客户端"""
        websocket = self.active_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                print(f"Send personal message error: {e}")
                return False
        return False

    async def broadcast_to_room(
        self,
        message: dict,
        room_id: str,
        exclude_client_id: Optional[str] = None
    ) -> int:
        """向房间内所有客户端广播消息"""
        clients = self.room_connections.get(room_id, set())
        count = 0

        for client_id in clients:
            if exclude_client_id and client_id == exclude_client_id:
                continue

            if await self.send_personal_message(message, client_id):
                count += 1

        return count

    async def broadcast_to_all(
        self,
        message: dict,
        exclude_client_id: Optional[str] = None
    ) -> int:
        """向所有连接广播消息"""
        count = 0
        for client_id in list(self.active_connections.keys()):
            if exclude_client_id and client_id == exclude_client_id:
                continue

            if await self.send_personal_message(message, client_id):
                count += 1

        return count

    async def join_room(
        self,
        client_id: str,
        room_id: str,
        user_id: Optional[int] = None
    ) -> bool:
        """加入房间"""
        try:
            # 获取连接信息
            conn_info = self.connection_info.get(client_id)
            if not conn_info:
                return False

            # 如果已经在房间中，先离开
            current_room = conn_info.get("current_room")
            if current_room:
                await self.leave_room(client_id, current_room)

            # 验证房间是否存在
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Room).where(Room.room_id == room_id, Room.is_active == True)
                )
                room = result.scalar_one_or_none()

                if not room:
                    return False

            # 添加到房间连接集合
            if room_id not in self.room_connections:
                self.room_connections[room_id] = set()
            self.room_connections[room_id].add(client_id)

            # 更新连接信息
            conn_info["current_room"] = room_id

            # 添加到 Redis 房间状态
            await self.room_manager.add_client_to_room(room_id, client_id, user_id)

            return True

        except Exception as e:
            print(f"Join room error: {e}")
            return False

    async def leave_room(self, client_id: str, room_id: str) -> bool:
        """离开房间"""
        try:
            # 获取连接信息
            conn_info = self.connection_info.get(client_id)
            if not conn_info:
                return False

            # 从房间连接集合中移除
            if room_id in self.room_connections:
                self.room_connections[room_id].discard(client_id)
                if not self.room_connections[room_id]:
                    del self.room_connections[room_id]

            # 更新连接信息
            if conn_info.get("current_room") == room_id:
                conn_info["current_room"] = None

            # 从 Redis 房间状态移除
            await self.room_manager.remove_client_from_room(room_id, client_id)

            return True

        except Exception as e:
            print(f"Leave room error: {e}")
            return False

    async def authenticate_user(
        self,
        client_id: str,
        token: str
    ) -> Optional[User]:
        """验证用户"""
        try:
            user = await get_current_user(token)
            if not user:
                return None

            # 更新连接信息
            conn_info = self.connection_info.get(client_id)
            if conn_info:
                conn_info["user_id"] = user.id
                conn_info["is_authenticated"] = True

            # 添加到用户连接映射
            if user.id not in self.user_connections:
                self.user_connections[user.id] = set()
            self.user_connections[user.id].add(client_id)

            # 更新在线状态
            await self.online_manager.add_online_user(user.id, client_id)
            await auth_manager.update_user_online_status(user.id, True)

            return user

        except Exception as e:
            print(f"Authenticate user error: {e}")
            return None

    async def check_rate_limit(
        self,
        client_id: str,
        limit: Optional[int] = None
    ) -> tuple[bool, int]:
        """检查速率限制"""
        if not settings.RATE_LIMIT_ENABLED:
            return True, settings.RATE_LIMIT_PER_MINUTE

        limit = limit or settings.RATE_LIMIT_PER_MINUTE
        return await self.rate_limiter.is_allowed(
            f"ws:{client_id}",
            limit,
            60
        )

    def get_connection_info(self, client_id: str) -> Optional[dict]:
        """获取连接信息"""
        return self.connection_info.get(client_id)

    def get_user_connections(self, user_id: int) -> Set[str]:
        """获取用户的所有连接"""
        return self.user_connections.get(user_id, set())

    def get_room_connections(self, room_id: str) -> Set[str]:
        """获取房间的所有连接"""
        return self.room_connections.get(room_id, set())

    async def update_heartbeat(self, client_id: str):
        """更新心跳时间"""
        conn_info = self.connection_info.get(client_id)
        if conn_info:
            conn_info["last_heartbeat"] = datetime.utcnow()

    async def cleanup_inactive_connections(self, timeout_seconds: int = 300):
        """清理不活跃的连接"""
        now = datetime.utcnow()
        inactive_clients = []

        for client_id, conn_info in self.connection_info.items():
            last_heartbeat = conn_info.get("last_heartbeat", conn_info.get("connected_at"))
            if (now - last_heartbeat).total_seconds() > timeout_seconds:
                inactive_clients.append(client_id)

        for client_id in inactive_clients:
            print(f"Cleaning up inactive client: {client_id}")
            websocket = self.active_connections.get(client_id)
            if websocket:
                try:
                    await websocket.close()
                except Exception:
                    pass
            await self.disconnect(client_id)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_connections": len(self.active_connections),
            "authenticated_connections": sum(
                1 for info in self.connection_info.values()
                if info.get("is_authenticated")
            ),
            "total_rooms": len(self.room_connections),
            "online_users": len(self.user_connections)
        }


# 全局连接管理器实例
manager = ConnectionManager()


# 从 auth.py 导入的函数
async def get_current_user(token: str) -> Optional[User]:
    """从 JWT token 获取当前用户"""
    try:
        payload = auth_manager.decode_access_token(token)
        if payload is None:
            return None

        user_id: int = payload.get("sub")
        if user_id is None:
            return None

        user = await auth_manager.get_user_by_id(user_id)
        return user
    except Exception as e:
        print(f"Get current user error: {e}")
        return None
