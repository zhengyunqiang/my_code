from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime

from auth import auth_manager
from database import async_session_maker, User, Room, Message
from sqlalchemy import select, func, desc
from redis_client import redis_manager, RoomStateManager

# 创建路由器
router = APIRouter()

# HTTP Bearer 认证
security = HTTPBearer()

# Pydantic 模型
class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class RoomCreate(BaseModel):
    room_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    is_private: bool = False
    password: Optional[str] = None
    max_clients: Optional[int] = None

class RoomResponse(BaseModel):
    id: int
    room_id: str
    name: str
    description: Optional[str]
    is_private: bool
    max_clients: Optional[int]
    created_at: datetime
    client_count: int = 0

class MessageResponse(BaseModel):
    id: int
    room_id: str
    user_id: Optional[int]
    content: str
    message_type: str
    created_at: datetime
    sender: Optional[dict] = None


# 依赖项：获取当前用户
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """从 JWT token 获取当前用户"""
    token = credentials.credentials
    user = await auth_manager.get_user_by_username(token)  # 简化版，实际应解析 JWT
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    return user


# ============= 用户相关 API =============

@router.post("/auth/register", response_model=dict)
async def register(user_data: UserRegister):
    """用户注册"""
    try:
        # 检查用户名是否已存在
        existing_user = await auth_manager.get_user_by_username(user_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )

        # 创建用户
        user = await auth_manager.create_user(
            username=user_data.username,
            password=user_data.password,
            email=user_data.email,
            display_name=user_data.display_name
        )

        return {
            "success": True,
            "message": "User registered successfully",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    """用户登录"""
    user = await auth_manager.authenticate_user(user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # 创建 token
    access_token = auth_manager.create_access_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url
        }
    )


@router.get("/users/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "is_online": current_user.is_online,
        "created_at": current_user.created_at
    }


@router.get("/users", response_model=List[dict])
async def get_users(
    online_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    """获取用户列表"""
    async with async_session_maker() as session:
        query = select(User)
        if online_only:
            query = query.where(User.is_online == True)
        query = query.order_by(User.username)

        result = await session.execute(query)
        users = result.scalars().all()

        return [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
                "is_online": user.is_online,
                "last_seen": user.last_seen
            }
            for user in users
        ]


@router.get("/users/{user_id}")
async def get_user_info(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """获取指定用户信息"""
    user = await auth_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "is_online": user.is_online,
        "last_seen": user.last_seen,
        "created_at": user.created_at
    }


# ============= 房间相关 API =============

@router.get("/rooms", response_model=List[RoomResponse])
async def get_rooms(
    public_only: bool = True,
    current_user: User = Depends(get_current_user)
):
    """获取房间列表"""
    room_state_manager = RoomStateManager(redis_manager)

    async with async_session_maker() as session:
        query = select(Room).where(Room.is_active == True)
        if public_only:
            query = query.where(Room.is_private == False)
        query = query.order_by(Room.created_at.desc())

        result = await session.execute(query)
        rooms = result.scalars().all()

        rooms_data = []
        for room in rooms:
            client_count = await room_state_manager.get_room_client_count(room.room_id)
            rooms_data.append(RoomResponse(
                id=room.id,
                room_id=room.room_id,
                name=room.name,
                description=room.description,
                is_private=room.is_private,
                max_clients=room.max_clients,
                created_at=room.created_at,
                client_count=client_count
            ))

        return rooms_data


