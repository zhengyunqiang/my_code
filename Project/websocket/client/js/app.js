// 应用状态管理
class AppState {
    constructor() {
        this.ws = null;
        this.clientId = null;
        this.sessionId = null;
        this.currentUser = null;
        this.currentRoom = null;
        this.isConnected = false;
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.pingInterval = null;
        this.rooms = [];
        this.users = [];
        this.messageHistory = [];
        this.typingUsers = new Set();
        this.typingTimer = null;
    }
}

// UI 管理器
class UIManager {
    constructor(app) {
        this.app = app;
        this.elements = this.initializeElements();
        this.attachEventListeners();
    }

    initializeElements() {
        return {
            // 连接相关
            connectionStatus: document.getElementById('connectionStatus'),
            statusDot: document.querySelector('.status-dot'),
            statusText: document.querySelector('.status-text'),
            connectBtn: document.getElementById('connectBtn'),

            // 用户相关
            userPanel: document.getElementById('userPanel'),
            userName: document.getElementById('userName'),
            userStatus: document.getElementById('userStatus'),
            userAvatar: document.getElementById('userAvatar'),
            userCount: document.getElementById('userCount'),
            userList: document.getElementById('userList'),

            // 登录注册
            loginContainer: document.getElementById('loginContainer'),
            loginForm: document.getElementById('loginForm'),
            registerContainer: document.getElementById('registerContainer'),
            registerForm: document.getElementById('registerForm'),
            showRegisterBtn: document.getElementById('showRegisterBtn'),
            showLoginBtn: document.getElementById('showLoginBtn'),

            // 聊天相关
            chatContainer: document.getElementById('chatContainer'),
            currentRoomName: document.getElementById('currentRoomName'),
            roomInfo: document.getElementById('roomInfo'),
            messages: document.getElementById('messages'),
            messageInput: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            typingIndicator: document.getElementById('typingIndicator'),

            // 房间相关
            roomList: document.getElementById('roomList'),
            createRoomBtn: document.getElementById('createRoomBtn'),
            createRoomModal: document.getElementById('createRoomModal'),
            createRoomForm: document.getElementById('createRoomForm'),
            closeCreateRoomModal: document.getElementById('closeCreateRoomModal'),
            leaveRoomBtn: document.getElementById('leaveRoomBtn'),
            roomSettingsBtn: document.getElementById('roomSettingsBtn'),

            // 信息面板
            infoPanel: document.getElementById('infoPanel'),
            infoContent: document.getElementById('infoContent'),
            closeInfoPanel: document.getElementById('closeInfoPanel'),

            // 通知
            notifications: document.getElementById('notifications')
        };
    }

