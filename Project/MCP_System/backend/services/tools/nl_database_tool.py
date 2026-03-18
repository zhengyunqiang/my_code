"""
Natural Language Database Tool
自然语言数据库操作工具 - 使用千问 API 解析自然语言并执行数据库操作

功能：
1. 解析自然语言数据库操作请求
2. 获取目标表结构
3. 根据表结构生成符合的测试数据
4. 执行数据库插入操作
"""

import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from openai import AsyncOpenAI
from sqlalchemy import text, inspect as sql_inspect

from backend.core.logging import get_logger
from backend.core.exceptions import (
    ToolExecutionError,
    InvalidParamsError,
)
from backend.adapters.database import async_session_maker
from backend.config import settings
from backend.services.tools.registry import tool
from backend.services.prompts.prompt_manager import (
    prompt_manager,
    NL_DATABASE_PARSE_SYSTEM,
    NL_DATABASE_PARSE_USER,
)

logger = get_logger(__name__)


# ========================================
# 数据结构定义
# ========================================

@dataclass
class ParsedIntent:
    """解析后的意图"""
    operation: str  # insert, select, update, delete
    table_name: str
    count: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    raw_query: Optional[str] = None

    def __repr__(self):
        return f"ParsedIntent(op={self.operation}, table={self.table_name}, count={self.count})"


@dataclass
class ColumnInfo:
    """列信息"""
    name: str
    type: str
    nullable: bool
    primary_key: bool
    default: Optional[Any]
    max_length: Optional[int]
    foreign_key: Optional[str] = None


@dataclass
class TableSchema:
    """表结构"""
    name: str
    columns: List[ColumnInfo]
    primary_keys: List[str]

    def get_column(self, name: str) -> Optional[ColumnInfo]:
        """获取列信息"""
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def get_non_pk_columns(self) -> List[ColumnInfo]:
        """获取非主键列"""
        return [col for col in self.columns if not col.primary_key]


# ========================================
# 千问 API 客户端
# ========================================

