"""
数据库初始化脚本
用于创建数据库表和初始数据
"""
import asyncio
from database import init_db, close_db, async_session_maker
from sqlalchemy import text
from passlib.context import CryptContext


async def create_database():
    """创建数据库（如果不存在）"""
    import asyncpg
    try:
        # 连接到默认 postgres 数据库
        conn = await asyncpg.connect(
            user="postgres",
            password="postgres",
            host="localhost",
            port=5432,
            database="postgres"
        )

        # 检查数据库是否存在
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = 'websocket_db')"
        )

        if not exists:
            # 创建数据库
            await conn.execute('CREATE DATABASE websocket_db')
            print("✅ Database 'websocket_db' created")
        else:
            print("ℹ️  Database 'websocket_db' already exists")

        await conn.close()
    except Exception as e:
        print(f"❌ Error creating database: {e}")


async def init_database():
    """初始化数据库表"""
    try:
        await init_db()
        print("✅ Database tables initialized")

        # 创建一些测试数据
        await create_test_data()

        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False


async def create_test_data():
    """创建测试数据"""
    try:
        from database import User, Room
        from sqlalchemy import select

        async with async_session_maker() as session:
            # 检查是否已有用户
            result = await session.execute(select(User).limit(1))
            existing_user = result.scalar_one_or_none()

            if not existing_user:
                # 创建测试用户
                pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

                test_users = [
                    User(
                        username="admin",
                        hashed_password=pwd_context.hash("admin123"),
                        email="admin@example.com",
                        display_name="管理员",
                        is_active=True
                    ),
                    User(
                        username="test",
                        hashed_password=pwd_context.hash("test123"),
                        email="test@example.com",
                        display_name="测试用户",
                        is_active=True
                    )
                ]

                for user in test_users:
                    session.add(user)

                # 创建测试房间
                test_rooms = [
                    Room(
                        room_id="general",
                        name="公共大厅",
                        description="欢迎大家来到公共大厅",
                        is_private=False,
                        max_clients=None
                    ),
                    Room(
                        room_id="tech",
                        name="技术交流",
                        description="讨论技术话题",
                        is_private=False,
                        max_clients=50
                    ),
                    Room(
                        room_id="random",
                        name="闲聊",
                        description="随意聊天",
                        is_private=False,
                        max_clients=None
                    )
                ]

                for room in test_rooms:
                    session.add(room)

                await session.commit()
                print("✅ Test data created")
            else:
                print("ℹ️  Test data already exists")

    except Exception as e:
        print(f"❌ Error creating test data: {e}")


async def reset_database():
    """重置数据库（删除所有数据）"""
    try:
        from database import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            print("✅ Database tables dropped")

        await init_db()
        print("✅ Database tables recreated")

        await create_test_data()
        print("✅ Test data recreated")

    except Exception as e:
        print(f"❌ Error resetting database: {e}")


async def show_database_info():
    """显示数据库信息"""
    try:
        from database import User, Room, Message
        from sqlalchemy import select, func

        async with async_session_maker() as session:
            # 统计用户数量
            user_count = await session.execute(select(func.count(User.id)))
            print(f"👥 Users: {user_count.scalar()}")

            # 统计房间数量
            room_count = await session.execute(select(func.count(Room.id)))
            print(f"🏠 Rooms: {room_count.scalar()}")

            # 统计消息数量
            message_count = await session.execute(select(func.count(Message.id)))
            print(f"💬 Messages: {message_count.scalar()}")

            # 列出所有房间
            rooms_result = await session.execute(
                select(Room.room_id, Room.name)
            )
            print("\n📋 Available Rooms:")
            for room_id, name in rooms_result:
                print(f"   - {room_id}: {name}")

    except Exception as e:
        print(f"❌ Error showing database info: {e}")


async def main():
    """主函数"""
    import sys

    print("🗄️  WebSocket Platform Database Manager")
    print("=" * 50)

    # 检查命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "create":
            await create_database()
            await init_database()
        elif command == "init":
            await init_database()
        elif command == "reset":
            confirm = input("⚠️  This will delete all data. Are you sure? (yes/no): ")
            if confirm.lower() == "yes":
                await reset_database()
            else:
                print("❌ Cancelled")
        elif command == "info":
            await show_database_info()
        elif command == "all":
            await create_database()
            await init_database()
            await show_database_info()
        else:
            print(f"❌ Unknown command: {command}")
            print("Available commands: create, init, reset, info, all")
    else:
        print("Usage: python init_db.py [command]")
        print("Commands:")
        print("  create  - Create database")
        print("  init    - Initialize database tables")
        print("  reset   - Reset database (delete all data)")
        print("  info    - Show database information")
        print("  all     - Create, init and show info")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
