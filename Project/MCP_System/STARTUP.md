# MCP System 启动指南

## 快速开始

### 方式一：使用启动脚本（推荐）

```bash
# 启动 HTTP 服务器
python startup.py

# 启动 stdio 服务器（Claude Desktop 集成）
python startup.py stdio
```

### 方式二：直接运行

```bash
# HTTP 模式
python backend/main.py --transport http --port 8000

# stdio 模式
python backend/main.py --transport stdio
```

## 环境准备

### 1. Python 环境

```bash
# 确保使用 Python 3.11+
python --version

# 推荐使用虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
```

### 2. 安装依赖

```bash
cd /Users/ywwl/P_my_code/Project/MCP_System

# 安装核心依赖
pip install -r backend/requirements/base.txt

# 开发环境额外依赖
pip install -r backend/requirements/dev.txt
```

### 3. 配置文件

```bash
# 复制示例配置
cp backend/.env.example backend/.env

# 编辑配置文件
nano backend/.env  # 或使用其他编辑器
```

**必需配置项**：

```bash
# 千问 API（自然语言解析必需）
QWEN_API_KEY=sk-your-api-key-here
QWEN_MODEL=qwen-plus

# 数据库（可选，不使用可跳过）
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mcp_db

# Redis（可选，不使用可跳过）
REDIS_URL=redis://localhost:6379/0
```

## 运行模式

### HTTP 模式

适用于 Web API 调用和测试。

```bash
# 启动服务器
python startup.py

# 访问地址
curl http://localhost:8000/health
```

**API 端点**：
- `GET /` - 服务信息
- `GET /health` - 健康检查
- `GET /metrics` - Prometheus 指标
- `POST /mcp` - MCP 请求（HTTP/SSE）

### stdio 模式

适用于 Claude Desktop 集成。

```bash
# 启动 stdio 服务器
python startup.py stdio
```

**Claude Desktop 配置**：

```json
{
  "mcpServers": {
    "mcp-system": {
      "command": "python",
      "args": [
        "/Users/ywwl/P_my_code/Project/MCP_System/backend/main.py",
        "--transport", "stdio"
      ],
      "env": {
        "QWEN_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## 使用 Docker

### 使用 Docker Compose（推荐）

```bash
# 启动所有服务（包括数据库、Redis）
docker-compose up -d

# 查看日志
docker-compose logs -f mcp-system

# 停止服务
docker-compose down
```

### 仅启动核心服务

```bash
# 不包含 Kafka 和监控
docker-compose up -d mcp-system postgres redis
```

## 测试工具

### 测试自然语言数据库工具

```bash
# 运行测试脚本
python backend/test_nl_tool.py
```

### 测试提示词管理

```bash
python -c "
from backend.services.prompts.prompt_manager import prompt_manager
print('模板数量:', prompt_manager.get_stats()['total_templates'])
print(prompt_manager.render('nl_database_parse_user',
                         tables='users',
                         user_input='查询数据'))
"
```

## 常见问题

### 1. 端口被占用

```bash
# 更改端口
python startup.py --port 8001
```

### 2. 数据库连接失败

```bash
# 检查 PostgreSQL 是否运行
pg_isready -h localhost -p 5432

# 启动 PostgreSQL
brew services start postgresql  # Mac
sudo systemctl start postgresql  # Linux
```

### 3. 千问 API 调用失败

```bash
# 检查 API Key
python -c "from backend.config import settings; print(settings.QWEN_API_KEY)"

# 测试 API 连接
python -c "
from backend.services.tools.nl_database_tool import QwenNLParser
import asyncio

async def test():
    parser = QwenNLParser()
    result = await parser.parse_intent('查询数据', ['users'])
    print(result)

asyncio.run(test())
"
```

### 4. 日志查看

```bash
# 查看日志文件
tail -f logs/mcp_system.log

# 调整日志级别
export LOG_LEVEL=DEBUG
python startup.py
```

## 开发模式

### 启用开发特性

```bash
# 设置开发环境
export ENVIRONMENT=development
export DEBUG=true

# 启用详细日志
export LOG_LEVEL=DEBUG

# 启动服务
python startup.py
```

### 热重载

```bash
# 使用 uvicorn 的自动重载
uvicorn backend.main:create_app --reload --host 0.0.0.0 --port 8000
```

## 生产部署

### 使用 Gunicorn

```bash
pip install gunicorn uvicorn

gunicorn backend.main:create_app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### 使用 systemd

创建 `/etc/systemd/system/mcp-system.service`：

```ini
[Unit]
Description=MCP System Server
After=network.target postgresql.service

[Service]
Type=notify
User=mcp
WorkingDirectory=/path/to/MCP_System
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/gunicorn backend.main:create_app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable mcp-system
sudo systemctl start mcp-system
sudo systemctl status mcp-system
```

## 监控和维护

### 健康检查

```bash
# 简单检查
curl http://localhost:8000/health

# 详细检查
curl http://localhost:8000/health | jq
```

### 查看指标

```bash
curl http://localhost:8000/metrics
```

### 日志管理

```bash
# 日志轮转已配置，自动管理
# 手动清理旧日志
find logs/ -name "*.log.*" -mtime +30 -delete
```

## 相关文档

- [README.md](README.md) - 项目概述
- [docs/nl_database_tool.md](docs/nl_database_tool.md) - 自然语言数据库工具
- [docs/prompt_management.md](docs/prompt_management.md) - 提示词管理
- [backend/.env.example](backend/.env.example) - 配置模板
