class MessageHandler {
  constructor(wsServer) {
    this.wsServer = wsServer;
    this.handlers = {
      // 认证相关
      'auth.login': this.handleLogin.bind(this),
      'auth.register': this.handleRegister.bind(this),
      'auth.logout': this.handleLogout.bind(this),

      // 聊天相关
      'chat.message': this.handleChatMessage.bind(this),
      'chat.private': this.handlePrivateMessage.bind(this),
      'chat.typing': this.handleTyping.bind(this),

      // 房间相关
      'room.join': this.handleRoomJoin.bind(this),
      'room.leave': this.handleRoomLeave.bind(this),
      'room.create': this.handleRoomCreate.bind(this),
      'room.list': this.handleRoomList.bind(this),
      'room.info': this.handleRoomInfo.bind(this),

      // 用户相关
      'user.list': this.handleUserList.bind(this),
      'user.info': this.handleUserInfo.bind(this),
      'user.status': this.handleUserStatus.bind(this),

      // 系统相关
      'system.ping': this.handlePing.bind(this),
      'system.stats': this.handleStats.bind(this),
      'system.history': this.handleHistory.bind(this)
    };
  }

  async handle(client, message) {
    const { type, action, data, _meta } = message;

    if (!type || !action) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'invalid_message',
        data: { message: 'Message must have type and action' }
      });
      return;
    }

    const handlerKey = `${type}.${action}`;
    const handler = this.handlers[handlerKey];

    if (!handler) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'unknown_action',
        data: {
          message: `Unknown action: ${handlerKey}`,
          availableActions: Object.keys(this.handlers)
        }
      });
      return;
    }

    try {
      await handler(client, data, _meta);
    } catch (error) {
      console.error(`Error handling ${handlerKey}:`, error);
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'handler_error',
        data: {
          message: 'Error processing your request',
          error: error.message
        }
      });
    }
  }

  // 认证处理器
  async handleLogin(client, data) {
    const { username, password } = data;

    if (!username || !password) {
      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'login_failed',
        data: { message: 'Username and password are required' }
      });
      return;
    }

    const result = this.wsServer.userManager.authenticateUser(username, password);

    if (result.success) {
      this.wsServer.userManager.updateClientUser(client.id, result.user);
      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'login_success',
        data: {
          user: result.user,
          sessionId: result.sessionId
        }
      });

      // 广播用户上线
      this.wsServer.broadcast({
        type: 'presence',
        action: 'user_online',
        data: {
          user: result.user,
          timestamp: new Date().toISOString()
        }
      }, client.id);
    } else {
      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'login_failed',
        data: { message: result.error }
      });
    }
  }

  async handleRegister(client, data) {
    const { username, password, userInfo } = data;

    if (!username || !password) {
      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'register_failed',
        data: { message: 'Username and password are required' }
      });
      return;
    }

    const result = this.wsServer.userManager.registerUser(username, password, userInfo);

    if (result.success) {
      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'register_success',
        data: { user: result.user }
      });
    } else {
      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'register_failed',
        data: { message: result.error }
      });
    }
  }

  async handleLogout(client, data) {
    const { sessionId } = data;
    const result = this.wsServer.userManager.logout(sessionId);

    if (result.success && client.user) {
      const user = client.user;
      this.wsServer.userManager.updateClientUser(client.id, null);

      this.wsServer.sendToClient(client, {
        type: 'auth',
        action: 'logout_success',
        data: { message: 'Logged out successfully' }
      });

      // 广播用户离线
      this.wsServer.broadcast({
        type: 'presence',
        action: 'user_offline',
        data: {
          user: user,
          timestamp: new Date().toISOString()
        }
      }, client.id);
    }
  }

  // 聊天处理器
  async handleChatMessage(client, data) {
    const { content, room } = data;
    const targetRoom = room || client.currentRoom;

    if (!targetRoom) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'no_room',
        data: { message: 'You must join a room first' }
      });
      return;
    }

    const message = {
      type: 'chat',
      action: 'message',
      data: {
        content,
        room: targetRoom,
        sender: client.user ? {
          username: client.user.username,
          displayName: client.user.displayName,
          avatar: client.user.avatar
        } : {
          username: `Guest_${client.id.substr(0, 8)}`,
          displayName: 'Guest',
          avatar: null
        },
        timestamp: new Date().toISOString()
      }
    };

    // 保存到历史记录
    this.wsServer.roomManager.addMessageToHistory(targetRoom, message.data);

    // 广播到房间
    this.wsServer.broadcastToRoom(targetRoom, message);
  }

  async handlePrivateMessage(client, data) {
    const { to, content } = data;

    if (!to || !content) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'invalid_message',
        data: { message: 'Recipient and content are required' }
      });
      return;
    }

    const recipientClients = this.wsServer.userManager.getClientsByUsernames([to]);

    if (recipientClients.length === 0) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'user_not_found',
        data: { message: 'Recipient not found or offline' }
      });
      return;
    }

    const message = {
      type: 'chat',
      action: 'private_message',
      data: {
        content,
        from: client.user ? {
          username: client.user.username,
          displayName: client.user.displayName,
          avatar: client.user.avatar
        } : {
          username: `Guest_${client.id.substr(0, 8)}`,
          displayName: 'Guest',
          avatar: null
        },
        to,
        timestamp: new Date().toISOString()
      }
    };

    // 发送给接收者
    recipientClients.forEach(recipient => {
      this.wsServer.sendToClient(recipient, message);
    });

    // 确认发送给发送者
    this.wsServer.sendToClient(client, {
      ...message,
      data: {
        ...message.data,
        delivered: true,
        recipientCount: recipientClients.length
      }
    });
  }

  async handleTyping(client, data) {
    const { room, isTyping } = data;
    const targetRoom = room || client.currentRoom;

    if (!targetRoom) return;

    this.wsServer.broadcastToRoom(targetRoom, {
      type: 'chat',
      action: 'typing',
      data: {
        user: client.user ? {
          username: client.user.username,
          displayName: client.user.displayName
        } : {
          username: `Guest_${client.id.substr(0, 8)}`,
          displayName: 'Guest'
        },
        isTyping,
        room: targetRoom
      }
    }, client.id);
  }

  // 房间处理器
  async handleRoomJoin(client, data) {
    const { roomId, password } = data;

    if (!roomId) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'invalid_room',
        data: { message: 'Room ID is required' }
      });
      return;
    }

    // 如果房间不存在，创建它
    let room = this.wsServer.roomManager.getRoom(roomId);
    if (!room) {
      this.wsServer.roomManager.createRoom(roomId);
      room = this.wsServer.roomManager.getRoom(roomId);
    }

    // 检查密码
    if (room.isPrivate && room.password !== password) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'invalid_password',
        data: { message: 'Invalid room password' }
      });
      return;
    }

    const result = this.wsServer.roomManager.addClientToRoom(roomId, client.id);

    if (result.success) {
      this.wsServer.userManager.setUserRoom(client.id, roomId);

      // 发送房间信息给加入者
      this.wsServer.sendToClient(client, {
        type: 'room',
        action: 'joined',
        data: {
          room: result.room,
          history: this.wsServer.roomManager.getRoomHistory(roomId)
        }
      });

      // 通知房间内其他用户
      this.wsServer.broadcastToRoom(roomId, {
        type: 'presence',
        action: 'user_joined',
        data: {
          user: client.user || {
            username: `Guest_${client.id.substr(0, 8)}`,
            displayName: 'Guest'
          },
          room: roomId,
          timestamp: new Date().toISOString()
        }
      }, client.id);
    } else {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'join_failed',
        data: { message: result.error }
      });
    }
  }

  async handleRoomLeave(client, data) {
    const { roomId } = data;
    const targetRoom = roomId || client.currentRoom;

    if (!targetRoom) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'no_room',
        data: { message: 'You are not in a room' }
      });
      return;
    }

    const result = this.wsServer.roomManager.removeClientFromRoom(targetRoom, client.id);

    if (result.success) {
      this.wsServer.userManager.setUserRoom(client.id, null);

      this.wsServer.sendToClient(client, {
        type: 'room',
        action: 'left',
        data: { room: targetRoom }
      });

      // 通知房间内其他用户
      this.wsServer.broadcastToRoom(targetRoom, {
        type: 'presence',
        action: 'user_left',
        data: {
          user: client.user || {
            username: `Guest_${client.id.substr(0, 8)}`,
            displayName: 'Guest'
          },
          room: targetRoom,
          timestamp: new Date().toISOString()
        }
      }, client.id);
    }
  }

  async handleRoomCreate(client, data) {
    const { roomId, name, isPrivate, password, maxClients } = data;

    const newRoomId = roomId || `room_${Date.now()}`;
    const result = this.wsServer.roomManager.createRoom(newRoomId, {
      name: name || newRoomId,
      isPrivate: isPrivate || false,
      password: password || null,
      maxClients: maxClients || null
    });

    this.wsServer.sendToClient(client, {
      type: 'room',
      action: 'created',
      data: {
        room: this.wsServer.roomManager.getRoomInfo(newRoomId)
      }
    });
  }

  async handleRoomList(client, data) {
    const { publicOnly } = data || {};
    const rooms = publicOnly
      ? this.wsServer.roomManager.getPublicRooms()
      : this.wsServer.roomManager.getAllRooms();

    this.wsServer.sendToClient(client, {
      type: 'room',
      action: 'list',
      data: { rooms }
    });
  }

  async handleRoomInfo(client, data) {
    const { roomId } = data;

    if (!roomId) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'invalid_room',
        data: { message: 'Room ID is required' }
      });
      return;
    }

    const room = this.wsServer.roomManager.getRoomInfo(roomId);

    if (room) {
      this.wsServer.sendToClient(client, {
        type: 'room',
        action: 'info',
        data: { room }
      });
    } else {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'room_not_found',
        data: { message: 'Room not found' }
      });
    }
  }

  // 用户处理器
  async handleUserList(client, data) {
    const { onlineOnly } = data || {};

    const users = onlineOnly
      ? this.wsServer.userManager.getOnlineUsers()
      : this.wsServer.userManager.getAllUsers();

    this.wsServer.sendToClient(client, {
      type: 'user',
      action: 'list',
      data: { users }
    });
  }

  async handleUserInfo(client, data) {
    const { username } = data;

    if (!username) {
      // 返回当前用户信息
      if (client.user) {
        this.wsServer.sendToClient(client, {
          type: 'user',
          action: 'info',
          data: { user: client.user }
        });
      } else {
        this.wsServer.sendToClient(client, {
          type: 'error',
          action: 'not_authenticated',
          data: { message: 'Not authenticated' }
        });
      }
      return;
    }

    const user = this.wsServer.userManager.getUserPublicInfo(username);

    if (user) {
      this.wsServer.sendToClient(client, {
        type: 'user',
        action: 'info',
        data: { user }
      });
    } else {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'user_not_found',
        data: { message: 'User not found' }
      });
    }
  }

  async handleUserStatus(client, data) {
    const { status } = data;

    if (!status) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'invalid_status',
        data: { message: 'Status is required' }
      });
      return;
    }

    const result = this.wsServer.userManager.setUserStatus(client.id, status);

    if (result.success) {
      // 广播状态变化
      if (client.currentRoom) {
        this.wsServer.broadcastToRoom(client.currentRoom, {
          type: 'presence',
          action: 'status_changed',
          data: {
            user: client.user || {
              username: `Guest_${client.id.substr(0, 8)}`,
              displayName: 'Guest'
            },
            status,
            room: client.currentRoom
          }
        }, client.id);
      }
    }
  }

  // 系统处理器
  async handlePing(client, data) {
    this.wsServer.sendToClient(client, {
      type: 'system',
      action: 'pong',
      data: {
        timestamp: new Date().toISOString(),
        serverTime: Date.now()
      }
    });
  }

  async handleStats(client, data) {
    const stats = this.wsServer.getStats();
    const userStats = this.wsServer.userManager.getStats();

    this.wsServer.sendToClient(client, {
      type: 'system',
      action: 'stats',
      data: {
        server: stats,
        users: userStats,
        rooms: this.wsServer.roomManager.getAllRooms()
      }
    });
  }

  async handleHistory(client, data) {
    const { room, limit } = data;
    const targetRoom = room || client.currentRoom;

    if (!targetRoom) {
      this.wsServer.sendToClient(client, {
        type: 'error',
        action: 'no_room',
        data: { message: 'Room not specified' }
      });
      return;
    }

    const history = this.wsServer.roomManager.getRoomHistory(targetRoom, limit);

    this.wsServer.sendToClient(client, {
      type: 'chat',
      action: 'history',
      data: {
        room: targetRoom,
        messages: history
      }
    });
  }
}

module.exports = MessageHandler;
