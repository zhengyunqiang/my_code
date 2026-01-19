"""
Test configuration and fixtures.
"""
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.core.database import get_db
from app.models.database import Base


settings = get_settings()

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    # Create test engine
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with async_session_maker() as session:
        yield session

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_client(test_db: AsyncSession):
    """Create test client with database override."""
    from fastapi.testclient import TestClient
    from app.main import app

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_jd_request():
    """Sample JD request data."""
    return {
        "client_id": 1,
        "raw_requirement": "我们需要一个Java开发工程师，3-5年经验，熟悉Spring Boot微服务框架。",
        "created_by": 1,
        "priority": "normal",
    }


@pytest.fixture
def sample_resume_text():
    """Sample resume text for testing."""
    return """
张三
手机：13800138000
邮箱：zhangsan@example.com

工作经验
5年

教育背景
本科 - 计算机科学与技术

技能
Java, Spring Boot, MySQL, Redis, Docker, 微服务

工作经历
ABC科技有限公司 | Java开发工程师 | 2020.01 - 至今
- 参与微服务架构设计和开发
- 负责核心业务模块实现
    """
