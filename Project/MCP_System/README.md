# MCP System

生产级 MCP (Model Context Protocol) 服务系统，采用 5 层分层架构。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        接入与协议层 (Layer 1)                     │
│              JSON-RPC 处理 | stdio/HTTP 传输                      │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                       安全与网关层 (Layer 2)                      │
│            认证 | 授权 | 输入清洗 | 速率限制                     │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                      编排与路由层 (Layer 3)                       │
│         请求路由 | Schema 映射 | 工具发现 | 结果聚合            │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                     业务逻辑层 (Layer 4)                         │
│              工具系统 | 资源系统 | 提示词系统                    │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   数据与集成层 (Layer 5)                         │
│        缓存 (Redis) | 消息队列 (Kafka) | 存储 | API            │
└─────────────────────────────────────────────────────────────────┘
```

## 功能特性

### 协议支持
- ✅ JSON-RPC 2.0 协议
- ✅ stdio 传输（Claude Desktop 集成）
- ✅ HTTP/SSE 传输（生产环境）
- ✅ 完整的 MCP 协议方法实现

### 安全特性
- ✅ JWT 认证
- ✅ API 密钥认证
- ✅ RBAC 权限控制
- ✅ Prompt 注入检测
- ✅ 速率限制和配额管理

### 核心功能
- ✅ 工具注册表和执行器
- ✅ 资源管理和缓存
- ✅ 提示词模板系统
- ✅ 上下文管理
- ✅ 结果聚合

### 数据集成
- ✅ Redis 缓存（多级缓存）
- ✅ Kafka 消息队列
- ✅ 本地文件存储
- ✅ HTTP 客户端

## 快速开始

### 环境要求
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### 使用 Docker Compose

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f mcp-system

# 启动带 Kafka 和监控的完整系统
docker-compose --profile kafka --profile monitoring up -d
```

### 手动安装

```bash
# 安装依赖
cd backend
pip install -r requirements/base.txt

# 复制环境变量
cp .env.example .env

# 启动 HTTP 服务
python main.py --transport http

# 启动 stdio 服务（Claude Desktop）
python main.py --transport stdio
```

## 配置

主要配置项（参见 `backend/.env.example`）：

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mcp_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=your-secret-key-change-this

# 速率限制
RATE_LIMIT_PER_MINUTE=60
USER_DAILY_QUOTA=10000
```

## 使用示例

### 注册工具

```python
from backend.services.tools import tool

@tool(
    name="echo",
    description="Echo back the input message",
    category="utility",
)
async def echo_tool(arguments: dict, context):
    message = arguments.get("message", "")
    return [{"type": "text", "text": f"Echo: {message}"}]
```

### 注册资源

```python
from backend.services.resources import resource

@resource(
    uri="file:///config.json",
    name="Configuration",
    description="Application configuration",
)
async def read_config(uri: str):
    return '{"version": "1.0.0"}'
```

### 注册提示词

```python
from backend.services.prompts import prompt

@prompt(
    name="summarize",
    description="Summarize the given text",
    variables=[
        {"name": "text", "description": "Text to summarize", "required": True}
    ],
)
def summarize_prompt():
    '''Please summarize the following text: {text}'''
    pass
```

## API 端点

- `GET /health` - 健康检查
- `POST /` - MCP 请求（HTTP/SSE）

## 开发

```bash
# 安装开发依赖
pip install -r requirements/dev.txt

# 运行测试
pytest

# 代码格式化
black backend/
isort backend/

# 类型检查
mypy backend/
```

## 许可证

MIT
