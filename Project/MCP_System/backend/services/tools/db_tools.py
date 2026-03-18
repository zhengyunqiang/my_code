"""
Database Test Data Generator Tool
数据库测试数据自动生成工具
"""

import asyncio
import random
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
import re

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.core.exceptions import ToolExecutionError
from backend.adapters.database import async_session_maker
from backend.services.tools import tool, ExecutionContext
from backend.services.tools.executor import tool_executor

logger = get_logger(__name__)


@dataclass
class ColumnInfo:
    """列信息"""
    name: str
    type: str
    nullable: bool
    primary_key: bool
    autoincrement: bool
    default: Optional[Any]
    max_length: Optional[int] = None
    foreign_keys: List[str] = None


class DatabaseInspector:
    """数据库检查器 - 获取表结构信息"""

    async def get_table_info(self, table_name: str) -> List[ColumnInfo]:
        """
        获取表的列信息

        Args:
            table_name: 表名

        Returns:
            列信息列表
        """
        async with async_session_maker() as session:
            # 使用 SQLAlchemy inspector
            def _get_columns(sync_session):
                inspector = inspect(sync_session.bind)
                columns = []

                for column in inspector.get_columns(table_name):
                    col_info = ColumnInfo(
                        name=column['name'],
                        type=str(column['type']),
                        nullable=column.get('nullable', True),
                        primary_key=column.get('primary_key', False),
                        autoincrement=column.get('autoincrement', False),
                        default=column.get('default'),
                    )

                    # 获取最大长度
                    if hasattr(column['type'], 'length'):
                        col_info.max_length = column['type'].length

                    columns.append(col_info)

                return columns

            return await session.run_sync(_get_columns)

    async def get_foreign_keys(self, table_name: str) -> Dict[str, str]:
        """
        获取外键关系

        Args:
            table_name: 表名

        Returns:
            外键字典 {列名: 引用表.引用列}
        """
        async with async_session_maker() as session:
            def _get_fks(sync_session):
                inspector = inspect(sync_session.bind)
                fks = inspector.get_foreign_keys(table_name)

                result = {}
                for fk in fks:
                    for col in fk['constrained_columns']:
                        ref_table = fk['referred_table']
                        ref_cols = fk['referred_columns']
                        result[col] = f"{ref_table}.{ref_cols[0] if ref_cols else 'id'}"

                return result

            return await session.run_sync(_get_fks)

    async def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在

        Args:
            table_name: 表名

        Returns:
            是否存在
        """
        async with async_session_maker() as session:
            def _check(sync_session):
                inspector = inspect(sync_session.bind)
                return table_name in inspector.get_table_names()

            return await session.run_sync(_check)

    async def get_all_tables(self) -> List[str]:
        """
        获取所有表名

        Returns:
            表名列表
        """
        async with async_session_maker() as session:
            def _get_tables(sync_session):
                inspector = inspect(sync_session.bind)
                return inspector.get_table_names()

            return await session.run_sync(_get_tables)


class TestDataGenerator:
    """测试数据生成器"""

    # 中文姓氏和名字
    SURNAMES = ['王', '李', '张', '刘', '陈', '杨', '黄', '赵', '周', '吴',
                '徐', '孙', '马', '朱', '胡', '郭', '何', '罗', '高', '林']
    NAMES = ['伟', '芳', '娜', '敏', '静', '丽', '强', '磊', '军', '洋',
             '勇', '艳', '杰', '娟', '涛', '明', '超', '秀', '霞', '平']

    # 中文公司名后缀
    COMPANY_SUFFIXES = ['科技有限公司', '信息技术有限公司', '网络科技有限公司',
                        '电子商务有限公司', '咨询服务有限公司', '贸易有限公司']
    COMPANY_PREFIXES = ['腾讯', '阿里', '百度', '字节', '华为', '小米', '京东',
                       '美团', '滴滴', '网易', '新浪', '搜狐', '360', '金山']

    # 中文地址
    CITIES = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安',
             '南京', '重庆', '天津', '苏州', '长沙', '郑州', '东莞']
    DISTRICTS = ['朝阳区', '海淀区', '浦东新区', '南山区', '福田区', '天河区',
                 '武昌区', '江汉区', '雁塔区', '江宁区', '渝中区', '和平区']

    # 中文描述
    DESCRIPTIONS = [
        '这是一个非常好的产品',
        '质量上乘，值得推荐',
        '性价比高，服务周到',
        '功能完善，使用方便',
        '设计精美，做工精细',
        '物流快速，包装完好',
    ]

    def __init__(self, inspector: DatabaseInspector):
        self.inspector = inspector

    async def generate_test_data(
        self,
        table_name: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        """
        生成测试数据

        Args:
            table_name: 表名
            count: 生成数量

        Returns:
            数据字典列表
        """
        # 获取表结构
        columns = await self.inspector.get_table_info(table_name)
        foreign_keys = await self.inspector.get_foreign_keys(table_name)

        # 生成数据
        data_list = []

        for i in range(count):
            row_data = {}

            for column in columns:
                # 跳过自增主键
                if column.autoincrement:
                    continue

                # 生成值
                value = await self._generate_value(
                    column,
                    foreign_keys.get(column.name),
                    i,
                )

                if value is not None:
                    row_data[column.name] = value

            data_list.append(row_data)

        return data_list

    async def _generate_value(
        self,
        column: ColumnInfo,
        foreign_key: Optional[str],
        index: int,
    ) -> Any:
        """为列生成值"""

        # 处理外键
        if foreign_key:
            return await self._generate_foreign_key_value(foreign_key)

        # 根据列名猜测类型
        column_lower = column.name.lower()

        # 根据列名推断语义
        if self._is_name_column(column_lower):
            return self._generate_chinese_name()

        if self._is_email_column(column_lower):
            return self._generate_email()

        if self._is_phone_column(column_lower):
            return self._generate_phone()

        if self._is_company_column(column_lower):
            return self._generate_company()

        if self._is_address_column(column_lower):
            return self._generate_address()

        if self._is_age_column(column_lower):
            return random.randint(18, 65)

        if self._is_price_column(column_lower) or self._is_amount_column(column_lower):
            return round(random.uniform(10, 10000), 2)

        if self._is_status_column(column_lower):
            return random.choice(['active', 'inactive', 'pending'])

        if self._is_description_column(column_lower) or self._is_remark_column(column_lower):
            return random.choice(self.DESCRIPTIONS)

        if self._is_created_at_column(column_lower) or self._is_updated_at_column(column_lower):
            return datetime.now() - timedelta(days=random.randint(0, 365))

        if self._is_date_column(column_lower):
            return datetime.now() - timedelta(days=random.randint(0, 365))

        # 根据数据库类型生成
        return self._generate_by_type(column, index)

    def _is_name_column(self, name: str) -> bool:
        """判断是否是姓名列"""
        return any(keyword in name for keyword in
                   ['name', '姓名', '用户名', 'username', 'nick'])

    def _is_email_column(self, name: str) -> bool:
        """判断是否是邮箱列"""
        return 'email' in name or '邮箱' in name or '邮件' in name

    def _is_phone_column(self, name: str) -> bool:
        """判断是否是电话列"""
        return any(keyword in name for keyword in
                   ['phone', 'mobile', 'tel', '电话', '手机', '联系'])

    def _is_company_column(self, name: str) -> bool:
        """判断是否是公司列"""
        return any(keyword in name for keyword in
                   ['company', 'corp', 'firm', '公司', '企业'])

    def _is_address_column(self, name: str) -> bool:
        """判断是否是地址列"""
        return any(keyword in name for keyword in
                   ['address', 'addr', '地址', '位置'])

    def _is_age_column(self, name: str) -> bool:
        """判断是否是年龄列"""
        return 'age' in name or '年龄' in name

    def _is_price_column(self, name: str) -> bool:
        """判断是否是价格列"""
        return any(keyword in name for keyword in
                   ['price', 'pricing', '价格', '单价'])

    def _is_amount_column(self, name: str) -> bool:
        """判断是否是金额列"""
        return any(keyword in name for keyword in
                   ['amount', 'total', 'sum', 'money', '金额', '总计'])

    def _is_status_column(self, name: str) -> bool:
        """判断是否是状态列"""
        return any(keyword in name for keyword in
                   ['status', 'state', '状态'])

    def _is_description_column(self, name: str) -> bool:
        """判断是否是描述列"""
        return any(keyword in name for keyword in
                   ['desc', 'description', '描述', '说明'])

    def _is_remark_column(self, name: str) -> bool:
        """判断是否是备注列"""
        return any(keyword in name for keyword in
                   ['remark', 'note', 'comment', '备注', '评论'])

    def _is_created_at_column(self, name: str) -> bool:
        """判断是否是创建时间列"""
        return any(keyword in name for keyword in
                   ['created_at', 'created', 'ctime', '创建时间', '录入时间'])

    def _is_updated_at_column(self, name: str) -> bool:
        """判断是否是更新时间列"""
        return any(keyword in name for keyword in
                   ['updated_at', 'updated', 'utime', 'mtime', '更新时间', '修改时间'])

    def _is_date_column(self, name: str) -> bool:
        """判断是否是日期列"""
        return any(keyword in name for keyword in
                   ['date', 'time', 'day', '日期', '时间', '日子'])

    def _generate_chinese_name(self) -> str:
        """生成中文姓名"""
        surname = random.choice(self.SURNAMES)
        name = random.choice(self.NAMES)
        if random.random() > 0.5:
            name += random.choice(self.NAMES)
        return surname + name

    def _generate_email(self) -> str:
        """生成邮箱"""
        domains = ['qq.com', '163.com', 'gmail.com', 'outlook.com', 'hotmail.com']
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{username}@{random.choice(domains)}"

    def _generate_phone(self) -> str:
        """生成手机号"""
        prefixes = ['130', '131', '132', '133', '135', '136', '137', '138',
                   '139', '150', '151', '152', '153', '155', '156', '157',
                   '158', '159', '186', '187', '188', '189']
        return f"{random.choice(prefixes)}{''.join(random.choices('0123456789', k=8))}"

    def _generate_company(self) -> str:
        """生成公司名"""
        prefix = random.choice(self.COMPANY_PREFIXES)
        suffix = random.choice(self.COMPANY_SUFFIXES)
        return f"{prefix}{suffix}"

    def _generate_address(self) -> str:
        """生成地址"""
        city = random.choice(self.CITIES)
        district = random.choice(self.DISTRICTS)
        street = f"{random.randint(1, 999)}号"
        return f"{city}{district}{random.choice(['建设路', '人民路', '解放路', '和平路', '文化路'])}{street}"

    def _generate_by_type(self, column: ColumnInfo, index: int) -> Any:
        """根据数据库类型生成值"""
        col_type = column.type.lower()

        if 'varchar' in col_type or 'char' in col_type or 'text' in col_type:
            return self._generate_string(column.max_length or 50, column.name)

        if 'int' in col_type:
            return random.randint(1, 10000) + index

        if 'bigint' in col_type:
            return random.randint(1000000, 9999999) + index

        if 'float' in col_type or 'double' in col_type or 'decimal' in col_type:
            return round(random.uniform(1, 1000), 2)

        if 'bool' in col_type:
            return random.choice([True, False])

        if 'date' in col_type or 'time' in col_type:
            return datetime.now() - timedelta(days=random.randint(0, 365))

        if 'json' in col_type or 'jsonb' in col_type:
            return {"key": f"value_{index}", "count": random.randint(1, 100)}

        # 默认生成字符串
        return f"test_data_{index}"

    def _generate_string(self, max_length: int, column_name: str) -> str:
        """生成字符串"""
        if max_length and max_length < 10:
            return ''.join(random.choices(string.ascii_lowercase, k=max_length))

        # 根据列名生成相关内容
        column_lower = column_name.lower()

        if any(keyword in column_lower for keyword in ['title', '标题', 'name', '名称']):
            words = ['测试', '示例', '演示', '样品', '模型']
            return random.choice(words) + f"_{random.randint(1, 999)}"

        if 'code' in column_lower or '编号' in column_lower:
            return f"CODE{random.randint(10000, 99999)}"

        # 默认生成随机字符串
        length = min(max_length - 7, 20) if max_length else 20
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

    async def _generate_foreign_key_value(self, fk_ref: str) -> Any:
        """生成外键值（从引用表获取）"""
        ref_table, ref_column = fk_ref.split('.')

        async with async_session_maker() as session:
            # 获取引用表的有效值
            query = text(f"SELECT {ref_column} FROM {ref_table} LIMIT 100")
            result = await session.execute(query)
            values = [row[0] for row in result.fetchall()]

            if values:
                return random.choice(values)

        # 如果没有值，返回 None 或默认值
        return None


class NaturalLanguageParser:
    """自然语言解析器"""

    # 提取数字的正则
    NUMBER_PATTERN = re.compile(r'(\d+)(?:条|个|项|记录|行)?')

    # 表名提取模式
    TABLE_PATTERNS = [
        r'在\s*["\']?([a-zA-Z_]\w*)["\']?\s*表中',
        r'表\s*["\']?([a-zA-Z_]\w*)["\']?',
        r'into\s+([a-zA-Z_]\w+)',
        r'插入.*?["\']?([a-zA-Z_]\w*)["\']?',
    ]

    def parse_intent(
        self,
        text: str,
        available_tables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        解析自然语言意图

        Args:
            text: 用户输入文本
            available_tables: 可用的表名列表

        Returns:
            意图字典
            {
                "action": "insert_test_data",  # 操作类型
                "table_name": "users",          # 表名
                "count": 3,                    # 数量
                "confidence": 0.9,             # 置信度
            }
        """
        text = text.strip().lower()

        # 默认意图
        intent = {
            "action": "insert_test_data",
            "table_name": None,
            "count": 1,
            "confidence": 0.0,
        }

        # 检测操作类型
        if any(keyword in text for keyword in
               ['添加', '插入', '生成', 'create', 'insert', 'add', 'generate']):
            intent["action"] = "insert_test_data"

        # 提取数量
        number_match = self.NUMBER_PATTERN.search(text)
        if number_match:
            intent["count"] = int(number_match.group(1))

        # 查找中文数字
        chinese_numbers = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '两': 2,
        }
        for cn_num, value in chinese_numbers.items():
            if cn_num in text:
                intent["count"] = value
                break

        # 提取表名
        intent["table_name"] = self._extract_table_name(text, available_tables)

        # 计算置信度
        if intent["table_name"]:
            intent["confidence"] += 0.6
        if intent["count"] > 1:
            intent["confidence"] += 0.3
        if '测试' in text or 'test' in text:
            intent["confidence"] += 0.1

        return intent

    def _extract_table_name(
        self,
        text: str,
        available_tables: Optional[List[str]] = None,
    ) -> Optional[str]:
        """从文本中提取表名"""
        # 尝试正则匹配
        for pattern in self.TABLE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                # 验证表名是否有效
                if available_tables is None or table_name in available_tables:
                    return table_name

        # 如果有可用表列表，尝试模糊匹配
        if available_tables:
            for table in available_tables:
                if table.lower() in text:
                    return table

        return None


