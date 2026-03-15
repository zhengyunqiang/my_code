class RateLimiter {
  constructor(maxMessagesPerMinute = 60) {
    this.maxMessagesPerMinute = maxMessagesPerMinute;
    this.clientMessageCounts = new Map(); // clientId -> {count, resetTime}
    this.cleanupInterval = null;

    // 每分钟清理一次计数器
    this.startCleanup();
  }

  checkLimit(clientId) {
    const now = Date.now();
    let clientData = this.clientMessageCounts.get(clientId);

    if (!clientData) {
      clientData = {
        count: 0,
        resetTime: now + 60000 // 1分钟后重置
      };
      this.clientMessageCounts.set(clientId, clientData);
    }

    // 检查是否需要重置计数
    if (now > clientData.resetTime) {
      clientData.count = 0;
      clientData.resetTime = now + 60000;
    }

    // 检查是否超过限制
    if (clientData.count >= this.maxMessagesPerMinute) {
      return false;
    }

    clientData.count++;
    return true;
  }

  startCleanup() {
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60000); // 每分钟清理一次
  }

  cleanup() {
    const now = Date.now();
    for (const [clientId, data] of this.clientMessageCounts) {
      if (now > data.resetTime) {
        this.clientMessageCounts.delete(clientId);
      }
    }
  }

  getClientCount(clientId) {
    const data = this.clientMessageCounts.get(clientId);
    return data ? data.count : 0;
  }

  resetClient(clientId) {
    this.clientMessageCounts.delete(clientId);
  }

  setMaxMessages(max) {
    this.maxMessagesPerMinute = max;
  }

  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    this.clientMessageCounts.clear();
  }
}

module.exports = RateLimiter;