class QwenNLParser:
    """千问自然语言解析器 - 使用阿里云通义千问 API"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or getattr(settings, 'QWEN_API_KEY', None)
        self.base_url = base_url or getattr(settings, 'QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        self.model = getattr(settings, 'QWEN_MODEL', 'qwen-plus')

        if self.api_key:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            logger.info(f"QwenNLParser initialized with model: {self.model}")
        else:
            self.client = None
            logger.warning("Qwen API key not configured, NL parsing will use fallback regex")

    async def parse_intent(self, text: str, available_tables: List[str]) -> ParsedIntent:
        """
        解析自然语言意图

        Args:
            text: 自然语言输入
            available_tables: 可用的表名列表

        Returns:
            ParsedIntent 解析后的意图
        """
        if self.client:
            return await self._parse_with_qwen(text, available_tables)
        else:
            return self._parse_with_regex(text, available_tables)

    async def _parse_with_qwen(self, text: str, available_tables: List[str]) -> ParsedIntent:
        """使用千问 API 解析"""
        # 使用统一的提示词管理器获取提示词
        tables_str = "、".join(available_tables)

        system_prompt = prompt_manager.render(
            NL_DATABASE_PARSE_SYSTEM.name,
            available_tables=available_tables,
        )

        user_message = prompt_manager.render(
            NL_DATABASE_PARSE_USER.name,
            tables=tables_str,
            user_input=text,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"}  # 强制返回 JSON
            )

            content = response.choices[0].message.content
            logger.debug(f"Qwen API response: {content}")

            # 解析 JSON
            result = json.loads(content)

            # 验证表名是否在可用列表中
            table_name = result.get("table_name", "")
            if table_name and table_name not in available_tables:
                # 尝试模糊匹配
                for tbl in available_tables:
                    if tbl.lower() in table_name.lower() or table_name.lower() in tbl.lower():
                        table_name = tbl
                        break
                else:
                    table_name = available_tables[0] if available_tables else ""

            return ParsedIntent(
                operation=result.get("operation", "insert"),
                table_name=table_name,
                count=result.get("count"),
                conditions=result.get("conditions"),
                data=result.get("data"),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Qwen API JSON parsing failed: {e}, falling back to regex")
            return self._parse_with_regex(text, available_tables)
        except Exception as e:
            logger.warning(f"Qwen API call failed: {e}, falling back to regex")
            return self._parse_with_regex(text, available_tables)

    def _parse_with_regex(self, text: str, available_tables: List[str]) -> ParsedIntent:
        """使用正则表达式回退解析"""
        text_lower = text.lower()

        # 检测操作类型
        operation = "insert"  # 默认
        if any(word in text_lower for word in ["插入", "添加", "新增", "增加", "insert", "add"]):
            operation = "insert"
        elif any(word in text_lower for word in ["查询", "查找", "搜索", "查看", "select", "find", "search"]):
            operation = "select"
        elif any(word in text_lower for word in ["更新", "修改", "update", "modify"]):
            operation = "update"
        elif any(word in text_lower for word in ["删除", "移除", "delete", "remove"]):
            operation = "delete"

        # 提取表名
        table_name = None
        for tbl in available_tables:
            if tbl.lower() in text_lower or tbl.lower().replace("_", "") in text_lower.replace(" ", ""):
                table_name = tbl
                break

        if not table_name and available_tables:
            # 如果找不到匹配的表，使用第一个可用表
            table_name = available_tables[0]

        # 提取数量
        count = None
        count_patterns = [
            r"(\d+)条",
            r"(\d+)个",
            r"(\d+)行",
            r"第?(\d+)条?",
        ]
        for pattern in count_patterns:
            match = re.search(pattern, text)
            if match:
                count = int(match.group(1))
                break

        # 中文数字转换
        if count is None:
            cn_numbers = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                         "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            for cn, num in cn_numbers.items():
                if cn in text:
                    count = num
                    break

        return ParsedIntent(
            operation=operation,
            table_name=table_name or "",
            count=count or 1,
        )


# ========================================
# 数据库操作类
# ========================================

class DatabaseSchemaReader:
    """数据库表结构读取器"""

    async def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """
        获取表结构

        Args:
            table_name: 表名

        Returns:
            TableSchema 表结构信息
        """
        try:
            from backend.adapters.database import engine

            def _get_schema_info(bind):
                from sqlalchemy import inspect
                inspector = inspect(bind)

                # 检查表是否存在
                if table_name not in inspector.get_table_names():
                    return None

                # 获取列信息
                columns = []
                primary_keys = inspector.get_pk_constraint(table_name).get("constrained_columns", [])

                for col in inspector.get_columns(table_name):
                    col_info = ColumnInfo(
                        name=col["name"],
                        type=str(col["type"]),
                        nullable=col.get("nullable", True),
                        primary_key=col["name"] in primary_keys,
                        default=col.get("default"),
                        max_length=self._get_max_length(col["type"]),
                    )
                    columns.append(col_info)

                # 获取外键信息
                for fk in inspector.get_foreign_keys(table_name):
                    for col_name in fk["constrained_columns"]:
                        for col in columns:
                            if col.name == col_name:
                                col.foreign_key = f"{fk['referred_table']}.{fk['referred_columns'][0]}"

                return TableSchema(
                    name=table_name,
                    columns=columns,
                    primary_keys=primary_keys,
                )

            async with engine.begin() as conn:
                result = await conn.run_sync(_get_schema_info)
                return result

        except Exception as e:
            logger.error(f"Failed to get table schema for '{table_name}': {e}")
            raise ToolExecutionError(f"Failed to read table schema: {str(e)}")

    def _get_max_length(self, col_type) -> Optional[int]:
        """获取列最大长度"""
        type_str = str(col_type)
        if "varchar" in type_str.lower() or "char" in type_str.lower():
            match = re.search(r"\((\d+)\)", type_str)
            if match:
                return int(match.group(1))
        return None

    async def list_tables(self) -> List[str]:
        """列出所有表"""
        try:
            from backend.adapters.database import engine
            # 直接从 engine 获取表名
            def _get_table_names(bind):
                from sqlalchemy import inspect
                return inspect(bind).get_table_names()

            async with engine.begin() as conn:
                table_names = await conn.run_sync(_get_table_names)
                return table_names
        except Exception as e:
            logger.error(f"Failed to list tables: {e}")
            return []


class TestDataGenerator:
    """测试数据生成器"""

    def __init__(self):
        # 按类型分类的样本数据
        self.sample_data = {
            "name": ["张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十",
                    "Alice", "Bob", "Charlie", "David", "Emma", "Frank", "Grace", "Henry"],
            "username": ["user001", "test_user", "demo_account", "sample_user", "john_doe"],
            "email": ["test@example.com", "user@test.com", "demo@sample.com",
                     "admin@example.org", "user123@testmail.com"],
            "title": ["测试标题1", "示例数据", "Sample Title", "测试条目", "Demo Record"],
            "description": ["这是测试数据", "示例描述内容", "Sample description text",
                          "Test record description", "演示数据说明"],
            "status": ["active", "inactive", "pending", "completed"],
            "phone": ["13800138000", "13900139000", "13700137000", "13600136000"],
            "address": ["北京市朝阳区", "上海市浦东新区", "广州市天河区",
                       "深圳市南山区", "杭州市西湖区"],
            "company": ["测试公司A", "示例企业B", "Sample Corp", "Demo Inc", "Test Company"],
            "url": ["https://example.com", "https://test.com", "http://demo.example"],
        }

    async def generate_row_data(
        self,
        schema: TableSchema,
        index: int = 0
    ) -> Dict[str, Any]:
        """
        生成单行数据

        Args:
            schema: 表结构
            index: 数据索引（用于生成唯一值）

        Returns:
            字段名到值的字典
        """
        row = {}

        for col in schema.columns:
            # 跳过自增主键
            if col.primary_key and col.default is not None:
                continue

            # 跳过有默认值的非空字段
            if col.default is not None and not col.nullable:
                continue

            # 生成值
            value = self._generate_value(col, index)
            if value is not None:
                row[col.name] = value

        return row

    def _generate_value(self, col: ColumnInfo, index: int) -> Any:
        """为单个列生成值"""
        col_type_lower = col.type.lower()
        col_name_lower = col.name.lower()

        # 根据列名语义推断
        if "email" in col_name_lower:
            return self.sample_data["email"][index % len(self.sample_data["email"])]
        elif "name" in col_name_lower and "user" not in col_name_lower:
            return self.sample_data["name"][index % len(self.sample_data["name"])]
        elif "username" in col_name_lower or "user_name" in col_name_lower:
            return f"{self.sample_data['username'][index % len(self.sample_data['username'])]}_{index}"
        elif "title" in col_name_lower:
            return self.sample_data["title"][index % len(self.sample_data["title"])]
        elif "description" in col_name_lower or "desc" in col_name_lower:
            return self.sample_data["description"][index % len(self.sample_data["description"])]
        elif "status" in col_name_lower:
            return self.sample_data["status"][0]  # 默认使用第一个状态
        elif "phone" in col_name_lower or "mobile" in col_name_lower or "tel" in col_name_lower:
            return self.sample_data["phone"][index % len(self.sample_data["phone"])]
        elif "address" in col_name_lower:
            return self.sample_data["address"][index % len(self.sample_data["address"])]
        elif "company" in col_name_lower:
            return self.sample_data["company"][index % len(self.sample_data["company"])]
        elif "url" in col_name_lower or "link" in col_name_lower:
            return self.sample_data["url"][index % len(self.sample_data["url"])]
        elif "password" in col_name_lower or "pwd" in col_name_lower:
            return "test_password_123"

        # 根据数据类型生成
        if "int" in col_type_lower:
            return 1000 + index
        elif "bigint" in col_type_lower:
            return 1000000 + index
        elif "float" in col_type_lower or "double" in col_type_lower or "decimal" in col_type_lower:
            return 100.5 + (index * 0.1)
        elif "bool" in col_type_lower:
            return index % 2 == 0
        elif "date" in col_type_lower:
            return datetime.now().strftime("%Y-%m-%d")
        elif "time" in col_type_lower:
            return datetime.now().strftime("%H:%M:%S")
        elif "timestamp" in col_type_lower or "datetime" in col_type_lower:
            return datetime.now().isoformat()
        elif "text" in col_type_lower or "varchar" in col_type_lower or "char" in col_type_lower:
            max_len = col.max_length or 100
            return f"测试数据_{index}".ljust(max_len)[:max_len]
        elif "json" in col_type_lower:
            return json.dumps({"test": True, "index": index})
        else:
            return f"value_{index}"


class NLDatabaseExecutor:
    """自然语言数据库执行器"""

    def __init__(self):
        self.parser = QwenNLParser()
        self.schema_reader = DatabaseSchemaReader()
        self.data_generator = TestDataGenerator()

    async def execute_nl_request(
        self,
        natural_language: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        执行自然语言数据库请求

        Args:
            natural_language: 自然语言输入
            dry_run: 是否预演模式（只生成SQL不执行）

        Returns:
            执行结果
        """
        # 1. 获取可用表
        available_tables = await self.schema_reader.list_tables()
        if not available_tables:
            raise ToolExecutionError("no_tables", "No tables found in database")

        # 2. 解析意图
        intent = await self.parser.parse_intent(natural_language, available_tables)

        if not intent.table_name:
            raise InvalidParamsError(
                "Could not determine target table. "
                f"Available tables: {', '.join(available_tables)}"
            )

        logger.info(f"Parsed intent: {intent}")

        # 3. 根据操作类型执行
        if intent.operation == "insert":
            return await self._execute_insert(intent, dry_run)
        elif intent.operation == "select":
            return await self._execute_select(intent)
        else:
            raise ToolExecutionError(
                "unsupported_operation",
                f"Operation '{intent.operation}' is not yet supported. "
                "Currently supported: insert, select"
            )

    async def _execute_insert(
        self,
        intent: ParsedIntent,
        dry_run: bool
    ) -> Dict[str, Any]:
        """执行插入操作"""
        # 获取表结构
        schema = await self.schema_reader.get_table_schema(intent.table_name)
        if not schema:
            raise ToolExecutionError(
                "table_not_found",
                f"Table '{intent.table_name}' not found"
            )

        count = intent.count or 1
        logger.info(f"Generating {count} rows for table '{intent.table_name}'")

        # 生成数据
        rows = []
        for i in range(count):
            row = await self.data_generator.generate_row_data(schema, i)
            rows.append(row)

        # 构建SQL
        columns = list(rows[0].keys())
        sql = f"INSERT INTO {intent.table_name} ({', '.join(columns)}) VALUES\n"
        values_list = []
        for row in rows:
            values = []
            for col in columns:
                val = row[col]
                if isinstance(val, str):
                    # 转义单引号
                    val = val.replace("'", "''")
                    values.append(f"'{val}'")
                elif isinstance(val, bool):
                    values.append("TRUE" if val else "FALSE")
                elif val is None:
                    values.append("NULL")
                else:
                    values.append(str(val))
            values_list.append(f"({', '.join(values)})")
        sql += ",\n".join(values_list) + ";"

        if dry_run:
            return {
                "operation": "insert",
                "table": intent.table_name,
                "count": count,
                "dry_run": True,
                "generated_sql": sql,
                "sample_data": rows[0] if rows else None,
            }

        # 执行SQL
        try:
            async with async_session_maker() as session:
                await session.execute(text(sql))
                await session.commit()

                return {
                    "operation": "insert",
                    "table": intent.table_name,
                    "count": count,
                    "success": True,
                    "sql": sql,
                    "sample_data": rows[0] if rows else None,
                }

        except Exception as e:
            logger.error(f"Failed to execute insert: {e}")
            raise ToolExecutionError(
                "insert_failed",
                f"Failed to insert data: {str(e)}"
            )

    async def _execute_select(self, intent: ParsedIntent) -> Dict[str, Any]:
        """执行查询操作"""
        schema = await self.schema_reader.get_table_schema(intent.table_name)
        if not schema:
            raise ToolExecutionError(
                "table_not_found",
                f"Table '{intent.table_name}' not found"
            )

        # 构建查询SQL
        sql = f"SELECT * FROM {intent.table_name}"

        # 简单限制
        if intent.count:
            sql += f" LIMIT {intent.count}"
        else:
            sql += " LIMIT 10"

        try:
            async with async_session_maker() as session:
                result = await session.execute(text(sql))
                rows = result.fetchall()
                columns = result.keys()

                return {
                    "operation": "select",
                    "table": intent.table_name,
                    "count": len(rows),
                    "sql": sql,
                    "data": [dict(zip(columns, row)) for row in rows],
                }

        except Exception as e:
            logger.error(f"Failed to execute select: {e}")
            raise ToolExecutionError(
                "select_failed",
                f"Failed to query data: {str(e)}"
            )


