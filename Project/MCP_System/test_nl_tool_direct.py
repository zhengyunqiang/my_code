#!/usr/bin/env python3
"""
直接测试自然语言数据库工具（不通过 HTTP）

使用方法：
python test_nl_tool_direct.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from backend.services.tools.nl_database_tool import (
    nl_db_executor,
    QwenNLParser,
    DatabaseSchemaReader,
    TestDataGenerator,
)
from backend.config import settings
from backend.core.logging import setup_logging, get_logger


async def test_parser():
    """测试自然语言解析器"""
    print("\n" + "=" * 60)
    print("测试1: 千问自然语言解析器")
    print("=" * 60)

    parser = QwenNLParser()

    test_inputs = [
        "在 users 表中添加 3 条测试数据",
        "给 products 表插入 10 条数据",
        "查询 orders 表的数据，显示前 5 条",
    ]

    for text in test_inputs:
        try:
            intent = await parser.parse_intent(text, ["users", "products", "orders"])
            print(f"\n输入: {text}")
            print(f"解析: {intent}")
        except Exception as e:
            print(f"\n输入: {text}")
            print(f"错误: {e}")

    return True


async def test_schema_reader():
    """测试数据库表结构读取器"""
    print("\n" + "=" * 60)
    print("测试2: 数据库表结构读取器")
    print("=" * 60)

    reader = DatabaseSchemaReader()

    try:
        tables = await reader.list_tables()
        print(f"\n数据库中的表: {tables}")

        if tables:
            # 获取第一个表的结构
            schema = await reader.get_table_schema(tables[0])
            if schema:
                print(f"\n表 '{tables[0]}' 的结构:")
                for col in schema.columns:
                    pk = " [PK]" if col.primary_key else ""
                    null = " NULL" if col.nullable else " NOT NULL"
                    print(f"  - {col.name}: {col.type}{pk}{null}")

        return True
    except Exception as e:
        print(f"\n错误: {e}")
        return False


async def test_data_generator():
    """测试数据生成器"""
    print("\n" + "=" * 60)
    print("测试3: 测试数据生成器")
    print("=" * 60)

    from backend.services.tools.nl_database_tool import TableSchema, ColumnInfo

    generator = TestDataGenerator()

    # 创建模拟表结构
    mock_schema = TableSchema(
        name="test_users",
        columns=[
            ColumnInfo(name="id", type="INTEGER", nullable=False, primary_key=True, default=None, max_length=None),
            ColumnInfo(name="username", type="VARCHAR(50)", nullable=False, primary_key=False, default=None, max_length=50),
            ColumnInfo(name="email", type="VARCHAR(100)", nullable=False, primary_key=False, default=None, max_length=100),
            ColumnInfo(name="status", type="VARCHAR(20)", nullable=True, primary_key=False, default=None, max_length=20),
        ],
        primary_keys=["id"]
    )

    print("\n生成 3 条测试数据:")
    for i in range(3):
        row = await generator.generate_row_data(mock_schema, i)
        print(f"\n记录 {i + 1}:")
        for key, value in row.items():
            print(f"  {key}: {value}")

    return True


async def test_dry_run():
    """测试预演模式（生成 SQL 但不执行）"""
    print("\n" + "=" * 60)
    print("测试4: 预演模式 - 生成 SQL")
    print("=" * 60)

    try:
        result = await nl_db_executor.execute_nl_request(
            "生成 2 条测试数据",
            dry_run=True
        )

        print(f"\n操作: {result.get('operation')}")
        print(f"表: {result.get('table')}")
        print(f"数量: {result.get('count')}")
        print(f"\n生成的 SQL:")
        print(result.get('generated_sql', ''))
        print(f"\n示例数据:")
        import json
        print(json.dumps(result.get('sample_data'), ensure_ascii=False, indent=2))

        return True
    except Exception as e:
        print(f"\n错误: {e}")
        return False


async def test_insert():
    """测试实际插入数据"""
    print("\n" + "=" * 60)
    print("测试5: 实际插入数据")
    print("=" * 60)

    try:
        result = await nl_db_executor.execute_nl_request(
            "在 users 表中添加 3 条测试数据",
            dry_run=False
        )

        print(f"\n✅ 成功!")
        print(f"操作: {result.get('operation')}")
        print(f"表: {result.get('table')}")
        print(f"数量: {result.get('count')}")
        print(f"\n示例数据:")
        import json
        print(json.dumps(result.get('sample_data'), ensure_ascii=False, indent=2))

        return True
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        return False


async def test_select():
    """测试查询数据"""
    print("\n" + "=" * 60)
    print("测试6: 查询数据")
    print("=" * 60)

    try:
        result = await nl_db_executor.execute_nl_request(
            "查询 users 表的数据，显示前 3 条"
        )

        print(f"\n✅ 成功!")
        print(f"操作: {result.get('operation')}")
        print(f"表: {result.get('table')}")
        print(f"数量: {result.get('count')}")
        print(f"\n数据:")
        import json
        print(json.dumps(result.get('data'), ensure_ascii=False, indent=2))

        return True
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("MCP System - 自然语言数据库工具直接测试")
    print("=" * 60)

    # 设置日志
    setup_logging()

    # 检查配置
    print(f"\n配置:")
    print(f"  千问模型: {settings.QWEN_MODEL}")
    print(f"  数据库: {settings.DATABASE_URL}")

    # 运行测试
    results = []

    results.append(("解析器", await test_parser()))
    results.append(("表结构", await test_schema_reader()))
    results.append(("数据生成", await test_data_generator()))
    results.append(("预演模式", await test_dry_run()))
    results.append(("插入数据", await test_insert()))
    results.append(("查询数据", await test_select()))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name}: {status}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n总计: {passed}/{total} 测试通过")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试已中断")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
