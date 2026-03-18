"""
Authorization Module
授权模块 - RBAC 权限控制
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from backend.core.logging import get_logger
from backend.core.exceptions import ForbiddenError
from backend.gateway.auth import AuthContext

logger = get_logger(__name__)


class ResourceType(str, Enum):
    """资源类型"""
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"
    ADMIN = "admin"


class Action(str, Enum):
    """操作类型"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    MANAGE = "manage"


@dataclass
class Permission:
    """权限定义"""
    resource: ResourceType
    action: Action
    scope: Optional[str] = None  # 特定资源范围，如工具名称

    def __str__(self) -> str:
        if self.scope:
            return f"{self.resource.value}:{self.action.value}:{self.scope}"
        return f"{self.resource.value}:{self.action.value}"

    @classmethod
    def from_string(cls, permission_str: str) -> "Permission":
        """
        从字符串创建权限对象

        Args:
            permission_str: 权限字符串，格式 "resource:action" 或 "resource:action:scope"

        Returns:
            Permission 对象
        """
        parts = permission_str.split(":")
        if len(parts) < 2:
            raise ValueError(f"Invalid permission string: {permission_str}")

        resource = ResourceType(parts[0])
        action = Action(parts[1])
        scope = parts[2] if len(parts) > 2 else None

        return cls(resource=resource, action=action, scope=scope)


@dataclass
class Role:
    """角色定义"""
    name: str
    permissions: Set[Permission] = field(default_factory=set)
    is_system: bool = False
    description: str = ""


# ========================================
# 预定义角色
# ========================================

class SystemRoles:
    """系统预定义角色"""

    @staticmethod
    def admin() -> Role:
        """管理员角色 - 拥有所有权限"""
        permissions = {
            Permission(resource, action)
            for resource in ResourceType
            for action in Action
        }
        return Role(
            name="admin",
            permissions=permissions,
            is_system=True,
            description="Full system access",
        )

    @staticmethod
    def user() -> Role:
        """普通用户角色 - 基本权限"""
        permissions = {
            # 可以读取和执行工具
            Permission(ResourceType.TOOL, Action.READ),
            Permission(ResourceType.TOOL, Action.EXECUTE),
            # 可以读取资源
            Permission(ResourceType.RESOURCE, Action.READ),
            # 可以读取提示词
            Permission(ResourceType.PROMPT, Action.READ),
        }
        return Role(
            name="user",
            permissions=permissions,
            is_system=True,
            description="Standard user access",
        )

    @staticmethod
    def readonly() -> Role:
        """只读角色 - 仅读取权限"""
        permissions = {
            Permission(ResourceType.TOOL, Action.READ),
            Permission(ResourceType.RESOURCE, Action.READ),
            Permission(ResourceType.PROMPT, Action.READ),
        }
        return Role(
            name="readonly",
            permissions=permissions,
            is_system=True,
            description="Read-only access",
        )

    @staticmethod
    def tool_developer() -> Role:
        """工具开发者角色"""
        permissions = {
            Permission(ResourceType.TOOL, Action.READ),
            Permission(ResourceType.TOOL, Action.EXECUTE),
            Permission(ResourceType.TOOL, Action.WRITE),
            Permission(ResourceType.TOOL, Action.MANAGE),
            Permission(ResourceType.RESOURCE, Action.READ),
            Permission(ResourceType.PROMPT, Action.READ),
        }
        return Role(
            name="tool_developer",
            permissions=permissions,
            is_system=True,
            description="Tool developer access",
        )


