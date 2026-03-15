from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "WebSocket Realtime Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS 配置
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:8000"]

    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # WebSocket 配置
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds
    WS_MAX_CONNECTIONS: int = 1000
    WS_MESSAGE_QUEUE_SIZE: int = 100

    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/websocket_db"
    DATABASE_ECHO: bool = False

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_DECODE_RESPONSES: bool = True

    # 速率限制
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # 房间配置
    MAX_ROOM_SIZE: int = 100
    MAX_MESSAGE_LENGTH: int = 5000
    MESSAGE_HISTORY_LIMIT: int = 100
    ROOM_AUTO_DELETE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
