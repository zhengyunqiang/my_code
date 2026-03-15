import redis.asyncio as redis
from redis.asyncio import Redis
from typing import Optional, List, Dict, Any
import json
from datetime import timedelta
from config import settings


class RedisManager:
    def __init__(self):
        self.redis: Optional[Redis] = None

    async def connect(self):
        """连接到 Redis"""
        self.redis = await redis.from_url(
            settings.REDIS_URL,
            decode_responses=settings.REDIS_DECODE_RESPONSES
        )

    async def disconnect(self):
        """断开 Redis 连接"""
        if self.redis:
            await self.redis.close()

    async def ping(self) -> bool:
        """检查 Redis 连接"""
        try:
            return await self.redis.ping() if self.redis else False
        except Exception:
            return False

    # 字符串操作
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """设置键值"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            if expire:
                return await self.redis.setex(key, expire, value)
            return await self.redis.set(key, value)
        except Exception as e:
            print(f"Redis set error: {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """获取值"""
        try:
            value = await self.redis.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            print(f"Redis get error: {e}")
            return None

    async def delete(self, *keys: str) -> int:
        """删除键"""
        try:
            return await self.redis.delete(*keys)
        except Exception as e:
            print(f"Redis delete error: {e}")
            return 0

    async def exists(self, *keys: str) -> int:
        """检查键是否存在"""
        try:
            return await self.redis.exists(*keys)
        except Exception as e:
            print(f"Redis exists error: {e}")
            return 0

    # 列表操作
    async def lpush(self, key: str, *values: Any) -> int:
        """从左侧推入列表"""
        try:
            serialized = [json.dumps(v) for v in values]
            return await self.redis.lpush(key, *serialized)
        except Exception as e:
            print(f"Redis lpush error: {e}")
            return 0

    async def rpush(self, key: str, *values: Any) -> int:
        """从右侧推入列表"""
        try:
            serialized = [json.dumps(v) for v in values]
            return await self.redis.rpush(key, *serialized)
        except Exception as e:
            print(f"Redis rpush error: {e}")
            return 0

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表范围"""
        try:
            values = await self.redis.lrange(key, start, end)
            return [json.loads(v) for v in values]
        except Exception as e:
            print(f"Redis lrange error: {e}")
            return []

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """修剪列表"""
        try:
            await self.redis.ltrim(key, start, end)
            return True
        except Exception as e:
            print(f"Redis ltrim error: {e}")
            return False

    async def llen(self, key: str) -> int:
        """获取列表长度"""
        try:
            return await self.redis.llen(key)
        except Exception as e:
            print(f"Redis llen error: {e}")
            return 0

    # 集合操作
    async def sadd(self, key: str, *members: Any) -> int:
        """添加到集合"""
        try:
            serialized = [json.dumps(m) for m in members]
            return await self.redis.sadd(key, *serialized)
        except Exception as e:
            print(f"Redis sadd error: {e}")
            return 0

    async def srem(self, key: str, *members: Any) -> int:
        """从集合移除"""
        try:
            serialized = [json.dumps(m) for m in members]
            return await self.redis.srem(key, *serialized)
        except Exception as e:
            print(f"Redis srem error: {e}")
            return 0

    async def smembers(self, key: str) -> List[Any]:
        """获取集合所有成员"""
        try:
            members = await self.redis.smembers(key)
            return [json.loads(m) for m in members]
        except Exception as e:
            print(f"Redis smembers error: {e}")
            return []

    async def sismember(self, key: str, member: Any) -> bool:
        """检查是否是集合成员"""
        try:
            return await self.redis.sismember(key, json.dumps(member))
        except Exception as e:
            print(f"Redis sismember error: {e}")
            return False

    async def scard(self, key: str) -> int:
        """获取集合大小"""
        try:
            return await self.redis.scard(key)
        except Exception as e:
            print(f"Redis scard error: {e}")
            return 0

    # 哈希操作
    async def hset(self, name: str, key: str, value: Any) -> bool:
        """设置哈希字段"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            return await self.redis.hset(name, key, value)
        except Exception as e:
            print(f"Redis hset error: {e}")
            return False

    async def hget(self, name: str, key: str) -> Optional[Any]:
        """获取哈希字段"""
        try:
            value = await self.redis.hget(name, key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            print(f"Redis hget error: {e}")
            return None

    async def hgetall(self, name: str) -> Dict[str, Any]:
        """获取所有哈希字段"""
        try:
            values = await self.redis.hgetall(name)
            return {k: json.loads(v) if v else v for k, v in values.items()}
        except Exception as e:
            print(f"Redis hgetall error: {e}")
            return {}

    async def hdel(self, name: str, *keys: str) -> int:
        """删除哈希字段"""
        try:
            return await self.redis.hdel(name, *keys)
        except Exception as e:
            print(f"Redis hdel error: {e}")
            return 0

    # 发布订阅
    async def publish(self, channel: str, message: Any) -> int:
        """发布消息到频道"""
        try:
            if isinstance(message, (dict, list)):
                message = json.dumps(message)
            return await self.redis.publish(channel, message)
        except Exception as e:
            print(f"Redis publish error: {e}")
            return 0

    async def subscribe(self, *channels: str):
        """订阅频道"""
        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(*channels)
            return pubsub
        except Exception as e:
            print(f"Redis subscribe error: {e}")
            return None

    # 过期时间
    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        try:
            return await self.redis.expire(key, seconds)
        except Exception as e:
            print(f"Redis expire error: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """获取剩余过期时间"""
        try:
            return await self.redis.ttl(key)
        except Exception as e:
            print(f"Redis ttl error: {e}")
            return -1


# 全局 Redis 管理器实例
redis_manager = RedisManager()


# 速率限制器
class RateLimiter:
    def __init__(self, redis_manager: RedisManager):
        self.redis = redis_manager

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window: int = 60
    ) -> tuple[bool, int]:
        """
        检查速率限制
        :param key: 限制键（通常是用户ID或IP）
        :param limit: 时间窗口内允许的请求数
        :param window: 时间窗口（秒）
        :return: (是否允许, 剩余请求数)
        """
        try:
            current = await self.redis.get(f"rate_limit:{key}")
            if current is None:
                await self.redis.set(f"rate_limit:{key}", 1, expire=window)
                return True, limit - 1

            count = int(current)
            if count >= limit:
                return False, 0

            await self.redis.incr(f"rate_limit:{key}")
            return True, limit - count - 1

        except Exception as e:
            print(f"Rate limiter error: {e}")
            return True, limit  # 出错时允许通过


# 在线用户管理器
class OnlineUserManager:
    def __init__(self, redis_manager: RedisManager):
        self.redis = redis_manager

    async def add_online_user(self, user_id: int, connection_id: str) -> bool:
        """添加在线用户"""
        try:
            await self.redis.sadd("online_users", user_id)
            await self.redis.hset("user_connections", str(user_id), connection_id)
            await self.redis.set(f"user_last_seen:{user_id}", int(__import__('time').time()))
            return True
        except Exception as e:
            print(f"Add online user error: {e}")
            return False

    async def remove_online_user(self, user_id: int) -> bool:
        """移除在线用户"""
        try:
            await self.redis.srem("online_users", user_id)
            await self.redis.hdel("user_connections", str(user_id))
            return True
        except Exception as e:
            print(f"Remove online user error: {e}")
            return False

    async def is_online(self, user_id: int) -> bool:
        """检查用户是否在线"""
        try:
            return await self.redis.sismember("online_users", user_id)
        except Exception as e:
            print(f"Check online error: {e}")
            return False

    async def get_online_users(self) -> List[int]:
        """获取所有在线用户"""
        try:
            return await self.redis.smembers("online_users")
        except Exception as e:
            print(f"Get online users error: {e}")
            return []

    async def get_online_count(self) -> int:
        """获取在线用户数"""
        try:
            return await self.redis.scard("online_users")
        except Exception as e:
            print(f"Get online count error: {e}")
            return 0


# 房间管理器（Redis 版本）
class RoomStateManager:
    def __init__(self, redis_manager: RedisManager):
        self.redis = redis_manager

    async def add_client_to_room(
        self,
        room_id: str,
        client_id: str,
        user_id: Optional[int] = None
    ) -> bool:
        """添加客户端到房间"""
        try:
            await self.redis.sadd(f"room:{room_id}:clients", client_id)
            if user_id:
                await self.redis.hset(
                    f"room:{room_id}:users",
                    str(client_id),
                    user_id
                )
            await self.redis.incr(f"room:{room_id}:count")
            return True
        except Exception as e:
            print(f"Add client to room error: {e}")
            return False

    async def remove_client_from_room(
        self,
        room_id: str,
        client_id: str
    ) -> bool:
        """从房间移除客户端"""
        try:
            await self.redis.srem(f"room:{room_id}:clients", client_id)
            await self.redis.hdel(f"room:{room_id}:users", str(client_id))
            await self.redis.decr(f"room:{room_id}:count")
            return True
        except Exception as e:
            print(f"Remove client from room error: {e}")
            return False

    async def get_room_clients(self, room_id: str) -> List[str]:
        """获取房间内的所有客户端"""
        try:
            return await self.redis.smembers(f"room:{room_id}:clients")
        except Exception as e:
            print(f"Get room clients error: {e}")
            return []

    async def get_room_client_count(self, room_id: str) -> int:
        """获取房间客户端数量"""
        try:
            return await self.redis.scard(f"room:{room_id}:clients")
        except Exception as e:
            print(f"Get room client count error: {e}")
            return 0

    async def add_message_to_history(
        self,
        room_id: str,
        message: Dict[str, Any]
    ) -> bool:
        """添加消息到历史记录"""
        try:
            await self.redis.rpush(f"room:{room_id}:history", message)
            # 限制历史记录大小
            await self.redis.ltrim(
                f"room:{room_id}:history",
                -100,
                -1
            )
            return True
        except Exception as e:
            print(f"Add message to history error: {e}")
            return False

    async def get_message_history(
        self,
        room_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取消息历史"""
        try:
            return await self.redis.lrange(
                f"room:{room_id}:history",
                -limit,
                -1
            )
        except Exception as e:
            print(f"Get message history error: {e}")
            return []
