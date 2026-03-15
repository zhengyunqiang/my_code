# WebSocket 实时协作平台 (FastAPI + Docker)

基于 FastAPI、PostgreSQL、Redis 和 Docker 的完整 WebSocket 实时通信平台。

## 技术栈

### 后端
- **FastAPI**: 现代化的 Python Web 框架
- **WebSocket**: 实时双向通信
- **PostgreSQL**: 关系型数据库（用户、房间、消息存储）
- **Redis**: 缓存和会话管理（在线用户、速率限制、消息历史）
- **SQLAlchemy**: ORM 和数据库管理
- **JWT**: 用户认证和授权

### 前端
- **原生 JavaScript**: 无框架依赖
- **WebSocket API**: 浏览器原生 WebSocket
- **响应式设计**: 适配桌面和移动设备

### 基础设施
- **Docker & Docker Compose**: 容器化部署
- **Uvicorn**: ASGI 服务器

## 功能特性

### 核心功能
- ✅ 实时双向通信（WebSocket）
- ✅ 用户注册、登录、认证（JWT）
- ✅ 房间管理（创建、加入、离开）
- ✅ 即时聊天（群聊和私信）
- ✅ 在线状态管理
- ✅ 输入指示器
- ✅ 消息历史记录
- ✅ 速率限制
- ✅ 心跳检测
- ✅ 自动重连
- ✅ 数据持久化

## 快速开始

### 使用 Docker Compose（推荐）

1. **克隆项目**
```bash
cd websocket
```

2. **启动所有服务**
```bash
docker-compose up -d
```

这将启动：
- PostgreSQL 数据库（端口 5432）
- Redis 缓存（端口 6379）
- FastAPI 后端（端口 8000）

3. **访问应用**
- 后端 API: http://localhost:8000
- WebSocket: ws://localhost:8000/ws
- API 文档: http://localhost:8000/docs

### 手动启动

#### 1. 启动数据库服务

```bash
# 仅启动 PostgreSQL 和 Redis
docker-compose up -d postgres redis
```

#### 2. 配置环境变量

```bash
cd server-fastapi
cp .env.example .env
# 编辑 .env 文件，配置数据库连接等
```

#### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

#### 4. 初始化数据库

```bash
python init_db.py all
```

#### 5. 启动 FastAPI 服务器

```bash
# 开发模式（自动重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 项目结构

```
websocket/
├── server-fastapi/          # FastAPI 后端
│   ├── main.py             # 应用入口
│   ├── config.py           # 配置管理
│   ├── database.py         # 数据库模型和连接
│   ├── redis_client.py     # Redis 客户端和管理器
│   ├── auth.py             # 认证和授权
│   ├── websocket_manager.py # WebSocket 连接管理
│   ├── websocket_handlers.py # WebSocket 消息处理
│   ├── schemas.py          # Pydantic 模型
│   ├── init_db.py          # 数据库初始化脚本
│   ├── requirements.txt    # Python 依赖
│   ├── Dockerfile          # Docker 镜像
│   └── .env.example        # 环境变量示例
├── client/                  # 前端客户端
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js          # 原版（Node.js 后端）
│       └── app-fastapi.js  # FastAPI 版本
├── docker-compose.yml       # Docker Compose 配置
└── README-FASTAPI.md        # 本文档
```

## 数据库架构

### PostgreSQL 表结构

**users** - 用户表
- id: 主键
- username: 用户名（唯一）
- email: 邮箱（唯一）
- hashed_password: 哈希密码
- display_name: 显示名称
- avatar_url: 头像 URL
- is_online: 在线状态
- last_seen: 最后活跃时间
- created_at: 创建时间
- updated_at: 更新时间
- metadata: JSON 元数据

**rooms** - 房间表
- id: 主键
- room_id: 房间 ID（唯一，用于 WebSocket）
- name: 房间名称
- description: 描述
- is_private: 是否私密
- password: 密码（哈希）
- max_clients: 最大人数
- created_by: 创建者 ID
- created_at: 创建时间
- is_active: 是否活跃

**messages** - 消息表
- id: 主键
- room_id: 房间 ID
- user_id: 发送者 ID
- content: 消息内容
- message_type: 消息类型
- created_at: 发送时间
- metadata: JSON 元数据

**room_members** - 房间成员表
- id: 主键
- room_id: 房间 ID
- user_id: 用户 ID
- joined_at: 加入时间
- last_read_at: 最后阅读时间
- role: 角色（owner/admin/member）

### Redis 数据结构

**在线用户管理**
- `online_users`: Set - 存储在线用户 ID
- `user_connections`: Hash - 用户 ID 到连接 ID 的映射
- `user_last_seen:{user_id}`: String - 用户最后活跃时间

**房间状态管理**
- `room:{room_id}:clients`: Set - 房间内的客户端 ID
- `room:{room_id}:users`: Hash - 客户端到用户的映射
- `room:{room_id}:count`: String - 房间人数
- `room:{room_id}:history`: List - 消息历史记录

**速率限制**
- `rate_limit:{client_id}`: String - 速率限制计数器

## API 文档

### WebSocket 消息协议

#### 连接端点
```
ws://localhost:8000/ws
```

#### 消息格式
```json
{
  "type": "消息类型",
  "action": "操作类型",
  "data": { }
}
```

### 认证相关

#### 登录
```json
{
  "type": "auth",
  "action": "login",
  "data": {
    "username": "admin",
    "password": "admin123"
  }
}
```

#### 注册
```json
{
  "type": "auth",
  "action": "register",
  "data": {
    "username": "newuser",
    "password": "password123",
    "email": "user@example.com",
    "displayName": "New User"
  }
}
```

### 聊天相关

#### 发送消息
```json
{
  "type": "chat",
  "action": "message",
  "data": {
    "content": "Hello, world!",
    "room": "general"
  }
}
```

#### 私信
```json
{
  "type": "chat",
  "action": "private",
  "data": {
    "to": "username",
    "content": "Private message"
  }
}
```

### 房间相关

#### 加入房间
```json
{
  "type": "room",
  "action": "join",
  "data": {
    "roomId": "general",
    "password": null
  }
}
```

#### 创建房间
```json
{
  "type": "room",
  "action": "create",
  "data": {
    "roomName": "My Room",
    "isPrivate": false,
    "maxClients": 50
  }
}
```

### REST API 端点

#### 健康检查
```
GET /health
```

#### 服务器统计
```
GET /api/stats
```

## 配置说明

### 环境变量

创建 `.env` 文件（参考 `.env.example`）：

```bash
# 应用配置
APP_NAME=WebSocket Realtime Platform
DEBUG=True
HOST=0.0.0.0
PORT=8000

