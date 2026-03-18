"""
Resources System Package
资源系统 - 资源管理器
"""

from backend.services.resources.manager import (
    ResourceType,
    ResourceDefinition,
    ResourceContent,
    ResourceCache,
    ResourceManager,
    resource_manager,
    resource,
)

__all__ = [
    "ResourceType",
    "ResourceDefinition",
    "ResourceContent",
    "ResourceCache",
    "ResourceManager",
    "resource_manager",
    "resource",
]
