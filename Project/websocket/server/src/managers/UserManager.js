class UserManager {
  constructor() {
    this.clients = new Map(); // clientId -> client object
    this.users = new Map();   // username -> user info
    this.sessions = new Map(); // sessionId -> user info
  }

  addClient(client) {
    this.clients.set(client.id, client);
  }

  removeClient(clientId) {
    const client = this.clients.get(clientId);
    if (client && client.user) {
      // 如果是已认证用户，更新用户状态
      const userInfo = this.users.get(client.user.username);
      if (userInfo) {
        userInfo.isOnline = false;
        userInfo.lastSeen = new Date();
      }
    }
    this.clients.delete(clientId);
  }

  getClient(clientId) {
    return this.clients.get(clientId);
  }

  getAllClients() {
    return Array.from(this.clients.values());
  }

  getTotalClients() {
    return this.clients.size;
  }

  // 用户认证和注册
  registerUser(username, password, userInfo = {}) {
    if (this.users.has(username)) {
      return { success: false, error: 'Username already exists' };
    }

    const user = {
      username,
      password, // 在生产环境中应该使用哈希密码
      email: userInfo.email || '',
      displayName: userInfo.displayName || username,
      avatar: userInfo.avatar || null,
      createdAt: new Date(),
      isOnline: false,
      lastSeen: new Date(),
      metadata: userInfo.metadata || {}
    };

    this.users.set(username, user);
    return { success: true, user: this.getUserPublicInfo(username) };
  }

  authenticateUser(username, password) {
    const user = this.users.get(username);
    if (!user) {
      return { success: false, error: 'User not found' };
    }

    if (user.password !== password) {
      return { success: false, error: 'Invalid password' };
    }

    // 创建会话
    const sessionId = this.generateSessionId();
    const session = {
      id: sessionId,
      username,
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000) // 24小时
    };

    this.sessions.set(sessionId, session);
    user.isOnline = true;

    return {
      success: true,
      user: this.getUserPublicInfo(username),
      sessionId
    };
  }

  validateSession(sessionId) {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return { success: false, error: 'Invalid session' };
    }

    if (session.expiresAt < new Date()) {
      this.sessions.delete(sessionId);
      return { success: false, error: 'Session expired' };
    }

    const user = this.users.get(session.username);
    if (!user) {
      return { success: false, error: 'User not found' };
    }

    return { success: true, user: this.getUserPublicInfo(session.username) };
  }

  logout(sessionId) {
    const session = this.sessions.get(sessionId);
    if (session) {
      const user = this.users.get(session.username);
      if (user) {
        user.isOnline = false;
        user.lastSeen = new Date();
      }
      this.sessions.delete(sessionId);
      return { success: true };
    }
    return { success: false, error: 'Session not found' };
  }

  getUserPublicInfo(username) {
    const user = this.users.get(username);
    if (!user) {
      return null;
    }

    return {
      username: user.username,
      displayName: user.displayName,
      avatar: user.avatar,
      isOnline: user.isOnline,
      lastSeen: user.lastSeen,
      createdAt: user.createdAt
    };
  }

  getClientByUser(username) {
    for (const [clientId, client] of this.clients) {
      if (client.user && client.user.username === username) {
        return client;
      }
    }
    return null;
  }

  getClientsByUsernames(usernames) {
    const clients = [];
    for (const username of usernames) {
      const client = this.getClientByUser(username);
      if (client) {
        clients.push(client);
      }
    }
    return clients;
  }

  updateClientUser(clientId, user) {
    const client = this.clients.get(clientId);
    if (client) {
      client.user = user;
      return { success: true };
    }
    return { success: false, error: 'Client not found' };
  }

  updateUserProfile(username, updates) {
    const user = this.users.get(username);
    if (!user) {
      return { success: false, error: 'User not found' };
    }

    // 允许更新的字段
    const allowedFields = ['displayName', 'avatar', 'email', 'metadata'];
    for (const field of allowedFields) {
      if (updates[field] !== undefined) {
        user[field] = updates[field];
      }
    }

    return { success: true, user: this.getUserPublicInfo(username) };
  }

  getOnlineUsers() {
    const onlineUsers = [];
    for (const [username, user] of this.users) {
      if (user.isOnline) {
        onlineUsers.push(this.getUserPublicInfo(username));
      }
    }
    return onlineUsers;
  }

  getAllUsers() {
    const users = [];
    for (const [username, user] of this.users) {
      users.push(this.getUserPublicInfo(username));
    }
    return users;
  }

  searchUsers(query) {
    const lowerQuery = query.toLowerCase();
    return this.getAllUsers().filter(user =>
      user.username.toLowerCase().includes(lowerQuery) ||
      user.displayName.toLowerCase().includes(lowerQuery)
    );
  }

  generateSessionId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  // 用户状态管理
  setUserStatus(clientId, status) {
    const client = this.clients.get(clientId);
    if (client) {
      client.status = status;
      return { success: true, status };
    }
    return { success: false, error: 'Client not found' };
  }

  getUserStatus(clientId) {
    const client = this.clients.get(clientId);
    return client ? {
      status: client.status || 'online',
      lastSeen: client.lastMessageTime
    } : null;
  }

  // 统计信息
  getStats() {
    return {
      totalClients: this.clients.size,
      totalUsers: this.users.size,
      activeSessions: this.sessions.size,
      onlineUsers: this.getOnlineUsers().length
    };
  }

  // 清理过期会话
  cleanupExpiredSessions() {
    const now = new Date();
    for (const [sessionId, session] of this.sessions) {
      if (session.expiresAt < now) {
        const user = this.users.get(session.username);
        if (user) {
          user.isOnline = false;
          user.lastSeen = new Date();
        }
        this.sessions.delete(sessionId);
      }
    }
  }

  // 获取用户所在的房间
  getUserRoom(clientId) {
    const client = this.clients.get(clientId);
    return client ? client.currentRoom : null;
  }

  // 设置用户当前房间
  setUserRoom(clientId, roomId) {
    const client = this.clients.get(clientId);
    if (client) {
      client.currentRoom = roomId;
      return { success: true };
    }
    return { success: false, error: 'Client not found' };
  }
}

module.exports = UserManager;
