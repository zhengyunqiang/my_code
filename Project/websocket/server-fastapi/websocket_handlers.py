from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
from datetime import datetime
import json

from websocket_manager import manager
from auth import auth_manager
from redis_client import redis_manager
from database import async_session_maker, User, Room, Message
from sqlalchemy import select


class WebSocketHandlers:
    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id

    async def handle_message(self, message: Dict[str, Any]):
        """处理接收到的消息"""
        message_type = message.get("type")
        action = message.get("action")
        data = message.get("data", {})

        # 检查速率限制
        allowed, remaining = await manager.check_rate_limit(self.client_id)
        if not allowed:
            await self.send_error("rate_limit_exceeded", "Too many messages. Please slow down.")
            return

        # 更新心跳
        await manager.update_heartbeat(self.client_id)

        # 路由消息到对应的处理器
        handler_map = {
            "auth": self.handle_auth,
            "chat": self.handle_chat,
            "room": self.handle_room,
            "user": self.handle_user,
            "system": self.handle_system,
            "presence": self.handle_presence,
        }

        handler = handler_map.get(message_type)
        if handler:
            try:
                await handler(action, data)
            except Exception as e:
                print(f"Handler error for {message_type}.{action}: {e}")
                await self.send_error("handler_error", str(e))
        else:
            await self.send_error("unknown_type", f"Unknown message type: {message_type}")

    async def handle_auth(self, action: str, data: Dict[str, Any]):
        """处理认证相关消息"""
        if action == "login":
            await self.handle_login(data)
        elif action == "register":
            await self.handle_register(data)
        elif action == "logout":
            await self.handle_logout(data)
        else:
            await self.send_error("unknown_action", f"Unknown auth action: {action}")

    async def handle_login(self, data: Dict[str, Any]):
        """处理登录"""
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            await self.send_error("invalid_credentials", "Username and password are required")
            return

        user = await auth_manager.authenticate_user(username, password)
        if user:
            # 创建 token
            access_token = auth_manager.create_access_token(
                data={"sub": str(user.id)},
            )

            # 验证连接
            authenticated_user = await manager.authenticate_user(self.client_id, access_token)
            if authenticated_user:
                await self.send_message("auth", "login_success", {
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "display_name": user.display_name,
                        "avatar_url": user.avatar_url,
                        "is_online": True,
                    },
                    "access_token": access_token,
                    "token_type": "bearer"
                })

                # 广播用户上线
                await manager.broadcast_to_all({
                    "type": "presence",
                    "action": "user_online",
                    "data": {
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "display_name": user.display_name,
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }, exclude_client_id=self.client_id)
            else:
                await self.send_error("auth_failed", "Authentication failed")
        else:
            await self.send_error("invalid_credentials", "Invalid username or password")

    async def handle_register(self, data: Dict[str, Any]):
        """处理注册"""
        username = data.get("username")
        password = data.get("password")
        email = data.get("email")
        display_name = data.get("display_name")

        if not username or not password:
            await self.send_error("invalid_input", "Username and password are required")
            return

        # 检查用户是否已存在
        existing_user = await auth_manager.get_user_by_username(username)
        if existing_user:
            await self.send_error("user_exists", "Username already exists")
            return

        # 创建用户
        try:
            user = await auth_manager.create_user(username, password, email, display_name)
            await self.send_message("auth", "register_success", {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                }
            })
        except Exception as e:
            await self.send_error("registration_failed", str(e))

    async def handle_logout(self, data: Dict[str, Any]):
        """处理登出"""
        conn_info = manager.get_connection_info(self.client_id)
        if conn_info:
            user_id = conn_info.get("user_id")
            if user_id:
                await manager.online_manager.remove_online_user(user_id)
                await auth_manager.update_user_online_status(user_id, False)

                # 更新连接信息
                conn_info["is_authenticated"] = False
                conn_info["user_id"] = None

        await self.send_message("auth", "logout_success", {"message": "Logged out successfully"})

    async def handle_chat(self, action: str, data: Dict[str, Any]):
        """处理聊天相关消息"""
        conn_info = manager.get_connection_info(self.client_id)
        if not conn_info or not conn_info.get("is_authenticated"):
            await self.send_error("not_authenticated", "Please login first")
            return

        if action == "message":
            await self.handle_chat_message(data, conn_info)
        elif action == "private":
            await self.handle_private_message(data, conn_info)
        elif action == "typing":
            await self.handle_typing(data, conn_info)
        elif action == "history":
            await self.handle_message_history(data, conn_info)
        else:
            await self.send_error("unknown_action", f"Unknown chat action: {action}")

    async def handle_chat_message(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理聊天消息"""
        content = data.get("content")
        room_id = data.get("room") or conn_info.get("current_room")

        if not content:
            await self.send_error("invalid_message", "Message content is required")
            return

        if not room_id:
            await self.send_error("no_room", "You must join a room first")
            return

        # 获取用户信息
        user_id = conn_info.get("user_id")
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

        if not user:
            await self.send_error("user_not_found", "User not found")
            return

        # 创建消息对象
        message_data = {
            "type": "chat",
            "action": "message",
            "data": {
                "content": content,
                "room": room_id,
                "sender": {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        # 保存到数据库
        try:
            async with async_session_maker() as session:
                db_message = Message(
                    room_id=room_id,
                    user_id=user.id,
                    content=content,
                    message_type="text"
                )
                session.add(db_message)
                await session.commit()
        except Exception as e:
            print(f"Save message error: {e}")

        # 保存到 Redis 历史记录
        await manager.room_manager.add_message_to_history(room_id, message_data["data"])

        # 广播到房间
        await manager.broadcast_to_room(message_data, room_id)

    async def handle_private_message(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理私信"""
        to_username = data.get("to")
        content = data.get("content")

        if not to_username or not content:
            await self.send_error("invalid_message", "Recipient and content are required")
            return

        # 获取发送者信息
        user_id = conn_info.get("user_id")
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            sender = result.scalar_one_or_none()

        if not sender:
            await self.send_error("user_not_found", "User not found")
            return

        # 查找接收者
        recipient = await auth_manager.get_user_by_username(to_username)
        if not recipient:
            await self.send_error("recipient_not_found", "Recipient not found")
            return

        # 检查接收者是否在线
        is_online = await manager.online_manager.is_online(recipient.id)

        # 创建消息对象
        message_data = {
            "type": "chat",
            "action": "private_message",
            "data": {
                "content": content,
                "from": {
                    "id": sender.id,
                    "username": sender.username,
                    "display_name": sender.display_name,
                    "avatar_url": sender.avatar_url
                },
                "to": to_username,
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        # 发送给接收者
        if is_online:
            recipient_connections = manager.get_user_connections(recipient.id)
            for client_id in recipient_connections:
                await manager.send_personal_message(message_data, client_id)

        # 确认发送给发送者
        await self.send_message("chat", "private_sent", {
            "delivered": is_online,
            "recipient": to_username
        })

    async def handle_typing(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理输入状态"""
        is_typing = data.get("isTyping", False)
        room_id = data.get("room") or conn_info.get("current_room")

        if not room_id:
            return

        user_id = conn_info.get("user_id")
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

        if user:
            await manager.broadcast_to_room({
                "type": "chat",
                "action": "typing",
                "data": {
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "display_name": user.display_name
                    },
                    "isTyping": is_typing,
                    "room": room_id
                }
            }, room_id, exclude_client_id=self.client_id)

    async def handle_message_history(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理消息历史请求"""
        room_id = data.get("room") or conn_info.get("current_room")
        limit = data.get("limit", 50)

        if not room_id:
            await self.send_error("no_room", "Room not specified")
            return

        # 从 Redis 获取历史记录
        history = await manager.room_manager.get_message_history(room_id, limit)

        await self.send_message("chat", "history", {
            "room": room_id,
            "messages": history
        })

    async def handle_room(self, action: str, data: Dict[str, Any]):
        """处理房间相关消息"""
        conn_info = manager.get_connection_info(self.client_id)
        if not conn_info or not conn_info.get("is_authenticated"):
            await self.send_error("not_authenticated", "Please login first")
            return

        if action == "join":
            await self.handle_join_room(data, conn_info)
        elif action == "leave":
            await self.handle_leave_room(data, conn_info)
        elif action == "create":
            await self.handle_create_room(data, conn_info)
        elif action == "list":
            await self.handle_list_rooms(data)
        elif action == "info":
            await self.handle_room_info(data)
        else:
            await self.send_error("unknown_action", f"Unknown room action: {action}")

    async def handle_join_room(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理加入房间"""
        room_id = data.get("roomId")
        password = data.get("password")

        if not room_id:
            await self.send_error("invalid_room", "Room ID is required")
            return

        # 验证房间
        async with async_session_maker() as session:
            result = await session.execute(
                select(Room).where(Room.room_id == room_id, Room.is_active == True)
            )
            room = result.scalar_one_or_none()

        if not room:
            await self.send_error("room_not_found", "Room not found")
            return

        # 检查密码
        if room.is_private and room.password:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            if not pwd_context.verify(password, room.password):
                await self.send_error("invalid_password", "Invalid room password")
                return

        # 加入房间
        success = await manager.join_room(
            self.client_id,
            room_id,
            conn_info.get("user_id")
        )

        if success:
            # 获取历史记录
            history = await manager.room_manager.get_message_history(room_id)

            await self.send_message("room", "joined", {
                "room": {
                    "id": room.id,
                    "room_id": room.room_id,
                    "name": room.name,
                    "description": room.description,
                    "clientCount": await manager.room_manager.get_room_client_count(room_id),
                    "hasPassword": bool(room.password)
                },
                "history": history
            })

            # 通知房间内其他用户
            user_id = conn_info.get("user_id")
            async with async_session_maker() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

            if user:
                await manager.broadcast_to_room({
                    "type": "presence",
                    "action": "user_joined",
                    "data": {
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "display_name": user.display_name,
                        },
                        "room": room_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }, room_id, exclude_client_id=self.client_id)
        else:
            await self.send_error("join_failed", "Failed to join room")

    async def handle_leave_room(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理离开房间"""
        room_id = data.get("roomId") or conn_info.get("current_room")

        if not room_id:
            await self.send_error("no_room", "You are not in a room")
            return

        success = await manager.leave_room(self.client_id, room_id)

        if success:
            await self.send_message("room", "left", {
                "room": room_id
            })

            # 通知房间内其他用户
            user_id = conn_info.get("user_id")
            async with async_session_maker() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

            if user:
                await manager.broadcast_to_room({
                    "type": "presence",
                    "action": "user_left",
                    "data": {
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "display_name": user.display_name,
                        },
                        "room": room_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }, room_id, exclude_client_id=self.client_id)
        else:
            await self.send_error("leave_failed", "Failed to leave room")

    async def handle_create_room(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理创建房间"""
        from passlib.context import CryptContext

        name = data.get("roomName")
        room_id = data.get("roomId")
        is_private = data.get("isPrivate", False)
        password = data.get("password")
        max_clients = data.get("maxClients")

        if not name:
            await self.send_error("invalid_input", "Room name is required")
            return

        user_id = conn_info.get("user_id")

        # 如果没有提供 room_id，生成一个
        if not room_id:
            import uuid
            room_id = f"room_{uuid.uuid4().hex[:8]}"

        # 哈希密码（如果提供）
        hashed_password = None
        if is_private and password:
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            hashed_password = pwd_context.hash(password)

        # 创建房间
        try:
            async with async_session_maker() as session:
                db_room = Room(
                    room_id=room_id,
                    name=name,
                    description=data.get("description"),
                    is_private=is_private,
                    password=hashed_password,
                    max_clients=max_clients,
                    created_by=user_id
                )
                session.add(db_room)
                await session.commit()
                await session.refresh(db_room)

            await self.send_message("room", "created", {
                "room": {
                    "id": db_room.id,
                    "room_id": db_room.room_id,
                    "name": db_room.name,
                    "is_private": db_room.is_private,
                    "max_clients": db_room.max_clients,
                    "hasPassword": bool(hashed_password)
                }
            })
        except Exception as e:
            await self.send_error("create_failed", f"Failed to create room: {str(e)}")

    async def handle_list_rooms(self, data: Dict[str, Any]):
        """处理获取房间列表"""
        public_only = data.get("publicOnly", False)

        async with async_session_maker() as session:
            query = select(Room).where(Room.is_active == True)
            if public_only:
                query = query.where(Room.is_private == False)

            result = await session.execute(query)
            rooms = result.scalars().all()

        rooms_data = []
        for room in rooms:
            client_count = await manager.room_manager.get_room_client_count(room.room_id)
            rooms_data.append({
                "id": room.id,
                "room_id": room.room_id,
                "name": room.name,
                "description": room.description,
                "is_private": room.is_private,
                "max_clients": room.max_clients,
                "clientCount": client_count,
                "hasPassword": bool(room.password),
                "createdAt": room.created_at.isoformat() if room.created_at else None
            })

        await self.send_message("room", "list", {"rooms": rooms_data})

    async def handle_room_info(self, data: Dict[str, Any]):
        """处理获取房间信息"""
        room_id = data.get("roomId")

        if not room_id:
            await self.send_error("invalid_room", "Room ID is required")
            return

        async with async_session_maker() as session:
            result = await session.execute(
                select(Room).where(Room.room_id == room_id, Room.is_active == True)
            )
            room = result.scalar_one_or_none()

        if room:
            client_count = await manager.room_manager.get_room_client_count(room.room_id)
            await self.send_message("room", "info", {
                "room": {
                    "id": room.id,
                    "room_id": room.room_id,
                    "name": room.name,
                    "description": room.description,
                    "is_private": room.is_private,
                    "max_clients": room.max_clients,
                    "clientCount": client_count,
                    "hasPassword": bool(room.password),
                    "createdAt": room.created_at.isoformat() if room.created_at else None
                }
            })
        else:
            await self.send_error("room_not_found", "Room not found")

    async def handle_user(self, action: str, data: Dict[str, Any]):
        """处理用户相关消息"""
        conn_info = manager.get_connection_info(self.client_id)
        if not conn_info or not conn_info.get("is_authenticated"):
            await self.send_error("not_authenticated", "Please login first")
            return

        if action == "list":
            await self.handle_user_list(data)
        elif action == "info":
            await self.handle_user_info(data, conn_info)
        elif action == "status":
            await self.handle_user_status(data, conn_info)
        else:
            await self.send_error("unknown_action", f"Unknown user action: {action}")

    async def handle_user_list(self, data: Dict[str, Any]):
        """处理获取用户列表"""
        online_only = data.get("onlineOnly", True)

        if online_only:
            online_user_ids = await manager.online_manager.get_online_users()
            users = []
            for user_id in online_user_ids:
                user = await auth_manager.get_user_by_id(user_id)
                if user:
                    users.append({
                        "id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "avatar_url": user.avatar_url,
                        "is_online": True,
                        "last_seen": user.last_seen.isoformat() if user.last_seen else None
                    })
        else:
            async with async_session_maker() as session:
                result = await session.execute(select(User))
                db_users = result.scalars().all()
                users = [{
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "is_online": user.is_online,
                    "last_seen": user.last_seen.isoformat() if user.last_seen else None
                } for user in db_users]

        await self.send_message("user", "list", {"users": users})

    async def handle_user_info(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理获取用户信息"""
        username = data.get("username")

        if not username:
            # 返回当前用户信息
            user_id = conn_info.get("user_id")
            user = await auth_manager.get_user_by_id(user_id)
        else:
            user = await auth_manager.get_user_by_username(username)

        if user:
            await self.send_message("user", "info", {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "is_online": user.is_online,
                    "last_seen": user.last_seen.isoformat() if user.last_seen else None
                }
            })
        else:
            await self.send_error("user_not_found", "User not found")

    async def handle_user_status(self, data: Dict[str, Any], conn_info: Dict[str, Any]):
        """处理更新用户状态"""
        # 这里可以扩展为处理不同的用户状态（如忙碌、离开等）
        pass

    async def handle_system(self, action: str, data: Dict[str, Any]):
        """处理系统相关消息"""
        if action == "ping":
            await self.send_message("system", "pong", {
                "timestamp": datetime.utcnow().isoformat(),
                "serverTime": int(datetime.utcnow().timestamp() * 1000)
            })
        elif action == "stats":
            stats = manager.get_stats()
            online_count = await manager.online_manager.get_online_count()
            await self.send_message("system", "stats", {
                "server": stats,
                "onlineUsers": online_count
            })
        else:
            await self.send_error("unknown_action", f"Unknown system action: {action}")

    async def handle_presence(self, action: str, data: Dict[str, Any]):
        """处理在线状态相关消息"""
        # 在线状态处理逻辑
        pass

    async def send_message(
        self,
        msg_type: str,
        action: str,
        data: Dict[str, Any]
    ):
        """发送消息给客户端"""
        message = {
            "type": msg_type,
            "action": action,
            "data": data
        }
        await manager.send_personal_message(message, self.client_id)

    async def send_error(self, action: str, message: str):
        """发送错误消息"""
        await self.send_message("error", action, {"message": message})
