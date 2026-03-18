"""
Resources Manager Module
资源管理器 - 管理和访问资源
"""

import asyncio
import hashlib
import mimetypes
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.core.logging import get_logger
from backend.core.exceptions import ResourceNotFoundError, ResourceAccessDeniedError
from backend.config import settings

logger = get_logger(__name__)


class ResourceType(str, Enum):
    """资源类型"""
    FILE = "file"
    DATABASE = "database"
    API = "api"
    MEMORY = "memory"
    CUSTOM = "custom"


@dataclass
class ResourceDefinition:
    """资源定义"""
    uri: str
    name: str
    description: str = ""
    resource_type: ResourceType = ResourceType.FILE
    mime_type: str = "text/plain"
    handler: Optional[Callable] = None
    adapter_type: str = "local"
    connection_config: Dict[str, Any] = field(default_factory=dict)
    cache_config: Dict[str, Any] = field(default_factory=dict)
    is_public: bool = False
    required_permissions: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class ResourceContent:
    """资源内容"""
    uri: str
    mime_type: str
    text: Optional[str] = None
    data: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    last_modified: Optional[datetime] = None


class ResourceCache:
    """资源缓存"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        初始化资源缓存

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
        """
        self._cache: Dict[str, tuple[ResourceContent, float]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, uri: str) -> Optional[ResourceContent]:
        """
        获取缓存内容

        Args:
            uri: 资源 URI

        Returns:
            ResourceContent 或 None
        """
        if uri not in self._cache:
            return None

        content, expiry = self._cache[uri]

        # 检查是否过期
        if asyncio.get_event_loop().time() > expiry:
            del self._cache[uri]
            return None

        content.cached = True
        return content

    def set(self, uri: str, content: ResourceContent, ttl: Optional[int] = None) -> None:
        """
        设置缓存

        Args:
            uri: 资源 URI
            content: 资源内容
            ttl: 过期时间（秒）
        """
        # 检查缓存大小
        if len(self._cache) >= self._max_size:
            # 简单的 LRU：删除第一个
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        expiry = asyncio.get_event_loop().time() + (ttl or self._default_ttl)
        self._cache[uri] = (content, expiry)

    def invalidate(self, uri: str) -> None:
        """
        使缓存失效

        Args:
            uri: 资源 URI
        """
        if uri in self._cache:
            del self._cache[uri]

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "default_ttl": self._default_ttl,
        }


