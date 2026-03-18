"""
Tools Initialization Module
工具初始化 - 自动注册所有工具到系统中
"""

from backend.core.logging import get_logger
from backend.services.tools.registry import tool_registry, tool
from backend.services.tools.db_tools import (
    generate_test_data_handler,
    show_table_structure_handler,
    parse_database_intent_handler,
)
# Import the new natural language database tool
from backend.services.tools import nl_database_tool

logger = get_logger(__name__)


async def init_default_tools() -> None:
    """
    初始化默认工具集

    在应用启动时调用，注册所有预定义的工具
    """
    logger.info("Initializing default tools...")

    # ========================================
    # 数据库工具
    # ========================================

    # 1. 生成测试数据工具
    tool_registry.register(
        name="generate_test_data",
        description=(
            "自动生成并插入数据库测试数据。支持自然语言描述，"
            "例如：'在users表中添加3条测试数据'。"
            "会根据表结构自动生成符合字段类型的测试数据。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "目标表名",
                },
                "count": {
                    "type": "integer",
                    "description": "生成的数据条数",
                    "default": 1,
                },
                "natural_language": {
                    "type": "string",
                    "description": "自然语言描述（可选）",
                },
            },
            "required": ["table_name"],
        },
        handler=generate_test_data_handler,
        category="database",
        timeout=60,
    )

    # 2. 显示表结构工具
    tool_registry.register(
        name="show_table_structure",
        description="显示数据库表的结构信息，包括列名、数据类型、是否可空等",
        input_schema={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "表名（可选，不指定则列出所有表）",
                },
            },
        },
        handler=show_table_structure_handler,
        category="database",
        timeout=30,
    )

    # 3. 解析数据库意图工具
    tool_registry.register(
        name="parse_database_intent",
        description="解析数据库操作的自然语言意图，识别要操作的表、操作类型和参数",
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "自然语言文本",
                },
            },
            "required": ["text"],
        },
        handler=parse_database_intent_handler,
        category="database",
        timeout=10,
    )

    # ========================================
    # 通用工具
    # ========================================

    @tool(
        name="echo",
        description="回显输入的消息",
        category="utility",
        timeout=5,
    )
    async def echo_tool(arguments: dict, context):
        message = arguments.get("message", "")
        return [{"type": "text", "text": f"Echo: {message}"}]

    @tool(
        name="get_current_time",
        description="获取当前时间",
        category="utility",
        timeout=5,
    )
    async def get_time_tool(arguments: dict, context):
        from datetime import datetime
        now = datetime.now()
        return [{
            "type": "text",
            "text": f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        }]

    @tool(
        name="calculate",
        description="执行简单的数学计算",
        category="utility",
        timeout=5,
    )
    async def calculate_tool(arguments: dict, context):
        expression = arguments.get("expression", "")
        try:
            # 安全的数学表达式计算
            allowed_names = {
                "abs": abs,
                "min": min,
                "max": max,
                "sum": sum,
                "round": round,
            }
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return [{
                "type": "text",
                "text": f"{expression} = {result}"
            }]
        except Exception as e:
            return [{
                "type": "text",
                "text": f"计算错误: {str(e)}"
            }]

    logger.info(f"Default tools initialized. Total tools: {tool_registry.get_count()}")


__all__ = ["init_default_tools"]
