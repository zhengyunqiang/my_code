"""
Redis Cache Adapter
Redis 缓存适配器 - 复用 FastAPI 项目的 Redis 客户端
"""

import json
import asyncio
from typing import Any, Dict, List, Optional, Union
from datetime import timedelta

from backend.core.logging import get_logger
from backend.config import settings

logger = get_logger(__name__)


class RedisCache:
    """
    Redis 缓存适配器

    提供多级缓存支持
    """

    def __init__(self, redis_client=None):
        """
        初始化 Redis 缓存

        Args:
            redis_client: Redis 客户端（可选）
        """
        self.redis = redis_client
        self._local_cache: Dict[str, tuple[Any, float]] = {}  # 本地 L1 缓存
        self._local_ttl = 60  # 本地缓存默认 TTL（秒）

    async def get(
        self,
        key: str,
        default: Any = None,
        use_local: bool = True,
    ) -> Any:
        """
        获取缓存值

        Args:
            key: 缓存键
            default: 默认值
            use_local: 是否使用本地缓存

        Returns:
            缓存值或默认值
        """
        # 先检查本地缓存
        if use_local and key in self._local_cache:
            value, expiry = self._local_cache[key]
            if asyncio.get_event_loop().time() < expiry:
                return value
            else:
                del self._local_cache[key]

        # 检查 Redis
        if self.redis:
            try:
                value = await self.redis.get(key)
                if value is not None:
                    # 反序列化
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass

                    # 更新本地缓存
                    if use_local:
                        self._set_local(key, value, self._local_ttl)

                    return value
            except Exception as e:
                logger.error(f"Redis get error: {e}")

        return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        use_local: bool = True,
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            use_local: 是否同时设置本地缓存

        Returns:
            是否成功
        """
        ttl = ttl or settings.CACHE_TTL

        # 序列化
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as e:
            logger.error(f"Cache serialization error: {e}")
            return False

        # 设置 Redis
        if self.redis:
            try:
                await self.redis.set(key, serialized, expire=ttl)
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                return False

        # 设置本地缓存
        if use_local:
            self._set_local(key, value, min(ttl, self._local_ttl))

        return True

    async def delete(self, *keys: str, local: bool = True) -> int:
        """
        删除缓存值

        Args:
            *keys: 缓存键列表
            local: 是否同时删除本地缓存

        Returns:
            删除数量
        """
        count = 0

        # 删除本地缓存
        if local:
            for key in keys:
                if key in self._local_cache:
                    del self._local_cache[key]
                    count += 1

        # 删除 Redis 缓存
        if self.redis:
            try:
                count += await self.redis.delete(*keys)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")

        return count

    async def exists(self, *keys: str) -> int:
        """
        检查键是否存在

        Args:
            *keys: 缓存键列表

        Returns:
            存在的数量
        """
        # 检查本地缓存
        local_exists = sum(1 for key in keys if key in self._local_cache)

        # 检查 Redis
        if self.redis:
            try:
                redis_exists = await self.redis.exists(*keys)
                return max(local_exists, redis_exists)
            except Exception as e:
                logger.error(f"Redis exists error: {e}")

        return local_exists

    async def increment(
        self,
        key: str,
        amount: int = 1,
    ) -> int:
        """
        递增计数器

        Args:
            key: 缓存键
            amount: 递增量

        Returns:
            递增后的值
        """
        if self.redis:
            try:
                return await self.redis.incr(key, amount)
            except Exception as e:
                logger.error(f"Redis incr error: {e}")

        # 降级到本地
        if key in self._local_cache:
            self._local_cache[key] = (
                self._local_cache[key][0] + amount,
                self._local_cache[key][1],
            )
        else:
            self._set_local(key, amount, self._local_ttl)

        return self._local_cache[key][0]

    async def expire(
        self,
        key: str,
        ttl: int,
    ) -> bool:
        """
        设置过期时间

        Args:
            key: 缓存键
            ttl: 过期时间（秒）

        Returns:
            是否成功
        """
        if self.redis:
            try:
                return await self.redis.expire(key, ttl)
            except Exception as e:
                logger.error(f"Redis expire error: {e}")

        return False

    async def ttl(self, key: str) -> int:
        """
        获取剩余过期时间

        Args:
            key: 缓存键

        Returns:
            剩余秒数，-1 表示永不过期，-2 表示不存在
        """
        if self.redis:
            try:
                return await self.redis.ttl(key)
            except Exception as e:
                logger.error(f"Redis ttl error: {e}")

        return -2

    def _set_local(
        self,
        key: str,
        value: Any,
        ttl: int,
    ) -> None:
        """
        设置本地缓存

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
        """
        expiry = asyncio.get_event_loop().time() + ttl
        self._local_cache[key] = (value, expiry)

        # 清理过期缓存
        self._cleanup_local()

    def _cleanup_local(self) -> None:
        """清理本地过期缓存"""
        now = asyncio.get_event_loop().time()
        expired = [
            key for key, (_, expiry) in self._local_cache.items()
            if expiry < now
        ]
        for key in expired:
            del self._local_cache[key]

    def clear_local(self) -> None:
        """清空本地缓存"""
        self._local_cache.clear()

    async def flush_all(self) -> bool:
        """
        清空所有缓存

        Returns:
            是否成功
        """
        self.clear_local()

        if self.redis:
            try:
                await self.redis.flushdb()
                return True
            except Exception as e:
                logger.error(f"Redis flush error: {e}")

        return False

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计

        Returns:
            统计字典
        """
        return {
            "local_cache_size": len(self._local_cache),
            "local_ttl": self._local_ttl,
        }


# 全局 Redis 缓存实例
redis_cache: Optional[RedisCache] = None


async def init_cache(redis_client) -> RedisCache:
    """
    初始化缓存

    Args:
        redis_client: Redis 客户端

    Returns:
        RedisCache 实例
    """
    global redis_cache
    redis_cache = RedisCache(redis_client)
    logger.info("Redis cache initialized")
    return redis_cache


__all__ = [
    "RedisCache",
    "redis_cache",
    "init_cache",
]
