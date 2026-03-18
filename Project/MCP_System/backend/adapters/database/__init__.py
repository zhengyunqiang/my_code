"""
Database Adapter Package
数据库适配器 - 支持 SQLite 和 PostgreSQL
"""

from backend.adapters.database.connection import (
    get_db,
    init_db,
    close_db,
    async_session_maker,
    Base,
    engine,
)
from backend.adapters.database.models import (
    User,
    Role,
    Permission,
    Tool,
    Resource,
    Prompt,
    APIToken,
    AuditLog,
    ToolExecution,
    Session,
    Quota,
)

__all__ = [
    # Connection
    "get_db",
    "init_db",
    "close_db",
    "async_session_maker",
    "engine",
    "Base",
    # Models
    "User",
    "Role",
    "Permission",
    "Tool",
    "Resource",
    "Prompt",
    "APIToken",
    "AuditLog",
    "ToolExecution",
    "Session",
    "Quota",
]
