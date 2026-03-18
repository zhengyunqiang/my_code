"""
Database Connection Management
数据库连接管理 - 复用 FastAPI 项目模式
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
import os

from backend.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


def get_engine_config():
    """根据数据库 URL 获取引擎配置"""
    db_url = settings.DATABASE_URL

    if "sqlite" in db_url.lower():
        # SQLite 配置
        return {
            "url": db_url,
            "echo": settings.DATABASE_ECHO,
            "connect_args": {"check_same_thread": False},
        }
    else:
        # PostgreSQL 配置
        return {
            "url": db_url,
            "echo": settings.DATABASE_ECHO,
            "pool_pre_ping": True,
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        }


# 创建异步引擎
engine_config = get_engine_config()
engine = create_async_engine(**engine_config)

# 创建会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 创建基类
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话

    用于依赖注入，提供异步数据库会话

    Yields:
        AsyncSession: 数据库会话
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    初始化数据库

    创建所有表
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_db() -> None:
    """
    关闭数据库连接

    优雅关闭数据库引擎
    """
    try:
        await engine.dispose()
        logger.info("Database connection closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connection: {e}")
        raise


async def check_db_connection() -> bool:
    """
    检查数据库连接

    Returns:
        bool: 连接是否正常
    """
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
