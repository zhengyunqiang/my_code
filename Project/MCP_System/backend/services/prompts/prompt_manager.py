"""
统一提示词管理系统
Unified Prompt Management System

集中管理所有系统中使用的提示词模板，支持：
1. 提示词模板定义和存储
2. 变量插值和渲染
3. 版本控制
4. 多语言支持
5. 提示词分类管理
"""

import json
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import re

from backend.core.logging import get_logger
from backend.config import settings

logger = get_logger(__name__)


# ========================================
# 提示词分类枚举
# ========================================

class PromptCategory(str, Enum):
    """提示词分类"""
    NL_PARSING = "nl_parsing"  # 自然语言解析
    TOOL_GENERATION = "tool_generation"  # 工具生成
    DATA_VALIDATION = "data_validation"  # 数据验证
    ERROR_RECOVERY = "error_recovery"  # 错误恢复
    SYSTEM_PROMPT = "system_prompt"  # 系统提示
    USER_GUIDANCE = "user_guidance"  # 用户引导


class PromptLanguage(str, Enum):
    """提示词语言"""
    ZH_CN = "zh-CN"  # 简体中文
    EN_US = "en-US"  # 英语
    JA_JP = "ja-JP"  # 日语


# ========================================
# 提示词模板数据结构
# ========================================

@dataclass
class PromptVariable:
    """提示词变量定义"""
    name: str
    description: str
    type: str = "string"  # string, number, boolean, array, object
    required: bool = True
    default: Any = None
    examples: List[Any] = field(default_factory=list)


@dataclass
class PromptTemplate:
    """提示词模板"""
    name: str
    category: PromptCategory
    template: str
    variables: List[PromptVariable] = field(default_factory=list)
    language: PromptLanguage = PromptLanguage.ZH_CN
    version: str = "1.0.0"
    author: str = "system"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, **kwargs) -> str:
        """
        渲染提示词模板

        Args:
            **kwargs: 变量值

        Returns:
            渲染后的提示词
        """
        result = self.template

        # 替换变量
        for var in self.variables:
            value = kwargs.get(var.name, var.default)

            # 检查必需变量
            if var.required and value is None:
                raise ValueError(f"Required variable '{var.name}' is missing")

            # 替换模板中的占位符
            placeholder = f"{{{var.name}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        # 替换剩余的可选占位符为空字符串
        result = re.sub(r'\{[^}]+\}', '', result)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "category": self.category.value,
            "template": self.template,
            "variables": [
                {
                    "name": v.name,
                    "description": v.description,
                    "type": v.type,
                    "required": v.required,
                    "default": v.default,
                    "examples": v.examples,
                }
                for v in self.variables
            ],
            "language": self.language.value,
            "version": self.version,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


# ========================================
# 内置提示词模板
# ========================================

# 数据库操作自然语言解析提示词
NL_DATABASE_PARSE_SYSTEM = PromptTemplate(
    name="nl_database_parse_system",
    category=PromptCategory.NL_PARSING,
    template="""你是一个数据库操作意图解析器。请分析用户的自然语言输入，提取以下信息：

1. **operation**: 操作类型
   - "insert" - 插入数据（关键词：插入、添加、新增、增加、insert、add）
   - "select" - 查询数据（关键词：查询、查找、搜索、查看、select、find、search）
   - "update" - 更新数据（关键词：更新、修改、update、modify）
   - "delete" - 删除数据（关键词：删除、移除、delete、remove）

2. **table_name**: 目标表名，从提供的可用表名列表中精确匹配

3. **count**: 数据条数，提取提到的具体数字

4. **conditions**: WHERE 条件（如果有）

请严格按照以下 JSON 格式返回：
```json
{
    "operation": "insert",
    "table_name": "users",
    "count": 3,
    "conditions": {},
    "data": {}
}
```

**重要**：
- 只返回 JSON，不要包含任何解释文字
- table_name 必须从可用表名列表中匹配
- operation 必须是 insert、select、update、delete 之一
- 如果没有明确数量，count 默认为 1""",
    variables=[
        PromptVariable(
            name="available_tables",
            description="可用的数据库表名列表",
            type="array",
            required=True,
        ),
    ],
    language=PromptLanguage.ZH_CN,
    version="1.0.0",
    metadata={"model": "qwen-plus", "temperature": 0.3},
)

# 数据库操作用户消息模板
NL_DATABASE_PARSE_USER = PromptTemplate(
    name="nl_database_parse_user",
    category=PromptCategory.NL_PARSING,
    template="""可用表名列表：{tables}

用户输入：{user_input}

请解析这个数据库操作意图，返回 JSON 格式。""",
    variables=[
        PromptVariable(
            name="tables",
            description="可用的表名列表，用顿号分隔",
            type="string",
            required=True,
        ),
        PromptVariable(
            name="user_input",
            description="用户的自然语言输入",
            type="string",
            required=True,
        ),
    ],
    language=PromptLanguage.ZH_CN,
    version="1.0.0",
)

# SQL 生成提示词
SQL_GENERATION_SYSTEM = PromptTemplate(
    name="sql_generation_system",
    category=PromptCategory.TOOL_GENERATION,
    template="""你是一个 SQL 语句生成专家。根据用户的需求生成准确的 SQL 语句。

表结构信息：
{table_schema}

注意事项：
1. 只生成 SQL 语句，不要包含任何解释
2. 使用标准 SQL 语法
3. 注意 SQL 注入防护，使用参数化查询
4. 对于字符串值，使用单引号包裹并转义内部单引号
5. 对于日期时间，使用 ISO 格式""",
    variables=[
        PromptVariable(
            name="table_schema",
            description="数据库表结构描述",
            type="string",
            required=True,
        ),
    ],
    language=PromptLanguage.ZH_CN,
    version="1.0.0",
)

