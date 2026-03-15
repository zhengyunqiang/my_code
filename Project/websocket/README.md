# WebSocket 实时协作平台

一个功能完整的 WebSocket 实时通信和协作平台，演示了 WebSocket 在现代 Web 应用中的各种应用场景。

## 功能特性

### 核心功能
- **实时通信**: 基于 WebSocket 的双向实时通信
- **用户系统**: 注册、登录、在线状态管理
- **房间管理**: 创建、加入、离开房间，支持公开和私密房间
- **即时聊天**: 房间内群聊和私信功能
- **在线状态**: 实时显示用户在线/离线状态
- **输入指示器**: 显示正在输入的用户
- **消息历史**: 自动保存和加载房间聊天记录
- **心跳检测**: 自动保持连接活跃
- **自动重连**: 连接断开时自动尝试重连

### 技术特性
- **速率限制**: 防止消息发送过快
- **消息路由**: 统一的消息处理和分发系统
- **会话管理**: 用户会话和权限控制
- **错误处理**: 完善的错误处理和用户反馈
- **响应式设计**: 适配桌面和移动设备

## 项目结构

```
websocket/
├── server/                 # 服务器端代码
│   ├── src/
│   │   ├── index.js       # 服务器入口
│   │   ├── websocket.js   # WebSocket 服务器核心
│   │   ├── handlers/      # 消息处理器
│   │   │   └── MessageHandler.js
│   │   ├── managers/      # 管理器
│   │   │   ├── RoomManager.js
│   │   │   └── UserManager.js
│   │   └── utils/         # 工具函数
│   │       └── RateLimiter.js
│   ├── config.js          # 配置文件
│   └── package.json
├── client/                 # 客户端代码
│   ├── index.html         # 主页面
│   ├── css/
│   │   └── style.css      # 样式文件
│   └── js/
│       └── app.js         # 客户端应用逻辑
└── README.md
```

## 快速开始

### 安装依赖

```bash
cd server
npm install
```

### 启动服务器

```bash
npm start
```

或者使用开发模式（自动重启）：

```bash
npm run dev
```

### 访问应用

打开浏览器访问：
- HTTP: http://localhost:3000
- WebSocket: ws://localhost:3000

## API 文档

### 消息协议

所有消息都遵循以下格式：

```json
{
  "type": "消息类型",
  "action": "操作类型",
  "data": {
    // 消息数据
  }
}
```

### 认证相关

#### 登录
```json
{
  "type": "auth",
  "action": "login",
  "data": {
    "username": "用户名",
    "password": "密码"
  }
}
```

#### 注册
```json
{
  "type": "auth",
  "action": "register",
  "data": {
    "username": "用户名",
    "password": "密码",
    "userInfo": {
      "displayName": "显示名称",
      "email": "邮箱"
    }
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
    "content": "消息内容",
    "room": "房间ID"
  }
}
```

#### 私信
```json
{
  "type": "chat",
  "action": "private",
  "data": {
    "to": "接收者用户名",
    "content": "消息内容"
  }
}
```

#### 输入状态
```json
{
  "type": "chat",
  "action": "typing",
  "data": {
    "room": "房间ID",
    "isTyping": true
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
    "roomId": "房间ID",
    "password": "密码（如果需要）"
  }
}
```

#### 离开房间
```json
{
  "type": "room",
  "action": "leave",
  "data": {
    "roomId": "房间ID"
  }
}
```

#### 创建房间
```json
{
  "type": "room",
  "action": "create",
  "data": {
    "roomId": "房间ID（可选）",
    "name": "房间名称",
    "isPrivate": false,
    "password": "密码（可选）",
    "maxClients": 10
  }
}
```

#### 获取房间列表
```json
{
  "type": "room",
  "action": "list",
  "data": {
    "publicOnly": true
  }
}
```

### 用户相关

#### 获取用户列表
```json
{
  "type": "user",
  "action": "list",
  "data": {
    "onlineOnly": true
  }
}
```

