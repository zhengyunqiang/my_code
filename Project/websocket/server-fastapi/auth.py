from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from config import settings
from database import async_session_maker, User
from sqlalchemy import select


# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthManager:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """获取密码哈希"""
        return pwd_context.hash(password)

    def create_access_token(
        self,
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_access_token(self, token: str) -> Optional[dict]:
        """解码访问令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """通过ID获取用户"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> User:
        """创建新用户"""
        async with async_session_maker() as session:
            hashed_password = self.get_password_hash(password)
            db_user = User(
                username=username,
                hashed_password=hashed_password,
                email=email,
                display_name=display_name or username
            )
            session.add(db_user)
            await session.commit()
            await session.refresh(db_user)
            return db_user

    async def authenticate_user(
        self,
        username: str,
        password: str
    ) -> Optional[User]:
        """验证用户"""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

    async def update_user_online_status(
        self,
        user_id: int,
        is_online: bool
    ) -> bool:
        """更新用户在线状态"""
        async with async_session_maker() as session:
            try:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user:
                    user.is_online = is_online
                    user.last_seen = datetime.utcnow()
                    await session.commit()
                    return True
                return False
            except Exception as e:
                print(f"Update user online status error: {e}")
                await session.rollback()
                return False


# 全局认证管理器实例
auth_manager = AuthManager()


# 依赖项：获取当前用户
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
