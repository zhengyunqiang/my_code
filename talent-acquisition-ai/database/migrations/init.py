"""
Database initialization and migration scripts.
Run with: python -m database.migrations.init
"""
import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.logger import get_logger
from app.models.database import Base

settings = get_settings()
logger = get_logger(__name__)


async def create_tables():
    """Create all database tables."""
    logger.info("Creating database tables...")

    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created successfully")


async def drop_tables():
    """Drop all database tables (use with caution!)."""
    logger.warning("Dropping all database tables...")

    from app.core.database import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    logger.info("Database tables dropped")


async def seed_sample_data():
    """Seed database with sample data for testing."""
    logger.info("Seeding sample data...")

    from app.core.database import async_session_factory
    from app.models.database import (
        User,
        Client,
        Project,
        ProjectDocument,
    )
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async with async_session_factory() as session:
        # Create admin user
        admin_user = User(
            username="admin",
            email="admin@talentai.com",
            hashed_password=pwd_context.hash("admin123"),
            full_name="System Administrator",
            role="admin",
            is_active=True,
            is_superuser=True,
        )
        session.add(admin_user)

        # Create demo client
        demo_client = Client(
            name="Demo Tech Company",
            company_code="DEM001",
            industry="Technology",
            contact_person="张三",
            contact_phone="13800138000",
            contact_email="zhangsan@demo.com",
            address="北京市朝阳区XX路XX号",
            is_active=True,
        )
        session.add(demo_client)

        await session.flush()

        # Create demo project
        demo_project = Project(
            name="移动物联网基地项目",
            code="PROJ-IOT-001",
            client_id=demo_client.id,
            description="基于物联网技术的智能监控系统，包含设备管理、数据采集、分析展示等功能模块",
            tech_stack={
                "languages": ["Java", "Python", "JavaScript"],
                "frameworks": ["Spring Boot", "Vue.js", "React"],
                "databases": ["MySQL", "Redis", "InfluxDB"],
                "tools": ["Docker", "Kubernetes", "Git", "Jenkins"],
            },
            business_domain="物联网",
            start_date=datetime(2024, 1, 1),
            team_size=15,
            project_type="web",
            complexity_level="high",
            key_challenges=[
                "高并发数据处理",
                "实时数据传输",
                "多设备协议适配",
            ],
            success_metrics=[
                "支持10万+设备接入",
                "数据处理延迟<100ms",
                "系统可用性99.9%",
            ],
            is_active=True,
        )
        session.add(demo_project)

        await session.flush()

        # Create demo project document
        demo_doc = ProjectDocument(
            project_id=demo_project.id,
            title="移动物联网基地技术需求文档",
            document_type="requirement",
            file_path="/docs/iot-requirements.pdf",
            content_text="""
项目名称：移动物联网基地智能监控系统

1. 项目背景
本项目旨在构建一套完整的物联网设备管理和监控系统，实现设备的远程监控、数据采集、智能分析等功能。

2. 技术要求
2.1 后端开发
- 熟练掌握Java编程语言，3年以上开发经验
- 精通Spring Boot、Spring Cloud等微服务框架
- 熟悉MySQL、Redis等数据库技术
- 了解消息队列（RabbitMQ/Kafka）使用
- 有高并发、分布式系统开发经验优先

2.2 前端开发
- 熟练掌握Vue.js或React框架
- 熟悉前端工程化工具
- 了解数据可视化库（ECharts/D3.js）

2.3 其他要求
- 了解物联网协议（MQTT/CoAP）优先
- 有智能硬件相关项目经验优先
- 良好的沟通能力和团队协作精神

3. 工作要求
- 能接受项目周期内适度加班
- 可根据项目需求出差
- 具备快速学习能力
            """.strip(),
            metadata={"version": "1.0", "author": "技术部"},
            is_processed=True,
        )
        session.add(demo_doc)

        # Create demo recruiter
        demo_recruiter = User(
            username="recruiter",
            email="recruiter@talentai.com",
            hashed_password=pwd_context.hash("recruiter123"),
            full_name="招聘专员",
            role="recruiter",
            department="人力资源部",
            is_active=True,
        )
        session.add(demo_recruiter)

        await session.commit()

        logger.info("Sample data seeded successfully")


async def reset_database():
    """Reset database: drop, create, and seed."""
    logger.info("Resetting database...")

    await drop_tables()
    await create_tables()
    await seed_sample_data()

    logger.info("Database reset completed")


async def main():
    """Main entry point for database operations."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m database.migrations.init [create|drop|seed|reset]")
        return

    command = sys.argv[1].lower()

    if command == "create":
        await create_tables()
    elif command == "drop":
        await drop_tables()
    elif command == "seed":
        await seed_sample_data()
    elif command == "reset":
        await reset_database()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: create, drop, seed, reset")


if __name__ == "__main__":
    asyncio.run(main())
