# MCP_System 项目详细解析

## 一、项目概述

**MCP System** 是一个生产级的 **MCP (Model Context Protocol)** 服务系统，实现了完整的 MCP 协议，允许 AI 模型（如 Claude）与外部工具、资源和提示词进行交互。

### 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Web框架 | FastAPI |
| 数据库 | PostgreSQL / SQLite + SQLAlchemy 2.0 |
| 缓存 | Redis |
| 消息队列 | Kafka (可选) |
| AI集成 | 阿里云通义千问 API |
| 部署 | Docker + Docker Compose |

---

## 二、五层架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 1: 接入与协议层 (Protocol)              │
│                 protocol/ - JSON-RPC | stdio/HTTP 传输           │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Layer 2: 安全与网关层 (Gateway)                │
│              gateway/ - 认证 | 授权 | 速率限制 | 输入清洗         │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Layer 3: 编排与路由层 (Orchestration)           │
│          orchestration/ - 请求路由 | 工具发现 | 结果聚合          │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Layer 4: 业务逻辑层 (Services)                 │
│              services/ - 工具 | 资源 | 提示词 系统                │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                 Layer 5: 数据与集成层 (Adapters)                 │
│          adapters/ - 缓存 | 数据库 | 消息队列 | 外部 API          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、目录结构

```
MCP_System/
├── backend/                    # 后端核心代码
│   ├── adapters/               # 数据集成层
│   │   ├── database/           # 数据库适配器
│   │   ├── cache/              # Redis 缓存适配器
│   │   ├── external/           # 外部 API 客户端
│   │   ├── messaging/          # Kafka 消息队列适配器
│   │   └── storage/            # 存储适配器
│   ├── core/                   # 核心模块
│   │   ├── logging.py          # 日志系统
│   │   ├── exceptions.py       # 异常定义
│   │   └── __init__.py
│   ├── gateway/                # 安全与网关层
│   ├── orchestration/          # 编排与路由层
│   ├── protocol/               # 协议处理层
│   │   ├── handlers.py         # MCP 协议处理器
│   │   ├── json_rpc.py         # JSON-RPC 实现
│   │   └── transports/         # 传输协议
│   │       ├── stdio.py        # stdio 传输
│   │       └── http_sse.py     # HTTP/SSE 传输
│   ├── services/               # 业务逻辑层
│   │   ├── tools/              # 工具系统
│   │   │   ├── registry.py     # 工具注册表
│   │   │   ├── executor.py     # 工具执行器
│   │   │   └── nl_database_tool.py  # 自然语言数据库工具
│   │   ├── resources/          # 资源系统
│   │   └── prompts/            # 提示词系统
│   ├── utils/                  # 工具函数
│   ├── requirements/           # 依赖管理
│   │   ├── base.txt            # 基础依赖
│   │   ├── dev.txt             # 开发依赖
│   │   └── prod.txt            # 生产依赖
│   ├── main.py                 # 主应用入口
│   └── config.py               # 配置管理
├── deployment/                 # 部署相关
│   └── docker/                 # Docker 配置
├── docs/                       # 文档目录
├── logs/                       # 日志目录
├── mcp_system.db               # SQLite 数据库（开发环境）
├── startup.py                  # 快速启动脚本
├── quick_test.py               # 快速测试脚本
├── README.md                   # 项目说明
└── mcp_system.md               # 架构设计文档
```

---

## 四、核心模块详解

### 1. 配置管理 (`backend/config.py`)

```python
class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "MCP System"
    APP_VERSION: str = "1.0.0"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    TRANSPORT_TYPE: str = "stdio"  # stdio, http, both

    # MCP 协议配置
    MCP_PROTOCOL_VERSION: str = "2024-11-05"

    # 千问 API 配置（用于自然语言解析）
    QWEN_API_KEY: str = ""
    QWEN_MODEL: str = "qwen-plus"
```

**特点：**
- 使用 `pydantic-settings` 管理配置
- 支持从 `.env` 文件和环境变量读取
- 单例模式确保全局配置一致性

---

### 2. 协议处理层 (`backend/protocol/`)

#### 2.1 MCP 协议处理器 (`handlers.py`)

```python
class MCPProtocolHandler:
    """实现 MCP 协议的核心方法"""

    async def initialize(self, params) -> Dict:
        """初始化 MCP 连接"""

    async def list_tools(self, params) -> Dict:
        """列出可用工具"""

    async def call_tool(self, params) -> Dict:
        """调用工具"""

    async def list_resources(self, params) -> Dict:
        """列出可用资源"""

    async def read_resource(self, params) -> Dict:
        """读取资源"""

    async def list_prompts(self, params) -> Dict:
        """列出可用提示词"""

    async def get_prompt(self, params) -> Dict:
        """获取提示词"""
```

#### 2.2 传输协议

**stdio 传输 (`transports/stdio.py`)：**
- 通过标准输入/输出与 Claude Desktop 通信
- 支持 Content-Length 头格式
- 异步消息处理

**HTTP 传输：**
- 通过 FastAPI 提供 REST API
- 支持 SSE (Server-Sent Events)

---

### 3. 工具系统 (`backend/services/tools/`)

#### 3.1 工具注册表 (`registry.py`)

