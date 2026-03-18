"""
Authentication Module
认证模块 - 复用 FastAPI 项目的 JWT 认证 + bcrypt 密码哈希
"""

from dataclasses import dataclass
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from backend.config import settings
from backend.core.logging import get_logger
from backend.core.exceptions import (
    UnauthorizedError,
    InvalidTokenError,
    TokenExpiredError,
    InvalidAPIKey,
)

logger = get_logger(__name__)


# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthManager:
    """
    认证管理器

    提供 JWT 和 API 密钥认证功能
    """

    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        验证密码

        Args:
            plain_password: 明文密码
            hashed_password: 哈希密码

        Returns:
            是否匹配
        """
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """
        获取密码哈希

        Args:
            password: 明文密码

        Returns:
            哈希密码
        """
        return pwd_context.hash(password)

    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        创建访问令牌

        Args:
            data: 令牌数据
            expires_delta: 过期时间增量

        Returns:
            JWT 令牌字符串
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.access_token_expire_minutes
            )

        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        })

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        解码访问令牌

        Args:
            token: JWT 令牌字符串

        Returns:
            令牌数据字典，解码失败返回 None

        Raises:
            InvalidTokenError: 令牌无效
            TokenExpiredError: 令牌过期
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError()
        except JWTError as e:
            raise InvalidTokenError(str(e))

    def create_refresh_token(
        self,
        data: Dict[str, Any],
    ) -> str:
        """
        创建刷新令牌

        Args:
            data: 令牌数据

        Returns:
            刷新令牌字符串
        """
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        to_encode = data.copy()
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh",
        })

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证刷新令牌

        Args:
            token: 刷新令牌字符串

        Returns:
            令牌数据字典，验证失败返回 None
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )

            # 检查是否是刷新令牌
            if payload.get("type") != "refresh":
                return None

            return payload
        except JWTError:
            return None


class APIKeyManager:
    """
    API 密钥管理器

    管理 API 密钥的生成、验证和存储
    """

    def __init__(self):
        self.key_length = settings.API_KEY_LENGTH
        self.key_prefix = "mcp_"

    def generate_api_key(self) -> str:
        """
        生成 API 密钥

        Returns:
            API 密钥字符串
        """
        import secrets

        random_part = secrets.token_urlsafe(self.key_length)
        return f"{self.key_prefix}{random_part}"

    def hash_api_key(self, api_key: str) -> str:
        """
        哈希 API 密钥（用于存储）

        Args:
            api_key: API 密钥

        Returns:
            哈希值
        """
        import hashlib

        return hashlib.sha256(api_key.encode()).hexdigest()

    def verify_api_key(
        self,
        api_key: str,
        hashed_key: str,
    ) -> bool:
        """
        验证 API 密钥

        Args:
            api_key: API 密钥
            hashed_key: 存储的哈希值

        Returns:
            是否匹配
        """
        computed_hash = self.hash_api_key(api_key)
        return computed_hash == hashed_key

    def extract_api_key_from_header(self, auth_header: str) -> Optional[str]:
        """
        从请求头提取 API 密钥

        Args:
            auth_header: Authorization 请求头

        Returns:
            API 密钥字符串，提取失败返回 None
        """
        if not auth_header:
            return None

        # 支持 Bearer 和直接传递密钥两种方式
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        elif auth_header.startswith(settings.API_KEY_HEADER):
            # X-API-Key: key_value
            return auth_header.split(":", 1)[1].strip()
        else:
            # 直接传递密钥
            return auth_header


# ========================================
# 认证上下文
# ========================================

@dataclass
class AuthContext:
    """认证上下文"""
    user_id: Optional[int] = None
    token_type: Optional[str] = None  # jwt, api_key
    permissions: list = None
    scopes: list = None

    def is_authenticated(self) -> bool:
        """是否已认证"""
        return self.user_id is not None

    def has_permission(self, permission: str) -> bool:
        """检查是否有指定权限"""
        return permission in (self.permissions or [])

    def has_scope(self, scope: str) -> bool:
        """检查是否有指定范围"""
        return scope in (self.scopes or [])


from dataclasses import dataclass


# 全局实例
auth_manager = AuthManager()
api_key_manager = APIKeyManager()


__all__ = [
    "AuthManager",
    "APIKeyManager",
    "AuthContext",
    "auth_manager",
    "api_key_manager",
]