class RBACManager:
    """
    RBAC 权限管理器

    基于角色的访问控制
    """

    def __init__(self):
        # 角色存储
        self._roles: Dict[str, Role] = {}

        # 用户角色映射
        self._user_roles: Dict[int, Set[str]] = {}

        # 初始化系统角色
        self._init_system_roles()

    def _init_system_roles(self) -> None:
        """初始化系统角色"""
        for role in [SystemRoles.admin(), SystemRoles.user(), SystemRoles.readonly(), SystemRoles.tool_developer()]:
            self._roles[role.name] = role
            logger.debug(f"Loaded system role: {role.name}")

    def register_role(self, role: Role) -> None:
        """
        注册角色

        Args:
            role: 角色对象
        """
        self._roles[role.name] = role
        logger.info(f"Registered role: {role.name}")

    def assign_role_to_user(self, user_id: int, role_name: str) -> None:
        """
        为用户分配角色

        Args:
            user_id: 用户 ID
            role_name: 角色名称
        """
        if role_name not in self._roles:
            raise ValueError(f"Role not found: {role_name}")

        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()

        self._user_roles[user_id].add(role_name)
        logger.info(f"Assigned role '{role_name}' to user {user_id}")

    def remove_role_from_user(self, user_id: int, role_name: str) -> None:
        """
        移除用户角色

        Args:
            user_id: 用户 ID
            role_name: 角色名称
        """
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role_name)
            logger.info(f"Removed role '{role_name}' from user {user_id}")

    def get_user_roles(self, user_id: int) -> Set[str]:
        """
        获取用户角色

        Args:
            user_id: 用户 ID

        Returns:
            角色名称集合
        """
        return self._user_roles.get(user_id, set())

    def get_user_permissions(self, user_id: int) -> Set[Permission]:
        """
        获取用户所有权限

        Args:
            user_id: 用户 ID

        Returns:
            权限集合
        """
        permissions = set()
        for role_name in self.get_user_roles(user_id):
            role = self._roles.get(role_name)
            if role:
                permissions.update(role.permissions)
        return permissions

    def has_permission(
        self,
        user_id: int,
        resource: ResourceType,
        action: Action,
        scope: Optional[str] = None,
    ) -> bool:
        """
        检查用户是否有指定权限

        Args:
            user_id: 用户 ID
            resource: 资源类型
            action: 操作类型
            scope: 资源范围

        Returns:
            是否有权限
        """
        # 获取用户权限
        user_permissions = self.get_user_permissions(user_id)

        # 检查精确匹配
        required_permission = Permission(resource=resource, action=action, scope=scope)
        if required_permission in user_permissions:
            return True

        # 检查通配符匹配（无 scope 的权限适用于所有 scope）
        wildcard_permission = Permission(resource=resource, action=action, scope=None)
        if wildcard_permission in user_permissions:
            return True

        # 检查管理员权限
        admin_permission = Permission(resource=ResourceType.ADMIN, action=Action.MANAGE)
        if admin_permission in user_permissions:
            return True

        return False

    def check_permission(
        self,
        user_id: int,
        resource: ResourceType,
        action: Action,
        scope: Optional[str] = None,
    ) -> None:
        """
        检查权限，无权限时抛出异常

        Args:
            user_id: 用户 ID
            resource: 资源类型
            action: 操作类型
            scope: 资源范围

        Raises:
            ForbiddenError: 无权限
        """
        if not self.has_permission(user_id, resource, action, scope):
            required = Permission(resource, action, scope)
            raise ForbiddenError(
                message=f"Permission denied: {required}",
                required_permission=str(required),
            )

    def can_execute_tool(self, user_id: int, tool_name: str) -> bool:
        """
        检查是否可以执行工具

        Args:
            user_id: 用户 ID
            tool_name: 工具名称

        Returns:
            是否可以执行
        """
        return self.has_permission(
            user_id,
            ResourceType.TOOL,
            Action.EXECUTE,
            scope=tool_name,
        )

    def can_read_resource(self, user_id: int, resource_uri: str) -> bool:
        """
        检查是否可以读取资源

        Args:
            user_id: 用户 ID
            resource_uri: 资源 URI

        Returns:
            是否可以读取
        """
        return self.has_permission(
            user_id,
            ResourceType.RESOURCE,
            Action.READ,
            scope=resource_uri,
        )

    def can_write_resource(self, user_id: int, resource_uri: str) -> bool:
        """
        检查是否可以写入资源

        Args:
            user_id: 用户 ID
            resource_uri: 资源 URI

        Returns:
            是否可以写入
        """
        return self.has_permission(
            user_id,
            ResourceType.RESOURCE,
            Action.WRITE,
            scope=resource_uri,
        )

    def get_role(self, role_name: str) -> Optional[Role]:
        """
        获取角色

        Args:
            role_name: 角色名称

        Returns:
            角色对象，不存在返回 None
        """
        return self._roles.get(role_name)

    def list_roles(self) -> List[Role]:
        """
        列出所有角色

        Returns:
            角色列表
        """
        return list(self._roles.values())


# ========================================
# 全局实例
# ========================================

rbac_manager = RBACManager()


__all__ = [
    "ResourceType",
    "Action",
    "Permission",
    "Role",
    "SystemRoles",
    "RBACManager",
    "rbac_manager",
]
