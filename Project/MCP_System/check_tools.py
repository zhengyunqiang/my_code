#!/usr/bin/env python3
"""检查工具是否注册"""
import sys
import asyncio
sys.path.insert(0, '.')

async def main():
    from backend.protocol.handlers import create_default_handler
    from backend.services.tools.registry import tool_registry
    from backend.services.tools.init_tools import init_default_tools

    print("1. 初始化工具...")
    await init_default_tools()

    print(f"\n2. 全局工具注册表中的工具: {list(tool_registry._tools.keys())}")

    print("\n3. 创建 handler...")
    handler = create_default_handler()

    print(f"\n4. Handler 中的工具: {handler.get_registered_tools()}")

    print("\n5. 测试 nl_database_operation 是否存在:")
    if "nl_database_operation" in handler.get_registered_tools():
        print("✅ nl_database_operation 已注册")
    else:
        print("❌ nl_database_operation 未注册")

asyncio.run(main())