#### 更新用户状态
```json
{
  "type": "user",
  "action": "status",
  "data": {
    "status": "online|away|busy"
  }
}
```

### 系统相关

#### 心跳检测
```json
{
  "type": "system",
  "action": "ping",
  "data": {}
}
```

#### 获取服务器统计
```json
{
  "type": "system",
  "action": "stats",
  "data": {}
}
```

## 架构设计

### 服务器端架构

1. **WebSocketServer**: WebSocket 服务器核心类
   - 管理客户端连接
   - 处理消息分发
   - 实现心跳检测

2. **MessageHandler**: 消息处理器
   - 路由消息到对应的处理器
   - 统一的错误处理
   - 消息验证和权限检查

3. **RoomManager**: 房间管理器
   - 创建和管理房间
   - 维护房间客户端列表
   - 保存聊天历史

4. **UserManager**: 用户管理器
   - 用户认证和授权
   - 在线状态管理
   - 会话管理

5. **RateLimiter**: 速率限制器
   - 防止消息泛滥
   - 自动清理过期数据

### 客户端架构

1. **WebSocketApp**: 主应用类
   - 应用状态管理
   - 业务逻辑处理

2. **WebSocketManager**: WebSocket 管理器
   - 连接管理
   - 消息发送和接收
   - 自动重连

3. **UIManager**: UI 管理器
   - DOM 元素管理
   - 事件处理
   - 界面更新

## WebSocket 关键概念

### 1. 连接生命周期

```
连接建立 → 握手 → 消息交换 → 心跳保持 → 连接关闭
```

### 2. 消息类型

- **文本消息**: JSON 格式的业务数据
- **二进制消息**: 文件传输等（可扩展）
- **控制消息**: Ping/Pong 心跳

### 3. 心跳机制

```javascript
// 客户端定期发送 Ping
setInterval(() => {
    ws.send(JSON.stringify({ type: 'system', action: 'ping' }));
}, 30000);

// 服务器响应 Pong
ws.on('message', (data) => {
    const message = JSON.parse(data);
    if (message.action === 'pong') {
        // 更新最后活跃时间
    }
});
```

### 4. 自动重连

```javascript
function reconnect() {
    setTimeout(() => {
        if (reconnectAttempts < maxAttempts) {
            reconnectAttempts++;
            connect();
        }
    }, Math.pow(2, reconnectAttempts) * 1000);
}
```

## 性能优化

1. **消息批处理**: 合并多个小消息减少网络开销
2. **连接池**: 复用 WebSocket 连接
3. **消息压缩**: 使用二进制格式或压缩算法
4. **负载均衡**: 使用 Redis 实现跨服务器通信

## 安全考虑

1. **输入验证**: 严格验证所有输入数据
2. **速率限制**: 防止 DDoS 攻击
3. **认证授权**: 实现用户认证和权限控制
4. **数据加密**: 使用 WSS（WebSocket Secure）
5. **CSRF 防护**: 实现 token 验证

## 扩展功能

可以添加的功能：

- [ ] 文件传输
- [ ] 语音/视频通话
- [ ] 屏幕共享
- [ ] 白板协作
- [ ] 代码编辑器协作
- [ ] 数据库持久化
- [ ] Redis 消息队列
- [ ] 微服务架构

## 部署

### 生产环境配置

1. 使用 PM2 管理进程：
```bash
pm2 start src/index.js --name websocket-server
```

2. 配置 Nginx 反向代理：
```nginx
location / {
    proxy_pass http://localhost:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

3. 使用 SSL 证书启用 WSS

## 故障排除

### 连接问题
- 检查防火墙设置
- 确认 WebSocket 端口开放
- 检查代理配置

### 性能问题
- 监控内存使用
- 检查消息频率
- 优化数据库查询

## 许可证

MIT License

## 贡献

欢迎提交 Pull Request 和 Issue！

## 联系方式

如有问题，请提交 Issue 或联系维护者。