    attachEventListeners() {
        // 连接按钮
        this.elements.connectBtn.addEventListener('click', () => {
            if (this.app.isConnected) {
                this.app.disconnect();
            } else {
                this.app.connect();
            }
        });

        // 登录表单
        this.elements.loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            this.app.login(username, password);
        });

        // 注册表单
        this.elements.registerForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const username = document.getElementById('regUsername').value;
            const password = document.getElementById('regPassword').value;
            const displayName = document.getElementById('regDisplayName').value;
            this.app.register(username, password, { displayName });
        });

        // 显示/隐藏注册表单
        this.elements.showRegisterBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.elements.loginContainer.style.display = 'none';
            this.elements.registerContainer.style.display = 'flex';
        });

        this.elements.showLoginBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.elements.registerContainer.style.display = 'none';
            this.elements.loginContainer.style.display = 'flex';
        });

        // 消息输入
        this.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.app.sendMessage();
            }
        });

        this.elements.messageInput.addEventListener('input', () => {
            this.app.sendTypingIndicator(true);
            this.clearTypingTimer();
            this.typingTimer = setTimeout(() => {
                this.app.sendTypingIndicator(false);
            }, 1000);
        });

        this.elements.sendBtn.addEventListener('click', () => {
            this.app.sendMessage();
        });

        // 房间创建
        this.elements.createRoomBtn.addEventListener('click', () => {
            this.elements.createRoomModal.classList.add('active');
        });

        this.elements.closeCreateRoomModal.addEventListener('click', () => {
            this.elements.createRoomModal.classList.remove('active');
        });

        this.elements.createRoomForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const roomName = document.getElementById('roomName').value;
            const roomId = document.getElementById('roomId').value;
            const isPrivate = document.getElementById('isPrivate').checked;
            const password = document.getElementById('roomPassword').value;
            const maxClients = document.getElementById('maxClients').value;
            this.app.createRoom({ roomName, roomId, isPrivate, password, maxClients });
            this.elements.createRoomModal.classList.remove('active');
        });

        document.getElementById('isPrivate').addEventListener('change', (e) => {
            document.getElementById('passwordGroup').style.display = e.target.checked ? 'block' : 'none';
        });

        // 离开房间
        this.elements.leaveRoomBtn.addEventListener('click', () => {
            this.app.leaveRoom();
        });

        // 房间设置
        this.elements.roomSettingsBtn.addEventListener('click', () => {
            this.showRoomInfo();
        });

        this.elements.closeInfoPanel.addEventListener('click', () => {
            this.elements.infoPanel.style.display = 'none';
        });
    }

    updateConnectionStatus(status) {
        const statusMap = {
            connected: { text: '已连接', class: 'connected' },
            connecting: { text: '连接中...', class: 'connecting' },
            disconnected: { text: '未连接', class: '' }
        };

        const statusInfo = statusMap[status] || statusMap.disconnected;
        this.elements.statusText.textContent = statusInfo.text;
        this.elements.statusDot.className = 'status-dot ' + statusInfo.class;
        this.elements.connectBtn.textContent = status === 'connected' ? '断开' : '连接';
    }

    updateUserPanel(user) {
        if (user) {
            this.elements.userPanel.style.display = 'flex';
            this.elements.userName.textContent = user.displayName || user.username;
            if (user.avatar) {
                this.elements.userAvatar.querySelector('img').src = user.avatar;
            }
        } else {
            this.elements.userPanel.style.display = 'none';
        }
    }

    updateRoomList(rooms) {
        this.elements.roomList.innerHTML = '';
        rooms.forEach(room => {
            const roomItem = document.createElement('div');
            roomItem.className = 'room-item' + (this.app.currentRoom === room.id ? ' active' : '');
            roomItem.innerHTML = `
                <div class="room-name">${room.name}</div>
                <div class="room-users">👥 ${room.clientCount}</div>
            `;
            roomItem.addEventListener('click', () => {
                this.app.joinRoom(room.id);
            });
            this.elements.roomList.appendChild(roomItem);
        });
    }

    updateUserList(users) {
        this.elements.userList.innerHTML = '';
        this.elements.userCount.textContent = users.length;

        users.forEach(user => {
            const userItem = document.createElement('div');
            userItem.className = 'user-item';
            userItem.innerHTML = `
                <div class="user-info-item">
                    <span class="online-status ${user.isOnline ? 'online' : 'offline'}"></span>
                    <span>${user.displayName || user.username}</span>
                </div>
            `;
            this.elements.userList.appendChild(userItem);
        });
    }

    addMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message' + (this.isOwnMessage(message) ? ' own' : '');

        if (message.type === 'system') {
            messageDiv.className = 'message system';
            messageDiv.innerHTML = `
                <div class="message-bubble">${message.content}</div>
            `;
        } else {
            const sender = message.sender || {};
            const avatarUrl = sender.avatar || this.getDefaultAvatar(sender.username);

            messageDiv.innerHTML = `
                <div class="message-avatar">
                    <img src="${avatarUrl}" alt="${sender.displayName}">
                </div>
                <div class="message-content">
                    <div class="message-header">
                        <span class="message-sender">${sender.displayName || sender.username}</span>
                        <span class="message-time">${this.formatTime(message.timestamp)}</span>
                    </div>
                    <div class="message-bubble">${this.escapeHtml(message.content)}</div>
                </div>
            `;
        }

        this.elements.messages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addSystemMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message system';
        messageDiv.innerHTML = `
            <div class="message-bubble">${this.escapeHtml(content)}</div>
        `;
        this.elements.messages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    updateTypingIndicator(users) {
        if (users.size === 0) {
            this.elements.typingIndicator.textContent = '';
            return;
        }

        const usernames = Array.from(users).map(u => u.displayName || u.username);
        if (usernames.length <= 2) {
            this.elements.typingIndicator.textContent = `${usernames.join(' 和 ')} 正在输入...`;
        } else {
            this.elements.typingIndicator.textContent = `${usernames.length} 人正在输入...`;
        }
    }

    showRoomInfo() {
        if (!this.app.currentRoom) return;

        const room = this.app.rooms.find(r => r.id === this.app.currentRoom);
        if (!room) return;

        this.elements.infoContent.innerHTML = `
            <div class="info-section">
                <h4>房间信息</h4>
                <div class="info-item">
                    <span class="info-label">房间名称</span>
                    <span class="info-value">${room.name}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">房间ID</span>
                    <span class="info-value">${room.id}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">在线人数</span>
                    <span class="info-value">${room.clientCount}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">创建时间</span>
                    <span class="info-value">${this.formatTime(room.createdAt)}</span>
                </div>
            </div>
        `;

        this.elements.infoPanel.style.display = 'flex';
    }

    showNotification(type, message, duration = 3000) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-icon">${this.getNotificationIcon(type)}</span>
                <span class="notification-message">${message}</span>
                <button class="notification-close">×</button>
            </div>
        `;

        notification.querySelector('.notification-close').addEventListener('click', () => {
            notification.remove();
        });

        this.elements.notifications.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, duration);
    }

    getNotificationIcon(type) {
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        return icons[type] || icons.info;
    }

    isOwnMessage(message) {
        return this.app.currentUser &&
               message.sender &&
               message.sender.username === this.app.currentUser.username;
    }

    getDefaultAvatar(username) {
        return `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23666'%3E%3Cpath d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/%3E%3C/svg%3E`;
    }

    formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;

        if (diff < 60000) { // 1分钟内
            return '刚刚';
        } else if (diff < 3600000) { // 1小时内
            return `${Math.floor(diff / 60000)}分钟前`;
        } else if (date.toDateString() === now.toDateString()) { // 今天
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        } else {
            return date.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollToBottom() {
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    clearTypingTimer() {
        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
            this.typingTimer = null;
        }
    }

    clearMessages() {
        this.elements.messages.innerHTML = '';
    }

    focusInput() {
        this.elements.messageInput.focus();
    }

    getInputValue() {
        return this.elements.messageInput.value.trim();
    }

    clearInput() {
        this.elements.messageInput.value = '';
        this.elements.messageInput.style.height = 'auto';
    }
}

