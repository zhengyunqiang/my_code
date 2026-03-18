"""
Rate Limiting Module
速率限制模块 - 复用 Redis 客户端的速率限制器
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from backend.core.logging import get_logger
from backend.core.exceptions import RateLimitError, QuotaExceededError
from backend.config import settings

logger = get_logger(__name__)


class RateLimiter:
    """
    速率限制器

    基于滑动窗口的速率限制实现
    """

    def __init__(self, redis_client=None):
        """
        初始化速率限制器

        Args:
            redis_client: Redis 客户端（可选，用于分布式）
        """
        self.redis = redis_client
        self._local_store: Dict[str, list] = {}  # 本地存储（用于测试）

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window: int = 60,
    ) -> tuple[bool, int]:
        """
        检查速率限制

        Args:
            key: 限制键（通常是用户ID或IP）
            limit: 时间窗口内允许的请求数
            window: 时间窗口（秒）

        Returns:
            (是否允许, 剩余请求数, 重试时间)
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window)

        if self.redis:
            return await self._check_redis(key, limit, window, now, window_start)
        else:
            return self._check_local(key, limit, window, now, window_start)

    async def _check_redis(
        self,
        key: str,
        limit: int,
        window: int,
        now: datetime,
        window_start: datetime,
    ) -> tuple[bool, int]:
        """使用 Redis 检查"""
        redis_key = f"rate_limit:{key}"

        try:
            # 获取当前计数
            current = await self.redis.get(redis_key)

            if current is None:
                # 首次请求
                await self.redis.set(redis_key, 1, expire=window)
                return True, limit - 1

            count = int(current)

            if count >= limit:
                # 超过限制，计算重试时间
                ttl = await self.redis.ttl(redis_key)
                return False, 0

            # 增加计数
            await self.redis.incr(redis_key)
            return True, limit - count - 1

        except Exception as e:
            logger.error(f"Redis rate limiter error: {e}")
            # 出错时允许通过（降级策略）
            return True, limit

    def _check_local(
        self,
        key: str,
        limit: int,
        window: int,
        now: datetime,
        window_start: datetime,
    ) -> tuple[bool, int]:
        """使用本地存储检查"""
        if key not in self._local_store:
            self._local_store[key] = []

        # 清理过期记录
        timestamps = self._local_store[key]
        self._local_store[key] = [
            ts for ts in timestamps
            if ts > window_start.timestamp()
        ]

        # 检查限制
        if len(self._local_store[key]) >= limit:
            # 计算重试时间
            oldest = min(self._local_store[key])
            retry_after = int(oldest + window - now.timestamp()) + 1
            return False, 0

        # 记录请求
        self._local_store[key].append(now.timestamp())
        return True, limit - len(self._local_store[key])

    async def check_and_raise(
        self,
        key: str,
        limit: Optional[int] = None,
        window: Optional[int] = None,
    ) -> None:
        """
        检查速率限制，超限时抛出异常

        Args:
            key: 限制键
            limit: 限制数量（默认使用配置）
            window: 时间窗口（默认使用配置）

        Raises:
            RateLimitError: 超过速率限制
        """
        limit = limit or settings.RATE_LIMIT_PER_MINUTE
        window = window or settings.RATE_LIMIT_WINDOW

        allowed, remaining, retry_after = await self.is_allowed(key, limit, window)

        if not allowed:
            raise RateLimitError(
                limit=limit,
                window=window,
                retry_after=retry_after,
            )

    def reset(self, key: str) -> None:
        """
        重置速率限制

        Args:
            key: 限制键
        """
        if key in self._local_store:
            del self._local_store[key]


