// FastAPI 版本的 WebSocket 客户端
// 修改 WebSocket URL 以适配 FastAPI 后端

class WebSocketManagerFastAPI {
    constructor(app) {
        this.app = app;
        // 使用 FastAPI 的 WebSocket 端点
        this.url = `ws://${window.location.hostname}:8000/ws`;
    }

    connect() {
        if (this.app.isConnected || this.app.isConnecting) {
            return;
        }

        this.app.isConnecting = true;
        this.app.ui.updateConnectionStatus('connecting');

        try {
            this.app.ws = new WebSocket(this.url);

            this.app.ws.onopen = () => {
                this.handleOpen();
            };

            this.app.ws.onmessage = (event) => {
                this.handleMessage(event.data);
            };

            this.app.ws.onclose = () => {
                this.handleClose();
            };

            this.app.ws.onerror = (error) => {
                this.handleError(error);
            };

        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.app.isConnecting = false;
            this.app.ui.updateConnectionStatus('disconnected');
        }
    }

    disconnect() {
        if (this.app.pingInterval) {
            clearInterval(this.app.pingInterval);
            this.app.pingInterval = null;
        }

        if (this.app.ws) {
            this.app.ws.close();
            this.app.ws = null;
        }

        this.app.isConnected = false;
        this.app.isConnecting = false;
        this.app.ui.updateConnectionStatus('disconnected');
    }

    handleOpen() {
        console.log('WebSocket connected to FastAPI backend');
        this.app.isConnected = true;
        this.app.isConnecting = false;
        this.app.reconnectAttempts = 0;
        this.app.ui.updateConnectionStatus('connected');
        this.app.ui.showNotification('success', '已连接到 FastAPI 服务器');

        // 启动心跳检测
        this.startHeartbeat();

        // 请求房间列表
        this.send({ type: 'room', action: 'list', data: { publicOnly: true } });

        // 请求用户列表
        this.send({ type: 'user', action: 'list', data: { onlineOnly: true } });
    }

    handleClose() {
        console.log('WebSocket disconnected');
        this.app.isConnected = false;
        this.app.isConnecting = false;

        if (this.app.pingInterval) {
            clearInterval(this.app.pingInterval);
            this.app.pingInterval = null;
        }

        this.app.ui.updateConnectionStatus('disconnected');

        // 尝试重连
        if (this.app.reconnectAttempts < this.app.maxReconnectAttempts) {
            this.app.reconnectAttempts++;
            const delay = this.app.reconnectDelay * Math.pow(2, this.app.reconnectAttempts - 1);
            console.log(`Reconnecting in ${delay}ms...`);

            setTimeout(() => {
                this.connect();
            }, delay);
        } else {
            this.app.ui.showNotification('error', '连接失败，请手动重新连接');
        }
    }

    handleError(error) {
        console.error('WebSocket error:', error);
    }

    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            console.log('Received message:', message);
            this.app.handleMessage(message);
        } catch (error) {
            console.error('Error parsing message:', error);
        }
    }

    send(message) {
        if (this.app.ws && this.app.ws.readyState === WebSocket.OPEN) {
            this.app.ws.send(JSON.stringify(message));
            return true;
        } else {
            console.warn('WebSocket is not connected');
            return false;
        }
    }

    startHeartbeat() {
        // 每30秒发送一次ping
        this.app.pingInterval = setInterval(() => {
            this.send({ type: 'system', action: 'ping', data: {} });
        }, 30000);
    }
}

// 在原有的 app.js 中，替换 WebSocketManager 为 WebSocketManagerFastAPI
// 或者通过配置选择使用哪个版本
