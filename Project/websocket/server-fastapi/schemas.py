from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# 用户相关 Schema
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: int
    is_online: bool
    last_seen: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithToken(UserResponse):
    access_token: str
    token_type: str = "bearer"


# 房间相关 Schema
class RoomBase(BaseModel):
    room_id: Optional[str] = Field(None, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_private: bool = False
    password: Optional[str] = Field(None, max_length=100)
    max_clients: Optional[int] = Field(None, gt=0)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_private: Optional[bool] = None
    max_clients: Optional[int] = Field(None, gt=0)


class RoomResponse(RoomBase):
    id: int
    created_at: datetime
    client_count: int = 0
    has_password: bool = False

    class Config:
        from_attributes = True


# 消息相关 Schema
class MessageBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    room_id: Optional[str] = None
    message_type: str = "text"


class MessageCreate(MessageBase):
    to: Optional[str] = None  # 用于私信


class MessageResponse(MessageBase):
    id: int
    user_id: Optional[int]
    sender: Optional[UserResponse]
    created_at: datetime

    class Config:
        from_attributes = True


# WebSocket 消息 Schema
class WSMessage(BaseModel):
    type: str
    action: str
    data: Dict[str, Any] = {}


class WSMessageSystem(WSMessage):
    type: str = "system"
    action: str


class WSMessageAuth(WSMessage):
    type: str = "auth"


class WSMessageChat(WSMessage):
    type: str = "chat"


class WSMessageRoom(WSMessage):
    type: str = "room"


class WSMessageUser(WSMessage):
    type: str = "user"


class WSMessagePresence(WSMessage):
    type: str = "presence"


class WSMessageError(WSMessage):
    type: str = "error"


# 通用响应 Schema
class APIResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int


# 连接信息 Schema
class ConnectionInfo(BaseModel):
    client_id: str
    user_id: Optional[int]
    connected_at: datetime
    last_heartbeat: datetime
    current_room: Optional[str] = None
