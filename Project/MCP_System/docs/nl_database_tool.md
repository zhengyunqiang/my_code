# 自然语言数据库操作工具

## 概述

`nl_database_tool` 是一个基于**阿里云通义千问（Qwen）** API 的自然语言数据库操作工具，允许用户使用自然语言完成数据库的增删改查操作。

## 功能特性

### 支持的操作

1. **插入测试数据**
   - 使用千问 AI 解析自然语言中的表名和数据条数
   - 自动读取目标表结构
   - 根据字段类型和名称语义生成合适的测试数据
   - 支持预演模式（dry_run）

2. **查询数据**
   - 自然语言查询表数据
   - 自动限制返回条数

### 智能数据生成

工具会根据字段名称的语义来生成更合理的数据：

| 字段名模式 | 生成数据示例 |
|-----------|-------------|
| `*email*` | test@example.com |
| `*name*` | 张三, 李四, Alice |
| `*username*` | user001_0 |
| `*phone*` | 13800138000 |
| `*status*` | active, inactive |
| `*address*` | 北京市朝阳区 |
| `*password*` | test_password_123 |

### 数据类型支持

- 整数：递增数值（1000, 1001...）
- 浮点数：递增小数（100.5, 100.6...）
- 布尔值：交替 true/false
- 日期时间：当前时间
- 字符串：根据语义或生成通用测试数据
- JSON：自动生成的 JSON 对象

## 配置

在 `backend/.env` 文件中添加：

```bash
# 千问 API 配置
QWEN_API_KEY=your_qwen_api_key_here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

### 获取千问 API Key

1. 访问 [阿里云百炼平台](https://bailian.console.aliyun.com/)
2. 开通服务并创建 API Key
3. 将 API Key 填入配置文件

### 可用模型

| 模型 | 说明 |
|------|------|
| `qwen-plus` | 推荐使用，平衡性能和成本 |
| `qwen-turbo` | 响应更快，适合简单任务 |
| `qwen-max` | 最强性能，适合复杂任务 |

## 使用示例

### 通过 MCP 协议调用

```json
{
  "method": "tools/call",
  "params": {
    "name": "nl_database_operation",
    "arguments": {
      "natural_language": "在users表中添加3条测试数据"
    }
  }
}
```

### 自然语言示例

| 自然语言输入 | 解析意图 |
|-------------|---------|
| "在users表中添加3条测试数据" | INSERT 3条到users表 |
| "给products表插入10条数据" | INSERT 10条到products表 |
| "查看orders表的数据" | SELECT * FROM orders LIMIT 10 |
| "查询customers表前5条记录" | SELECT * FROM customers LIMIT 5 |

### 预演模式

只生成 SQL 不执行：

```json
{
  "natural_language": "在users表中添加5条测试数据",
  "dry_run": true
}
```

返回结果包含生成的 SQL 供确认。

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    nl_database_operation                  │
│                       (MCP Tool)                         │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   NLDatabaseExecutor                     │
│  ┌────────────────────────────────────────────────────┐ │
│  │  1. QwenNLParser (千问自然语言解析)                │ │
│  │     - 调用阿里云千问 API 解析自然语言              │ │
│  │     - 回退到正则表达式匹配                          │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  2. DatabaseSchemaReader                           │ │
│  │     - 读取数据库表结构                              │ │
│  │     - 获取列信息、类型、约束                        │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  3. TestDataGenerator                              │ │
│  │     - 根据表结构生成测试数据                        │ │
│  │     - 语义感知的字段值生成                          │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Async Database Session                       │
│              (SQLAlchemy + asyncpg)                       │
└─────────────────────────────────────────────────────────┘
```

## 千问 API 调用

工具使用 OpenAI SDK 的兼容模式调用千问 API：

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=qwen_api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

response = await client.chat.completions.create(
    model="qwen-plus",
    messages=[...],
    response_format={"type": "json_object"}  # 强制返回 JSON
)
```

## 安全说明

1. **权限继承**：工具使用当前用户配置的数据库权限
2. **表名验证**：只操作实际存在的表
3. **预演模式**：建议先使用 dry_run=true 预览 SQL
4. **SQL 注入防护**：使用参数化查询和值转义

## 扩展

### 添加新的语义规则

在 `TestDataGenerator._generate_value()` 方法中添加新的字段名模式：

```python
elif "custom_field" in col_name_lower:
    return self.sample_data["custom"][index % len(...)]
```

### 支持更多操作类型

在 `NLDatabaseExecutor.execute_nl_request()` 中添加新的操作类型处理。

## 故障排除

### 千问 API 调用失败

如果 API 调用失败，工具会自动回退到正则表达式解析模式：

```python
# 日志输出
WARNING - Qwen API call failed: xxx, falling back to regex
```

### 表名匹配不准确

如果千问返回的表名不在可用列表中，工具会尝试模糊匹配。如需更准确的匹配，可以在自然语言中明确指定表名。

## 依赖

```txt
# AI/LLM (使用 OpenAI SDK 调用千问 API)
openai>=1.0.0

# 数据库
sqlalchemy>=2.0.23
asyncpg>=0.29.0
```

## 价格参考

千问 API 按实际调用计费，具体价格请参考 [阿里云百炼定价](https://bailian.console.aliyun.com/price)。

建议使用 `qwen-plus` 模型，性价比最高。