# CORS 配置
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]

# JWT 认证
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# 数据库
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/websocket_db

# Redis
REDIS_URL=redis://localhost:6379/0

# 速率限制
RATE_LIMIT_ENABLED=True
RATE_LIMIT_PER_MINUTE=60
```

## 开发指南

### 数据库管理

```bash
# 创建数据库
python init_db.py create

# 初始化表结构
python init_db.py init

# 重置数据库
python init_db.py reset

# 查看数据库信息
python init_db.py info
```

### 测试用户

系统初始化时会创建以下测试用户：

- **admin / admin123** - 管理员账号
- **test / test123** - 测试账号

### 默认房间

系统初始化时会创建以下房间：

- **general** - 公共大厅
- **tech** - 技术交流
- **random** - 闲聊

## 生产部署

### Docker 部署

1. **更新环境变量**
```bash
# 修改 docker-compose.yml 中的敏感信息
# 使用强密码和安全的 SECRET_KEY
```

2. **构建并启动**
```bash
docker-compose up -d --build
```

3. **查看日志**
```bash
docker-compose logs -f backend
```

4. **停止服务**
```bash
docker-compose down
```

### 安全建议

1. **使用 HTTPS/WSS**
   - 配置 SSL 证书
   - 使用反向代理（Nginx）

2. **环境变量**
   - 使用强密钥
   - 不要提交 .env 文件

3. **数据库**
   - 使用强密码
   - 限制网络访问
   - 定期备份

4. **速率限制**
   - 启用速率限制
   - 配置合理的限制值

### Nginx 反向代理配置

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 监控和日志

### 健康检查

```bash
curl http://localhost:8000/health
```

### 服务器统计

```bash
curl http://localhost:8000/api/stats
```

### 查看连接统计

访问 http://localhost:8000/docs 使用 Swagger UI 查看 API 文档。

## 故障排除

### 数据库连接失败

```bash
# 检查 PostgreSQL 是否运行
docker-compose ps postgres

# 查看 PostgreSQL 日志
docker-compose logs postgres

# 重启 PostgreSQL
docker-compose restart postgres
```

### Redis 连接失败

```bash
# 检查 Redis 是否运行
docker-compose ps redis

# 查看 Redis 日志
docker-compose logs redis

# 重启 Redis
docker-compose restart redis
```

### WebSocket 连接失败

1. 检查后端是否运行
2. 检查防火墙设置
3. 查看 CORS 配置
4. 检查浏览器控制台错误

## 性能优化

1. **使用连接池**
   - SQLAlchemy 已配置连接池
   - Redis 使用连接池

2. **缓存策略**
   - 使用 Redis 缓存热点数据
   - 合理设置过期时间

3. **数据库优化**
   - 添加索引
   - 优化查询
   - 使用读写分离

4. **水平扩展**
   - 使用负载均衡
   - Redis 发布/订阅实现跨服务器通信

## 扩展功能

可以添加的功能：

- [ ] 文件传输和分享
- [ ] 语音/视频通话
- [ ] 屏幕共享
- [ ] 协作白板
- [ ] 代码编辑器
- [ ] 机器人集成
- [ ] 消息加密
- [ ] 多语言支持
- [ ] 移动应用

## 许可证

MIT License

## 支持

如有问题，请提交 Issue 或 Pull Request。
