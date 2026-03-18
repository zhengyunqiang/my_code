# 统一提示词管理系统

## 概述

统一提示词管理系统用于集中管理 MCP System 中所有使用到的提示词模板，提供版本控制、变量插值、多语言支持等功能。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                   PromptManager                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  注册表 (Registry)                                  │ │
│  │  - 按名称索引                                       │ │
│  │  - 按分类索引                                       │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  内置模板 (Built-in Templates)                      │ │
│  │  - NL_DATABASE_PARSE_SYSTEM                       │ │
│  │  - NL_DATABASE_PARSE_USER                         │ │
│  │  - SQL_GENERATION_SYSTEM                          │ │
│  │  - ERROR_RECOVERY_GUIDANCE                        │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  功能方法                                           │ │
│  │  - register(): 注册模板                            │ │
│  │  - get(): 获取模板                                 │ │
│  │  - render(): 渲染模板                              │ │
│  │  - list_by_category(): 按分类列出                  │ │
│  │  - export/import(): 导出/导入                      │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 提示词分类

| 分类 | 说明 | 使用场景 |
|------|------|---------|
| `nl_parsing` | 自然语言解析 | 解析用户意图，提取结构化信息 |
| `tool_generation` | 工具生成 | 生成工具调用、SQL 语句等 |
| `data_validation` | 数据验证 | 验证输入数据的格式和有效性 |
| `error_recovery` | 错误恢复 | 提供错误恢复建议和解决方案 |
| `system_prompt` | 系统提示 | AI 模型的系统级提示词 |
| `user_guidance` | 用户引导 | 帮助用户理解和操作系统 |

## 使用示例

### 1. 渲染提示词

```python
from backend.services.prompts.prompt_manager import prompt_manager

# 渲染系统提示词
system_prompt = prompt_manager.render(
    "nl_database_parse_system",
    available_tables=["users", "products", "orders"]
)

# 渲染用户消息
user_message = prompt_manager.render(
    "nl_database_parse_user",
    tables="users、products、orders",
    user_input="在users表中添加3条测试数据"
)
```

### 2. 注册新模板

```python
from backend.services.prompts.prompt_manager import (
    prompt_manager,
    PromptTemplate,
    PromptCategory,
    PromptVariable,
)

# 创建新模板
template = PromptTemplate(
    name="sql_optimization_tips",
    category=PromptCategory.USER_GUIDANCE,
    template="""SQL 优化建议：

**当前查询**：{query}

**优化建议**：
{suggestions}

**预期性能提升**：{improvement}""",
    variables=[
        PromptVariable(
            name="query",
            description="原始 SQL 查询",
            type="string",
            required=True,
        ),
        PromptVariable(
            name="suggestions",
            description="优化建议列表",
            type="string",
            required=True,
        ),
        PromptVariable(
            name="improvement",
            description="预期性能提升百分比",
            type="string",
            required=False,
            default="10-20%",
        ),
    ],
)

# 注册模板
prompt_manager.register(template)
```

### 3. 获取模板信息

```python
# 按名称获取
template = prompt_manager.get("nl_database_parse_system")

# 按分类获取
nl_templates = prompt_manager.list_by_category(PromptCategory.NL_PARSING)

# 获取统计信息
stats = prompt_manager.get_stats()
print(f"总模板数: {stats['total_templates']}")
print(f"分类统计: {stats['categories']}")
```

### 4. 导出/导入模板

```python
# 导出所有模板到 JSON 文件
prompt_manager.export("prompts_backup.json")

# 从 JSON 文件导入模板
prompt_manager.import_from_file("prompts_backup.json")
```

## 内置模板详解

### NL_DATABASE_PARSE_SYSTEM

用于数据库操作自然语言解析的系统提示词。

**变量**：
- `available_tables`: 可用的数据库表名列表

**返回格式**：
```json
{
    "operation": "insert",
    "table_name": "users",
    "count": 3,
    "conditions": {},
    "data": {}
}
```

### NL_DATABASE_PARSE_USER

用于数据库操作自然语言解析的用户消息模板。

**变量**：
- `tables`: 可用的表名列表（用顿号分隔）
- `user_input`: 用户的自然语言输入

### SQL_GENERATION_SYSTEM

用于生成 SQL 语句的系统提示词。

**变量**：
- `table_schema`: 数据库表结构描述

### ERROR_RECOVERY_GUIDANCE

用于提供错误恢复指导的模板。

**变量**：
- `error_message`: 错误消息
- `possible_causes`: 可能的错误原因
- `solutions`: 建议的解决方案

## 最佳实践

### 1. 模板命名规范

- 使用小写字母和下划线
- 格式：`{功能}_{用途}_{角色}`
- 示例：`nl_database_parse_system`, `sql_generation_user`

### 2. 变量定义

- 所有变量必须在 `variables` 列表中声明
- 必需变量设置 `required=True`
- 提供有意义的描述和示例

### 3. 版本控制

- 重要模板变更时更新版本号
- 在 `metadata` 中记录变更历史
- 保留旧版本模板作为备份

### 4. 多语言支持

- 使用 `PromptLanguage` 枚举定义语言
- 同一模板的不同语言版本使用不同名称
- 命名规范：`{template_name}_{lang_code}`

## 集成到现有代码

### 将硬编码的提示词迁移到统一管理

**迁移前**：
```python
system_prompt = """你是一个数据库操作意图解析器。
请分析用户的自然语言输入..."""
```

**迁移后**：
```python
from backend.services.prompts.prompt_manager import prompt_manager

system_prompt = prompt_manager.render("nl_database_parse_system")
```

### 在工具中使用

```python
from backend.services.prompts.prompt_manager import prompt_manager, PromptCategory

# 获取特定分类的所有模板
nl_prompts = prompt_manager.list_by_category(PromptCategory.NL_PARSING)

# 在工具中渲染
@tool(name="my_tool")
async def my_tool(arguments: dict, context):
    prompt = prompt_manager.render("my_template", **arguments)
    # 使用 prompt 调用 AI 模型
    ...
```

## 配置

提示词管理系统无需额外配置，开箱即用。如需自定义模板路径：

```python
from backend.services.prompts.prompt_manager import prompt_manager

# 从自定义路径导入模板
prompt_manager.import_from_file("/path/to/custom_prompts.json")
```

## 扩展

### 添加新的提示词分类

```python
from backend.services.prompts.prompt_manager import PromptCategory

class PromptCategory(str, Enum):
    NL_PARSING = "nl_parsing"
    TOOL_GENERATION = "tool_generation"
    CUSTOM_CATEGORY = "custom_category"  # 新增分类
```

### 自定义渲染逻辑

继承 `PromptTemplate` 类并重写 `render()` 方法。

## 故障排除

### 模板未找到

```
ValueError: Prompt template 'xxx' not found
```

解决：检查模板名称是否正确，或使用 `list_all()` 查看所有可用模板。

### 缺少必需变量

```
ValueError: Required variable 'yyy' is missing
```

解决：在 `render()` 调用时提供所有必需变量的值。

## 相关文件

- `backend/services/prompts/prompt_manager.py` - 提示词管理器实现
- `backend/services/prompts/templates.py` - 旧的模板系统（兼容性保留）
- `backend/services/tools/nl_database_tool.py` - 使用示例