# ========================================
# 全局执行器实例
# ========================================
nl_db_executor = NLDatabaseExecutor()


# ========================================
# MCP 工具注册
# ========================================

@tool(
    name="nl_database_operation",
    description="""
    使用自然语言执行数据库操作。

    支持的操作：
    - 插入测试数据：例如"在users表中添加3条测试数据"、"给products表插入10条数据"
    - 查询数据：例如"查看users表的数据"、"查询orders表前5条记录"

    系统会自动：
    1. 解析你的自然语言意图（使用千问 AI）
    2. 读取目标表结构
    3. 根据字段类型生成合适的测试数据
    4. 执行数据库操作

    注意：操作将使用当前用户的数据库权限。
    """,
    category="database",
    timeout=60,
)
async def nl_database_operation(arguments: dict, context) -> list:
    """
    自然语言数据库操作工具

    Args:
        arguments: 包含以下键的字典
            - natural_language (str, required): 自然语言指令
            - dry_run (bool, optional): 是否预演模式，默认false
        context: 执行上下文

    Returns:
        工具执行结果
    """
    natural_language = arguments.get("natural_language")
    if not natural_language:
        raise InvalidParamsError("Missing required parameter: natural_language")

    dry_run = arguments.get("dry_run", False)

    try:
        result = await nl_db_executor.execute_nl_request(
            natural_language,
            dry_run=dry_run
        )

        # 构建友好的响应消息
        if result.get("operation") == "insert":
            if result.get("dry_run"):
                msg = f"""📋 预演模式：将在 {result['table']} 表中插入 {result['count']} 条数据

生成的 SQL：
{result.get('generated_sql', '')}

示例数据：
{json.dumps(result.get('sample_data'), ensure_ascii=False, indent=2)}

如需执行，请设置 dry_run=false"""
            else:
                msg = f"""✅ 成功在 {result['table']} 表中插入 {result['count']} 条数据

示例数据：
{json.dumps(result.get('sample_data'), ensure_ascii=False, indent=2)}"""

        elif result.get("operation") == "select":
            msg = f"""📊 查询 {result['table']} 表，共 {result['count']} 条记录

数据：
{json.dumps(result.get('data'), ensure_ascii=False, indent=2)}"""
        else:
            msg = json.dumps(result, ensure_ascii=False, indent=2)

        return [{
            "type": "text",
            "text": msg
        }]

    except Exception as e:
        logger.exception("nl_database_operation failed")
        return [{
            "type": "text",
            "text": f"❌ 操作失败：{str(e)}"
        }]


# ========================================
# 导出
# ========================================

__all__ = [
    "nl_database_operation",
    "NLDatabaseExecutor",
    "QwenNLParser",
    "ParsedIntent",
    "TableSchema",
    "ColumnInfo",
]
