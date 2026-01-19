"""
Core configuration management for Talent Acquisition AI System.
Uses pydantic-settings for type-safe configuration with environment variables.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application Info
    app_name: str = "TALENT_ACQUISITION_AI"
    app_version: str = "1.0.0"
    app_env: Literal["development", "testing", "production"] = "development"
    debug: bool = True
    secret_key: str
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/talent_ai"
    )
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_max_connections: int = 50

    # Qwen API
    qwen_api_key: str
    qwen_model: str = "qwen-max"
    qwen_temperature: float = 0.7
    qwen_max_tokens: int = 2000
    qwen_timeout: int = 60

    # RAG Configuration
    rag_embedding_model: str = "text-embedding-v3"
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 5
    rag_score_threshold: float = 0.7

    # Boss Zhipin RPA
    boss_username: Optional[str] = None
    boss_password: Optional[str] = None
    boss_base_url: str = "https://www.zhipin.com"
    boss_headless: bool = False
    boss_download_path: str = "/tmp/automation_downloads"

    # File Storage
    upload_dir: Path = Field(default_factory=lambda: Path("./static/uploads"))
    max_upload_size: int = 10485760  # 10MB
    allowed_extensions: list[str] = Field(
        default_factory=lambda: ["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"]
    )

    # OCR
    tesseract_cmd: str = "/usr/bin/tesseract"
    tesseract_language: str = "chi_sim+eng"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: Path = Field(default_factory=lambda: Path("./logs"))
    log_rotation: str = "500 MB"
    log_retention: str = "30 days"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: list[str] = Field(default_factory=lambda: ["json"])
    celery_timezone: str = "Asia/Shanghai"
    celery_enable_utc: bool = True

    # Security / JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Monitoring
    sentry_dsn: Optional[str] = None
    sentry_environment: str = "development"
    prometheus_port: int = 9090

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: str = "noreply@talentai.com"
    smtp_from_name: str = "Talent AI System"

    # WeChat Work
    wechat_work_corp_id: Optional[str] = None
    wechat_work_agent_id: Optional[str] = None
    wechat_work_agent_secret: Optional[str] = None

    # External APIs
    chsi_api_url: str = "https://www.chsi.com.cn"
    aliyun_ocr_access_key_id: Optional[str] = None
    aliyun_ocr_access_key_secret: Optional[str] = None

    # Feature Flags
    enable_rpa: bool = True
    enable_auto_jd_optimization: bool = True
    enable_talent_recommendation: bool = True
    enable_auto_feedback_collection: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("upload_dir", "log_dir", mode="before")
    @classmethod
    def convert_to_path(cls, v: str | Path) -> Path:
        """Convert string paths to Path objects and ensure they exist."""
        path = Path(v) if isinstance(v, str) else v
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated allowed hosts string into list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def parse_extensions(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated extensions string into list."""
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS allowed origins based on environment."""
        if self.is_production:
            return ["https://your-production-domain.com"]
        return [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    This ensures settings are loaded only once per application lifecycle.
    """
    return Settings()