# 全局实例
db_inspector = DatabaseInspector()
nl_parser = NaturalLanguageParser()


# ========================================
# MCP 工具实现
# ========================================

@tool(
    name="generate_test_data",
    description="自动生成并插入数据库测试数据。支持自然语言描述，例如：'在users表中添加3条测试数据'。会根据表结构自动生成符合字段类型的测试数据。",
    category="database",
    timeout=60,
)
async def generate_test_data_handler(
    arguments: Dict[str, Any],
    context: ExecutionContext,
) -> List[Dict[str, Any]]:
    """
    生成测试数据工具处理器

    Args:
        arguments: 参数
            - table_name: 表名
            - count: 生成数量（默认1）
            - natural_language: 自然语言描述（可选）
        context: 执行上下文

    Returns:
        执行结果
    """
    # 获取参数
    table_name = arguments.get("table_name")
    count = arguments.get("count", 1)
    natural_language = arguments.get("natural_language", "")

    # 如果有自然语言输入，解析意图
    if natural_language:
        available_tables = await db_inspector.get_all_tables()
        intent = nl_parser.parse_intent(natural_language, available_tables)

        # 使用解析的结果
        if intent["table_name"]:
            table_name = intent["table_name"]
        if intent.get("count"):
            count = intent["count"]

    # 验证参数
    if not table_name:
        return [{
            "type": "text",
            "text": "❌ 请指定表名。例如：{'table_name': 'users', 'count': 3}"
        }]

    if not await db_inspector.table_exists(table_name):
        return [{
            "type": "text",
            "text": f"❌ 表 '{table_name}' 不存在。可用表：{', '.join(await db_inspector.get_all_tables())}"
        }]

    # 限制数量
    count = min(count, 1000)  # 最多一次生成1000条

    # 生成测试数据
    generator = TestDataGenerator(db_inspector)
    test_data = await generator.generate_test_data(table_name, count)

    # 插入数据
    async with async_session_maker() as session:
        try:
            # 构建插入语句
            if test_data:
                columns = list(test_data[0].keys())
                placeholders = ', '.join([f':{col}' for col in columns])

                query = text(
                    f"INSERT INTO {table_name} ({', '.join(columns)}) "
                    f"VALUES ({placeholders})"
                )

                # 批量插入
                result = await session.execute(query, test_data)
                await session.commit()

                inserted_count = result.rowcount
            else:
                inserted_count = 0

            # 返回结果
            return [{
                "type": "text",
                "text": f"✅ 成功在表 '{table_name}' 中插入 {inserted_count} 条测试数据"
            }]

        except Exception as e:
            await session.rollback()
            logger.error(f"插入测试数据失败: {e}")
            return [{
                "type": "text",
                "text": f"❌ 插入数据失败: {str(e)}"
            }]


