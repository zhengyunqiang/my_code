class RoomManager {
  constructor() {
    this.rooms = new Map();
    this.roomHistory = new Map(); // 存储房间消息历史
    this.maxHistorySize = 100; // 每个房间最多保存100条历史消息
  }

  createRoom(roomId, options = {}) {
    if (!this.rooms.has(roomId)) {
      this.rooms.set(roomId, {
        id: roomId,
        name: options.name || roomId,
        clients: new Set(),
        createdAt: new Date(),
        metadata: options.metadata || {},
        isPrivate: options.isPrivate || false,
        password: options.password || null,
        maxClients: options.maxClients || null
      });
      this.roomHistory.set(roomId, []);
      console.log(`🏠 Room created: ${roomId}`);
      return this.getRoom(roomId);
    }
    return this.getRoom(roomId);
  }

  getRoom(roomId) {
    return this.rooms.get(roomId);
  }

  getAllRooms() {
    return Array.from(this.rooms.values()).map(room => ({
      id: room.id,
      name: room.name,
      clientCount: room.clients.size,
      createdAt: room.createdAt,
      metadata: room.metadata,
      isPrivate: room.isPrivate
    }));
  }

  getPublicRooms() {
    return this.getAllRooms().filter(room => !room.isPrivate);
  }

  addClientToRoom(roomId, clientId) {
    const room = this.getRoom(roomId);
    if (!room) {
      return { success: false, error: 'Room not found' };
    }

    // 检查房间是否已满
    if (room.maxClients && room.clients.size >= room.maxClients) {
      return { success: false, error: 'Room is full' };
    }

    // 如果客户端在之前的房间，先移除
    this.rooms.forEach(r => {
      if (r.clients.has(clientId)) {
        r.clients.delete(clientId);
      }
    });

    room.clients.add(clientId);
    console.log(`👤 Client ${clientId} joined room ${roomId}`);
    return { success: true, room: this.getRoomInfo(roomId) };
  }

  removeClientFromRoom(roomId, clientId) {
    const room = this.getRoom(roomId);
    if (!room) {
      return { success: false, error: 'Room not found' };
    }

    room.clients.delete(clientId);
    console.log(`🚪 Client ${clientId} left room ${roomId}`);

    // 如果房间为空，可以选择删除房间或保留
    if (room.clients.size === 0) {
      // 保留空房间，但可以添加清理逻辑
      console.log(`🏠 Room ${roomId} is now empty`);
    }

    return { success: true };
  }

  getClientsInRoom(roomId) {
    const room = this.getRoom(roomId);
    return room ? Array.from(room.clients) : [];
  }

  getRoomInfo(roomId) {
    const room = this.getRoom(roomId);
    if (!room) {
      return null;
    }

    return {
      id: room.id,
      name: room.name,
      clientCount: room.clients.size,
      createdAt: room.createdAt,
      metadata: room.metadata,
      isPrivate: room.isPrivate,
      hasPassword: !!room.password
    };
  }

  addMessageToHistory(roomId, message) {
    if (!this.roomHistory.has(roomId)) {
      this.roomHistory.set(roomId, []);
    }

    const history = this.roomHistory.get(roomId);
    history.push({
      ...message,
      timestamp: new Date().toISOString()
    });

    // 限制历史记录大小
    if (history.length > this.maxHistorySize) {
      history.shift(); // 移除最老的消息
    }
  }

  getRoomHistory(roomId, limit = 50) {
    const history = this.roomHistory.get(roomId);
    if (!history) {
      return [];
    }
    return history.slice(-limit);
  }

  clearRoomHistory(roomId) {
    if (this.roomHistory.has(roomId)) {
      this.roomHistory.set(roomId, []);
      return true;
    }
    return false;
  }

  deleteRoom(roomId) {
    const room = this.getRoom(roomId);
    if (!room) {
      return { success: false, error: 'Room not found' };
    }

    // 通知房间内所有客户端房间将被删除
    this.rooms.delete(roomId);
    this.roomHistory.delete(roomId);
    console.log(`🗑️  Room deleted: ${roomId}`);
    return { success: true };
  }

  updateRoomMetadata(roomId, metadata) {
    const room = this.getRoom(roomId);
    if (!room) {
      return { success: false, error: 'Room not found' };
    }

    room.metadata = { ...room.metadata, ...metadata };
    return { success: true, room: this.getRoomInfo(roomId) };
  }

  getTotalRooms() {
    return this.rooms.size;
  }

  searchRooms(query) {
    const lowerQuery = query.toLowerCase();
    return this.getAllRooms().filter(room =>
      room.name.toLowerCase().includes(lowerQuery) ||
      room.id.toLowerCase().includes(lowerQuery)
    );
  }
}

module.exports = RoomManager;
