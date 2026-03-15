const WebSocket = require('ws');
const { v4: uuidv4 } = require('uuid');
const RoomManager = require('./managers/RoomManager');
const UserManager = require('./managers/UserManager');
const MessageHandler = require('./handlers/MessageHandler');
const RateLimiter = require('./utils/RateLimiter');

class WebSocketServer {
  constructor(server) {
    this.wss = new WebSocket.Server({
      server,
      ...this.getWebSocketConfig()
    });

    this.roomManager = new RoomManager();
    this.userManager = new UserManager();
    this.messageHandler = new MessageHandler(this);
    this.rateLimiter = new RateLimiter();

    this.setupWebSocketServer();
    this.setupEventHandlers();
  }

  getWebSocketConfig() {
    return {
      clientTracking: true,
      maxPayload: 1048576 // 1MB
    };
  }

  setupWebSocketServer() {
    this.wss.on('connection', (ws, req) => {
      this.handleConnection(ws, req);
    });

    // 定时清理不活跃的连接
    setInterval(() => {
      this.cleanupInactiveConnections();
    }, 60000);
  }

  setupEventHandlers() {
    this.wss.on('error', (error) => {
      console.error('WebSocket Server Error:', error);
    });

    this.wss.on('close', () => {
      console.log('WebSocket Server closed');
    });
  }

  handleConnection(ws, req) {
    const clientId = uuidv4();
    const clientIp = req.socket.remoteAddress;

    // 创建客户端对象
    const client = {
      id: clientId,
      ws: ws,
      ip: clientIp,
      isAlive: true,
      user: null,
      currentRoom: null,
      connectedAt: new Date(),
      lastMessageTime: new Date()
    };

    // 存储客户端
    this.userManager.addClient(client);
    console.log(`📥 New connection: ${clientId} from ${clientIp}`);

    // 发送欢迎消息
    this.sendToClient(client, {
      type: 'system',
      action: 'connected',
      data: {
        clientId: clientId,
        timestamp: new Date().toISOString(),
        message: 'Connected to WebSocket Realtime Platform'
      }
    });

    // 设置WebSocket事件处理器
    ws.on('message', (message) => {
      this.handleMessage(client, message);
    });

    ws.on('pong', () => {
      client.isAlive = true;
    });

    ws.on('close', () => {
      this.handleDisconnection(client);
    });

    ws.on('error', (error) => {
      console.error(`Client ${clientId} error:`, error);
      this.handleDisconnection(client);
    });
  }

  handleMessage(client, message) {
    try {
      // 速率限制检查
      if (!this.rateLimiter.checkLimit(client.id)) {
        this.sendToClient(client, {
          type: 'error',
          action: 'rate_limit_exceeded',
          data: {
            message: 'Message rate limit exceeded. Please slow down.'
          }
        });
        return;
      }

      // 更新最后消息时间
      client.lastMessageTime = new Date();

      // 解析消息
      let parsedMessage;
      try {
        parsedMessage = JSON.parse(message);
      } catch (e) {
        // 如果不是JSON，处理为原始文本消息
        parsedMessage = {
          type: 'chat',
          action: 'message',
          data: {
            content: message.toString()
          }
        };
      }

      // 添加消息元数据
      parsedMessage._meta = {
        clientId: client.id,
        timestamp: new Date().toISOString()
      };

      // 委托给消息处理器
      this.messageHandler.handle(client, parsedMessage);

    } catch (error) {
      console.error('Error handling message:', error);
      this.sendToClient(client, {
        type: 'error',
        action: 'message_processing_error',
        data: {
          message: 'Failed to process message',
          error: error.message
        }
      });
    }
  }

  handleDisconnection(client) {
    console.log(`📤 Client disconnected: ${client.id}`);

    // 如果用户在房间中，从房间移除
    if (client.currentRoom) {
      this.roomManager.removeClientFromRoom(client.currentRoom, client.id);

      // 通知房间内其他用户
      this.broadcastToRoom(client.currentRoom, {
        type: 'presence',
        action: 'user_left',
        data: {
          userId: client.id,
          room: client.currentRoom,
          timestamp: new Date().toISOString()
        }
      }, client.id);
    }

    // 移除客户端
    this.userManager.removeClient(client.id);

    // 广播用户离线消息
    this.broadcast({
      type: 'presence',
      action: 'user_offline',
      data: {
        userId: client.id,
        timestamp: new Date().toISOString()
      }
    });
  }

  sendToClient(client, message) {
    if (client.ws && client.ws.readyState === WebSocket.OPEN) {
      try {
        client.ws.send(JSON.stringify(message));
      } catch (error) {
        console.error(`Error sending to client ${client.id}:`, error);
      }
    }
  }

  broadcast(message, excludeClient = null) {
    this.wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        if (!excludeClient || client.id !== excludeClient) {
          this.sendToClient(client, message);
        }
      }
    });
  }

  broadcastToRoom(roomId, message, excludeClient = null) {
    const room = this.roomManager.getRoom(roomId);
    if (!room) return;

    room.clients.forEach((clientId) => {
      const client = this.userManager.getClient(clientId);
      if (client && client.ws.readyState === WebSocket.OPEN) {
        if (!excludeClient || client.id !== excludeClient) {
          this.sendToClient(client, message);
        }
      }
    });
  }

  cleanupInactiveConnections() {
    const now = new Date();
    this.userManager.getAllClients().forEach((client) => {
      const inactiveTime = now - client.lastMessageTime;
      // 如果5分钟没有活动，关闭连接
      if (inactiveTime > 300000) {
        console.log(`🧹 Cleaning up inactive client: ${client.id}`);
        if (client.ws && client.ws.readyState === WebSocket.OPEN) {
          client.ws.terminate();
        }
      }
    });
  }

  getStats() {
    return {
      totalConnections: this.wss.clients.size,
      totalRooms: this.roomManager.getTotalRooms(),
      totalUsers: this.userManager.getTotalClients(),
      uptime: process.uptime()
    };
  }

  close() {
    this.wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.close();
      }
    });
    this.wss.close();
  }
}

module.exports = WebSocketServer;