@tool(
    name="show_table_structure",
    description="显示数据库表的结构信息，包括列名、数据类型、是否可空等",
    category="database",
    timeout=30,
)
async def show_table_structure_handler(
    arguments: Dict[str, Any],
    context: ExecutionContext,
) -> List[Dict[str, Any]]:
    """
    显示表结构工具处理器

    Args:
        arguments: 参数
            - table_name: 表名

    Returns:
        表结构信息
    """
    table_name = arguments.get("table_name")

    if not table_name:
        # 列出所有表
        tables = await db_inspector.get_all_tables()
        return [{
            "type": "text",
            "text": f"📋 数据库中的表：\n" + "\n".join([f"  - {t}" for t in tables])
        }]

    # 检查表是否存在
    if not await db_inspector.table_exists(table_name):
        return [{
            "type": "text",
            "text": f"❌ 表 '{table_name}' 不存在"
        }]

    # 获取表结构
    columns = await db_inspector.get_table_info(table_name)

    # 格式化输出
    lines = [f"📋 表 '{table_name}' 的结构：\n"]
    lines.append(f"{'列名':<20} {'类型':<20} {'主键':<8} {'可空':<8}")
    lines.append("-" * 60)

    for col in columns:
        pk = "✓" if col.primary_key else ""
        nullable = "✓" if col.nullable else ""
        lines.append(f"{col.name:<20} {col.type:<20} {pk:<8} {nullable:<8}")

    return [{
        "type": "text",
        "text": "\n".join(lines)
    }]


