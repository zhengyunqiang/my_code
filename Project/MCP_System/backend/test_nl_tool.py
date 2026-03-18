"""
测试自然语言数据库工具
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings
from backend.core.logging import setup_logging, get_logger
from backend.services.tools.nl_database_tool import (
    QwenNLParser,
    DatabaseSchemaReader,
    TestDataGenerator,
    NLDatabaseExecutor,
)

# Setup logging
setup_logging()
logger = get_logger(__name__)


async def test_qwen_parser():
    """测试千问解析器"""
    print("\n" + "=" * 60)
    print("测试 1: 千问自然语言解析器")
    print("=" * 60)

    # 检查配置
    print(f"\n📋 配置检查:")
    print(f"  API Key: {'已配置' if hasattr(settings, 'QWEN_API_KEY') and settings.QWEN_API_KEY else '未配置'}")
    print(f"  Base URL: {getattr(settings, 'QWEN_BASE_URL', 'N/A')}")
    print(f"  Model: {getattr(settings, 'QWEN_MODEL', 'N/A')}")

    parser = QwenNLParser()

    # 测试用例
    test_cases = [
        "在users表中添加3条测试数据",
        "给products表插入10条数据",
        "查看orders表的数据",
        "查询customers表前5条记录",
    ]

    print(f"\n🔍 解析测试（模拟有可用表）:")
    mock_tables = ["users", "products", "orders", "customers"]

    for text in test_cases:
        try:
            intent = await parser.parse_intent(text, mock_tables)
            print(f"\n  输入: {text}")
            print(f"  解析: {intent}")
        except Exception as e:
            print(f"\n  输入: {text}")
            print(f"  错误: {e}")


async def test_schema_reader():
    """测试数据库表结构读取器"""
    print("\n" + "=" * 60)
    print("测试 2: 数据库表结构读取器")
    print("=" * 60)

    reader = DatabaseSchemaReader()

    try:
        # 列出所有表
        tables = await reader.list_tables()
        print(f"\n📋 数据库中的表:")
        if tables:
            for tbl in tables:
                print(f"  - {tbl}")

            # 获取第一个表的结构
            if tables:
                first_table = tables[0]
                schema = await reader.get_table_schema(first_table)
                if schema:
                    print(f"\n📋 表 '{first_table}' 的结构:")
                    for col in schema.columns:
                        pk = " [PK]" if col.primary_key else ""
                        null = " NULL" if col.nullable else " NOT NULL"
                        default = f" DEFAULT {col.default}" if col.default else ""
                        print(f"  - {col.name}: {col.type}{pk}{null}{default}")
        else:
            print("  数据库中没有表")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("  提示: 请确保数据库已启动并可连接")


async def test_data_generator():
    """测试数据生成器"""
    print("\n" + "=" * 60)
    print("测试 3: 测试数据生成器")
    print("=" * 60)

    generator = TestDataGenerator()

    # 创建模拟表结构
    from backend.services.tools.nl_database_tool import TableSchema, ColumnInfo

    mock_schema = TableSchema(
        name="users",
        columns=[
            ColumnInfo(name="id", type="INTEGER", nullable=False, primary_key=True, default=None, max_length=None),
            ColumnInfo(name="username", type="VARCHAR(50)", nullable=False, primary_key=False, default=None, max_length=50),
            ColumnInfo(name="email", type="VARCHAR(100)", nullable=False, primary_key=False, default=None, max_length=100),
            ColumnInfo(name="status", type="VARCHAR(20)", nullable=True, primary_key=False, default=None, max_length=20),
            ColumnInfo(name="created_at", type="TIMESTAMP", nullable=True, primary_key=False, default=None, max_length=None),
        ],
        primary_keys=["id"]
    )

    print(f"\n📋 生成 3 条测试数据:")
    for i in range(3):
        row = await generator.generate_row_data(mock_schema, i)
        print(f"\n  记录 {i + 1}:")
        for key, value in row.items():
            print(f"    {key}: {value}")


async def test_full_workflow():
    """测试完整工作流"""
    print("\n" + "=" * 60)
    print("测试 4: 完整工作流（dry_run 模式）")
    print("=" * 60)

    executor = NLDatabaseExecutor()

    # 使用预演模式测试
    test_query = "生成 2 条测试数据"

    try:
        result = await executor.execute_nl_request(test_query, dry_run=True)
        print(f"\n✅ 查询成功: {test_query}")
        print(f"  操作: {result.get('operation')}")
        print(f"  表: {result.get('table')}")
        print(f"  数量: {result.get('count')}")
        if result.get('dry_run'):
            print(f"\n  生成的 SQL:")
            for line in result.get('generated_sql', '').split('\n')[:10]:
                print(f"    {line}")
    except Exception as e:
        print(f"\n❌ 错误: {e}")


async def main():
    """主测试函数"""
    print("\n" + "🔧" * 30)
    print("MCP System - 自然语言数据库工具测试")
    print("🔧" * 30)

    try:
        # 测试 1: 解析器
        await test_qwen_parser()

        # 测试 2: 数据库连接
        await test_schema_reader()

        # 测试 3: 数据生成器
        await test_data_generator()

        # 测试 4: 完整工作流
        await test_full_workflow()

        print("\n" + "=" * 60)
        print("✅ 测试完成")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
