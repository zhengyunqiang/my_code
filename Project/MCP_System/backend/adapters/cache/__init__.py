"""
Cache Adapters Package
缓存适配器 - Redis 缓存
"""

from backend.adapters.cache.redis_client import (
    RedisCache,
    redis_cache,
    init_cache,
)

__all__ = [
    "RedisCache",
    "redis_cache",
    "init_cache",
]