@tool(
    name="parse_database_intent",
    description="解析数据库操作的自然语言意图，识别要操作的表、操作类型和参数",
    category="database",
    timeout=10,
)
async def parse_database_intent_handler(
    arguments: Dict[str, Any],
    context: ExecutionContext,
) -> List[Dict[str, Any]]:
    """
    解析数据库意图工具处理器

    Args:
        arguments: 参数
            - text: 自然语言文本

    Returns:
        解析结果
    """
    text = arguments.get("text", "")
    available_tables = await db_inspector.get_all_tables()

    intent = nl_parser.parse_intent(text, available_tables)

    # 格式化输出
    lines = [
        "🎯 意图解析结果：",
        f"  操作类型: {intent['action']}",
        f"  目标表: {intent['table_name'] or '未识别'}",
        f"  数量: {intent['count']}",
        f"  置信度: {intent['confidence']:.0%}",
    ]

    if intent["confidence"] > 0.7 and intent["table_name"]:
        lines.append(f"\n💡 建议操作: generate_test_data(table_name='{intent['table_name']}', count={intent['count']})")

    return [{
        "type": "text",
        "text": "\n".join(lines)
    }]


__all__ = [
    "DatabaseInspector",
    "TestDataGenerator",
    "NaturalLanguageParser",
    "db_inspector",
    "nl_parser",
]
