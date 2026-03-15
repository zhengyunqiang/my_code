import asyncio
from database import async_session_maker, User, Room
from sqlalchemy import select
from passlib.context import CryptContext


async def create_test_users():
    """创建测试用户"""
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async with async_session_maker() as session:
        # 检查是否已有用户
        result = await session.execute(select(User).limit(1))
        existing_user = result.scalar_one_or_none()

        if not existing_user:
            # 创建测试用户（使用更短的密码避免 bcrypt 72字节限制）
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

            await session.commit()
            print("✅ 测试用户创建成功")
            print("   - admin / admin123")
            print("   - test / test123")
        else:
            print("ℹ️  用户已存在")


async def create_test_rooms():
    """创建测试房间"""
    async with async_session_maker() as session:
        # 检查是否已有房间
        result = await session.execute(select(Room).limit(1))
        existing_room = result.scalar_one_or_none()

        if not existing_room:
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
            print("✅ 测试房间创建成功")
            print("   - general: 公共大厅")
            print("   - tech: 技术交流")
            print("   - random: 闲聊")
        else:
            print("ℹ️  房间已存在")


async def show_info():
    """显示数据库信息"""
    from sqlalchemy import func

    async with async_session_maker() as session:
        # 统计用户数量
        user_count = await session.execute(select(func.count(User.id)))
        print(f"\n📊 数据库状态:")
        print(f"👥 用户数: {user_count.scalar()}")

        # 统计房间数量
        room_count = await session.execute(select(func.count(Room.id)))
        print(f"🏠 房间数: {room_count.scalar()}")


async def main():
    print("🗄️  创建测试数据")
    print("=" * 30)

    try:
        await create_test_users()
        await create_test_rooms()
        await show_info()
        print("\n✅ 初始化完成！")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