// WebSocket 管理器
class WebSocketManager {
    constructor(app) {
        this.app = app;
        this.url = `ws://${window.location.hostname}:3000`;
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
        console.log('WebSocket connected');
        this.app.isConnected = true;
        this.app.isConnecting = false;
        this.app.reconnectAttempts = 0;
        this.app.ui.updateConnectionStatus('connected');
        this.app.ui.showNotification('success', '已连接到服务器');

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

// 主应用类
class WebSocketApp {
    constructor() {
        this.state = new AppState();
        this.ui = new UIManager(this);
        this.wsManager = new WebSocketManager(this);
    }

    connect() {
        this.wsManager.connect();
    }

    disconnect() {
        this.wsManager.disconnect();
    }

    login(username, password) {
        this.wsManager.send({
            type: 'auth',
            action: 'login',
            data: { username, password }
        });
    }

    register(username, password, userInfo) {
        this.wsManager.send({
            type: 'auth',
            action: 'register',
            data: { username, password, userInfo }
        });
    }

    logout() {
        if (this.state.sessionId) {
            this.wsManager.send({
                type: 'auth',
                action: 'logout',
                data: { sessionId: this.state.sessionId }
            });
        }
    }

    sendMessage() {
        const content = this.ui.getInputValue();
        if (!content.trim()) return;

        if (!this.state.currentRoom) {
            this.ui.showNotification('warning', '请先加入一个房间');
            return;
        }

        if (this.wsManager.send({
            type: 'chat',
            action: 'message',
            data: { content, room: this.state.currentRoom }
        })) {
            this.ui.clearInput();
        }
    }

    sendTypingIndicator(isTyping) {
        if (!this.state.currentRoom) return;

        this.wsManager.send({
            type: 'chat',
            action: 'typing',
            data: { room: this.state.currentRoom, isTyping }
        });
    }

    joinRoom(roomId) {
        if (this.state.currentRoom === roomId) return;

        this.wsManager.send({
            type: 'room',
            action: 'join',
            data: { roomId }
        });
    }

    leaveRoom() {
        if (!this.state.currentRoom) return;

        this.wsManager.send({
            type: 'room',
            action: 'leave',
            data: { roomId: this.state.currentRoom }
        });
    }

    createRoom(options) {
        this.wsManager.send({
            type: 'room',
            action: 'create',
            data: options
        });
    }

    handleMessage(message) {
        const { type, action, data } = message;

        switch (type) {
            case 'system':
                this.handleSystemMessage(action, data);
                break;
            case 'auth':
                this.handleAuthMessage(action, data);
                break;
            case 'chat':
                this.handleChatMessage(action, data);
                break;
            case 'room':
                this.handleRoomMessage(action, data);
                break;
            case 'user':
                this.handleUserMessage(action, data);
                break;
            case 'presence':
                this.handlePresenceMessage(action, data);
                break;
            case 'error':
                this.handleErrorMessage(action, data);
                break;
            default:
                console.log('Unknown message type:', type);
        }
    }

    handleSystemMessage(action, data) {
        switch (action) {
            case 'connected':
                this.state.clientId = data.clientId;
                this.ui.addSystemMessage(data.message);
                break;
            case 'pong':
                // 心跳响应
                break;
            case 'stats':
                console.log('Server stats:', data);
                break;
        }
    }

    handleAuthMessage(action, data) {
        switch (action) {
            case 'login_success':
                this.state.currentUser = data.user;
                this.state.sessionId = data.sessionId;
                this.ui.updateUserPanel(data.user);
                this.ui.showNotification('success', '登录成功');

                // 隐藏登录表单，显示聊天界面
                this.ui.elements.loginContainer.style.display = 'none';
                this.ui.elements.chatContainer.style.display = 'flex';
                this.ui.focusInput();
                break;
            case 'login_failed':
                this.ui.showNotification('error', data.message);
                break;
            case 'register_success':
                this.ui.showNotification('success', '注册成功，请登录');
                this.ui.elements.registerContainer.style.display = 'none';
                this.ui.elements.loginContainer.style.display = 'flex';
                break;
            case 'register_failed':
                this.ui.showNotification('error', data.message);
                break;
            case 'logout_success':
                this.state.currentUser = null;
                this.state.sessionId = null;
                this.ui.updateUserPanel(null);
                this.ui.showNotification('success', '已退出登录');
                break;
        }
    }

    handleChatMessage(action, data) {
        switch (action) {
            case 'message':
                this.ui.addMessage(data);
                break;
            case 'private_message':
                this.ui.showNotification('info', `${data.from.displayName} 给您发送了私信`);
                break;
            case 'typing':
                if (data.isTyping) {
                    this.state.typingUsers.add(data.user);
                } else {
                    this.state.typingUsers.delete(data.user);
                }
                this.ui.updateTypingIndicator(this.state.typingUsers);
                break;
            case 'history':
                data.messages.forEach(msg => {
                    this.ui.addMessage(msg);
                });
                break;
        }
    }

    handleRoomMessage(action, data) {
        switch (action) {
            case 'joined':
                this.state.currentRoom = data.room.id;
                this.ui.elements.currentRoomName.textContent = data.room.name;
                this.ui.elements.roomInfo.textContent = `${data.room.clientCount} 人在线`;
                this.ui.clearMessages();
                data.history.forEach(msg => {
                    this.ui.addMessage(msg);
                });
                this.ui.showNotification('success', `已加入房间: ${data.room.name}`);
                break;
            case 'left':
                this.state.currentRoom = null;
                this.ui.elements.currentRoomName.textContent = '公共大厅';
                this.ui.elements.roomInfo.textContent = '';
                this.ui.clearMessages();
                break;
            case 'created':
                this.ui.showNotification('success', `房间已创建: ${data.room.name}`);
                this.joinRoom(data.room.id);
                break;
            case 'list':
                this.state.rooms = data.rooms;
                this.ui.updateRoomList(data.rooms);
                break;
            case 'info':
                console.log('Room info:', data.room);
                break;
        }
    }

    handleUserMessage(action, data) {
        switch (action) {
            case 'list':
                this.state.users = data.users;
                this.ui.updateUserList(data.users);
                break;
            case 'info':
                console.log('User info:', data.user);
                break;
        }
    }

    handlePresenceMessage(action, data) {
        switch (action) {
            case 'user_joined':
                this.ui.addSystemMessage(`${data.user.displayName} 加入了房间`);
                break;
            case 'user_left':
                this.ui.addSystemMessage(`${data.user.displayName} 离开了房间`);
                break;
            case 'user_online':
                this.ui.showNotification('info', `${data.user.displayName} 上线了`);
                break;
            case 'user_offline':
                this.ui.showNotification('info', `${data.user.displayName} 下线了`);
                break;
            case 'status_changed':
                console.log('User status changed:', data.user, data.status);
                break;
        }
    }

    handleErrorMessage(action, data) {
        console.error('Server error:', action, data);
        this.ui.showNotification('error', data.message);
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new WebSocketApp();

    // 自动连接
    setTimeout(() => {
        window.app.connect();
    }, 500);
});
