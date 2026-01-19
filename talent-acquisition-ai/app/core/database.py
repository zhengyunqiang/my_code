"""
Database connection and session management.
Uses async SQLAlchemy with PostgreSQL.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    pool_use_lifo=True,  # Use LIFO to reduce idle connections
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class DatabaseManager:
    """Database connection manager."""

    def __init__(self):
        self.engine = engine
        self.session_factory = async_session_factory

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with proper error handling.

        Yields:
            AsyncSession: Database session
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close all database connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")

    async def health_check(self) -> bool:
        """
        Check database connectivity.

        Returns:
            bool: True if database is healthy, False otherwise
        """
        try:
            async with self.get_session() as session:
                await session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.

    Yields:
        AsyncSession: Database session
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.

    Usage:
        async with get_db_context() as session:
            # Use session
            pass

    Yields:
        AsyncSession: Database session
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, model) -> None:
        """Add a model instance to the session."""
        self.session.add(model)

    async def delete(self, model) -> None:
        """Delete a model instance from the session."""
        await self.session.delete(model)

    async def refresh(self, model) -> None:
        """Refresh a model instance from the database."""
        await self.session.refresh(model)

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        await self.session.rollback()

    async def execute(self, query):
        """Execute a SQL query."""
        return await self.session.execute(query)

    async def scalar(self, query):
        """Execute a query and return a scalar result."""
        return await self.session.scalar(query)

    async def scalars_all(self, query):
        """Execute a query and return all scalar results."""
        result = await self.session.execute(query)
        return result.scalars().all()
