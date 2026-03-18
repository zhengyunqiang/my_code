"""
MCP System Configuration Management
基于 pydantic-settings 的配置管理，复用 FastAPI 项目的配置管理模式
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    # ========================================
    # 应用配置
    # ========================================
    APP_NAME: str = "MCP System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"  # development, staging, production

    # ========================================
    # 服务器配置
    # ========================================
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 传输协议配置
    TRANSPORT_TYPE: str = "stdio"  # stdio, http, both
    STDIO_ENABLED: bool = True
    HTTP_ENABLED: bool = True

    # ========================================
    # CORS 配置
    # ========================================
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # ========================================
    # JWT 配置
    # ========================================
    SECRET_KEY: str = "your-mcp-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ========================================
    # API 密钥配置
    # ========================================
    API_KEY_HEADER: str = "X-API-Key"
    API_KEY_LENGTH: int = 32

    # ========================================
    # 数据库配置
    # ========================================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mcp_db"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ========================================
    # Redis 配置
    # ========================================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_DECODE_RESPONSES: bool = True
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5
    REDIS_SOCKET_KEEPALIVE: bool = True

    # 缓存配置
    CACHE_TTL: int = 3600  # 默认缓存过期时间（秒）
    CACHE_MAX_SIZE: int = 10000  # 内存缓存最大条目数

    # ========================================
    # 速率限制配置
    # ========================================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10
    RATE_LIMIT_WINDOW: int = 60  # 秒

    # 用户级别配额
    USER_DAILY_QUOTA: int = 10000  # 每用户每日请求配额
    USER_HOURLY_QUOTA: int = 1000  # 每用户每小时请求配额

    # ========================================
    # MCP 协议配置
    # ========================================
    MCP_PROTOCOL_VERSION: str = "2024-11-05"
    MCP_SERVER_NAME: str = "mcp-system-server"
    MCP_SERVER_VERSION: str = "1.0.0"

    # 能力配置
    MCP_CAPABILITIES_TOOLS: bool = True
    MCP_CAPABILITIES_RESOURCES: bool = True
    MCP_CAPABILITIES_PROMPTS: bool = True
    MCP_CAPABILITIES_LOGGING: bool = True

    # ========================================
    # 安全配置
    # ========================================
    # 输入验证
    MAX_INPUT_LENGTH: int = 100000  # 最大输入长度
    MAX_TOOL_ARGUMENTS_SIZE: int = 100000  # 工具参数最大大小

    # Prompt 注入检测
    PROMPT_INJECTION_ENABLED: bool = True
    PROMPT_INJECTION_PATTERNS: List[str] = [
        "ignore previous instructions",
        "disregard",
        "forget everything",
        "override",
    ]

    # 特殊字符过滤
    SANITIZE_SPECIAL_CHARS: bool = True
    SANITIZE_CONTROL_CHARS: bool = True

    # ========================================
    # 日志配置
    # ========================================
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "json"  # json, text
    LOG_OUTPUT: str = "both"  # stdout, file, both
    LOG_FILE_PATH: str = "logs/mcp_system.log"
    LOG_ROTATION: str = "100 MB"
    LOG_RETENTION: str = "7 days"

    # ========================================
    # 千问 API 配置（用于自然语言解析）
    # ========================================
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"  # qwen-plus, qwen-turbo, qwen-max
    QWEN_MAX_TOKENS: int = 4096
    QWEN_TEMPERATURE: float = 0.7

    # ========================================
    # Kafka 配置
    # ========================================
    KAFKA_BOOTSTRAP_SERVERS: List[str] = ["localhost:9092"]
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_ENABLED: bool = False

    # ========================================
    # 工具执行配置
    # ========================================
    TOOL_EXECUTION_TIMEOUT: int = 30  # 工具执行超时时间（秒）
    TOOL_MAX_CONCURRENT: int = 10  # 最大并发工具执行数
    TOOL_IDEMPOTENCY_ENABLED: bool = True  # 启用幂等性
    TOOL_IDEMPOTENCY_TTL: int = 3600  # 幂等性缓存过期时间（秒）

    # ========================================
    # 资源配置
    # ========================================
    RESOURCE_CACHE_ENABLED: bool = True
    RESOURCE_CACHE_TTL: int = 300  # 资源缓存过期时间（秒）
    RESOURCE_MAX_SIZE: int = 10485760  # 10MB

    # ========================================
    # 监控和健康检查
    # ========================================
    HEALTH_CHECK_ENABLED: bool = True
    HEALTH_CHECK_INTERVAL: int = 30  # 秒
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090

    # ========================================
    # 会话配置
    # ========================================
    SESSION_TIMEOUT: int = 3600  # 会话超时时间（秒）
    SESSION_MAX_REQUESTS: int = 1000  # 每会话最大请求数

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / "backend" / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # 忽略额外的环境变量
    )


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 全局配置实例
settings = get_settings()
