module.exports = {
  port: process.env.PORT || 3000,
  websocket: {
    pingInterval: 30000, // 30秒
    pingTimeout: 5000,   // 5秒
    clientTracking: true,
    maxPayload: 1048576  // 1MB
  },
  auth: {
    enabled: false,      // 是否启用认证
    secret: 'your-secret-key'
  },
  rateLimit: {
    enabled: true,
    maxMessagesPerMinute: 60
  }
};