class QuotaManager:
    """
    配额管理器

    管理用户的请求配额（每日、每小时等）
    """

    def __init__(self, redis_client=None):
        """
        初始化配额管理器

        Args:
            redis_client: Redis 客户端（可选）
        """
        self.redis = redis_client
        self._local_store: Dict[str, Dict[str, Any]] = {}

    async def check_quota(
        self,
        user_id: int,
        quota_type: str,
        limit: int,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[bool, int, int]:
        """
        检查配额

        Args:
            user_id: 用户 ID
            quota_type: 配额类型（daily, hourly）
            limit: 配额限制
            window_start: 时间窗口开始
            window_end: 时间窗口结束

        Returns:
            (是否允许, 已使用数量, 剩余数量)
        """
        key = f"quota:{user_id}:{quota_type}:{window_start.strftime('%Y%m%d%H')}"

        if self.redis:
            return await self._check_redis_quota(key, limit, window_end)
        else:
            return self._check_local_quota(key, limit, window_end)

    async def _check_redis_quota(
        self,
        key: str,
        limit: int,
        window_end: datetime,
    ) -> tuple[bool, int, int]:
        """使用 Redis 检查配额"""
        try:
            current = await self.redis.get(key)

            if current is None:
                # 首次请求
                ttl = int((window_end - datetime.now(timezone.utc)).total_seconds())
                await self.redis.set(key, 1, expire=ttl)
                return True, 1, limit - 1

            used = int(current)

            if used >= limit:
                return False, used, 0

            # 增加计数
            await self.redis.incr(key)
            return True, used + 1, limit - used - 1

        except Exception as e:
            logger.error(f"Redis quota check error: {e}")
            return True, 0, limit

    def _check_local_quota(
        self,
        key: str,
        limit: int,
        window_end: datetime,
    ) -> tuple[bool, int, int]:
        """使用本地存储检查配额"""
        now = datetime.now(timezone.utc)

        if now > window_end:
            # 时间窗口已过期，重置
            if key in self._local_store:
                del self._local_store[key]
            return True, 0, limit

        if key not in self._local_store:
            self._local_store[key] = {"used": 0, "expires": window_end.timestamp()}

        used = self._local_store[key]["used"]

        if used >= limit:
            return False, used, 0

        self._local_store[key]["used"] = used + 1
        return True, used + 1, limit - used - 1

    async def check_and_raise(
        self,
        user_id: int,
        quota_type: str,
    ) -> None:
        """
        检查配额，超限时抛出异常

        Args:
            user_id: 用户 ID
            quota_type: 配额类型

        Raises:
            QuotaExceededError: 超过配额
        """
        now = datetime.now(timezone.utc)

        if quota_type == "daily":
            window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = window_start + timedelta(days=1)
            limit = settings.USER_DAILY_QUOTA
        elif quota_type == "hourly":
            window_start = now.replace(minute=0, second=0, microsecond=0)
            window_end = window_start + timedelta(hours=1)
            limit = settings.USER_HOURLY_QUOTA
        else:
            raise ValueError(f"Unknown quota type: {quota_type}")

        allowed, used, remaining = await self.check_quota(
            user_id, quota_type, limit, window_start, window_end
        )

        if not allowed:
            reset_time = window_end.isoformat()
            raise QuotaExceededError(
                quota_type=quota_type,
                current=used,
                limit=limit,
                reset_time=reset_time,
            )

    def get_usage(
        self,
        user_id: int,
        quota_type: str,
    ) -> Dict[str, Any]:
        """
        获取配额使用情况

        Args:
            user_id: 用户 ID
            quota_type: 配额类型

        Returns:
            使用情况字典
        """
        # 这里简化实现，实际应该从存储中获取
        return {
            "user_id": user_id,
            "quota_type": quota_type,
            "used": 0,
            "limit": settings.USER_DAILY_QUOTA if quota_type == "daily" else settings.USER_HOURLY_QUOTA,
            "remaining": settings.USER_DAILY_QUOTA if quota_type == "daily" else settings.USER_HOURLY_QUOTA,
        }


# ========================================
# 全局实例（将在应用启动时初始化 Redis 客户端）
# ========================================

rate_limiter: Optional[RateLimiter] = None
quota_manager: Optional[QuotaManager] = None


async def init_rate_limiting(redis_client) -> None:
    """初始化速率限制"""
    global rate_limiter, quota_manager
    rate_limiter = RateLimiter(redis_client)
    quota_manager = QuotaManager(redis_client)
    logger.info("Rate limiting initialized")


__all__ = [
    "RateLimiter",
    "QuotaManager",
    "rate_limiter",
    "quota_manager",
    "init_rate_limiting",
]