# 错误恢复提示词
ERROR_RECOVERY_GUIDANCE = PromptTemplate(
    name="error_recovery_guidance",
    category=PromptCategory.ERROR_RECOVERY,
    template="""操作失败：{error_message}

**可能的原因**：
{possible_causes}

**建议的解决方案**：
{solutions}

如需更多帮助，请提供：
1. 完整的错误信息
2. 执行的操作
3. 相关的输入数据""",
    variables=[
        PromptVariable(
            name="error_message",
            description="错误消息",
            type="string",
            required=True,
        ),
        PromptVariable(
            name="possible_causes",
            description="可能的错误原因",
            type="string",
            required=True,
        ),
        PromptVariable(
            name="solutions",
            description="建议的解决方案",
            type="string",
            required=True,
        ),
    ],
    language=PromptLanguage.ZH_CN,
    version="1.0.0",
)


# ========================================
# 提示词管理器
# ========================================

class PromptManager:
    """
    统一提示词管理器

    负责管理系统中所有的提示词模板，提供注册、获取、渲染等功能。
    """

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._categories: Dict[PromptCategory, List[str]] = {
            category: [] for category in PromptCategory
        }
        self._register_builtin_templates()

    def _register_builtin_templates(self):
        """注册内置提示词模板"""
        builtin_templates = [
            NL_DATABASE_PARSE_SYSTEM,
            NL_DATABASE_PARSE_USER,
            SQL_GENERATION_SYSTEM,
            ERROR_RECOVERY_GUIDANCE,
        ]

        for template in builtin_templates:
            self.register(template)

        logger.info(f"Registered {len(builtin_templates)} builtin prompt templates")

    def register(self, template: PromptTemplate) -> None:
        """
        注册提示词模板

        Args:
            template: 提示词模板
        """
        self._templates[template.name] = template

        # 添加到分类索引
        if template.category not in self._categories:
            self._categories[template.category] = []
        if template.name not in self._categories[template.category]:
            self._categories[template.category].append(template.name)

        logger.debug(f"Registered prompt template: {template.name}")

    def get(self, name: str) -> Optional[PromptTemplate]:
        """
        获取提示词模板

        Args:
            name: 模板名称

        Returns:
            PromptTemplate 或 None
        """
        return self._templates.get(name)

    def render(self, name: str, **kwargs) -> str:
        """
        渲染提示词模板

        Args:
            name: 模板名称
            **kwargs: 模板变量

        Returns:
            渲染后的提示词
        """
        template = self.get(name)
        if template is None:
            raise ValueError(f"Prompt template '{name}' not found")

        return template.render(**kwargs)

    def list_by_category(
        self,
        category: PromptCategory
    ) -> List[PromptTemplate]:
        """
        按分类列出提示词模板

        Args:
            category: 分类

        Returns:
            提示词模板列表
        """
        names = self._categories.get(category, [])
        return [self._templates[name] for name in names if name in self._templates]

    def list_all(self) -> List[PromptTemplate]:
        """列出所有提示词模板"""
        return list(self._templates.values())

    def update(self, name: str, template: PromptTemplate) -> None:
        """
        更新提示词模板

        Args:
            name: 模板名称
            template: 新的模板
        """
        if name not in self._templates:
            raise ValueError(f"Prompt template '{name}' not found")

        template.updated_at = datetime.now()
        self._templates[name] = template
        logger.info(f"Updated prompt template: {name}")

    def delete(self, name: str) -> None:
        """
        删除提示词模板

        Args:
            name: 模板名称
        """
        if name not in self._templates:
            raise ValueError(f"Prompt template '{name}' not found")

        template = self._templates[name]
        category = template.category

        # 从分类索引中移除
        if category in self._categories and name in self._categories[category]:
            self._categories[category].remove(name)

        del self._templates[name]
        logger.info(f"Deleted prompt template: {name}")

    def export(self, file_path: str) -> None:
        """
        导出提示词模板到文件

        Args:
            file_path: 文件路径
        """
        data = {
            "exported_at": datetime.now().isoformat(),
            "version": "1.0",
            "templates": [t.to_dict() for t in self.list_all()],
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(self._templates)} prompt templates to {file_path}")

    def import_from_file(self, file_path: str) -> None:
        """
        从文件导入提示词模板

        Args:
            file_path: 文件路径
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for template_data in data.get("templates", []):
            variables = [
                PromptVariable(**v) for v in template_data.pop("variables", [])
            ]
            template_data["category"] = PromptCategory(template_data["category"])
            template_data["language"] = PromptLanguage(template_data["language"])
            template = PromptTemplate(**template_data, variables=variables)
            self.register(template)

        logger.info(f"Imported prompt templates from {file_path}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_templates": len(self._templates),
            "categories": {
                category.value: len(templates)
                for category, templates in self._categories.items()
            },
        }


# ========================================
# 全局提示词管理器实例
# ========================================
prompt_manager = PromptManager()


# ========================================
# 导出
# ========================================

__all__ = [
    "PromptCategory",
    "PromptLanguage",
    "PromptVariable",
    "PromptTemplate",
    "PromptManager",
    "prompt_manager",
    # 内置模板
    "NL_DATABASE_PARSE_SYSTEM",
    "NL_DATABASE_PARSE_USER",
    "SQL_GENERATION_SYSTEM",
    "ERROR_RECOVERY_GUIDANCE",
]
