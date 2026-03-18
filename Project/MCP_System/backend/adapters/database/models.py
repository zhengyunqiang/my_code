"""
Database Models
数据库模型定义 - MCP 系统所需的所有数据模型
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    JSON, Numeric, Enum as SQLEnum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional

from backend.adapters.database.connection import Base


# ========================================
# 枚举定义
# ========================================

class UserStatus(str, Enum):
    """用户状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class TokenStatus(str, Enum):
    """令牌状态"""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ToolStatus(str, Enum):
    """工具状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class ExecutionStatus(str, Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ========================================
# 用户和认证相关模型
# ========================================

class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)  # 可以为空（API密钥用户）
    display_name = Column(String(100))
    avatar_url = Column(String(255))
    status = Column(SQLEnum(UserStatus), default=UserStatus.PENDING)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta_data = Column(JSON, default=dict)

    # 关系
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    api_tokens = relationship("APIToken", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    quotas = relationship("Quota", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Role(Base):
    """角色模型"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text)
    is_system = Column(Boolean, default=False)  # 系统角色不可删除
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta_data = Column(JSON, default=dict)

    # 关系
    users = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    """权限模型"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    resource = Column(String(50), nullable=False, index=True)  # 工具、资源等
    action = Column(String(50), nullable=False)  # read, write, execute, delete
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_permission_resource_action', 'resource', 'action'),
    )


class UserRole(Base):
    """用户-角色关联表"""
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # 关系
    user = relationship("User", back_populates="roles", foreign_keys=[user_id])
    role = relationship("Role", back_populates="roles")

    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
    )


class RolePermission(Base):
    """角色-权限关联表"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")

    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
    )


class APIToken(Base):
    """API 令牌模型"""
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)  # SHA256 哈希
    name = Column(String(100))  # 令牌名称（如 "Production Token"）
    status = Column(SQLEnum(TokenStatus), default=TokenStatus.ACTIVE)
    scopes = Column(JSON, default=list)  # 权限范围
    rate_limit = Column(Integer)  # 自定义速率限制
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="api_tokens")


# ========================================
# MCP 核心模型
# ========================================

class Tool(Base):
    """工具定义模型"""
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    description = Column(Text)
    category = Column(String(50), index=True)
    status = Column(SQLEnum(ToolStatus), default=ToolStatus.ENABLED)

    # 工具配置
    input_schema = Column(JSON, nullable=False)  # JSON Schema
    output_schema = Column(JSON)  # JSON Schema
    handler_path = Column(String(255))  # 处理器路径
    config = Column(JSON, default=dict)

    # 执行配置
    timeout = Column(Integer, default=30)
    is_async = Column(Boolean, default=False)
    is_idempotent = Column(Boolean, default=True)
    rate_limit = Column(Integer)  # 每分钟调用次数限制
    required_permissions = Column(JSON, default=list)

    # 元数据
    version = Column(String(20))
    author = Column(String(100))
    tags = Column(JSON, default=list)
    examples = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    executions = relationship("ToolExecution", back_populates="tool", cascade="all, delete-orphan")


class Resource(Base):
    """资源定义模型"""
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    uri = Column(String(500), unique=True, nullable=False, index=True)
    name = Column(String(200))
    description = Column(Text)
    resource_type = Column(String(50), index=True)  # file, database, api, etc.
    category = Column(String(50), index=True)

    # 资源配置
    adapter_type = Column(String(50))  # local_file, s3, postgres, etc.
    connection_config = Column(JSON, default=dict)
    cache_config = Column(JSON, default=dict)

    # 访问控制
    required_permissions = Column(JSON, default=list)
    is_public = Column(Boolean, default=False)

    # 元数据
    mime_type = Column(String(100))
    size = Column(Integer)  # 字节
    tags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Prompt(Base):
    """提示词模板模型"""
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    description = Column(Text)
    category = Column(String(50), index=True)

    # 提示词内容
    template = Column(Text, nullable=False)
    variables = Column(JSON, default=list)  # 变量定义列表
    default_values = Column(JSON, default=dict)

    # 配置
    language = Column(String(10), default="zh-CN")
    version = Column(String(20))
    tags = Column(JSON, default=list)
    examples = Column(JSON, default=list)

    # 元数据
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))


# ========================================
# 会话和执行相关模型
# ========================================

class Session(Base):
    """会话模型"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # 会话信息
    transport_type = Column(String(20))  # stdio, http
    client_info = Column(JSON, default=dict)  # IP, User-Agent, etc.
    mcp_capabilities = Column(JSON, default=dict)  # 协商的 MCP 能力

    # 状态
    is_active = Column(Boolean, default=True)
    last_activity = Column(DateTime(timezone=True), default=datetime.utcnow)
    request_count = Column(Integer, default=0)

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    # 关系
    user = relationship("User", back_populates="sessions")


class ToolExecution(Base):
    """工具执行记录模型"""
    __tablename__ = "tool_executions"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(Integer, ForeignKey("tools.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(100), ForeignKey("sessions.session_id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # 执行信息
    status = Column(SQLEnum(ExecutionStatus), default=ExecutionStatus.PENDING)
    arguments = Column(JSON, default=dict)

    # 结果
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)

    # 性能指标
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # 关系
    tool = relationship("Tool", back_populates="executions")

    __table_args__ = (
        Index('idx_tool_execution_session', 'session_id'),
        Index('idx_tool_execution_user', 'user_id'),
        Index('idx_tool_execution_status', 'status'),
    )


# ========================================
# 配额和审计模型
# ========================================

class Quota(Base):
    """用户配额模型"""
    __tablename__ = "quotas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # 配额类型
    quota_type = Column(String(50), nullable=False)  # daily, hourly, monthly
    resource_type = Column(String(50), nullable=False)  # requests, tools, tokens

    # 配额值
    limit = Column(Integer, nullable=False)
    used = Column(Integer, default=0)
    reset_at = Column(DateTime(timezone=True), nullable=False)

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="quotas")

    __table_args__ = (
        UniqueConstraint('user_id', 'quota_type', 'resource_type', name='uq_user_quota'),
    )


class AuditLog(Base):
    """审计日志模型"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(100), ForeignKey("sessions.session_id", ondelete="SET NULL"), nullable=True)

    # 操作信息
    action = Column(String(100), nullable=False, index=True)  # tool.call, resource.read, etc.
    resource_type = Column(String(50))  # tool, resource, prompt
    resource_id = Column(String(100))

    # 请求信息
    request_data = Column(JSON, default=dict)
    response_status = Column(String(20))  # success, error
    response_data = Column(JSON, nullable=True)

    # 安全信息
    ip_address = Column(String(45))  # 支持 IPv6
    user_agent = Column(String(500))

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 关系
    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index('idx_audit_log_user_action', 'user_id', 'action'),
        Index('idx_audit_log_created_at', 'created_at'),
    )