```python
@dataclass
class ToolDefinition:
    """工具定义"""
    name: str                    # 工具名称
    description: str             # 工具描述
    input_schema: Dict[str, Any] # 输入 JSON Schema
    handler: Callable            # 处理函数
    status: ToolStatus           # 状态
    category: str                # 分类
    timeout: int                 # 超时时间

class ToolRegistry:
    """工具注册表 - 管理所有可用工具"""

    def register(self, name, description, input_schema, handler, **kwargs):
        """注册工具"""

    def get(self, name) -> ToolDefinition:
        """获取工具定义"""

    def list_tools(self, category=None, status=None) -> List:
        """列出工具"""

# 装饰器方式注册工具
@tool(name="echo", description="回显消息", category="utility")
async def echo_tool(args: dict) -> list:
    return [{"type": "text", "text": f"Echo: {args.get('message')}"}]
```

#### 3.2 自然语言数据库工具 (`nl_database_tool.py`)

这是项目的**核心亮点功能**：

```python
class QwenNLParser:
    """千问自然语言解析器"""

    async def parse_intent(self, text: str, available_tables: List[str]) -> ParsedIntent:
        """解析自然语言意图"""
        # 优先使用千问 API
        # 失败时回退到正则表达式

class NLDatabaseExecutor:
    """自然语言数据库执行器"""

    async def execute_nl_request(self, natural_language: str, dry_run: bool):
        """执行自然语言数据库请求"""
        # 1. 获取可用表
        # 2. 解析意图
        # 3. 执行操作
```

**支持的操作：**

| 操作 | 示例自然语言 |
|------|-------------|
| 插入 | "在users表中添加3条测试数据" |
| 查询 | "查看users表的数据" |
| 更新 | "把id为1000的用户名改为张三" |
| 删除 | "删除id为1000的用户" |

---

### 4. 数据与集成层 (`backend/adapters/`)

#### 4.1 数据库连接 (`adapters/database/connection.py`)

```python
# 支持 SQLite 和 PostgreSQL
engine = create_async_engine(**get_engine_config())

# 异步会话工厂
async_session_maker = async_sessionmaker(engine, class_=AsyncSession)

# 依赖注入
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

---

## 五、请求处理流程

```
客户端请求
     ↓
┌─────────────────┐
│   HTTP/stdio    │  Layer 1: 接入层
└────────┬────────┘
         ↓
┌─────────────────┐
│  认证 & 限流    │  Layer 2: 安全层
└────────┬────────┘
         ↓
┌─────────────────┐
│   路由 & 编排   │  Layer 3: 编排层
└────────┬────────┘
         ↓
┌─────────────────┐
│  工具/资源/提示 │  Layer 4: 业务层
└────────┬────────┘
         ↓
┌─────────────────┐
│  DB/缓存/外部API│  Layer 5: 集成层
└─────────────────┘
         ↓
     响应结果
```

---

## 六、MCP 协议交互示例

### 1. 初始化连接

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "clientInfo": {"name": "Claude", "version": "1.0"}
  }
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "serverInfo": {"name": "mcp-system-server", "version": "1.0.0"},
    "capabilities": {"tools": {}, "resources": {}, "prompts": {}}
  }
}
```

### 2. 列出工具

```json
// 请求
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

// 响应
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {"name": "echo", "description": "回显消息", "inputSchema": {...}},
      {"name": "nl_database_operation", "description": "自然语言数据库操作", ...}
    ]
  }
}
```

### 3. 调用工具

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "nl_database_operation",
    "arguments": {
      "natural_language": "在users表中添加3条测试数据",
      "dry_run": true
    }
  }
}
```

---

## 七、已注册工具列表

| 工具名 | 类别 | 功能描述 |
|--------|------|----------|
| `echo` | utility | 回显输入消息 |
| `get_current_time` | utility | 获取当前时间 |
| `calculate` | utility | 简单数学计算 |
| `generate_test_data` | database | 自动生成测试数据 |
| `show_table_structure` | database | 显示数据库表结构 |
| `parse_database_intent` | database | 解析自然语言意图 |
| `nl_database_operation` | database | **核心**：自然语言数据库操作 |

---

## 八、启动方式

```bash
# HTTP 模式（Web API）
python -m backend.main --transport http

# stdio 模式（Claude Desktop 集成）
python -m backend.main --transport stdio

# 指定端口
python -m backend.main --transport http --port 9000

# 使用 Docker Compose
docker-compose up -d
```

---

## 九、API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 服务信息 |
| `/health` | GET | 健康检查 |
| `/tools` | GET | 工具列表 |
| `/mcp` | POST | MCP 协议端点 |
| `/metrics` | GET | Prometheus 指标 |

---

## 十、环境配置

关键配置项（在 `backend/.env` 中设置）：

```bash
# 应用配置
APP_NAME=MCP System
DEBUG=true
ENVIRONMENT=development

# 数据库
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mcp_db
# 或使用 SQLite
# DATABASE_URL=sqlite+aiosqlite:///./mcp_system.db

# Redis
REDIS_URL=redis://localhost:6379/0

# 千问 API（用于自然语言功能）
QWEN_API_KEY=your-qwen-api-key-here
QWEN_MODEL=qwen-plus
```

---

## 十一、测试 API 调用

```bash
# 健康检查
curl http://localhost:8000/health

# 查看工具列表
curl http://localhost:8000/tools

# MCP 协议调用
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

---

*文档生成时间: 2026-03-24*
