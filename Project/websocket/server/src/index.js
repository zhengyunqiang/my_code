const express = require('express');
const http = require('http');
const WebSocketServer = require('./websocket');
const config = require('../config');
const path = require('path');

const app = express();
const server = http.createServer(app);

// 静态文件服务
app.use(express.static(path.join(__dirname, '../../client')));

// 主页路由
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../../client/index.html'));
});

// 创建WebSocket服务器
const wss = new WebSocketServer(server);

// 启动服务器
server.listen(config.port, () => {
  console.log(`🚀 WebSocket Realtime Platform Server running on port ${config.port}`);
  console.log(`📡 WebSocket endpoint: ws://localhost:${config.port}`);
  console.log(`🌐 HTTP endpoint: http://localhost:${config.port}`);
});

// 优雅关闭
process.on('SIGTERM', () => {
  console.log('📴 SIGTERM signal received: closing HTTP server');
  server.close(() => {
    console.log('👋 HTTP server closed');
    wss.close();
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('\n📴 SIGINT signal received: closing HTTP server');
  server.close(() => {
    console.log('👋 HTTP server closed');
    wss.close();
    process.exit(0);
  });
});