class ResourceManager:
    """
    资源管理器

    管理和访问各种类型的资源
    """

    def __init__(self):
        self._resources: Dict[str, ResourceDefinition] = {}
        self._cache = ResourceCache()

    def register(
        self,
        uri: str,
        name: str,
        description: str = "",
        resource_type: ResourceType = ResourceType.FILE,
        handler: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        """
        注册资源

        Args:
            uri: 资源 URI（唯一标识）
            name: 资源名称
            description: 资源描述
            resource_type: 资源类型
            handler: 资源读取函数
            **kwargs: 额外参数
        """
        if uri in self._resources:
            logger.warning(f"Resource '{uri}' already registered, overwriting")

        resource_def = ResourceDefinition(
            uri=uri,
            name=name,
            description=description,
            resource_type=resource_type,
            handler=handler,
            **kwargs,
        )

        self._resources[uri] = resource_def
        logger.info(f"Registered resource: {uri} (type: {resource_type.value})")

    def unregister(self, uri: str) -> None:
        """
        注销资源

        Args:
            uri: 资源 URI
        """
        if uri in self._resources:
            del self._resources[uri]
            self._cache.invalidate(uri)
            logger.info(f"Unregistered resource: {uri}")

    def get(self, uri: str) -> Optional[ResourceDefinition]:
        """
        获取资源定义

        Args:
            uri: 资源 URI

        Returns:
            ResourceDefinition 或 None
        """
        return self._resources.get(uri)

    def list_resources(
        self,
        resource_type: Optional[ResourceType] = None,
    ) -> List[ResourceDefinition]:
        """
        列出资源

        Args:
            resource_type: 资源类型过滤

        Returns:
            资源定义列表
        """
        resources = list(self._resources.values())

        if resource_type:
            resources = [r for r in resources if r.resource_type == resource_type]

        return resources

    def exists(self, uri: str) -> bool:
        """
        检查资源是否存在

        Args:
            uri: 资源 URI

        Returns:
            是否存在
        """
        return uri in self._resources

    async def read(
        self,
        uri: str,
        use_cache: bool = True,
        user_id: Optional[int] = None,
    ) -> ResourceContent:
        """
        读取资源

        Args:
            uri: 资源 URI
            use_cache: 是否使用缓存
            user_id: 用户 ID（用于权限检查）

        Returns:
            ResourceContent

        Raises:
            ResourceNotFoundError: 资源不存在
            ResourceAccessDeniedError: 无访问权限
        """
        # 检查资源是否存在
        resource_def = self._resources.get(uri)
        if resource_def is None:
            raise ResourceNotFoundError(uri)

        # 检查权限（简化实现）
        if not resource_def.is_public and user_id is None:
            # 实际应该检查用户权限
            pass

        # 检查缓存
        if use_cache and settings.RESOURCE_CACHE_ENABLED:
            cached = self._cache.get(uri)
            if cached:
                logger.debug(f"Cache hit for resource: {uri}")
                return cached

        # 读取资源
        try:
            content = await self._read_resource(resource_def)
            content.cached = False

            # 更新缓存
            if use_cache and settings.RESOURCE_CACHE_ENABLED:
                cache_ttl = resource_def.cache_config.get("ttl", settings.RESOURCE_CACHE_TTL)
                self._cache.set(uri, content, cache_ttl)

            return content

        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            raise

    async def _read_resource(self, resource_def: ResourceDefinition) -> ResourceContent:
        """
        读取资源内部实现

        Args:
            resource_def: 资源定义

        Returns:
            ResourceContent
        """
        # 如果有自定义处理器，使用它
        if resource_def.handler:
            result = await resource_def.handler(resource_def.uri)
            if isinstance(result, ResourceContent):
                return result
            # 转换为 ResourceContent
            return ResourceContent(
                uri=resource_def.uri,
                mime_type=resource_def.mime_type,
                text=str(result),
            )

        # 根据类型读取
        if resource_def.adapter_type == "local":
            return await self._read_local_file(resource_def)
        elif resource_def.adapter_type == "memory":
            return await self._read_memory(resource_def)
        else:
            raise ResourceAccessDeniedError(
                resource_uri=resource_def.uri,
                required_permission="unknown_adapter",
            )

    async def _read_local_file(self, resource_def: ResourceDefinition) -> ResourceContent:
        """读取本地文件"""
        file_path = resource_def.connection_config.get("path", resource_def.uri)

        # 移除 file:// 前缀
        if file_path.startswith("file://"):
            file_path = file_path[7:]

        path = Path(file_path)

        if not path.exists():
            raise ResourceNotFoundError(resource_def.uri)

        # 检查大小
        file_size = path.stat().st_size
        if file_size > settings.RESOURCE_MAX_SIZE:
            raise ResourceAccessDeniedError(
                resource_uri=resource_def.uri,
                required_permission="file_too_large",
            )

        # 读取文件
        content = path.read_text(encoding="utf-8")

        return ResourceContent(
            uri=resource_def.uri,
            mime_type=self._get_mime_type(path),
            text=content,
            last_modified=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
        )

    async def _read_memory(self, resource_def: ResourceDefinition) -> ResourceContent:
        """读取内存资源"""
        data = resource_def.connection_config.get("data", "")

        return ResourceContent(
            uri=resource_def.uri,
            mime_type=resource_def.mime_type,
            text=str(data),
        )

    def _get_mime_type(self, path: Path) -> str:
        """获取 MIME 类型"""
        mime_type, _ = mimetypes.guess_type(str(path))
        return mime_type or "text/plain"

    def invalidate_cache(self, uri: Optional[str] = None) -> None:
        """
        使缓存失效

        Args:
            uri: 资源 URI，None 表示清空所有缓存
        """
        if uri:
            self._cache.invalidate(uri)
        else:
            self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return self._cache.get_stats()


# 全局资源管理器
resource_manager = ResourceManager()


# ========================================
# 资源装饰器
# ========================================

def resource(
    uri: str,
    name: str,
    description: str = "",
    resource_type: ResourceType = ResourceType.FILE,
    **kwargs,
):
    """
    资源装饰器

    用于注册资源读取函数

    Args:
        uri: 资源 URI
        name: 资源名称
        description: 资源描述
        resource_type: 资源类型
        **kwargs: 额外参数
    """
    def decorator(func: Callable) -> Callable:
        resource_manager.register(
            uri=uri,
            name=name,
            description=description,
            resource_type=resource_type,
            handler=func,
            **kwargs,
        )
        return func

    return decorator


__all__ = [
    "ResourceType",
    "ResourceDefinition",
    "ResourceContent",
    "ResourceCache",
    "ResourceManager",
    "resource_manager",
    "resource",
]
