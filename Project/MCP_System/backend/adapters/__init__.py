"""
Adapters Layer Package
适配器层 - 数据访问和外部系统集成
"""

# Database
from backend.adapters.database import (
    get_db,
    init_db,
    close_db,
    async_session_maker,
    Base,
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

# Cache
from backend.adapters.cache import (
    RedisCache,
    redis_cache,
    init_cache,
)

# Messaging
from backend.adapters.messaging import (
    KafkaMessage,
    KafkaProducerAdapter,
    kafka_producer,
    init_kafka_producer,
)

# Storage
from backend.adapters.storage import (
    LocalStorageAdapter,
    local_storage,
)

# External API
from backend.adapters.external import (
    HTTPMethod,
    HTTPRequest,
    HTTPResponse,
    APIEndpoint,
    HTTPClientAdapter,
    http_client,
    init_http_client,
)

__all__ = [
    # Database
    "get_db",
    "init_db",
    "close_db",
    "async_session_maker",
    "Base",
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
    # Cache
    "RedisCache",
    "redis_cache",
    "init_cache",
    # Messaging
    "KafkaMessage",
    "KafkaProducerAdapter",
    "kafka_producer",
    "init_kafka_producer",
    # Storage
    "LocalStorageAdapter",
    "local_storage",
    # External API
    "HTTPMethod",
    "HTTPRequest",
    "HTTPResponse",
    "APIEndpoint",
    "HTTPClientAdapter",
    "http_client",
    "init_http_client",
]