@router.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_room_info(
    room_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取房间信息"""
    room_state_manager = RoomStateManager(redis_manager)

    async with async_session_maker() as session:
        result = await session.execute(
            select(Room).where(Room.room_id == room_id, Room.is_active == True)
        )
        room = result.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Room not found"
            )

        client_count = await room_state_manager.get_room_client_count(room_id)

        return RoomResponse(
            id=room.id,
            room_id=room.room_id,
            name=room.name,
            description=room.description,
            is_private=room.is_private,
            max_clients=room.max_clients,
            created_at=room.created_at,
            client_count=client_count
        )


@router.post("/rooms", response_model=dict)
async def create_room(
    room_data: RoomCreate,
    current_user: User = Depends(get_current_user)
):
    """创建房间"""
    from passlib.context import CryptContext
    import uuid

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # 生成 room_id（如果未提供）
    if not room_data.room_id:
        room_data.room_id = f"room_{uuid.uuid4().hex[:8]}"

    # 哈希密码（如果需要）
    hashed_password = None
    if room_data.is_private and room_data.password:
        hashed_password = pwd_context.hash(room_data.password)

    async with async_session_maker() as session:
        # 检查 room_id 是否已存在
        existing_room = await session.execute(
            select(Room).where(Room.room_id == room_data.room_id)
        )
        if existing_room.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room ID already exists"
            )

        # 创建房间
        new_room = Room(
            room_id=room_data.room_id,
            name=room_data.name,
            description=room_data.description,
            is_private=room_data.is_private,
            password=hashed_password,
            max_clients=room_data.max_clients,
            created_by=current_user.id
        )

        session.add(new_room)
        await session.commit()
        await session.refresh(new_room)

        return {
            "success": True,
            "message": "Room created successfully",
            "room": {
                "id": new_room.id,
                "room_id": new_room.room_id,
                "name": new_room.name,
                "description": new_room.description,
                "is_private": new_room.is_private,
                "max_clients": new_room.max_clients
            }
        }


# ============= 消息相关 API =============

@router.get("/rooms/{room_id}/messages", response_model=List[MessageResponse])
async def get_room_messages(
    room_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """获取房间消息历史"""
    room_state_manager = RoomStateManager(redis_manager)

    # 先从 Redis 获取
    messages = await room_state_manager.get_message_history(room_id, limit)

    # 如果 Redis 没有足够的历史，从数据库获取
    if len(messages) < limit:
        async with async_session_maker() as session:
            # 检查房间是否存在
            room_result = await session.execute(
                select(Room).where(Room.room_id == room_id, Room.is_active == True)
            )
            room = room_result.scalar_one_or_none()
            if not room:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Room not found"
                )

            # 从数据库获取消息
            result = await session.execute(
                select(Message)
                .where(Message.room_id == room_id)
                .order_by(desc(Message.created_at))
                .limit(limit - len(messages))
                .offset(offset)
            )
            db_messages = result.scalars().all()

            # 获取发送者信息
            for msg in reversed(db_messages):
                sender = None
                if msg.user_id:
                    user = await auth_manager.get_user_by_id(msg.user_id)
                    if user:
                        sender = {
                            "id": user.id,
                            "username": user.username,
                            "display_name": user.display_name,
                            "avatar_url": user.avatar_url
                        }

                messages.append({
                    "id": msg.id,
                    "room_id": msg.room_id,
                    "user_id": msg.user_id,
                    "content": msg.content,
                    "message_type": msg.message_type,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "sender": sender
                })

    return [
        MessageResponse(
            id=msg.get("id", 0),
            room_id=msg.get("room_id", room_id),
            user_id=msg.get("user_id"),
            content=msg.get("content", ""),
            message_type=msg.get("message_type", "text"),
            created_at=datetime.fromisoformat(msg.get("created_at")) if msg.get("created_at") else datetime.utcnow(),
            sender=msg.get("sender")
        )
        for msg in messages[-limit:]
    ]


# ============= 统计相关 API =============

@router.get("/stats/overview")
async def get_stats(
    current_user: User = Depends(get_current_user)
):
    """获取平台统计信息"""
    async with async_session_maker() as session:
        # 用户统计
        user_count = await session.execute(select(func.count(User.id)))
        online_user_count = await session.execute(
            select(func.count(User.id)).where(User.is_online == True)
        )

        # 房间统计
        room_count = await session.execute(select(func.count(Room.id)))
        public_room_count = await session.execute(
            select(func.count(Room.id)).where(Room.is_private == False)
        )

        # 消息统计
        message_count = await session.execute(select(func.count(Message.id)))

    return {
        "users": {
            "total": user_count.scalar(),
            "online": online_user_count.scalar()
        },
        "rooms": {
            "total": room_count.scalar(),
            "public": public_room_count.scalar()
        },
        "messages": {
            "total": message_count.scalar()
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health")
async def health_check():
    """健康检查"""
    redis_status = await redis_manager.ping()

    return {
        "status": "healthy" if redis_status else "degraded",
        "redis": "connected" if redis_status else "disconnected",
        "timestamp": datetime.utcnow().isoformat()
    }
